"""Exercise real PDF, LlamaIndex, Chroma, BM25, SQLite and lifecycle boundaries."""
from dataclasses import replace
import hashlib
import subprocess
import sys

import joblib
import pymupdf
import pytest

from src.embeddings import LocalEmbeddings
from src.ingestion.cleaning import clean_pages, clean_text
from src.ingestion.pdf import ResearchPDFReader, ordered_text
from src.ingestion.pipeline import PaperLibrary
from src.retrieval.bm25 import tokenize
from src.schemas import ConfigurationMismatch, IngestionError
from conftest import NoEmbeddings


def test_reader_follows_llamaindex_document_contract(settings, make_pdf):
    from llama_index.core import Document
    documents = ResearchPDFReader().load_data(
        make_pdf(), paper_id="test-paper", filename="study.pdf", settings=settings,
    )
    assert isinstance(documents, list) and isinstance(documents[0], Document)
    assert documents[0].metadata["page_number"] == 1
    assert documents[0].metadata["paper_id"] == "test-paper"


def test_upload_metadata_and_indexes_share_canonical_chunks(library, embeddings, make_pdf):
    payload = make_pdf(["Attention models learn long range dependencies. " * 60, "The second page reports accuracy 91.2 and baseline 86.5. " * 20])
    result = library.ingest(payload, "../private/research.pdf")
    paper = result.paper
    assert paper.paper_id == hashlib.sha256(payload).hexdigest()
    assert paper.filename == "research.pdf" and paper.status == "ready"
    assert paper.page_count == 2 and paper.chunk_count > 2
    chunks = library.catalog.chunks()
    stored = library.vectors.collection.get(include=["documents", "metadatas", "embeddings"])
    assert set(stored["ids"]) == {chunk.chunk_id for chunk in chunks} == set(library.sparse.chunk_ids)
    assert len({len(vector) for vector in stored["embeddings"]}) == 1
    assert all(len(vector) == 384 for vector in stored["embeddings"])
    assert embeddings.model._calls == len(chunks)  # Exactly one embedding per chunk.
    for chunk in chunks:
        metadata = stored["metadatas"][stored["ids"].index(chunk.chunk_id)]
        assert metadata["paper_id"] == paper.paper_id
        assert metadata["filename"] == paper.filename
        assert metadata["page_number"] in (1, 2)
        assert metadata["chunk_id"] == chunk.chunk_id
        assert chunk.text in library.pages(paper.paper_id)[chunk.page_number - 1].cleaned_text
    assert library._pdf_path(paper.paper_id).read_bytes() == payload
    assert library.sparse.index.get_scores(tokenize("accuracy")).shape == (len(chunks),)


def test_duplicate_does_not_reembed_or_change_metadata(library, embeddings, make_pdf):
    payload = make_pdf()
    first = library.ingest(payload, "first.pdf").paper
    calls = embeddings.model._calls
    library.embeddings = NoEmbeddings()
    second = library.ingest(payload, "renamed.pdf")
    assert second.duplicate and second.paper == first
    assert embeddings.model._calls == calls


def test_restart_restores_indexes_without_embedding(settings, embeddings, make_pdf):
    first = PaperLibrary(settings, embeddings=embeddings)
    paper = first.ingest(make_pdf(), "paper.pdf").paper
    ids = first.sparse.chunk_ids[:]
    first.close()
    second = PaperLibrary(settings, embeddings=NoEmbeddings())
    try:
        assert second.snapshot_loaded
        assert second.papers() == [paper]
        assert second.sparse.chunk_ids == ids
        assert set(second.vectors.collection.get()["ids"]) == set(ids)
        assert second.pages(paper.paper_id)[0].page_number == 1
    finally:
        second.close()


@pytest.mark.parametrize("damage", ["missing", "corrupt", "stale"])
def test_bm25_snapshot_recovers_without_reembedding(settings, embeddings, make_pdf, damage):
    first = PaperLibrary(settings, embeddings=embeddings)
    paper = first.ingest(make_pdf(), "paper.pdf").paper
    path = first.sparse.path
    first.close()
    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        path.write_bytes(b"not a joblib archive")
    else:
        payload = joblib.load(path)
        payload["ids"] = []
        joblib.dump(payload, path)
    second = PaperLibrary(settings, embeddings=NoEmbeddings())
    try:
        assert not second.snapshot_loaded
        assert len(second.sparse.chunk_ids) == paper.chunk_count
        assert second.vectors.collection.count() == paper.chunk_count
    finally:
        second.close()


