"""Comparison service through real retrieval, SQLite, LangChain and citations."""
from dataclasses import replace
import json

import pytest

from src.generation.comparison import ComparisonService
from src.generation.llm import CodexIntegrationError
from src.schemas import RetrievalError
from comparison_helpers import FakeComparisonGateway


@pytest.fixture
def comparison(library, make_pdf):
    ids = [library.ingest(make_pdf(title=f"Study {number}"), f"study-{number}.pdf").paper.paper_id for number in range(2)]
    gateway = FakeComparisonGateway()
    service = ComparisonService(library, gateway=gateway)
    return service, service.collect("Compare the studies", ids), gateway


def test_comparison_preserves_every_paper_category_and_original_passages(comparison):
    service, evidence, gateway = comparison
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "completed" and len(result.cells) == 10
    assert len(result.cards) == 2 and len(result.relationships) == 1
    assert [kind for kind, _request in gateway.calls] == ["card", "card", "synthesis"]
    assert gateway.tracing == [False] * 3
    assert {cell.paper_id for cell in result.cells} == set(result.selected_paper_ids)
    for citation in result.citations:
        chunk = service.library.catalog.chunk(citation.chunk_id)
        assert citation.passage == chunk.text and citation.page_number == chunk.page_number
    for cell in result.cells:
        card = next(card for card in result.cards if card.paper_id == cell.paper_id)
        section = next(section for section in card.sections if section.category == cell.category)
        assert cell.text == section.entries[0].text


def test_consent_is_required_before_any_generation(comparison):
    service, evidence, gateway = comparison
    with pytest.raises(RetrievalError, match="Allow sending"):
        service.compare(evidence)
    assert gateway.calls == []


def test_validated_card_cache_reuses_successful_papers(comparison):
    service, evidence, gateway = comparison
    first = service.compare(evidence, allow_remote=True)
    assert not first.cached_paper_ids
    second = service.compare(evidence, allow_remote=True)
    assert set(second.cached_paper_ids) == set(first.selected_paper_ids)
    assert [kind for kind, _request in gateway.calls] == ["card", "card", "synthesis", "synthesis"]


def test_changed_focus_or_categories_do_not_reuse_wrong_cards(comparison):
    service, evidence, gateway = comparison
    service.compare(evidence, allow_remote=True)
    other = service.collect("Different research focus", [paper.paper.paper_id for paper in evidence.papers], ["results"])
    result = service.compare(other, allow_remote=True)
    assert result.cached_paper_ids == []
    assert len(result.cells) == 2


@pytest.mark.parametrize("target", ["card", "synthesis"])
def test_bad_model_output_gets_only_one_repair_and_is_withheld(comparison, target):
    service, evidence, gateway = comparison
    gateway.transform = lambda kind, request, result: "not JSON" if kind == target else result
    result = service.compare(evidence, allow_remote=True)
    assert result.cells == []
    assert result.status == ("incomplete" if target == "card" else "validation_failed")
    assert sum(kind == target for kind, _ in gateway.calls) == (4 if target == "card" else 2)


def test_cross_paper_card_citations_are_rejected(comparison):
    service, evidence, gateway = comparison
    foreign = evidence.papers[1].contexts["methodology"].snapshot.documents[0].chunk_id
    def transform(kind, request, result):
        if kind == "card" and request["paper"]["paper_id"] == evidence.papers[0].paper.paper_id:
            result["sections"][0]["entries"][0]["source_ids"] = [foreign]
        return result
    gateway.transform = transform
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "incomplete" and len(result.cards) == 1
    assert all(kind != "synthesis" for kind, _ in gateway.calls)


def test_table_cannot_omit_a_selected_paper(comparison):
    service, evidence, gateway = comparison
    def transform(kind, request, result):
        if kind == "synthesis": result["cells"] = result["cells"][:5]
        return result
    gateway.transform = transform
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "validation_failed" and result.cells == []


def test_transient_failure_retries_only_failed_paper_then_uses_cache(comparison):
    service, evidence, gateway = comparison
    failing = evidence.papers[0].paper.paper_id
    def transform(kind, request, result):
        if kind == "card" and request["paper"]["paper_id"] == failing:
            raise CodexIntegrationError("timeout", "Synthetic timeout")
        return result
    gateway.transform = transform
    first = service.compare(evidence, allow_remote=True)
    assert first.status == "incomplete" and len(first.cards) == 1
    assert len(gateway.calls) == 3
    gateway.transform = None
    second = service.compare(evidence, allow_remote=True)
    assert second.status == "completed" and len(second.cached_paper_ids) == 1
    assert len(gateway.calls) == 5


def test_authentication_failure_stops_further_requests(comparison):
    service, evidence, gateway = comparison
    def transform(*args): raise CodexIntegrationError("authentication_required", "Sign in to Codex")
    gateway.transform = transform
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "incomplete" and len(gateway.calls) == 1
    assert {failure.code for failure in result.failures} == {"authentication_required", "not_attempted"}


@pytest.mark.parametrize("when", ["before", "during"])
def test_deleted_evidence_never_enters_a_comparison(comparison, when):
    service, evidence, gateway = comparison
    delete = lambda: service.library.delete(evidence.papers[0].paper.paper_id)
    if when == "before": delete()
    else:
        def transform(kind, request, result):
            delete()
            return result
        gateway.transform = transform
    with pytest.raises(RetrievalError, match="library changed"):
        service.compare(evidence, allow_remote=True)
    assert len(gateway.calls) == (0 if when == "before" else 1)
