"""Durability and actual local embedding repair, never hosted model calls."""
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import NoEmbeddings
from src.embeddings import LocalEmbeddings
from src.ingestion.pipeline import PaperLibrary
from src.retrieval.hybrid import HybridRetriever


def test_process_interruption_mid_deletion_recovers_on_restart(settings, embeddings, make_pdf):
    library = PaperLibrary(settings, embeddings=embeddings)
    first = library.ingest(make_pdf(title="Delete"), "delete.pdf").paper
    second = library.ingest(make_pdf(title="Keep"), "keep.pdf").paper
    library.catalog.save_comparison_card("delete", first.paper_id, "v", "{}")
    library.catalog.save_comparison_card("keep", second.paper_id, "v", "{}")
    library.close()
    script = '''
from pathlib import Path
import os, sys
from src.config import IngestionSettings
from src.ingestion.pipeline import PaperLibrary
library = PaperLibrary(IngestionSettings(data_dir=Path(sys.argv[1])))
library.catalog.mark_deleting(sys.argv[2])
library.vectors.remove(sys.argv[2])
os._exit(17)
'''
    result = subprocess.run([sys.executable, "-c", script, str(settings.data_dir), first.paper_id], capture_output=True, timeout=30)
    assert result.returncode == 17, result.stderr.decode()
    for _ in range(2):
        library = PaperLibrary(settings, embeddings=NoEmbeddings())
        try:
            assert library.papers() == [second]
            assert library.catalog.comparison_card("delete") is None
            assert library.catalog.comparison_card("keep") == "{}"
            assert not library._pdf_path(first.paper_id).exists()
            assert set(library.vectors.collection.get()["ids"]) == set(library.sparse.chunk_ids)
        finally: library.close()


@pytest.mark.embedding_integration
def test_real_minilm_repairs_missing_vector_and_restores_hybrid_search(settings, make_pdf):
    cache = replace(settings, data_dir=Path(__file__).resolve().parents[1] / "data")
    library = PaperLibrary(settings, embeddings=LocalEmbeddings(cache))
    try:
        paper = library.ingest(make_pdf(), "synthetic.pdf").paper
        ids = [chunk.chunk_id for chunk in library.catalog.chunks()]
        library.vectors.collection.delete(ids=ids)
        library.recover()
        result = HybridRetriever(library).retrieve("SyntheticQA accuracy", [paper.paper_id])
        assert result.dense_ids and result.sparse_ids and result.documents
        assert not any(library.vectors.audit(library.catalog.chunks()))
    finally: library.close()
    reopened = PaperLibrary(settings, embeddings=NoEmbeddings())
    try:
        assert reopened.snapshot_loaded and reopened.papers() == [paper]
    finally: reopened.close()
