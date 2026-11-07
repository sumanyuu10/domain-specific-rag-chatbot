"""Human claim review, separate from deterministic structural citation checks."""
from datetime import datetime

from pydantic import Field

from src.evaluation.dataset import EvaluationError, Record, digest
from src.evaluation.retrieval_metrics import describe
from src.evaluation.runner import MODES
from typing import Literal


class AtomicReview(Record):
    text: str = Field(min_length=1, max_length=5000)
    verdict: Literal["supported", "unsupported", "uncertain", "pending"] = "pending"
    citation_support: dict[str, Literal["supports", "does_not_support", "uncertain", "pending"]] = Field(default_factory=dict)


class ClaimReview(Record):
    claim_id: str
    atomic_coverage_confirmed: bool = False
    units: list[AtomicReview] = Field(default_factory=list, max_length=30)


class AnswerReview(Record):
    question_id: str
    mode: Literal["bm25", "vector", "hybrid"]
    answer_relevance: Literal["relevant", "partly_relevant", "irrelevant", "pending"] = "pending"
    claims: list[ClaimReview] = Field(default_factory=list)


class HumanReview(Record):
    run_id: str
    artifact_sha256: str
    reviewer: str | None = None
    reviewed_at: str | None = None
    answers: list[AnswerReview]


def validate_report(report):
    value = {key: item for key, item in report.items() if key != "artifact_sha256"}
    if report.get("artifact_sha256") != digest(value) or report.get("format_version") != 1:
        raise EvaluationError("The run artifact changed or has an unsupported format.")


def claims_for(row):
    result = row.get("answer")
    if result is None or row["generation_status"] not in {"generated", "cached"}:
        return []
    if row["task"] == "qa":
        return [(f"claim-{index}", item["text"], item["source_ids"]) for index, item in enumerate(result["claims"])]
    claims = [(f"cell-{index}", item["text"], item["source_ids"]) for index, item in enumerate(result["cells"]) if item["status"] == "supported"]
    claims.extend((f"relation-{index}", item["text"], item["source_ids"]) for index, item in enumerate(result["relationships"]))
    return claims


def review_template(report):
    validate_report(report)
    answers = []
    for row in report["rows"]:
        if row["answer"] is None or row["generation_status"] not in {"generated", "cached"}:
            continue
        claims = [ClaimReview(claim_id=key, units=[AtomicReview(
            text=text, citation_support={source: "pending" for source in source_ids},
        )]) for key, text, source_ids in claims_for(row)]
        answers.append(AnswerReview(question_id=row["question_id"], mode=row["mode"], claims=claims))
    return HumanReview(run_id=report["run_id"], artifact_sha256=report["artifact_sha256"], answers=answers)


