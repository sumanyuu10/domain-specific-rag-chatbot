"""Comparison coverage, relationship provenance and protocol compatibility."""
import pytest

from src.generation.comparison import ComparisonService
from comparison_helpers import FakeComparisonGateway


def prepare(library, make_pdf, transform=None, categories=None):
    ids = [library.ingest(make_pdf(title=str(number)), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    gateway = FakeComparisonGateway(transform)
    service = ComparisonService(library, gateway=gateway)
    return service, service.collect("", ids, categories), gateway


@pytest.mark.parametrize("hazard", ["unknown_entry", "duplicate_cell", "foreign_paper", "unknown_source", "one_paper_relation", "missing_category"])
def test_invalid_synthesis_is_withheld(library, make_pdf, hazard):
    def transform(kind, request, result):
        if kind == "synthesis":
            if hazard == "unknown_entry": result["cells"][0]["entry_indices"] = [999]
            if hazard == "duplicate_cell": result["cells"][1] = result["cells"][0]
            if hazard == "foreign_paper": result["cells"][0]["paper_id"] = "not selected"
            if hazard == "unknown_source": result["relationships"][0]["source_ids"][0] = "not supplied"
            if hazard == "one_paper_relation": result["relationships"][0]["paper_ids"] *= 0
            if hazard == "missing_category": result["cells"].pop()
        return result
    service, evidence, _gateway = prepare(library, make_pdf, transform)
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "validation_failed" and not result.cells and not result.relationships


def test_missing_paper_category_is_not_filled_from_another_paper(library, make_pdf):
    def transform(kind, request, result):
        if kind == "card" and request["paper"]["filename"] == "paper-0.pdf":
            section = next(section for section in result["sections"] if section["category"] == "datasets")
            section.update(status="missing", entries=[], missing_information="Dataset details were not found in these passages.")
        return result
    service, evidence, _gateway = prepare(library, make_pdf, transform)
    result = service.compare(evidence, allow_remote=True)
    missing = [cell for cell in result.cells if cell.category == "datasets" and cell.status == "missing"]
    assert result.status == "completed" and len(missing) == 1
    assert missing[0].source_ids == []


@pytest.mark.parametrize("field", ["dataset", "split", "metric", "task", "settings", "unknown"])
def test_result_disagreements_need_matching_complete_reported_conditions(library, make_pdf, field):
    def transform(kind, request, result):
        if kind == "card" and request["paper"]["filename"] == "paper-1.pdf":
            section = next(section for section in result["sections"] if section["category"] == "results")
            section["entries"][0]["experiment"]["dataset" if field == "unknown" else field] = None if field == "unknown" else "different protocol"
        if kind == "synthesis":
            cards = request["cards"]
            entries = [next(section for section in card["sections"] if section["category"] == "results")["entries"][0] for card in cards]
            result["relationships"] = [{
                "kind": "disagreement", "category": "results", "text": "The findings differ.",
                "paper_ids": [card["paper_id"] for card in cards],
                "source_ids": [entry["source_ids"][0] for entry in entries],
            }]
        return result
    service, evidence, _gateway = prepare(library, make_pdf, transform, ["results"])
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "validation_failed" and not result.relationships


def test_different_protocols_are_explicitly_not_directly_comparable(library, make_pdf):
    def transform(kind, request, result):
        if kind == "card" and request["paper"]["filename"] == "paper-1.pdf":
            result["sections"][0]["entries"][0]["experiment"]["dataset"] = "DifferentData"
        return result
    service, evidence, _gateway = prepare(library, make_pdf, transform, ["results"])
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "completed"
    assert result.result_comparability[0].status == "not_directly_comparable"


def test_source_relationship_requires_evidence_from_each_named_paper(library, make_pdf):
    def transform(kind, request, result):
        if kind == "synthesis":
            source = result["relationships"][0]["source_ids"][0]
            result["relationships"][0]["source_ids"] = [source, source]
        return result
    service, evidence, _gateway = prepare(library, make_pdf, transform)
    result = service.compare(evidence, allow_remote=True)
    assert result.status == "validation_failed"
