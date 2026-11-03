"""Canonical page and chunk records shared by indexing and future retrieval."""
from pydantic import BaseModel, Field


class IngestionError(RuntimeError):
    """An actionable local document-processing error."""


class ConfigurationMismatch(IngestionError):
    """Existing vectors must not be reused with an incompatible pipeline."""


class PaperRecord(BaseModel):
    paper_id: str
    filename: str
    display_title: str
    status: str = "processing"
    size_bytes: int
    page_count: int
    chunk_count: int = 0
    uploaded_at: str
    warnings: list[str] = Field(default_factory=list)


class PageRecord(BaseModel):
    paper_id: str
    page_number: int
    original_text: str
    cleaned_text: str
    warnings: list[str] = Field(default_factory=list)


class ChunkRecord(BaseModel):
    chunk_id: str
    paper_id: str
    filename: str
    display_title: str
    page_number: int
    chunk_ordinal: int
    text: str
    pipeline_version: str

    def metadata(self) -> dict:
        return self.model_dump(exclude={"text"})


class IngestionResult(BaseModel):
    paper: PaperRecord
    duplicate: bool = False