def test_delete_removes_only_target_paper(library, make_pdf):
    first = library.ingest(make_pdf(title="First"), "a.pdf").paper
    second = library.ingest(make_pdf(title="Second"), "b.pdf").paper
    library.embeddings = NoEmbeddings()
    assert library.delete(first.paper_id)
    assert not library.delete(first.paper_id)
    assert library.papers() == [second]
    assert not library._pdf_path(first.paper_id).exists()
    assert not library.catalog.pages(first.paper_id)
    assert not library.catalog.chunks(first.paper_id)
    assert not library.vectors.collection.get(where={"paper_id": first.paper_id})["ids"]
    assert set(library.sparse.chunk_ids) == {c.chunk_id for c in library.catalog.chunks(second.paper_id)}


def test_capacity_and_duplicate_at_capacity(settings, embeddings, make_pdf):
    service = PaperLibrary(replace(settings, max_papers=1), embeddings=embeddings)
    try:
        payload = make_pdf()
        service.ingest(payload, "one.pdf")
        assert service.ingest(payload, "again.pdf").duplicate
        with pytest.raises(IngestionError, match="limited to 1"):
            service.ingest(make_pdf(title="Different"), "two.pdf")
        assert len(service.papers()) == 1
    finally:
        service.close()


def test_twelve_paper_library_reopens_without_rebuilding(settings, embeddings, make_pdf):
    first = PaperLibrary(settings, embeddings=embeddings)
    try:
        for number in range(12):
            first.ingest(make_pdf(title=f"Study {number}"), f"study-{number}.pdf")
        with pytest.raises(IngestionError, match="limited to 12"):
            first.ingest(make_pdf(title="Thirteenth"), "overflow.pdf")
        ids = set(first.sparse.chunk_ids)
    finally:
        first.close()
    second = PaperLibrary(settings, embeddings=NoEmbeddings())
    try:
        assert len(second.papers()) == 12
        assert second.snapshot_loaded
        assert set(second.vectors.collection.get()["ids"]) == ids
        assert set(second.sparse.chunk_ids) == ids
    finally:
        second.close()
    # A different interpreter cannot reuse any in-process Chroma state.
    check = subprocess.run([
        sys.executable, "-c",
        "from pathlib import Path; import sys; "
        "from src.config import IngestionSettings; "
        "from src.ingestion.pipeline import PaperLibrary; "
        "library=PaperLibrary(IngestionSettings(data_dir=Path(sys.argv[1]))); "
        "assert len(library.papers())==12; assert library.snapshot_loaded; "
        "assert library.vectors.collection.count()==len(library.sparse.chunk_ids)>0; "
        "assert 'model' not in library.embeddings.__dict__; library.close()",
        str(settings.data_dir),
    ], capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stderr


@pytest.mark.parametrize("case, message", [
    ("empty", "nonempty"), ("corrupt", "corrupt"), ("encrypted", "Password-protected"),
    ("scanned", "No usable selectable text"), ("extension", ".pdf extension"),
])
def test_unsupported_pdf_fails_before_loading_model(library, make_pdf, case, message):
    library.embeddings = NoEmbeddings()
    payload, name = make_pdf(), "paper.pdf"
    if case == "empty": payload = b""
    if case == "corrupt": payload = b"%PDF broken"
    if case == "encrypted": payload = make_pdf(password="secret")
    if case == "scanned": payload = make_pdf([""])
    if case == "extension": name = "paper.txt"
    with pytest.raises(IngestionError, match=message):
        library.ingest(payload, name)
    assert not library.papers()
    assert library.vectors.collection.count() == 0
    assert not list((library.settings.data_dir / "papers").glob("*.pdf"))


@pytest.mark.parametrize("limit", ["size", "pages"])
def test_file_and_page_limits(settings, make_pdf, limit):
    config = replace(settings, max_file_bytes=100) if limit == "size" else replace(settings, max_pages=1)
    with pytest.raises(IngestionError):
        ResearchPDFReader().load_data(make_pdf(["Research on machine learning. " * 10] * 2), paper_id="id", filename="paper.pdf", settings=config)


def test_blank_page_is_preserved_with_warning(library, make_pdf):
    paper = library.ingest(make_pdf(["Language models evaluate benchmark datasets with accuracy metrics. " * 4, ""]), "paper.pdf").paper
    pages = library.pages(paper.paper_id)
    assert len(pages) == 2 and pages[1].original_text == ""
    assert pages[1].warnings
    assert {chunk.page_number for chunk in library.catalog.chunks()} == {1}


def test_unexpected_pdf_extraction_failure_is_safe(library, make_pdf, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("Invalid internal PDF page structure")
    monkeypatch.setattr(ResearchPDFReader, "read_pdf", broken)
    with pytest.raises(IngestionError, match="No paper data was saved"):
        library.ingest(make_pdf(), "damaged.pdf")
    assert library.catalog.papers(include_pending=True) == []
    assert library.vectors.collection.count() == 0


@pytest.mark.parametrize("failure", ["tokenizer", "vectors", "bm25"])
def test_ingestion_failure_cleans_partial_paper(library, embeddings, make_pdf, monkeypatch, failure):
    existing = library.ingest(make_pdf(title="Existing"), "existing.pdf").paper
    payload = make_pdf(title="Will fail")
    if failure == "tokenizer":
        def broken(*args, **kwargs): raise RuntimeError("model unavailable")
        monkeypatch.setattr(embeddings, "tokenize", broken)
    elif failure == "vectors":
        original = library.vectors.add
        def broken(*args):
            original(*args)
            raise RuntimeError("simulated failure after writing vectors")
        monkeypatch.setattr(library.vectors, "add", broken)
    else:
        original = library.sparse.rebuild
        calls = []
        def broken(chunks):
            calls.append(1)
            if len(calls) == 1: raise OSError("simulated disk failure")
            return original(chunks)
        monkeypatch.setattr(library.sparse, "rebuild", broken)
    with pytest.raises(IngestionError, match="incomplete paper was removed"):
        library.ingest(payload, "failed.pdf")
    assert library.papers() == [existing]
    assert library.catalog.paper(hashlib.sha256(payload).hexdigest()) is None
    assert not library._pdf_path(hashlib.sha256(payload).hexdigest()).exists()
    assert library.vectors.collection.count() == existing.chunk_count
    assert len(library.sparse.chunk_ids) == existing.chunk_count


@pytest.mark.parametrize("status", ["processing", "deleting"])
def test_restart_purges_interrupted_operations(settings, embeddings, make_pdf, status):
    first = PaperLibrary(settings, embeddings=embeddings)
    paper = first.ingest(make_pdf(), "paper.pdf").paper
    with first.catalog.connection() as db:
        db.execute("UPDATE papers SET status=? WHERE paper_id=?", (status, paper.paper_id))
    first.close()
    second = PaperLibrary(settings, embeddings=NoEmbeddings())
    try:
        assert not second.papers()
        assert not second.catalog.papers(include_pending=True)
        assert second.vectors.collection.count() == 0
        assert second.sparse.chunk_ids == []
        assert not second._pdf_path(paper.paper_id).exists()
    finally:
        second.close()


def test_incompatible_pipeline_is_rejected_without_deleting_data(settings, embeddings, make_pdf):
    service = PaperLibrary(settings, embeddings=embeddings)
    paper = service.ingest(make_pdf(), "paper.pdf").paper
    service.close()
    with pytest.raises(ConfigurationMismatch, match="existing data was preserved"):
        PaperLibrary(replace(settings, chunk_size=180), embeddings=NoEmbeddings())
    restored = PaperLibrary(settings, embeddings=NoEmbeddings())
    try:
        assert restored.papers() == [paper]
        assert restored.vectors.collection.count() == paper.chunk_count
    finally:
        restored.close()


def test_cleaning_preserves_results_and_removes_repeated_edge_headers():
    pages = [f"Research proceedings\nAccuracy 91.2%, baseline 86.5%.\n{number}" for number in (1, 2, 3)]
    assert clean_pages(pages) == ["Accuracy 91.2%, baseline 86.5%."] * 3
    assert clean_text("The ﬁrst\x00  model\n\n\nworks") == "The first model\n\nworks"


def test_technical_bm25_tokenization():
    assert tokenize("GPT-4 BM25 C++ C# 91.2 arXiv/ML") == ["gpt-4", "bm25", "c++", "c#", "91.2", "arxiv/ml"]


def test_two_column_reading_order():
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((55, 50), "Full width title: Research paper methodology and results")
    page.insert_text((55, 100), "LEFT COLUMN FIRST")
    page.insert_text((330, 100), "RIGHT COLUMN FIRST")
    page.insert_text((55, 160), "LEFT COLUMN SECOND")
    page.insert_text((330, 160), "RIGHT COLUMN SECOND")
    text, columns = ordered_text(page)
    document.close()
    assert columns
    assert text.index("LEFT COLUMN SECOND") < text.index("RIGHT COLUMN FIRST")


def test_model_load_failure_is_actionable_and_lazy(settings, monkeypatch):
    import llama_index.embeddings.huggingface as module
    def broken(*args, **kwargs): raise OSError("no network")
    monkeypatch.setattr(module, "HuggingFaceEmbedding", broken)
    service = LocalEmbeddings(settings)
    assert "model" not in service.__dict__
    with pytest.raises(IngestionError, match="First use needs internet"):
        _ = service.model
