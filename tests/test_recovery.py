"""Failure injection across real SQLite/Chroma/BM25/PDF lifecycle boundaries."""
import hashlib
from pathlib import Path

import joblib
import pytest

from conftest import NoEmbeddings
from src.generation.comparison import ComparisonService
from src.ingestion.pipeline import PaperLibrary
from src.ingestion.indexing import VectorIndex
from src.retrieval.hybrid import HybridRetriever
from src.schemas import IngestionError, RetrievalError
from comparison_helpers import FakeComparisonGateway


def assert_consistent(library):
    chunks = library.catalog.chunks()
    damaged, extra = library.vectors.audit(chunks)
    assert not damaged and not extra
    assert library.sparse.chunk_ids == [chunk.chunk_id for chunk in chunks]
    for paper in library.papers():
        assert library._pdf_path(paper.paper_id).is_file()


@pytest.mark.parametrize("stage", ["add", "save_pages", "save_chunks", "mark_ready", "vectors", "pdf", "bm25"])
def test_each_ingestion_write_failure_preserves_existing_paper(library, make_pdf, monkeypatch, stage):
    healthy = library.ingest(make_pdf(title="Healthy"), "healthy.pdf").paper
    payload = make_pdf(title="Interrupted")
    owner, name = (library.vectors, "add") if stage == "vectors" else (library.sparse, "rebuild") if stage == "bm25" else (Path, "write_bytes") if stage == "pdf" else (library.catalog, stage)
    original = getattr(owner, name)
    calls = []
    def fail_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            # Fail after a write where possible: recovery must tolerate both
            # pre-write and post-write failures.
            if stage != "pdf": original(*args, **kwargs)
            raise OSError("private-fixture-disk-detail")
        return original(*args, **kwargs)
    monkeypatch.setattr(owner, name, fail_once)
    with pytest.raises(IngestionError, match="incomplete paper was removed"):
        library.ingest(payload, "interrupted.pdf")
    assert library.papers() == [healthy]
    assert not library.catalog.paper(hashlib.sha256(payload).hexdigest())
    assert_consistent(library)


