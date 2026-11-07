"""Strict labels bound to canonical chunks; draft labels are never ground truth."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas import ComparisonCategory


class EvaluationError(RuntimeError):
    """Safe evaluation diagnostic without private question/document content."""


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceLabel(Record):
    chunk_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(ge=1)
    passage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    category: ComparisonCategory | None = None


class Question(Record):
    question_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    question: str = Field(min_length=1, max_length=1000)
    kind: Literal["single_paper", "comparison", "unanswerable", "misleading"]
    task: Literal["qa", "comparison"] = "qa"
    split: Literal["dev", "heldout"]
    paper_ids: list[str] = Field(min_length=1, max_length=12)
    categories: list[ComparisonCategory] = Field(default_factory=list, max_length=5)
    answerable: bool
    expected_points: list[str] = Field(min_length=1, max_length=12)
    rationale: str = Field(min_length=1, max_length=2000)
    required_paper_ids: list[str] = Field(default_factory=list)
    relevant: list[EvidenceLabel] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent(self):
        if not self.question.strip() or any(not text.strip() for text in self.expected_points):
            raise ValueError("Blank question/expected point")
        for values in (self.paper_ids, self.categories, self.required_paper_ids):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate selection")
        if self.task == "comparison" and (len(self.paper_ids) < 2 or not self.categories):
            raise ValueError("Comparisons require multiple papers and categories")
        if self.task == "qa" and self.categories:
            raise ValueError("QA has no comparison categories")
        if self.kind == "comparison" and self.task != "comparison":
            raise ValueError("Comparison questions require the comparison workflow")
        keys = [(label.chunk_id, label.category) for label in self.relevant]
        if len(keys) != len(set(keys)) or not set(self.required_paper_ids) <= set(self.paper_ids):
            raise ValueError("Duplicate labels or invalid required paper")
        if any(label.paper_id not in self.paper_ids or (label.category not in self.categories if self.task == "comparison" else label.category is not None) for label in self.relevant):
            raise ValueError("Evidence outside question scope")
        if self.answerable != bool(self.relevant) or (not self.answerable and self.required_paper_ids):
            raise ValueError("Answerability and evidence disagree")
        if self.answerable and (not self.required_paper_ids or not set(self.required_paper_ids) <= {label.paper_id for label in self.relevant}):
            raise ValueError("Answerable records need labeled required-paper evidence")
        return self


class Dataset(Record):
    format_version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    purpose: Literal["literature_benchmark", "synthetic_smoke"]
    review_status: Literal["draft", "reviewed", "synthetic_fixture"]
    reviewer: str | None = None
    reviewed_at: str | None = None
    pipeline_fingerprint: str
    corpus_version: str
    paper_versions: dict[str, str]
    relevance_scope: Literal["pooled_labeled_evidence"] = "pooled_labeled_evidence"
    questions: list[Question] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def coherent(self):
        if len({question.question_id for question in self.questions}) != len(self.questions):
            raise ValueError("Duplicate question ID")
        if self.review_status == "reviewed":
            if not self.reviewer or not self.reviewer.strip() or not self.reviewed_at:
                raise ValueError("Human reviewer and review time required")
            datetime.fromisoformat(self.reviewed_at.replace("Z", "+00:00"))
        elif self.reviewer is not None or self.reviewed_at is not None:
            raise ValueError("Unreviewed records cannot claim a human reviewer")
        if (self.purpose == "synthetic_smoke") != (self.review_status == "synthetic_fixture"):
            raise ValueError("Synthetic fixtures must be explicitly distinguished")
        if any(not set(question.paper_ids) <= set(self.paper_versions) for question in self.questions):
            raise ValueError("Question selects a paper outside the frozen corpus")
        return self


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def label_for(chunk, category=None):
    return EvidenceLabel(chunk_id=chunk.chunk_id, paper_id=chunk.paper_id, page_number=chunk.page_number,
                         passage_sha256=hashlib.sha256(chunk.text.encode()).hexdigest(), category=category)


def freeze(library, questions, *, name, synthetic=False):
    with library.lock:
        library.ensure_available(EvaluationError)
        papers = library.catalog.papers()
        dataset = Dataset(
            name=name, purpose="synthetic_smoke" if synthetic else "literature_benchmark",
            review_status="synthetic_fixture" if synthetic else "draft",
            pipeline_fingerprint=library.settings.fingerprint, corpus_version=library.catalog.corpus_version(),
            paper_versions={paper.paper_id: library.catalog.paper_version(paper.paper_id) for paper in papers},
            questions=questions,
        )
        validate_dataset(library, dataset, allow_draft=True)
        return dataset


def validate_dataset(library, dataset, *, allow_draft=False):
    with library.lock:
        library.ensure_available(EvaluationError)
        if dataset.review_status == "draft" and not allow_draft:
            raise EvaluationError("Dataset labels await human review. Use --allow-draft only for an explicitly exploratory run.")
        if (dataset.pipeline_fingerprint != library.settings.fingerprint
                or dataset.corpus_version != library.catalog.corpus_version()
                or set(dataset.paper_versions) != {paper.paper_id for paper in library.catalog.papers()}
                or any(library.catalog.paper_version(key) != value for key, value in dataset.paper_versions.items())):
            raise EvaluationError("The frozen corpus changed. Revalidate/rebind the labels before evaluating; no stale labels were used.")
        for question in dataset.questions:
            for label in question.relevant:
                chunk = library.catalog.chunk(label.chunk_id)
                if chunk is None or label_for(chunk, label.category) != label:
                    raise EvaluationError("A labeled passage no longer matches its canonical paper/page/content.")
    return dataset


def load_dataset(path):
    try:
        path = Path(path)
        if path.stat().st_size > 4_000_000:
            raise EvaluationError("The evaluation dataset exceeds its size limit.")
        return Dataset.model_validate_json(path.read_text())
    except EvaluationError:
        raise
    except (OSError, ValueError, TypeError) as error:
        raise EvaluationError("The evaluation dataset could not be read or failed its schema checks.") from error


def save_dataset(dataset, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Do not overwrite a user's labels or mark generated drafts reviewed.
    with path.open("x") as stream:
        stream.write(dataset.model_dump_json(indent=2) + "\n")
