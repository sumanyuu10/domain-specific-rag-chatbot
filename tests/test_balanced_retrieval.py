"""Per-paper/category retrieval budgets over real persistent local indexes."""
from dataclasses import replace

import pytest

from src.config import ComparisonSettings
from src.generation.comparison import ComparisonService
from src.retrieval.comparison import BalancedRetriever
from src.schemas import RetrievalError
from comparison_helpers import FakeComparisonGateway


def test_twelve_papers_receive_separate_budgets_despite_a_dominant_paper(library, make_pdf):
    dominant = library.ingest(make_pdf([
        "Transformer methodology dataset experiments accuracy limitations conclusions. " * 35
    ] * 3, title="Dominant"), "dominant.pdf").paper
    others = [library.ingest(make_pdf(title=f"Study {number}"), f"paper-{number}.pdf").paper for number in range(11)]
    evidence = BalancedRetriever(library).collect("Compare methods and results", [dominant.paper_id] + [paper.paper_id for paper in others])
    assert len(evidence.papers) == 12 and len(evidence.categories) == 5
    for paper in evidence.papers:
        assert len(paper.contexts) == 5
        for context in paper.contexts.values():
            assert 1 <= len(context.documents) <= 2
            assert {doc.metadata["paper_id"] for doc in context.documents} == {paper.paper.paper_id}
        assert sum(len(doc.page_content) for context in paper.contexts.values() for doc in context.documents) <= 16000
    gateway = FakeComparisonGateway()
    result = ComparisonService(library, gateway=gateway).compare(evidence, allow_remote=True)
    assert result.status == "completed" and len(result.cells) == 60 and len(result.cards) == 12
    assert len(gateway.calls) == 13


@pytest.mark.parametrize("ids,categories,focus", [
    ([], None, ""), (["a"], None, ""), (["a", "b"], [], ""),
    (["a", "b"], ["results", "results"], ""), (["a", "b"], ["unknown"], ""),
    (["a", "b"], None, "x" * 1001), (["a", "b"], None, None),
])
def test_invalid_comparison_requests_are_rejected(library, ids, categories, focus):
    with pytest.raises(RetrievalError): BalancedRetriever(library).collect(focus, ids, categories)


def test_empty_categories_are_missing_without_model_inference(library, make_pdf):
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    gateway = FakeComparisonGateway()
    service = ComparisonService(library, gateway=gateway)
    evidence = service.collect("", ids)
    for paper in evidence.papers:
        for context in paper.contexts.values():
            context.snapshot.documents.clear()
            context.documents.clear()
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "insufficient_evidence" and len(result.cells) == 10
    assert not gateway.calls and not result.citations and not result.relationships
    assert all(cell.status == "missing" for cell in result.cells)


def test_tampered_context_fails_before_generation(library, make_pdf):
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    gateway = FakeComparisonGateway()
    service = ComparisonService(library, gateway=gateway)
    evidence = service.collect("", ids)
    evidence.papers[0].contexts["results"].documents[0].metadata["page_number"] = 999
    with pytest.raises(RetrievalError, match="metadata changed"):
        service.compare(evidence, allow_remote=True)
    assert not gateway.calls


def test_changed_settings_require_new_preview(library, make_pdf):
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    service = ComparisonService(library)
    evidence = service.collect("", ids, ["results"])
    other = ComparisonService(library, settings=replace(service.settings, passages_per_category=1))
    with pytest.raises(RetrievalError, match="settings changed"):
        other.compare(evidence, allow_remote=True)


def test_invalid_comparison_limits():
    with pytest.raises(ValueError): ComparisonSettings(candidates_per_method=0)
