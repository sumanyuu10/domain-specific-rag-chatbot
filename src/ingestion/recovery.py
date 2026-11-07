"""Local consistency checks. Canonical corruption is preserved, never guessed away."""
import hashlib
import logging
import re

from src.schemas import IngestionError

LOGGER = logging.getLogger(__name__)
ISSUES = {
    "missing_pdf": "The original PDF is missing. Restore the exact file or delete and upload the paper again.",
    "changed_pdf": "The saved PDF differs from the indexed original. Restore the exact file or delete and upload again.",
    "canonical_records": "Saved paper/page/chunk records are inconsistent. Restore a backup or delete and upload this paper again.",
}


def audit_paper(library, paper_id):
    """Return a fixed diagnostic code; no parsing/rechunking or model invocation."""
    try:
        paper = library.catalog.paper(paper_id)
        pages = library.catalog.pages(paper_id)
        chunks = library.catalog.chunks(paper_id, include_unavailable=True)
        if (paper.size_bytes <= 0 or paper.page_count != len(pages) or not chunks
                or paper.chunk_count != len(chunks)
                or [page.page_number for page in pages] != list(range(1, paper.page_count + 1))):
            return "canonical_records"
        by_page = {page.page_number: page for page in pages}
        ordinals = {}
        for chunk in chunks:
            ordinal = ordinals.get(chunk.page_number, 0)
            identity = f"{paper_id}:{library.settings.fingerprint}:{chunk.page_number}:{ordinal}"
            if (chunk.paper_id != paper_id or chunk.pipeline_version != library.settings.fingerprint
                    or chunk.chunk_id != hashlib.sha256(identity.encode()).hexdigest()
                    or chunk.chunk_ordinal != ordinal or not chunk.text.strip()
                    or chunk.filename != paper.filename or chunk.display_title != paper.display_title
                    or chunk.page_number not in by_page or chunk.text not in by_page[chunk.page_number].cleaned_text):
                return "canonical_records"
            ordinals[chunk.page_number] = ordinal + 1
        path = library._pdf_path(paper_id)
        if path.is_symlink():
            return "changed_pdf"
        if not path.is_file():
            return "missing_pdf"
        if path.stat().st_size != paper.size_bytes or hashlib.sha256(path.read_bytes()).hexdigest() != paper_id:
            return "changed_pdf"
    except (ValueError, TypeError, KeyError):
        return "canonical_records"
    return None


def recover_library(library):
    """Called under the library lock. Safe to repeat after interruption."""
    catalog = library.catalog
    catalog.check_integrity()
    with catalog.connection() as db:
        rows = db.execute("SELECT paper_id,status FROM papers ORDER BY paper_id").fetchall()
    # Validate identifiers before using them in filesystem paths or deleting data.
    if any(not re.fullmatch(r"[0-9a-f]{64}", row["paper_id"])
           or row["status"] not in {"ready", "processing", "deleting", "unavailable"} for row in rows):
        raise IngestionError("The catalog contains invalid identifiers or states. Restore a backup; no paper was removed.")
    events = []
    changed = False

    def changing():
        nonlocal changed
        if not changed:
            catalog.bump_revision()
            changed = True

    # Audit all committed sources before touching derived indexes.
    for row in rows:
        paper_id, status = row["paper_id"], row["status"]
        if status in {"processing", "deleting"}:
            changing()
            library._purge(paper_id)
            events.append("Finished cleanup of an interrupted paper operation.")
            continue
        reason = audit_paper(library, paper_id)
        previous = catalog.paper_issue(paper_id)
        if reason:
            if status != "unavailable" or previous != reason:
                changing()
                catalog.set_paper_issue(paper_id, reason)
            events.append("A paper was made unavailable: " + ISSUES[reason])
        elif status == "unavailable":
            changing()
            catalog.set_paper_issue(paper_id, None)
            events.append("Restored a paper after its original source records passed validation.")
    chunks = catalog.chunks()
    missing, extra = library.vectors.audit(chunks)
    if extra:
        changing()
        library.vectors.collection.delete(ids=extra)
        events.append("Removed vector entries without an active canonical source.")
    if missing:
        changing()
        # LlamaIndex remains the sole vector writer. Only damaged/missing chunks
        # are embedded; healthy restart never loads the model or parses PDFs.
        library.vectors.repair(missing, library.embeddings)
        remaining, extra = library.vectors.audit(chunks)
        if remaining or extra:
            raise IngestionError("Vector repair did not pass validation. Paper records were preserved; retry recovery.")
        events.append(f"Repaired {len(missing)} missing or inconsistent local vector entries.")
    library.snapshot_loaded = library.sparse.restore(chunks)
    if not library.snapshot_loaded:
        changing()
        events.append("Rebuilt the missing, stale or corrupt BM25 snapshot from saved chunks.")
    # The only abandoned files we remove are app-owned, hash-named PDFs. A
    # preserved unavailable paper still owns its PDF. Never traverse symlinks.
    owned = {row[0] for row in catalog.identities()}
    folder = library.settings.data_dir / "papers"
    if folder.exists():
        for path in folder.glob("*.pdf"):
            if re.fullmatch(r"[0-9a-f]{64}", path.stem) and path.stem not in owned:
                changing()
                path.unlink()
                events.append("Removed an abandoned application-owned PDF from an interrupted operation.")
    if changed:
        LOGGER.info("library_recovery_complete actions=%d", len(events))
    return events
