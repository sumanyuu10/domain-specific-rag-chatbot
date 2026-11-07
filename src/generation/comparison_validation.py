"""Canonical comparison provenance and conservative experimental-context checks."""
from itertools import combinations

from src.generation.citations import CitationValidationError, validate_context
from src.retrieval.comparison import CATEGORY_QUERIES
from src.schemas import (
    ComparisonCell, ComparisonDraft, EvidenceCard, ResultComparability,
    RetrievalError, SourceCitation,
)


def paper_sources(paper):
    return {chunk.chunk_id: chunk for context in paper.contexts.values() for chunk in context.snapshot.documents}


def comparison_sources(evidence):
    return {key: chunk for paper in evidence.papers for key, chunk in paper_sources(paper).items()}


def validate_evidence(library, evidence):
    library.ensure_available(RetrievalError)
    if library.catalog.corpus_version() != evidence.corpus_version:
        raise RetrievalError("The paper library changed. Collect comparison evidence again.")
    ids = [paper.paper.paper_id for paper in evidence.papers]
    if len(set(ids)) != len(ids) or not 2 <= len(ids) <= 12:
        raise RetrievalError("The comparison needs two to twelve distinct active papers.")
    if not evidence.categories or len(set(evidence.categories)) != len(evidence.categories) or not set(evidence.categories) <= set(CATEGORY_QUERIES):
        raise RetrievalError("The comparison categories are invalid. Collect evidence again.")
    for paper in evidence.papers:
        if (library.catalog.paper(paper.paper.paper_id) != paper.paper
                or library.catalog.paper_version(paper.paper.paper_id) != paper.paper_version
                or set(paper.contexts) != set(evidence.categories)):
            raise RetrievalError("A comparison paper or its version changed. Collect evidence again.")
        for category, context in paper.contexts.items():
            if (context.snapshot.selected_paper_ids != [paper.paper.paper_id]
                    or context.snapshot.corpus_version != evidence.corpus_version
                    or context.snapshot.question != " ".join(f"{evidence.question} {CATEGORY_QUERIES[category]}".split())
                    or len(context.documents) > evidence.settings.passages_per_category
                    or sum(len(doc.page_content) for doc in context.documents)
                    > max(1, evidence.settings.max_paper_context_chars // len(evidence.categories))):
                raise RetrievalError("Comparison evidence scope or budget changed. Collect it again.")
            validate_context(library, context)


def validate_card(card: EvidenceCard, paper, evidence, *, model, prompt_version):
    if (card.paper_id != paper.paper.paper_id or card.paper_version != paper.paper_version
            or card.question != evidence.question or card.model != model or card.prompt_version != prompt_version):
        raise CitationValidationError("Evidence card identity/version mismatch")
    categories = [section.category for section in card.sections]
    if len(categories) != len(set(categories)) or set(categories) != set(evidence.categories):
        raise CitationValidationError("Every requested category must occur exactly once")
    for section in card.sections:
        allowed = {chunk.chunk_id for chunk in paper.contexts[section.category].snapshot.documents}
        if not allowed and section.status != "missing":
            raise CitationValidationError("A category without retrieved passages must be marked missing")
        for entry in section.entries:
            if not set(entry.source_ids) <= allowed:
                raise CitationValidationError("Card citations must belong to this paper/category evidence")
            entry.source_ids = list(dict.fromkeys(entry.source_ids))
    by_category = {section.category: section for section in card.sections}
    card.sections = [by_category[category] for category in evidence.categories]


def _basis(entry):
    if entry.experiment is None:
        return None
    fields = [getattr(entry.experiment, name) for name in ("task", "dataset", "split", "metric", "settings")]
    unknown = {"", "unknown", "not reported", "not provided", "not established", "not specified",
               "not available", "not mentioned", "not stated", "unspecified", "n/a", "none"}
    normalized = tuple(" ".join((field or "").casefold().split()) for field in fields)
    return None if any(value in unknown for value in normalized) else normalized


def _section(card, category):
    return next(section for section in card.sections if section.category == category)


def results_assessments(cards, categories):
    if "results" not in categories:
        return []
    assessments = []
    for left, right in combinations(cards, 2):
        left_bases = {_basis(entry) for entry in _section(left, "results").entries} - {None}
        right_bases = {_basis(entry) for entry in _section(right, "results").entries} - {None}
        matching = bool(left_bases & right_bases)
        assessments.append(ResultComparability(
            paper_ids=[left.paper_id, right.paper_id],
            status="matching_reported_conditions" if matching else "not_directly_comparable",
            reason=("At least one reported task, dataset, split, metric and settings combination matches. "
                    "This does not establish scientific equivalence." if matching else
                    "Matching task, dataset, split, metric and settings were not established from the retrieved evidence."),
        ))
    return assessments


def materialize_cells(selections, cards, categories):
    by_id = {card.paper_id: card for card in cards}
    expected = {(paper_id, category) for paper_id in by_id for category in categories}
    keys = [(cell.paper_id, cell.category) for cell in selections]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise CitationValidationError("The table must represent every selected paper/category exactly once")
    cells = []
    for selection in selections:
        section = _section(by_id[selection.paper_id], selection.category)
        indices = selection.entry_indices
        if (len(indices) != len(set(indices)) or any(index < 0 or index >= len(section.entries) for index in indices)
                or bool(indices) != (section.status == "supported")):
            raise CitationValidationError("Table selection references invalid or missing card entries")
        entries = [section.entries[index] for index in indices]
        cells.append(ComparisonCell(
            paper_id=selection.paper_id, category=selection.category, status=section.status,
            text="\n".join(entry.text for entry in entries) if entries else section.missing_information,
            source_ids=list(dict.fromkeys(source for entry in entries for source in entry.source_ids)),
        ))
    return cells


def validate_synthesis(text, cards, evidence):
    try:
        draft = ComparisonDraft.model_validate_json(text)
    except (ValueError, TypeError) as error:
        raise CitationValidationError("Invalid comparison output schema") from error
    cells = materialize_cells(draft.cells, cards, evidence.categories)
    by_id = {card.paper_id: card for card in cards}
    for relation in draft.relationships:
        named = set(relation.paper_ids)
        if (len(named) != len(relation.paper_ids) or not named <= set(by_id)
                or relation.category not in evidence.categories or not relation.text.strip()):
            raise CitationValidationError("Invalid relationship scope")
        used = set(relation.source_ids)
        eligible = set()
        bases = []
        for paper_id in named:
            entries = _section(by_id[paper_id], relation.category).entries
            matched = [entry for entry in entries if used & set(entry.source_ids)]
            if not matched:
                raise CitationValidationError("A relationship needs category evidence from every named paper")
            eligible.update(source for entry in entries for source in entry.source_ids)
            if relation.category == "results" and relation.kind != "not_directly_comparable":
                signatures = {_basis(entry) for entry in matched}
                if None in signatures:
                    raise CitationValidationError("Do not compare numerical findings without complete reported conditions")
                bases.append(signatures)
        if not used <= eligible:
            raise CitationValidationError("A relationship cites evidence outside its validated cards")
        if bases and not set.intersection(*bases):
            raise CitationValidationError("Experimental settings do not match; mark results not directly comparable")
        relation.source_ids = list(dict.fromkeys(relation.source_ids))
    return cells, draft.relationships


def canonical_citations(cards, evidence):
    sources = comparison_sources(evidence)
    used = list(dict.fromkeys(source for card in cards for section in card.sections for entry in section.entries for source in entry.source_ids))
    return [SourceCitation(
        source_id=source, chunk_id=source, paper_id=sources[source].paper_id,
        filename=sources[source].filename, display_title=sources[source].display_title,
        page_number=sources[source].page_number, passage=sources[source].text,
    ) for source in used]
