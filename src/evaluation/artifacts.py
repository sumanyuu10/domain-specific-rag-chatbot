"""Private local artifacts, exclusive writes and canonical-checked result reuse."""
import itertools
import json
from pathlib import Path

from src.config import MODEL
from src.evaluation.dataset import EvaluationError, digest
from src.generation.citations import validate_answer, validate_context
from src.generation.comparison_validation import (
    canonical_citations, results_assessments, validate_card, validate_evidence, validate_synthesis,
)
from src.generation.prompts import CARD_PROMPT_VERSION
from src.schemas import AnswerResult, CellSelection, ComparisonResult


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Existing reports and human annotations are never overwritten.
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def read_json(path, *, max_bytes=20_000_000):
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise EvaluationError("Evaluation artifact exceeds its size limit.")
    return json.loads(path.read_text())


def validate_result(library, task, evidence, value):
    """Recheck cached provenance rather than treating summaries as original sources."""
    if task == "qa":
        result = AnswerResult.model_validate(value)
        validate_context(library, evidence)
        snapshot = evidence.snapshot
        if (result.question != snapshot.question or result.selected_paper_ids != snapshot.selected_paper_ids
                or result.corpus_version != snapshot.corpus_version or result.status == "validation_failed"
                or result.model not in (None, MODEL)
                or (result.model is None and (result.status != "insufficient_evidence" or evidence.documents))):
            raise ValueError("Cached answer identity/status mismatch")
        _, citations = validate_answer(json.dumps({
            "status": result.status, "claims": [claim.model_dump() for claim in result.claims],
            "missing_information": result.missing_information,
        }), library, evidence)
        if result.citations != citations:
            raise ValueError("Cached answer sources mismatch")
        return result
    result = ComparisonResult.model_validate(value)
    validate_evidence(library, evidence)
    if (result.status not in {"completed", "insufficient_evidence"} or result.failures
            or result.model != MODEL or result.question != evidence.question
            or result.categories != evidence.categories or result.corpus_version != evidence.corpus_version
            or result.selected_paper_ids != [paper.paper.paper_id for paper in evidence.papers]
            or {card.paper_id for card in result.cards} != set(result.selected_paper_ids)
            or len(result.cards) != len(result.selected_paper_ids)):
        raise ValueError("Cached comparison identity/status mismatch")
    selections = []
    for card in result.cards:
        paper = next(paper for paper in evidence.papers if paper.paper.paper_id == card.paper_id)
        validate_card(card, paper, evidence, model=MODEL, prompt_version=CARD_PROMPT_VERSION)
    for cell in result.cells:
        card = next(card for card in result.cards if card.paper_id == cell.paper_id)
        section = next(section for section in card.sections if section.category == cell.category)
        candidates = [()] if not section.entries else [indices for count in range(1, len(section.entries) + 1)
                                                       for indices in itertools.permutations(range(len(section.entries)), count)]
        match = None
        for indices in candidates:
            choice = CellSelection(paper_id=cell.paper_id, category=cell.category, entry_indices=list(indices))
            # materialize_cells expects the full grid, so compare this entry's
            # canonical text/IDs directly, then validate the complete grid below.
            entries = [section.entries[index] for index in indices]
            text = "\n".join(entry.text for entry in entries) if entries else section.missing_information
            ids = list(dict.fromkeys(source for entry in entries for source in entry.source_ids))
            if cell.text == text and cell.source_ids == ids and cell.status == section.status:
                match = choice
                break
        if match is None:
            raise ValueError("Cached table changed")
        selections.append(match)
    cells, relationships = validate_synthesis(json.dumps({
        "cells": [choice.model_dump() for choice in selections],
        "relationships": [item.model_dump() for item in result.relationships],
    }), result.cards, evidence)
    if (cells != result.cells or relationships != result.relationships or canonical_citations(result.cards, evidence) != result.citations
            or results_assessments(result.cards, evidence.categories) != result.result_comparability):
        raise ValueError("Cached comparison sources mismatch")
    return result


class ResultCache:
    def __init__(self, directory):
        self.directory = Path(directory)

    def get(self, key, validator):
        path = self.directory / (key + ".json")
        if not path.exists():
            return None
        try:
            envelope = read_json(path)
            if envelope["key"] != key or envelope["sha256"] != digest(envelope["result"]):
                raise ValueError("Cache digest mismatch")
            return validator(envelope["result"])
        except (ValueError, TypeError, KeyError, StopIteration):
            # App-owned invalid derived artifacts can be regenerated. Disk errors
            # are not hidden by silently spending model allowance instead.
            path.unlink()
            return None

    def put(self, key, result):
        path = self.directory / (key + ".json")
        if path.exists():
            return
        value = result.model_dump(mode="json")
        write_json(path, {"key": key, "sha256": digest(value), "result": value})
