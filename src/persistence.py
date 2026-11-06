"""SQLite catalog. Connections are short-lived; the library owns write locking."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from src.schemas import ChunkRecord, ConfigurationMismatch, PageRecord, PaperRecord


class Catalog:
    def __init__(self, path: Path, fingerprint: str):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS papers(
                    paper_id TEXT PRIMARY KEY, filename TEXT NOT NULL, display_title TEXT NOT NULL,
                    status TEXT NOT NULL, size_bytes INTEGER NOT NULL, page_count INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL, uploaded_at TEXT NOT NULL, warnings TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pages(
                    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
                    page_number INTEGER NOT NULL, original_text TEXT NOT NULL,
                    cleaned_text TEXT NOT NULL, warnings TEXT NOT NULL,
                    PRIMARY KEY(paper_id,page_number)
                );
                CREATE TABLE IF NOT EXISTS chunks(
                    chunk_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
                    filename TEXT NOT NULL, display_title TEXT NOT NULL, page_number INTEGER NOT NULL,
                    chunk_ordinal INTEGER NOT NULL, text TEXT NOT NULL, pipeline_version TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_paper ON chunks(paper_id);
            """)
            row = db.execute("SELECT value FROM metadata WHERE key='fingerprint'").fetchone()
            if row and row[0] != fingerprint and db.execute("SELECT count(*) FROM papers").fetchone()[0]:
                raise ConfigurationMismatch(
                    "This collection uses different chunking or embeddings. Keep its original "
                    "configuration or choose a new empty RAG_DATA_DIR; existing data was preserved."
                )
            db.execute("INSERT OR REPLACE INTO metadata VALUES('fingerprint',?)", (fingerprint,))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _paper(row) -> PaperRecord:
        values = dict(row)
        values["warnings"] = json.loads(values["warnings"])
        return PaperRecord(**values)

    def papers(self, *, include_pending=False) -> list[PaperRecord]:
        with self.connection() as db:
            query = "SELECT * FROM papers" + ("" if include_pending else " WHERE status='ready'")
            return [self._paper(row) for row in db.execute(query + " ORDER BY uploaded_at,paper_id")]

    def paper(self, paper_id: str) -> PaperRecord | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
            return self._paper(row) if row else None

    def add(self, paper: PaperRecord):
        with self.connection() as db:
            db.execute("INSERT INTO papers VALUES(?,?,?,?,?,?,?,?,?)", (
                paper.paper_id, paper.filename, paper.display_title, paper.status,
                paper.size_bytes, paper.page_count, paper.chunk_count, paper.uploaded_at,
                json.dumps(paper.warnings),
            ))

    def save_pages(self, pages: list[PageRecord]):
        with self.connection() as db:
            db.executemany("INSERT INTO pages VALUES(?,?,?,?,?)", [(
                page.paper_id, page.page_number, page.original_text, page.cleaned_text,
                json.dumps(page.warnings),
            ) for page in pages])

    def save_chunks(self, chunks: list[ChunkRecord]):
        with self.connection() as db:
            db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)", [(
                chunk.chunk_id, chunk.paper_id, chunk.filename, chunk.display_title,
                chunk.page_number, chunk.chunk_ordinal, chunk.text, chunk.pipeline_version,
            ) for chunk in chunks])

    def mark_ready(self, paper_id: str, count: int):
        with self.connection() as db:
            db.execute("UPDATE papers SET status='ready',chunk_count=? WHERE paper_id=?", (count, paper_id))

    def mark_deleting(self, paper_id: str):
        with self.connection() as db:
            db.execute("UPDATE papers SET status='deleting' WHERE paper_id=?", (paper_id,))

    def remove(self, paper_id: str):
        with self.connection() as db:
            db.execute("DELETE FROM papers WHERE paper_id=?", (paper_id,))

    def pages(self, paper_id: str) -> list[PageRecord]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM pages WHERE paper_id=? ORDER BY page_number", (paper_id,))
            return [PageRecord(**{**dict(row), "warnings": json.loads(row["warnings"])}) for row in rows]

    def chunks(self, paper_id: str | None = None, *, include_processing=False) -> list[ChunkRecord]:
        with self.connection() as db:
            query = "SELECT c.* FROM chunks c JOIN papers p ON c.paper_id=p.paper_id WHERE "
            query += "p.status IN ('ready','processing')" if include_processing else "p.status='ready'"
            args = ()
            if paper_id:
                query += " AND c.paper_id=?"
                args = (paper_id,)
            query += " ORDER BY c.paper_id,c.page_number,c.chunk_ordinal"
            return [ChunkRecord(**dict(row)) for row in db.execute(query, args)]

    def chunk(self, chunk_id: str) -> ChunkRecord | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT c.* FROM chunks c JOIN papers p ON c.paper_id=p.paper_id "
                "WHERE c.chunk_id=? AND p.status='ready'", (chunk_id,),
            ).fetchone()
            return ChunkRecord(**dict(row)) if row else None

    def corpus_version(self) -> str:
        """Identity of the active corpus, for invalidating in-memory answers."""
        import hashlib
        with self.connection() as db:
            rows = db.execute(
                "SELECT paper_id,uploaded_at,chunk_count FROM papers WHERE status='ready' ORDER BY paper_id"
            ).fetchall()
            fingerprint = db.execute("SELECT value FROM metadata WHERE key='fingerprint'").fetchone()[0]
        return hashlib.sha256(json.dumps([fingerprint, [tuple(row) for row in rows]]).encode()).hexdigest()
