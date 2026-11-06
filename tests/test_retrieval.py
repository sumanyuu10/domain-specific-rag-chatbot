"""Real local indexes with deterministic embeddings; no hosted calls."""
from dataclasses import replace

import pytest

from src.config import RetrievalSettings
from src.generation.chains import ResearchAssistant, resolve_question
from src.ingestion.pipeline import PaperLibrary
from src.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion, select_context
from src.schemas import RetrievalError


def test_rrf_shared_candidate_wins_and_ties_are_stable():
    assert reciprocal_rank_fusion(["a", "c"], ["b", "c"]) == ["c", "a", "b"]
    assert reciprocal_rank_fusion(["a", "a", "b"], ["b"]) == ["b", "a"]
    assert reciprocal_rank_fusion([]) == []
    with pytest.raises(ValueError):
        reciprocal_rank_fusion(["a"], constant=0)


@pytest.mark.parametrize("mode", ["bm25", "vector", "hybrid"])
def test_selected_papers_and_canonical_metadata(library, make_pdf, embeddings, mode):
    unwanted = library.ingest(make_pdf(["SyntheticQA transformer accuracy benchmark. " * 20], title="Unselected"), "unselected.pdf").paper
    selected = library.ingest(make_pdf(title="Selected"), "selected.pdf").paper
    calls = embeddings.model._calls
    service = ResearchAssistant(library)
    context = service.search("What is the SyntheticQA accuracy?", [selected.paper_id], mode=mode)
    assert context.documents
    assert {doc.metadata["paper_id"] for doc in context.documents} == {selected.paper_id}
    assert all(doc.metadata["paper_id"] != unwanted.paper_id for doc in context.documents)
    for doc in context.documents:
        canonical = library.catalog.chunk(doc.metadata["chunk_id"])
        assert doc.page_content == canonical.text
        assert doc.metadata == canonical.metadata()
    assert embeddings.model._calls - calls == (0 if mode == "bm25" else 1)


def test_bm25_filter_applies_before_top_k_and_keeps_nonpositive_matches(library, make_pdf):
    library.ingest(make_pdf(title="Outside"), "outside.pdf")
    wanted = library.ingest(make_pdf(title="Inside"), "inside.pdf").paper
    result = HybridRetriever(library, RetrievalSettings(candidates_per_method=1)).retrieve(
        "transformer", [wanted.paper_id], mode="bm25",
    )
    assert len(result.sparse_ids) == 1
    assert result.documents[0].paper_id == wanted.paper_id
    assert not HybridRetriever(library).retrieve("unfindablexyz", [wanted.paper_id], mode="bm25").documents


@pytest.mark.parametrize("question,papers,mode", [
    ("", [], "hybrid"), ("q", [], "hybrid"), ("q", ["missing"], "hybrid"),
    ("q", ["missing"], "other"), ("q" * 2001, ["missing"], "hybrid"),
])
def test_invalid_requests_never_search_all_documents(library, question, papers, mode):
    with pytest.raises(RetrievalError):
        HybridRetriever(library).retrieve(question, papers, mode=mode)


def test_deleted_selection_is_rejected(library, make_pdf):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    library.delete(paper.paper_id)
    with pytest.raises(RetrievalError, match="unavailable"):
        HybridRetriever(library).retrieve("accuracy", [paper.paper_id])


def test_dense_query_is_filtered_and_foreign_ids_are_discarded(library, make_pdf, monkeypatch):
    first = library.ingest(make_pdf(title="First"), "first.pdf").paper
    second = library.ingest(make_pdf(title="Second"), "second.pdf").paper
    foreign = library.catalog.chunks(second.paper_id)[0].chunk_id
    def wrong(*args): return [(foreign, 1.0), ("invented", 0.9)]
    monkeypatch.setattr("src.retrieval.hybrid.vector_search", wrong)
    result = HybridRetriever(library).retrieve("accuracy", [first.paper_id], mode="vector")
    assert result.documents == [] and result.dense_ids == []


def test_vector_filter_is_passed_to_chroma_before_ranking(library, make_pdf, monkeypatch):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    original = library.vectors.collection.query
    calls = []
    def capture(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(library.vectors.collection, "query", capture)
    HybridRetriever(library).retrieve("accuracy", [paper.paper_id], mode="vector")
    assert calls[0]["where"] == {"paper_id": {"$in": [paper.paper_id]}}
    assert "query_embeddings" in calls[0] and "query_texts" not in calls[0]


def test_context_bounds_preserve_distinct_results_and_other_papers(library, make_pdf):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    base = library.catalog.chunks(paper.paper_id)[0]
    chunks = [base.model_copy(update={"chunk_id": "a", "text": "Accuracy is 91.2 percent."}),
              base.model_copy(update={"chunk_id": "b", "text": "Accuracy is 86.5 percent."}),
              base.model_copy(update={"chunk_id": "c", "text": "Accuracy is 91.2 percent."}),
              base.model_copy(update={"chunk_id": "d", "paper_id": "other", "text": "Accuracy is 91.2 percent."})]
    assert [c.chunk_id for c in select_context(chunks, RetrievalSettings())] == ["a", "b", "d"]
    assert len(select_context(chunks, RetrievalSettings(context_chunks=1))) == 1
    assert select_context(chunks, RetrievalSettings(max_context_chars=5)) == []


def test_another_library_instance_refreshes_sparse_snapshot(library, settings, make_pdf, embeddings):
    first = library.ingest(make_pdf(title="First"), "first.pdf").paper
    second = PaperLibrary(settings, embeddings=embeddings)
    try:
        added = second.ingest(make_pdf(title="Added"), "added.pdf").paper
        result = HybridRetriever(library).retrieve("accuracy", [added.paper_id], mode="bm25")
        assert {item.paper_id for item in result.documents} == {added.paper_id}
        second.delete(first.paper_id)
        HybridRetriever(library).retrieve("accuracy", [added.paper_id], mode="bm25")
        assert set(library.sparse.chunk_ids) == {c.chunk_id for c in library.catalog.chunks()}
    finally:
        second.close()


def test_followups_use_only_bounded_user_question_context():
    assert resolve_question("What are its limitations?", ["Describe the Cobalt model."]).startswith("Previous user question: Describe")
    with pytest.raises(RetrievalError, match="name the paper"):
        resolve_question("What are its limitations?")


def test_long_dense_question_is_rejected_before_truncation(library, make_pdf):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    with pytest.raises(RetrievalError, match="256-token"):
        HybridRetriever(library).retrieve("word " * 270, [paper.paper_id])


def test_invalid_retrieval_limits():
    with pytest.raises(ValueError):
        replace(RetrievalSettings(), context_chunks=0)
