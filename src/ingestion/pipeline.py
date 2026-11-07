"""Document lifecycle: PDF → LlamaIndex → local Chroma + BM25 + catalog."""
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path

from filelock import FileLock, Timeout

from src.config import IngestionSettings
from src.embeddings import LocalEmbeddings
from src.ingestion.chunking import prepare_chunks
from src.ingestion.indexing import VectorIndex
from src.ingestion.pdf import ResearchPDFReader
from src.ingestion.recovery import recover_library
from src.persistence import Catalog
from src.retrieval.bm25 import SparseIndex
from src.schemas import IngestionError, IngestionResult, PaperRecord


LOGGER = logging.getLogger(__name__)


class PaperLibrary:
    def __init__(self, settings: IngestionSettings | None = None, *, embeddings=None):
        self.settings = settings or IngestionSettings.from_environment()
        self.vectors = None
        self._needs_recovery = True
        self.recovery_events = []
        self.embeddings = embeddings if embeddings is not None else LocalEmbeddings(self.settings)
        try:
            self.settings.data_dir.mkdir(parents=True, exist_ok=True)
            self.lock = FileLock(str(self.settings.data_dir / "library.lock"), timeout=120)
            with self.lock:
                self.catalog = Catalog(self.settings.data_dir / "catalog.sqlite3", self.settings.fingerprint)
                self.catalog.check_integrity()
                self.vectors = VectorIndex(self.settings)
                self.sparse = SparseIndex(self.settings.data_dir / "bm25.joblib", self.settings.fingerprint)
                self.recover()
        except Exception as error:
            self.close()
            if isinstance(error, (IngestionError, Timeout)):
                raise
            LOGGER.error("library_open_failed")
            raise IngestionError(
                "The local catalog/index could not be opened. Check disk space and permissions; "
                "for corrupt storage restore a backup. Existing files were preserved; no database was reset."
            ) from error

    def ensure_available(self, error_type=IngestionError):
        if self._needs_recovery:
            raise error_type("The local library needs recovery. Use Check and recover local library or restart before searching or generating.")

    def recover(self):
        """Inspect and repair derived state under the same lock as all writes."""
        with self.lock:
            self._needs_recovery = True
            try:
                events = recover_library(self)
            except IngestionError:
                LOGGER.warning("library_recovery_incomplete")
                raise
            except Exception as error:
                LOGGER.error("library_recovery_failed")
                raise IngestionError(
                    "Local recovery could not finish. Saved paper records were preserved. Check disk space, "
                    "permissions and the cached MiniLM model, then retry recovery. Corrupt storage may need a backup."
                ) from error
            self._needs_recovery = False
            self.recovery_events = events
            return events

    def _pdf_path(self, paper_id: str) -> Path:
        return self.settings.data_dir / "papers" / (paper_id + ".pdf")

    def _purge(self, paper_id):
        self.vectors.remove(paper_id, self.catalog.chunk_ids(paper_id))
        self._pdf_path(paper_id).unlink(missing_ok=True)
        self.catalog.remove(paper_id)

    def papers(self):
        with self.lock:
            self.ensure_available()
            return self.catalog.papers()

    def pages(self, paper_id):
        with self.lock:
            self.ensure_available()
            paper = self.catalog.paper(paper_id)
            return self.catalog.pages(paper_id) if paper and paper.status == "ready" else []

    def ingest(self, payload: bytes, filename: str, *, progress=None) -> IngestionResult:
        notify = progress or (lambda _message: None)
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        paper_id = hashlib.sha256(payload).hexdigest()
        with self.lock:
            self.ensure_available()
            existing = self.catalog.paper(paper_id)
            if existing and existing.status == "ready":
                return IngestionResult(paper=existing, duplicate=True)
            if existing is None and len(self.catalog.identities()) >= self.settings.max_papers:
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
            try:
                if existing:
                    self.catalog.mark_deleting(paper_id)
                    self._purge(paper_id)
                self.catalog.add(paper)
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
                    self._needs_recovery = True
                    LOGGER.error("ingestion_cleanup_incomplete")
                    raise IngestionError(
                        "Indexing failed and cleanup needs another attempt. Restart the application "
                        "to recover; the incomplete paper will not be shown as ready."
                    ) from error
                LOGGER.warning("ingestion_rolled_back")
                if isinstance(error, IngestionError):
                    raise
                raise IngestionError("Local indexing failed. The incomplete paper was removed; existing papers were preserved.") from error
            return IngestionResult(paper=self.catalog.paper(paper_id))

    def delete(self, paper_id: str) -> bool:
        with self.lock:
            self.ensure_available()
            if paper_id not in {identity for identity, _status in self.catalog.identities()}:
                return False
            try:
                self.catalog.mark_deleting(paper_id)
                self._purge(paper_id)
                self.sparse.rebuild(self.catalog.chunks())
            except Exception as error:
                self._needs_recovery = True
                LOGGER.error("deletion_incomplete")
                raise IngestionError("Deletion could not finish. Restart to retry recovery before using this collection.") from error
            return True

    def close(self):
        if self.vectors is not None:
            self.vectors.close()
