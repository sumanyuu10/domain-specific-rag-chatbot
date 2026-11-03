"""Small, explicit configuration for the approved Codex integration."""
from dataclasses import dataclass
import math
import os
from pathlib import Path


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