@pytest.mark.parametrize("stage", ["vectors", "pdf", "catalog", "bm25", "mark"])
def test_deletion_failure_blocks_queries_then_recovery_is_repeatable(settings, embeddings, make_pdf, monkeypatch, stage):
    library = PaperLibrary(settings, embeddings=embeddings)
    first = library.ingest(make_pdf(title="Delete"), "delete.pdf").paper
    second = library.ingest(make_pdf(title="Keep"), "keep.pdf").paper
    library.catalog.save_comparison_card("delete-card", first.paper_id, "version", "{}")
    library.catalog.save_comparison_card("keep-card", second.paper_id, "version", "{}")
    owner, name = {"vectors": (library.vectors, "remove"), "pdf": (Path, "unlink"), "catalog": (library.catalog, "remove"), "bm25": (library.sparse, "rebuild"), "mark": (library.catalog, "mark_deleting")}[stage]
    original = getattr(owner, name)
    def broken(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("private-fixture-permission-detail")
    monkeypatch.setattr(owner, name, broken)
    with pytest.raises(IngestionError, match="Deletion could not finish"):
        library.delete(first.paper_id)
    with pytest.raises(RetrievalError, match="needs recovery"):
        HybridRetriever(library).retrieve("accuracy", [second.paper_id], mode="bm25")
    monkeypatch.setattr(owner, name, original)
    library.embeddings = NoEmbeddings()
    library.recover()
    assert library.papers() == [second]
    assert library.catalog.comparison_card("delete-card") is None
    assert library.catalog.comparison_card("keep-card") == "{}"
    assert not library._pdf_path(first.paper_id).exists()
    assert not library.catalog.pages(first.paper_id)
    assert_consistent(library)
    library.close()
    for _ in range(2):
        library = PaperLibrary(settings, embeddings=NoEmbeddings())
        assert library.papers() == [second] and library.snapshot_loaded
        assert_consistent(library)
        library.close()


@pytest.mark.parametrize("damage", ["missing_pdf", "changed_pdf", "page", "chunk", "warnings", "count"])
def test_damaged_canonical_sources_are_preserved_and_excluded(library, make_pdf, damage):
    payload = make_pdf(title="Damaged")
    bad = library.ingest(payload, "bad.pdf").paper
    good = library.ingest(make_pdf(title="Good"), "good.pdf").paper
    library.catalog.save_comparison_card("bad-cache", bad.paper_id, "v", "{}")
    library.catalog.save_comparison_card("good-cache", good.paper_id, "v", "{}")
    if damage == "missing_pdf": library._pdf_path(bad.paper_id).unlink()
    elif damage == "changed_pdf": library._pdf_path(bad.paper_id).write_bytes(b"changed")
    else:
        statements = {
            "page": "DELETE FROM pages WHERE paper_id=?",
            "chunk": "UPDATE chunks SET text='tampered evidence' WHERE paper_id=?",
            "warnings": "UPDATE papers SET warnings='not JSON' WHERE paper_id=?",
            "count": "UPDATE papers SET chunk_count=999 WHERE paper_id=?",
        }
        with library.catalog.connection() as db: db.execute(statements[damage], (bad.paper_id,))
    library.embeddings = NoEmbeddings()
    library.recover()
    assert library.papers() == [good]
    assert library.catalog.paper_issue(bad.paper_id)
    assert library.catalog.comparison_card("bad-cache") is None
    assert library.catalog.comparison_card("good-cache") == "{}"
    assert any(identity == bad.paper_id for identity, _status in library.catalog.identities())
    assert not library.vectors.collection.get(where={"paper_id": bad.paper_id})["ids"]
    assert_consistent(library)
    # A second recovery must preserve, rather than purge, unavailable records.
    library.recover()
    assert library.catalog.paper_issue(bad.paper_id)
    assert library.delete(bad.paper_id)
    assert library.papers() == [good]


def test_exact_pdf_restore_reactivates_preserved_paper(library, make_pdf):
    payload = make_pdf()
    paper = library.ingest(payload, "paper.pdf").paper
    library._pdf_path(paper.paper_id).unlink()
    library.recover()
    assert not library.papers()
    library._pdf_path(paper.paper_id).write_bytes(payload)
    # Quarantine removes vectors; restoring needs local embedding repair.
    library.recover()
    assert library.papers() == [paper] and library.catalog.paper_issue(paper.paper_id) is None
    assert_consistent(library)


@pytest.mark.parametrize("damage", ["missing", "text", "metadata", "vector"])
def test_vector_damage_repairs_only_affected_chunks(library, embeddings, make_pdf, damage):
    first = library.ingest(make_pdf(title="First"), "first.pdf").paper
    library.ingest(make_pdf(title="Second"), "second.pdf")
    chunk = library.catalog.chunks(first.paper_id)[0]
    collection = library.vectors.collection
    if damage == "missing": collection.delete(ids=[chunk.chunk_id])
    elif damage == "text": collection.update(ids=[chunk.chunk_id], documents=["wrong text"], embeddings=[embeddings.model.get_text_embedding(chunk.text)])
    elif damage == "metadata": collection.update(ids=[chunk.chunk_id], metadatas=[{"page_number": 999}])
    else: collection.update(ids=[chunk.chunk_id], embeddings=[[0.0] * 384])
    before, version = embeddings.model._calls, library.catalog.corpus_version()
    library.recover()
    assert embeddings.model._calls - before == 1
    assert library.catalog.corpus_version() != version
    assert_consistent(library)
    library.embeddings = NoEmbeddings()
    version = library.catalog.corpus_version()
    assert library.recover() == []
    assert library.catalog.corpus_version() == version


def test_interrupted_repair_is_safe_to_retry(library, make_pdf, monkeypatch):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    chunk = library.catalog.chunks()[0]
    library.vectors.collection.delete(ids=[chunk.chunk_id])
    original = library.vectors.repair
    def broken(*args):
        original(*args)
        raise OSError("private repair detail")
    monkeypatch.setattr(library.vectors, "repair", broken)
    with pytest.raises(IngestionError, match="recovery could not finish"):
        library.recover()
    with pytest.raises(IngestionError, match="needs recovery"): library.papers()
    monkeypatch.setattr(library.vectors, "repair", original)
    library.embeddings = NoEmbeddings()
    library.recover()
    assert library.papers() == [paper]
    assert_consistent(library)


def test_orphan_files_and_vectors_are_cleaned_conservatively(library, make_pdf):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    orphan_id = "a" * 64
    folder = library.settings.data_dir / "papers"
    (folder / f"{orphan_id}.pdf").write_bytes(b"abandoned app-owned upload")
    private = folder / "my-notes.pdf"
    private.write_bytes(b"unmanaged")
    library.vectors.collection.add(ids=["orphan-vector"], documents=["orphan"], embeddings=[[1.0] + [0.0] * 383], metadatas=[{"paper_id": orphan_id}])
    library.embeddings = NoEmbeddings()
    library.recover()
    assert private.exists() and not (folder / f"{orphan_id}.pdf").exists()
    assert library.papers() == [paper]
    assert_consistent(library)


@pytest.mark.parametrize("damage", ["idf", "frequencies", "length", "parameters"])
def test_corrupt_bm25_statistics_are_rebuilt(library, make_pdf, damage):
    library.ingest(make_pdf(), "paper.pdf")
    path = library.sparse.path
    payload = joblib.load(path)
    index = payload["index"]
    if damage == "idf": index.idf = {"invented": 123.0}
    if damage == "frequencies": index.doc_freqs = [{}]
    if damage == "length": index.doc_len = [9999]
    if damage == "parameters": index.k1 = 999
    joblib.dump(payload, path)
    library.embeddings = NoEmbeddings()
    library.recover()
    assert not library.snapshot_loaded
    assert library.sparse.search("accuracy", library.catalog.chunks(), {library.papers()[0].paper_id}, 5)


def test_unreadable_catalog_is_not_replaced(settings):
    settings.data_dir.mkdir(parents=True)
    path = settings.data_dir / "catalog.sqlite3"
    payload = b"not a sqlite database private fixture"
    path.write_bytes(payload)
    with pytest.raises(IngestionError, match="no database was reset"):
        PaperLibrary(settings, embeddings=NoEmbeddings())
    assert path.read_bytes() == payload


def test_corrupt_identifiers_stop_before_filesystem_cleanup(library, make_pdf):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    with library.catalog.connection() as db:
        db.execute("INSERT INTO papers SELECT '../escape',filename,display_title,'deleting',size_bytes,page_count,chunk_count,uploaded_at,warnings FROM papers WHERE paper_id=?", (paper.paper_id,))
    with pytest.raises(IngestionError, match="invalid identifiers"):
        library.recover()
    assert library._pdf_path(paper.paper_id).exists()


def test_validated_cards_survive_derived_index_repair(library, make_pdf):
    ids = [library.ingest(make_pdf(title=str(i)), f"{i}.pdf").paper.paper_id for i in range(2)]
    gateway = FakeComparisonGateway()
    service = ComparisonService(library, gateway=gateway)
    result = service.compare(service.collect("", ids), allow_remote=True)
    assert result.status == "completed"
    library.vectors.collection.delete(ids=[library.catalog.chunks()[0].chunk_id])
    library.recover()
    result = service.compare(service.collect("", ids), allow_remote=True)
    assert set(result.cached_paper_ids) == set(ids)
    assert len(gateway.calls) == 4


def test_unavailable_papers_count_toward_capacity_but_can_be_reuploaded(settings, embeddings, make_pdf):
    from dataclasses import replace
    library = PaperLibrary(replace(settings, max_papers=1), embeddings=embeddings)
    payload = make_pdf()
    try:
        paper = library.ingest(payload, "paper.pdf").paper
        library._pdf_path(paper.paper_id).unlink()
        library.recover()
        with pytest.raises(IngestionError, match="limited to 1"):
            library.ingest(make_pdf(title="Another"), "other.pdf")
        # An identical original can replace its own unavailable saved record.
        restored = library.ingest(payload, "restored.pdf").paper
        assert restored.paper_id == paper.paper_id and restored.status == "ready"
        assert_consistent(library)
    finally:
        library.close()


def test_incomplete_recovery_blocks_comparison_before_generation(library, make_pdf):
    ids = [library.ingest(make_pdf(title=str(i)), f"{i}.pdf").paper.paper_id for i in range(2)]
    gateway = FakeComparisonGateway()
    service = ComparisonService(library, gateway=gateway)
    evidence = service.collect("", ids)
    library._needs_recovery = True
    with pytest.raises(RetrievalError, match="needs recovery"):
        service.compare(evidence, allow_remote=True)
    assert gateway.calls == []


def test_delete_uses_canonical_ids_when_vector_paper_metadata_is_damaged(library, make_pdf):
    target = library.ingest(make_pdf(title="Delete"), "delete.pdf").paper
    other = library.ingest(make_pdf(title="Keep"), "keep.pdf").paper
    ids = library.catalog.chunk_ids(target.paper_id)
    library.vectors.collection.update(ids=ids, metadatas=[{"paper_id": "damaged-foreign-id"} for _ in ids])
    library.embeddings = NoEmbeddings()
    assert library.delete(target.paper_id)
    assert not library.vectors.collection.get(ids=ids)["ids"]
    assert library.papers() == [other]
    assert_consistent(library)
