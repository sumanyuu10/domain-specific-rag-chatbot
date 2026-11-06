"""Canonical page and chunk records shared by indexing and future retrieval."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class RetrievalError(RuntimeError):
    """An invalid query, stale selection or unavailable local index."""


class RetrievalResult(BaseModel):
    question: str
    selected_paper_ids: list[str]
    corpus_version: str
    documents: list[ChunkRecord]
    sparse_ids: list[str]
    dense_ids: list[str]
    latency_ms: int


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] = Field(min_length=1, max_length=8)


class AnswerDraft(BaseModel):
    """Model output contains claims and IDs, never authoritative source labels."""
    model_config = ConfigDict(extra="forbid")
    status: Literal["answered", "insufficient_evidence"]
    claims: list[Claim] = Field(max_length=12)
    missing_information: list[str] = Field(max_length=8)

    @model_validator(mode="after")
    def coherent_answer(self):
        if self.status == "answered" and not self.claims:
            raise ValueError("An answered response needs cited claims.")
        if self.status == "insufficient_evidence" and self.claims:
            raise ValueError("An insufficient-evidence response cannot include claims.")
        if self.status == "insufficient_evidence" and not self.missing_information:
            raise ValueError("Explain the missing evidence.")
        if any(not claim.text.strip() or any(not item.strip() for item in claim.source_ids) for claim in self.claims):
            raise ValueError("Claim text and source IDs must not be blank.")
        if any(not item.strip() or len(item) > 1000 for item in self.missing_information):
            raise ValueError("Missing-information notes must be nonempty and bounded.")
        return self


class SourceCitation(BaseModel):
    source_id: str
    chunk_id: str
    paper_id: str
    filename: str
    display_title: str
    page_number: int
    passage: str


class AnswerResult(BaseModel):
    question: str
    status: Literal["answered", "insufficient_evidence", "validation_failed"]
    claims: list[Claim]
    missing_information: list[str]
    citations: list[SourceCitation]
    selected_paper_ids: list[str]
    corpus_version: str
    model: str | None = None
    repaired: bool = False
    retrieval_ms: int = 0
    total_ms: int = 0
