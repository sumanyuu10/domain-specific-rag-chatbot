"""Paper-balanced evidence cards, validated caching and cited synthesis."""
from dataclasses import asdict
import hashlib
import json
import sqlite3
import time

from langsmith import tracing_context

from src.config import MODEL, ComparisonSettings
from src.generation.citations import CitationValidationError
from src.generation.comparison_validation import (
    canonical_citations, comparison_sources, materialize_cells, paper_sources,
    results_assessments, validate_card, validate_evidence, validate_synthesis,
)
from src.generation.isolation import EvidenceGateway
from src.generation.llm import CodexIntegrationError
from src.generation.prompts import (
    CARD_PROMPT, CARD_PROMPT_VERSION, SYNTHESIS_PROMPT, SYNTHESIS_PROMPT_VERSION,
)
from src.retrieval.comparison import BalancedRetriever
from src.schemas import (
    CardDraft, CellSelection, ComparisonDraft, ComparisonResult, EvidenceCard,
    EvidenceSection, PaperFailure, RetrievalError,
)


FATAL_CODES = {"authentication_required", "model_not_listed", "model_mismatch", "isolation_unverified", "unexpected_activity", "quota_exceeded", "rate_limited", "context_limit", "request_rejected"}
TRANSIENT_CODES = {"timeout", "sdk_failure", "incomplete_turn", "empty_answer", "network_error"}


