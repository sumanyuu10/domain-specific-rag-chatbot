"""Explicit real-model check; public model download, synthetic papers, no LLM."""
from dataclasses import replace
from pathlib import Path

from langchain_core.documents import Document
import numpy as np
import pytest

from src.embeddings import LocalEmbeddings
from src.ingestion.pipeline import PaperLibrary
from conftest import NoEmbeddings


@pytest.mark.embedding_integration
def test_real_minilm_ingestion_restart_and_deletion(settings, make_pdf):
    # Reuse only public model assets across runs; documents/indexes remain temporary.
    cache_settings = replace(settings, data_dir=Path(__file__).resolve().parents[1] / "data")
    embeddings = LocalEmbeddings(cache_settings)
    service = PaperLibrary(settings, embeddings=embeddings)
    payload = make_pdf([
        "A transformer uses self-attention for language understanding. " * 30,
        "Our classifier evaluates SyntheticQA. Accuracy is 91.2 percent with limitations. " * 30,
    ])
    try:
        paper = service.ingest(payload, "synthetic-study.pdf").paper
        chunks = service.catalog.chunks()
        assert paper.chunk_count > 2
        assert embeddings.model._model.get_embedding_dimension() == 384
        assert embeddings.model._model.max_seq_length == 256
        assert all(len(embeddings.tokenize(chunk.text, special_tokens=True)) <= 256 for chunk in chunks)
        vectors = service.vectors.collection.get(include=["embeddings"])["embeddings"]
        assert vectors.shape == (paper.chunk_count, 384)
        assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
        query = embeddings.model.get_query_embedding("What accuracy did the classifier report?")
        hit = service.vectors.collection.query(query_embeddings=[query], n_results=1)
        metadata = hit["metadatas"][0][0]
        assert metadata["paper_id"] == paper.paper_id
        assert metadata["page_number"] in (1, 2)
        # Verify the canonical payload can cross the future LangChain boundary.
        document = Document(page_content=hit["documents"][0][0], metadata=metadata)
        assert document.metadata["chunk_id"] in {chunk.chunk_id for chunk in chunks}
    finally:
        service.close()
    restarted = PaperLibrary(settings, embeddings=NoEmbeddings())
    try:
        assert restarted.snapshot_loaded
        assert restarted.ingest(payload, "same.pdf").duplicate
        assert restarted.delete(paper.paper_id)
        assert restarted.vectors.collection.count() == 0
        assert restarted.sparse.chunk_ids == []
    finally:
        restarted.close()
