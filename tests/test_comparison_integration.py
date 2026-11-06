"""Explicit real MiniLM comparison integration with deterministic LLM responses."""
from dataclasses import replace
from pathlib import Path

import pytest

from src.embeddings import LocalEmbeddings
from src.generation.comparison import ComparisonService
from src.ingestion.pipeline import PaperLibrary
from comparison_helpers import FakeComparisonGateway


@pytest.mark.embedding_integration
def test_actual_minilm_balanced_comparison_and_cache(settings, make_pdf):
    cache = replace(settings, data_dir=Path(__file__).resolve().parents[1] / "data")
    library = PaperLibrary(settings, embeddings=LocalEmbeddings(cache))
    gateway = FakeComparisonGateway()
    try:
        ids = [library.ingest(make_pdf([
            f"Study {number} uses a transformer for classification on SyntheticQA. "
            "The held-out test accuracy is 91.2 percent under a fixed sample budget. "
            "The authors conclude that attention helps this task. A limitation is the small training dataset."
        ], title=f"Synthetic {number}"), f"synthetic-{number}.pdf").paper.paper_id for number in range(2)]
        service = ComparisonService(library, gateway=gateway)
        evidence = service.collect("Compare the two studies", ids)
        assert all(context.snapshot.sparse_ids or context.snapshot.dense_ids
                   for paper in evidence.papers for context in paper.contexts.values())
        result = service.compare(evidence, allow_remote=True)
        assert result.status == "completed" and len(result.cells) == 10
        assert {citation.paper_id for citation in result.citations} == set(ids)
        again = service.compare(evidence, allow_remote=True)
        assert set(again.cached_paper_ids) == set(ids) and len(gateway.calls) == 4
    finally:
        library.close()