def review_metrics(report, review):
    validate_report(report)
    if review.run_id != report["run_id"] or review.artifact_sha256 != report["artifact_sha256"]:
        raise EvaluationError("Review does not belong to this exact run artifact.")
    if not review.reviewer or not review.reviewer.strip() or not review.reviewed_at:
        raise EvaluationError("Record a human reviewer and review time before scoring semantic support.")
    try:
        datetime.fromisoformat(review.reviewed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvaluationError("The human review timestamp is invalid.") from error
    expected = {(row["question_id"], row["mode"]): row for row in report["rows"]
                if row["answer"] is not None and row["generation_status"] in {"generated", "cached"}}
    keys = [(item.question_id, item.mode) for item in review.answers]
    if len(keys) != len(set(keys)) or set(keys) != set(expected):
        raise EvaluationError("Review must cover every generated/cached answer exactly once.")
    totals = {mode: {"supported": 0, "unsupported": 0, "uncertain": 0, "pending": 0,
                     "citation_supported": 0, "citation_unsupported": 0, "citation_unassessed": 0,
                     "unconfirmed_parent_claims": 0, "parent_claims_total": 0, "answer_relevance": []} for mode in MODES}
    for answer in review.answers:
        row = expected[(answer.question_id, answer.mode)]
        parents = {key: set(sources) for key, _text, sources in claims_for(row)}
        if len({claim.claim_id for claim in answer.claims}) != len(answer.claims) or {claim.claim_id for claim in answer.claims} != set(parents):
            raise EvaluationError("Claim review does not cover the generated factual entries exactly once.")
        target = totals[answer.mode]
        relevance = {"relevant": 1.0, "partly_relevant": 0.5, "irrelevant": 0.0, "pending": None}[answer.answer_relevance]
        target["answer_relevance"].append(relevance)
        for claim in answer.claims:
            target["parent_claims_total"] += 1
            if not claim.atomic_coverage_confirmed or not claim.units:
                target["unconfirmed_parent_claims"] += 1
                continue
            for unit in claim.units:
                if not unit.text.strip() or set(unit.citation_support) != parents[claim.claim_id]:
                    raise EvaluationError("An atomic claim needs judgments for each original citation; foreign citations are invalid.")
                target[unit.verdict] += 1
                for verdict in unit.citation_support.values():
                    if verdict == "supports": target["citation_supported"] += 1
                    elif verdict == "does_not_support": target["citation_unsupported"] += 1
                    else: target["citation_unassessed"] += 1
    result = {}
    for mode, counts in totals.items():
        judged = counts["supported"] + counts["unsupported"]
        all_units = judged + counts["uncertain"] + counts["pending"]
        citations = counts["citation_supported"] + counts["citation_unsupported"]
        result[mode] = {**counts,
            "answer_relevance": describe(counts["answer_relevance"]),
            "faithfulness": counts["supported"] / judged if judged else None,
            "hallucination_rate": counts["unsupported"] / judged if judged else None,
            "atomic_review_coverage": judged / all_units if all_units else None,
            "parent_review_coverage": (counts["parent_claims_total"] - counts["unconfirmed_parent_claims"]) / counts["parent_claims_total"] if counts["parent_claims_total"] else None,
            "citation_support_correctness": counts["citation_supported"] / citations if citations else None,
            "assessed_factual_claims": judged, "assessed_citation_pairs": citations,
        }
    return {"run_id": review.run_id, "label_status": report["label_status"],
            "reviewer": review.reviewer, "reviewed_at": review.reviewed_at, "metrics": result}


def answer_checks(report):
    """Only structural citations/status-based abstention, never semantic judging."""
    validate_report(report)
    results = {}
    for mode in MODES:
        rows = [row for row in report["rows"] if row["mode"] == mode]
        valid, checked, correct_refusals, false_refusals, answerable_count, unanswerable_count, excluded = 0, 0, 0, 0, 0, 0, 0
        for row in rows:
            answer = row["answer"]
            if answer is None or row["generation_status"] not in {"generated", "cached"}:
                excluded += 1
                continue
            allowed = {key for unit in row["retrieval"]["units"] for key in unit["context_ids"]}
            citations = {citation["source_id"]: citation for citation in answer["citations"]}
            for _claim, _text, ids in claims_for(row):
                for source in ids:
                    checked += 1
                    valid += int(source in citations and citations[source]["chunk_id"] in allowed)
            refused = answer["status"] == "insufficient_evidence"
            if row["answerable"]:
                answerable_count += 1
                false_refusals += int(refused)
            else:
                unanswerable_count += 1
                correct_refusals += int(refused)
        results[mode] = {"citation_validity": valid / checked if checked else None,
                         "citation_pairs_checked": checked,
                         "correct_abstention_rate": correct_refusals / unanswerable_count if unanswerable_count else None,
                         "false_abstention_rate": false_refusals / answerable_count if answerable_count else None,
                         "answerable_assessed": answerable_count, "unanswerable_assessed": unanswerable_count,
                         "operational_or_not_generated_exclusions": excluded,
                         "faithfulness": None, "hallucination_rate": None, "answer_relevance": None}
    return results
