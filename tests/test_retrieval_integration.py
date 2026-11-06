"""Explicit real MiniLM search over existing persistent indexes, no LLM."""
from dataclasses import replace
from pathlib import Path

import pytest

from src.embeddings import LocalEmbeddings
from src.generation.chains import ResearchAssistant
from src.ingestion.pipeline import PaperLibrary


@pytest.mark.embedding_integration
def test_real_minilm_filtered_hybrid_search_preserves_sources(settings, make_pdf):
    cache = replace(settings, data_dir=Path(__file__).resolve().parents[1] / "data")
    library = PaperLibrary(settings, embeddings=LocalEmbeddings(cache))
    try:
        selected = library.ingest(make_pdf([
            "The Cobalt transformer achieves accuracy of 91.2 percent on SyntheticQA. "
            "Its baseline achieves 86.5 percent. The training dataset is small."
        ], title="Cobalt study"), "cobalt.pdf").paper
        other = library.ingest(make_pdf([
            "Graph neural networks predict molecular properties for chemistry. "
            "The training corpus contains chemical graphs and their properties."
        ], title="Graph study"), "graphs.pdf").paper
        assistant = ResearchAssistant(library)
        context = assistant.search("What is Cobalt's accuracy?", [selected.paper_id])
        assert context.documents and context.snapshot.sparse_ids and context.snapshot.dense_ids
        assert all(doc.metadata["paper_id"] == selected.paper_id for doc in context.documents)
        assert all(doc.metadata["paper_id"] != other.paper_id for doc in context.documents)
        assert "91.2" in context.documents[0].page_content
        assert context.documents[0].metadata["page_number"] == 1
    finally:
        library.close()
