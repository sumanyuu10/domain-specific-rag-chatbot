"""Local retrieval → LangChain prompt → isolated Codex → canonical citations."""
import re
import time

from langchain_core.runnables import RunnableLambda
from langsmith import tracing_context

from src.config import RetrievalSettings
from src.generation.citations import CitationValidationError, source_map, validate_answer, validate_context
from src.generation.isolation import EvidenceGateway
from src.generation.prompts import ANSWER_PROMPT, prompt_values
from src.retrieval.adapters import as_runnable
from src.retrieval.hybrid import HybridRetriever
from src.schemas import AnswerDraft, AnswerResult, RetrievalError


def resolve_question(question: str, recent_user_questions: list[str] | None = None):
    question = " ".join(question.split())
    if re.search(r"\b(it|its|they|their|those|this method|that method)\b", question, re.IGNORECASE):
        if not recent_user_questions:
            raise RetrievalError("Please name the paper or method you mean so the question can be answered from the right evidence.")
        previous = " ".join(recent_user_questions[-1].split())[:1000]
        return f"Previous user question: {previous}\nCurrent question: {question}"
    return question


class ResearchAssistant:
    def __init__(self, library, *, gateway=None, settings=None):
        self.library = library
        self.settings = settings or RetrievalSettings()
        self.gateway = gateway if gateway is not None else EvidenceGateway()
        self.retrieval = as_runnable(HybridRetriever(library, self.settings))

    def search(self, question, paper_ids, *, recent_user_questions=None, mode="hybrid"):
        if not isinstance(question, str) or not question.strip() or len(question) > self.settings.max_question_chars:
            raise RetrievalError(f"Enter a question of 1–{self.settings.max_question_chars} characters.")
        resolved = resolve_question(question, recent_user_questions)
        with tracing_context(enabled=False, parent=False, replicas=[]):
            return self.retrieval.invoke({"question": resolved, "paper_ids": paper_ids, "mode": mode})

    def _prompt(self, context, repair):
        with self.library.lock:
            validate_context(self.library, context)
        sources = [{
            "source_id": source_id, "paper": chunk.filename,
            "pdf_page": chunk.page_number, "passage": document.page_content,
        } for (source_id, chunk), document in zip(source_map(context).items(), context.documents)]
        return prompt_values(context.snapshot.question, sources, repair=repair)

    def answer(self, context, *, allow_remote=False) -> AnswerResult:
        if not allow_remote:
            raise RetrievalError("Allow sending the question and retrieved passages to Codex before generating an answer.")
        start = time.perf_counter()
        snapshot = context.snapshot
        with self.library.lock:
            validate_context(self.library, context)
        common = {
            "question": snapshot.question, "selected_paper_ids": snapshot.selected_paper_ids,
            "corpus_version": snapshot.corpus_version, "retrieval_ms": snapshot.latency_ms,
        }
        if not context.documents:
            return AnswerResult(
                **common, status="insufficient_evidence", claims=[], citations=[],
                missing_information=["No usable passages were retrieved from the selected papers."],
            )
        chain = (
            RunnableLambda(lambda repair: self._prompt(context, repair), name="canonical_evidence_context")
            | ANSWER_PROMPT
            | self.gateway.as_runnable(output_schema=AnswerDraft.model_json_schema())
        )
        for repair in (False, True):
            # Parent environment tracing must never export questions/passages.
            with tracing_context(enabled=False, parent=False, replicas=[]):
                generated = chain.invoke(repair)
            with self.library.lock:
                # A corpus change is never repaired by making another model call.
                validate_context(self.library, context)
                try:
                    draft, citations = validate_answer(generated.text, self.library, context)
                except CitationValidationError:
                    continue
            return AnswerResult(
                **common, status=draft.status, claims=draft.claims,
                missing_information=draft.missing_information, citations=citations,
                model=generated.model, repaired=repair,
                total_ms=round((time.perf_counter() - start) * 1000),
            )
        return AnswerResult(
            **common, status="validation_failed", claims=[], citations=[],
            missing_information=["The model's answer failed schema or citation checks after one repair and was withheld."],
            model=generated.model, repaired=True, total_ms=round((time.perf_counter() - start) * 1000),
        )
