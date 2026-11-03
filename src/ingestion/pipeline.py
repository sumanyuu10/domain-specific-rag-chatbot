"""Document lifecycle: PDF → LlamaIndex → local Chroma + BM25 + catalog."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from filelock import FileLock

from src.config import IngestionSettings
from src.embeddings import LocalEmbeddings
from src.ingestion.chunking import prepare_chunks
from src.ingestion.indexing import VectorIndex
from src.ingestion.pdf import ResearchPDFReader
from src.persistence import Catalog
from src.retrieval.bm25 import SparseIndex
from src.schemas import IngestionError, IngestionResult, PaperRecord


class PaperLibrary:
    def __init__(self, settings: IngestionSettings | None = None, *, embeddings=None):
        self.settings = settings or IngestionSettings.from_environment()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.settings.data_dir / "library.lock"), timeout=120)
        self.embeddings = embeddings if embeddings is not None else LocalEmbeddings(self.settings)
        with self.lock:
            self.catalog = Catalog(self.settings.data_dir / "catalog.sqlite3", self.settings.fingerprint)
            self.vectors = VectorIndex(self.settings)
            self.sparse = SparseIndex(self.settings.data_dir / "bm25.joblib", self.settings.fingerprint)
            for paper in self.catalog.papers(include_pending=True):
                if paper.status != "ready":
                    self._purge(paper.paper_id)
            self.snapshot_loaded = self.sparse.restore(self.catalog.chunks())

    def _pdf_path(self, paper_id: str) -> Path:
        return self.settings.data_dir / "papers" / (paper_id + ".pdf")

    def _purge(self, paper_id):
        self.vectors.remove(paper_id)
        self._pdf_path(paper_id).unlink(missing_ok=True)
        self.catalog.remove(paper_id)

    def papers(self):
        with self.lock:
            return self.catalog.papers()

    def pages(self, paper_id):
        with self.lock:
            paper = self.catalog.paper(paper_id)
            return self.catalog.pages(paper_id) if paper and paper.status == "ready" else []

    def ingest(self, payload: bytes, filename: str, *, progress=None) -> IngestionResult:
        notify = progress or (lambda _message: None)
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        paper_id = hashlib.sha256(payload).hexdigest()
        with self.lock:
            existing = self.catalog.paper(paper_id)
            if existing and existing.status == "ready":
                return IngestionResult(paper=existing, duplicate=True)
            if len(self.catalog.papers()) >= self.settings.max_papers:
                raise IngestionError(f"This library is limited to {self.settings.max_papers} papers. Remove one before adding another.")
            notify("Extracting selectable PDF text")
            try:
                extracted = ResearchPDFReader().read_pdf(
                    payload, paper_id=paper_id, filename=filename, settings=self.settings,
                )
            except IngestionError:
                raise
            except Exception as error:
                raise IngestionError(
                    "Text extraction failed for this PDF. No paper data was saved; "
                    "try an unlocked, selectable-text copy."
                ) from error
            pages, documents = extracted.pages, extracted.documents
            paper = PaperRecord(
                paper_id=paper_id, filename=filename, display_title=extracted.title,
                size_bytes=len(payload), page_count=len(pages),
                uploaded_at=datetime.now(timezone.utc).isoformat(),
                warnings=[f"PDF page {page.page_number}: {warning}" for page in pages for warning in page.warnings],
            )
            if existing:
                self._purge(paper_id)
            self.catalog.add(paper)
            try:
                target = self._pdf_path(paper_id)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                self.catalog.save_pages(pages)
                notify("Loading the local embedding model and preparing chunks")
                nodes, chunks = prepare_chunks(documents, self.settings, self.embeddings)
                self.catalog.save_chunks(chunks)
                notify("Generating local embeddings and writing Chroma")
                self.vectors.add(nodes, self.embeddings)
                notify("Saving the BM25 index")
                self.catalog.mark_ready(paper_id, len(chunks))
                self.sparse.rebuild(self.catalog.chunks())
            except Exception as error:
                try:
                    self.catalog.mark_deleting(paper_id)
                    self._purge(paper_id)
                    self.sparse.rebuild(self.catalog.chunks())
                except Exception:
                    raise IngestionError(
                        "Indexing failed and cleanup needs another attempt. Restart the application "
                        "to recover; the incomplete paper will not be shown as ready."
                    ) from error
                if isinstance(error, IngestionError):
                    raise
                raise IngestionError("Local indexing failed. The incomplete paper was removed; existing papers were preserved.") from error
            return IngestionResult(paper=self.catalog.paper(paper_id))

    def delete(self, paper_id: str) -> bool:
        with self.lock:
            if not self.catalog.paper(paper_id):
                return False
            self.catalog.mark_deleting(paper_id)
            try:
                self._purge(paper_id)
                self.sparse.rebuild(self.catalog.chunks())
            except Exception as error:
                raise IngestionError("Deletion could not finish. Restart to retry recovery before using this collection.") from error
            return True

    def close(self):
        self.vectors.close()
