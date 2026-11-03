"""Explicit configuration for Codex generation and the separate local library."""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import hashlib
import json


MODEL = "gpt-6.1-sol"


@dataclass(frozen=True)
class Settings:
    model: str = MODEL
    timeout_seconds: float = 60.0
    runtime_dir: Path = Path(__file__).resolve().parents[1] / ".runtime"

    def __post_init__(self):
        if self.model != MODEL:
            raise ValueError(f"Only {MODEL} is authorized; model fallback is disabled.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Timeout must be a finite positive number.")

    @classmethod
    def from_environment(cls):
        return cls(timeout_seconds=float(os.getenv("RAG_CODEX_TIMEOUT_SECONDS", "60")))


@dataclass(frozen=True)
class IngestionSettings:
    """Local library settings, separate from the unchanged Codex settings."""

    data_dir: Path = Path(__file__).resolve().parents[1] / "data"
    max_papers: int = 12
    max_file_bytes: int = 25 * 1024 * 1024
    max_pages: int = 200
    chunk_size: int = 220
    chunk_overlap: int = 40
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    embedding_dimension: int = 384
    embedding_max_tokens: int = 256

    def __post_init__(self):
        object.__setattr__(self, "data_dir", Path(self.data_dir).expanduser().resolve())
        if not 1 <= self.max_papers <= 12:
            raise ValueError("A library must allow between 1 and 12 papers.")
        if self.max_file_bytes <= 0 or self.max_pages <= 0:
            raise ValueError("PDF size and page limits must be positive.")
        if not 0 <= self.chunk_overlap < self.chunk_size < self.embedding_max_tokens - 2:
            raise ValueError("Chunks must fit the embedding limit and exceed their overlap.")

    @classmethod
    def from_environment(cls):
        value = os.getenv("RAG_DATA_DIR")
        return cls(data_dir=Path(value)) if value else cls()

    @property
    def fingerprint(self) -> str:
        configuration = {
            "format": 1, "pdf_reader": "lines-v1", "cleaning": "conservative-v1",
            "chunk_size": self.chunk_size, "overlap": self.chunk_overlap,
            "model": self.embedding_model, "revision": self.embedding_revision,
            "dimension": self.embedding_dimension, "max_tokens": self.embedding_max_tokens,
            "normalized": True, "distance": "cosine", "sparse_tokenizer": "technical-v1",
        }
        return hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
