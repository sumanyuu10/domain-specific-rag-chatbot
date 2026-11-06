"""Selected-paper retrieval, reciprocal rank fusion and bounded context."""
import time

from src.config import RetrievalSettings
from src.retrieval.vector import search as vector_search
from src.schemas import RetrievalError, RetrievalResult


def reciprocal_rank_fusion(*rankings, constant=60):
    """One-based ranks, absent contribution zero, repeated IDs counted once/list."""
    if constant <= 0:
        raise ValueError("RRF constant must be positive.")
    scores = {}
    for ranking in rankings:
        unique = list(dict.fromkeys(ranking))
        for rank, chunk_id in enumerate(unique, 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (constant + rank)
    return sorted(scores, key=lambda item: (-scores[item], item))


def select_context(ranked_chunks, settings):
    chosen, characters = [], 0
    for chunk in ranked_chunks:
        normalized = " " + " ".join(chunk.text.split()) + " "
        # Keep similar passages with different numbers, methods or negation.
        # Only remove exact/subsumed same-page text, not bag-of-words similarity.
        repeated = any(
            previous.paper_id == chunk.paper_id and previous.page_number == chunk.page_number
            and normalized in previous_text
            for previous, previous_text in chosen
        )
        if repeated or characters + len(chunk.text) > settings.max_context_chars:
            continue
        chosen.append((chunk, normalized))
        characters += len(chunk.text)
        if len(chosen) >= settings.context_chunks:
            break
    return [chunk for chunk, _text in chosen]


class HybridRetriever:
    def __init__(self, library, settings=None):
        self.library = library
        self.settings = settings or RetrievalSettings()

    def retrieve(self, question: str, paper_ids: list[str], *, mode="hybrid") -> RetrievalResult:
        start = time.perf_counter()
        if not isinstance(question, str):
            raise RetrievalError("Enter a text question.")
        question = " ".join(question.split())
        if not question or len(question) > self.settings.max_question_chars:
            raise RetrievalError(f"Enter a question of 1–{self.settings.max_question_chars} characters.")
        if mode not in {"bm25", "vector", "hybrid"}:
            raise RetrievalError("Unknown retrieval mode.")
        selected = set(paper_ids)
        if not selected:
            raise RetrievalError("Select at least one indexed paper.")
        # The same lock as ingestion/deletion prevents mixed corpus snapshots.
        with self.library.lock:
            ready = {paper.paper_id for paper in self.library.catalog.papers()}
            if not selected <= ready:
                raise RetrievalError("The paper selection changed or includes an unavailable paper. Select it again.")
            version = self.library.catalog.corpus_version()
            chunks = self.library.catalog.chunks()
            canonical = {chunk.chunk_id: chunk for chunk in chunks if chunk.paper_id in selected}
            sparse, dense = [], []
            if mode in {"bm25", "hybrid"}:
                if self.library.sparse.chunk_ids != [chunk.chunk_id for chunk in chunks]:
                    self.library.sparse.restore(chunks)
                sparse = self.library.sparse.search(question, chunks, selected, self.settings.candidates_per_method)
            if mode in {"vector", "hybrid"}:
                dense = vector_search(
                    self.library.vectors.collection, self.library.embeddings, question,
                    selected, self.settings.candidates_per_method,
                )
            sparse_ids = [item[0] for item in sparse if item[0] in canonical]
            dense_ids = [item[0] for item in dense if item[0] in canonical]
            order = reciprocal_rank_fusion(sparse_ids, dense_ids, constant=self.settings.rrf_constant)
            documents = select_context([canonical[item] for item in order], self.settings)
        return RetrievalResult(
            question=question, selected_paper_ids=sorted(selected), corpus_version=version,
            documents=documents, sparse_ids=sparse_ids, dense_ids=dense_ids,
            latency_ms=round((time.perf_counter() - start) * 1000),
        )