class ComparisonService:
    def __init__(self, library, *, gateway=None, settings=None):
        self.library = library
        self.gateway = gateway if gateway is not None else EvidenceGateway()
        self.settings = settings or ComparisonSettings()
        self.retriever = BalancedRetriever(library, self.settings)

    def collect(self, question, paper_ids, categories=None, *, progress=None, mode="hybrid"):
        return self.retriever.collect(question, paper_ids, categories, progress=progress, mode=mode)

    def _check(self, evidence):
        if evidence.settings != self.settings:
            raise RetrievalError("Comparison settings changed. Collect evidence again.")
        validate_evidence(self.library, evidence)

    def cache_key(self, paper, evidence):
        payload = {
            "paper_id": paper.paper.paper_id, "paper_version": paper.paper_version,
            "question": evidence.question, "categories": evidence.categories,
            "model": MODEL, "prompt_version": CARD_PROMPT_VERSION,
            "settings": asdict(self.settings),
            "sources": {category: [chunk.chunk_id for chunk in context.snapshot.documents]
                        for category, context in paper.contexts.items()},
        }
        # Preserve Phase 4/5 hybrid cache identities; baseline modes are isolated.
        if evidence.retrieval_mode != "hybrid":
            payload["retrieval_mode"] = evidence.retrieval_mode
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _request(self, template, schema, payload, parser, evidence):
        request_json = json.dumps(payload, ensure_ascii=False)
        if len(request_json) > self.settings.max_synthesis_chars:
            raise RetrievalError("Comparison context exceeds its limit. Select fewer categories or papers and collect again.")
        chain = template | self.gateway.as_runnable(output_schema=schema)
        instruction = "Produce the first response."
        for attempt in range(2):
            with self.library.lock:
                self._check(evidence)
            try:
                with tracing_context(enabled=False, parent=False, replicas=[]):
                    generated = chain.invoke({"request_json": request_json, "repair_instruction": instruction})
            except CodexIntegrationError as error:
                if error.code in TRANSIENT_CODES and attempt == 0:
                    instruction = "The previous request did not complete. Answer this same request."
                    continue
                raise
            with self.library.lock:
                self._check(evidence)
                if generated.model != MODEL:
                    raise CodexIntegrationError("model_mismatch", "The comparison did not use the authorized model.")
                try:
                    return parser(generated.text)
                except (ValueError, TypeError):
                    if attempt:
                        raise CitationValidationError("The response failed schema/source/comparability checks after one repair.")
                    instruction = (
                        "The previous output failed validation. Correct category coverage, source IDs, table entry indices "
                        "and experimental comparability. Use missing/not_directly_comparable when unsupported. "
                        "Do not add new facts. Return the required JSON."
                    )

    def _card(self, paper, evidence):
        key = self.cache_key(paper, evidence)
        with self.library.lock:
            self._check(evidence)
            cached = self.library.catalog.comparison_card(key)
            if cached:
                try:
                    card = EvidenceCard.model_validate_json(cached)
                    validate_card(card, paper, evidence, model=MODEL, prompt_version=CARD_PROMPT_VERSION)
                    return card, True
                except (ValueError, TypeError):
                    self.library.catalog.discard_comparison_card(key)
        owned = {
            "paper_id": paper.paper.paper_id, "paper_version": paper.paper_version,
            "question": evidence.question, "model": MODEL, "prompt_version": CARD_PROMPT_VERSION,
        }
        sources = paper_sources(paper)
        if not sources:
            card = EvidenceCard(**owned, sections=[EvidenceSection(
                category=category, status="missing", entries=[],
                missing_information="No usable passages were retrieved for this category.",
            ) for category in evidence.categories])
        else:
            schema = CardDraft.model_json_schema()
            schema["$defs"]["CardEntry"]["properties"]["source_ids"]["items"]["enum"] = sorted(sources)
            schema["$defs"]["EvidenceSection"]["properties"]["category"]["enum"] = evidence.categories
            payload = {
                "focus": evidence.question,
                "paper": {"paper_id": paper.paper.paper_id, "filename": paper.paper.filename, "title": paper.paper.display_title},
                "categories": [{"category": category, "source_ids": [chunk.chunk_id for chunk in context.snapshot.documents]}
                               for category, context in paper.contexts.items()],
                "passages": [{"source_id": source, "pdf_page": chunk.page_number, "passage": chunk.text}
                             for source, chunk in sources.items()],
            }
            def parse(text):
                draft = CardDraft.model_validate_json(text)
                parsed = EvidenceCard(**owned, sections=draft.sections)
                validate_card(parsed, paper, evidence, model=MODEL, prompt_version=CARD_PROMPT_VERSION)
                return parsed
            card = self._request(CARD_PROMPT, schema, payload, parse, evidence)
        with self.library.lock:
            self._check(evidence)
            validate_card(card, paper, evidence, model=MODEL, prompt_version=CARD_PROMPT_VERSION)
            self.library.catalog.save_comparison_card(
                key, card.paper_id, card.paper_version, card.model_dump_json(), limit=self.settings.cached_cards_per_paper,
            )
        return card, False

    def compare(self, evidence, *, allow_remote=False, progress=None):
        if not allow_remote:
            raise RetrievalError("Allow sending comparison passages and the focus to Codex before generating a comparison.")
        start = time.perf_counter()
        cards, failures, cached = [], [], []
        notify = progress or (lambda _stage, _paper_id, _category: None)
        with self.library.lock:
            self._check(evidence)
        try:
            for number, paper in enumerate(evidence.papers):
                paper_id = paper.paper.paper_id
                notify("preparing_card", paper_id, None)
                try:
                    card, reused = self._card(paper, evidence)
                except CodexIntegrationError as error:
                    failures.append(PaperFailure(paper_id=paper_id, code=error.code, message=str(error)))
                    notify("card_failed", paper_id, None)
                    if error.code in FATAL_CODES:
                        failures.extend(PaperFailure(
                            paper_id=item.paper.paper_id, code="not_attempted",
                            message="Generation stopped after an account, request, model or isolation failure.",
                        ) for item in evidence.papers[number + 1:])
                        break
                    continue
                except CitationValidationError:
                    failures.append(PaperFailure(
                        paper_id=paper_id, code="invalid_card", message="The evidence card failed validation after one repair and was withheld.",
                    ))
                    notify("card_failed", paper_id, None)
                    continue
                cards.append(card)
                if reused: cached.append(paper_id)
                notify("cached_card" if reused else "card_ready", paper_id, None)
            cells, relationships = [], []
            status = "incomplete" if failures else "completed"
            if not failures:
                if not any(section.entries for card in cards for section in card.sections):
                    status = "insufficient_evidence"
                    cells = materialize_cells([
                        CellSelection(paper_id=card.paper_id, category=category, entry_indices=[])
                        for card in cards for category in evidence.categories
                    ], cards, evidence.categories)
                else:
                    notify("synthesizing", None, None)
                    sources = comparison_sources(evidence)
                    cited = {source for card in cards for section in card.sections for entry in section.entries for source in entry.source_ids}
                    schema = ComparisonDraft.model_json_schema()
                    schema["properties"]["cells"].update(minItems=len(cards) * len(evidence.categories), maxItems=len(cards) * len(evidence.categories))
                    for name in ("CellSelection", "ComparisonRelation"):
                        schema["$defs"][name]["properties"]["category"]["enum"] = evidence.categories
                    schema["$defs"]["CellSelection"]["properties"]["paper_id"]["enum"] = [card.paper_id for card in cards]
                    schema["$defs"]["ComparisonRelation"]["properties"]["paper_ids"]["items"]["enum"] = [card.paper_id for card in cards]
                    schema["$defs"]["ComparisonRelation"]["properties"]["source_ids"]["items"]["enum"] = sorted(cited)
                    payload = {
                        "focus": evidence.question, "categories": evidence.categories,
                        "prompt_version": SYNTHESIS_PROMPT_VERSION,
                        "cards": [card.model_dump() for card in cards],
                        "passages": [{"source_id": source, "paper_id": sources[source].paper_id,
                                      "filename": sources[source].filename, "pdf_page": sources[source].page_number,
                                      "passage": sources[source].text} for source in sorted(cited)],
                        "result_comparability": [item.model_dump() for item in results_assessments(cards, evidence.categories)],
                    }
                    try:
                        cells, relationships = self._request(
                            SYNTHESIS_PROMPT, schema, payload,
                            lambda text: validate_synthesis(text, cards, evidence), evidence,
                        )
                    except (CitationValidationError, CodexIntegrationError) as error:
                        status = "validation_failed" if isinstance(error, CitationValidationError) else "incomplete"
                        failures.append(PaperFailure(
                            paper_id=None, code="invalid_synthesis" if isinstance(error, CitationValidationError) else error.code,
                            message="Comparison synthesis was withheld after validation failed." if isinstance(error, CitationValidationError) else str(error),
                        ))
            with self.library.lock:
                self._check(evidence)
                for card in cards:
                    paper = next(item for item in evidence.papers if item.paper.paper_id == card.paper_id)
                    validate_card(card, paper, evidence, model=MODEL, prompt_version=CARD_PROMPT_VERSION)
                citations = canonical_citations(cards, evidence)
            return ComparisonResult(
                question=evidence.question, categories=evidence.categories,
                selected_paper_ids=[paper.paper.paper_id for paper in evidence.papers],
                corpus_version=evidence.corpus_version, status=status, cards=cards,
                cells=cells, relationships=relationships,
                result_comparability=results_assessments(cards, evidence.categories) if not failures else [],
                citations=citations, failures=failures, cached_paper_ids=cached, model=MODEL,
                retrieval_ms=evidence.retrieval_ms, total_ms=round((time.perf_counter() - start) * 1000),
            )
        except (sqlite3.Error, OSError) as error:
            raise RetrievalError("The local comparison cache could not be read or saved. Check disk space/permissions; paper data was preserved.") from error
