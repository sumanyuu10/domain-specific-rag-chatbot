"""One page-aware LlamaIndex reader around local PyMuPDF extraction."""
import re
from dataclasses import dataclass

import pymupdf
from llama_index.core import Document
from llama_index.core.readers.base import BaseReader

from src.config import IngestionSettings
from src.ingestion.cleaning import clean_pages
from src.schemas import IngestionError, PageRecord


def ordered_text(page) -> tuple[str, bool]:
    """Read text lines by column when clear, respecting full-width separators.

    This heuristic cannot reconstruct every research layout; previews expose the
    actual text that will be indexed, and detected columns produce a warning.
    """
    # PyMuPDF can merge different columns into one block. Line bounding boxes
    # retain the distinction. Exclude image bytes from this extraction result.
    layout = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    blocks = []
    for block in layout["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                blocks.append((*line["bbox"], text))
    blocks.sort(key=lambda item: (item[1], item[0]))
    middle = page.rect.width / 2
    left = [b for b in blocks if b[2] < middle + 5]
    right = [b for b in blocks if b[0] > middle - 5 and b not in left]
    columns = bool(left and right and any(max(l[1], r[1]) < min(l[3], r[3]) for l in left for r in right))
    if not columns:
        return "\n\n".join(block[4].strip() for block in blocks), False
    spanning = [b for b in blocks if b not in left and b not in right]
    remaining = left + right
    ordered = []
    for separator in sorted(spanning, key=lambda b: (b[1], b[0])):
        before = [b for b in remaining if b[3] <= separator[1] + 2]
        for column in (left, right):
            ordered.extend(sorted((b for b in before if b in column), key=lambda b: b[1]))
        remaining = [b for b in remaining if b not in before]
        ordered.append(separator)
    for column in (left, right):
        ordered.extend(sorted((b for b in remaining if b in column), key=lambda b: b[1]))
    return "\n\n".join(block[4].strip() for block in ordered), True


@dataclass(frozen=True)
class PDFReadResult:
    title: str
    pages: list[PageRecord]
    documents: list[Document]


class ResearchPDFReader(BaseReader):
    def load_data(self, payload: bytes, **kwargs) -> list[Document]:
        """Preserve LlamaIndex's reader contract for other ingestion callers."""
        return self.read_pdf(payload, **kwargs).documents

    def read_pdf(self, payload: bytes, *, paper_id: str, filename: str, settings: IngestionSettings) -> PDFReadResult:
        """Also return originals/diagnostics for the local catalog and preview."""
        if not filename.casefold().endswith(".pdf"):
            raise IngestionError("Upload a PDF file with a .pdf extension.")
        if not payload or len(payload) > settings.max_file_bytes:
            raise IngestionError(f"PDFs must be nonempty and no larger than {settings.max_file_bytes // (1024 * 1024)} MB.")
        try:
            document = pymupdf.open(stream=payload, filetype="pdf")
        except Exception as error:
            raise IngestionError("This PDF is corrupt or cannot be opened.") from error
        with document:
            if document.needs_pass:
                raise IngestionError("Password-protected PDFs are unsupported. Upload an unlocked copy.")
            if not document.is_pdf or not 1 <= len(document) <= settings.max_pages:
                raise IngestionError(f"Upload a PDF containing 1–{settings.max_pages} pages.")
            title = (document.metadata or {}).get("title", "").strip()
            if not title or title.casefold() == "untitled":
                title = filename.rsplit(".", 1)[0]
            title = title[:300]
            originals, warnings = [], []
            for page in document:
                text, columns = ordered_text(page)
                originals.append(text)
                notices = []
                if columns:
                    notices.append("Multiple columns detected; check the extracted reading order.")
                if len(re.sub(r"\W", "", text)) < 20:
                    notices.append("Little selectable text; scans and image-only content are not indexed.")
                if page.get_images():
                    notices.append("Images and figures are not interpreted.")
                warnings.append(notices)
        cleaned = clean_pages(originals)
        if sum(char.isalpha() for text in cleaned for char in text) < 40:
            raise IngestionError("No usable selectable text was found. Scanned PDFs require OCR, which is outside Phase 2.")
        pages = [PageRecord(
            paper_id=paper_id, page_number=number, original_text=original,
            cleaned_text=text, warnings=notices,
        ) for number, (original, text, notices) in enumerate(zip(originals, cleaned, warnings), 1)]
        documents = []
        for page in pages:
            if not page.cleaned_text:
                continue
            metadata = {
                "paper_id": paper_id, "filename": filename, "display_title": title,
                "page_number": page.page_number,
            }
            documents.append(Document(
                id_=f"{paper_id}:page:{page.page_number}", text=page.cleaned_text,
                metadata=metadata, excluded_embed_metadata_keys=list(metadata),
                excluded_llm_metadata_keys=list(metadata),
            ))
        return PDFReadResult(title=title, pages=pages, documents=documents)
