"""Collect separate evidence budgets for every selected paper and category."""
from dataclasses import dataclass
import time
from typing import get_args

from langsmith import tracing_context

from src.config import ComparisonSettings, RetrievalSettings
from src.retrieval.adapters import RetrievedContext, as_runnable
from src.retrieval.hybrid import HybridRetriever
from src.schemas import ComparisonCategory, PaperRecord, RetrievalError


CATEGORY_QUERIES = {
    "methodology": "methodology architecture approach algorithm model training",
    "datasets": "datasets corpus benchmark samples evaluation data split",
    "results": "experimental results accuracy F1 performance metrics baseline",
    "conclusions": "conclusions findings contributions study conclusions",
    "limitations": "limitations drawbacks failure cases future work",
}
DEFAULT_FOCUS = "Compare the selected research papers."


@dataclass(frozen=True)
class PaperEvidence:
    paper: PaperRecord
    paper_version: str
    contexts: dict[str, RetrievedContext]


@dataclass(frozen=True)
class ComparisonEvidence:
    question: str
    categories: list[str]
    papers: list[PaperEvidence]
    corpus_version: str
    retrieval_ms: int
    settings: ComparisonSettings


class BalancedRetriever:
    def __init__(self, library, settings=None):
        self.library = library
        self.settings = settings or ComparisonSettings()

    def collect(self, question: str, paper_ids: list[str], categories=None, *, progress=None):
        start = time.perf_counter()
        if not isinstance(question, str):
            raise RetrievalError("Enter a text comparison focus.")
        question = " ".join(question.split()) or DEFAULT_FOCUS
        if len(question) > self.settings.max_focus_chars:
            raise RetrievalError(f"Keep the comparison focus within {self.settings.max_focus_chars} characters.")
        selected = sorted(set(paper_ids))
        if not 2 <= len(selected) <= 12:
            raise RetrievalError("Select between two and twelve indexed papers to compare.")
        requested = list(get_args(ComparisonCategory)) if categories is None else list(categories)
        if not requested or len(requested) != len(set(requested)) or not set(requested) <= set(CATEGORY_QUERIES):
            raise RetrievalError("Select one or more distinct supported comparison categories.")
        requested = [category for category in CATEGORY_QUERIES if category in requested]
        retrieve = as_runnable(HybridRetriever(self.library, RetrievalSettings(
            candidates_per_method=self.settings.candidates_per_method,
            context_chunks=self.settings.passages_per_category,
            max_context_chars=max(1, self.settings.max_paper_context_chars // len(requested)),
            rrf_constant=self.settings.rrf_constant,
        )))
        papers = []
        with self.library.lock:
            ready = {paper.paper_id: paper for paper in self.library.catalog.papers()}
            if not set(selected) <= set(ready):
                raise RetrievalError("A selected paper is unavailable. Select the current papers again.")
            version = self.library.catalog.corpus_version()
            for paper_id in selected:
                contexts = {}
                for category in requested:
                    if progress: progress("retrieving", paper_id, category)
                    with tracing_context(enabled=False, parent=False, replicas=[]):
                        contexts[category] = retrieve.invoke({
                            "question": f"{question} {CATEGORY_QUERIES[category]}", "paper_ids": [paper_id],
                        })
                papers.append(PaperEvidence(ready[paper_id], self.library.catalog.paper_version(paper_id), contexts))
        return ComparisonEvidence(
            question, requested, papers, version, round((time.perf_counter() - start) * 1000), self.settings,
        )
