"""Three-mode evaluation over existing services; inference is opt-in and capped."""
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import logging
import time
from uuid import uuid4

from langchain_core.runnables import RunnableLambda
from langsmith import tracing_context

from src.config import MODEL, ComparisonSettings, RetrievalSettings
from src.evaluation.artifacts import ResultCache, validate_result
from src.evaluation.dataset import EvaluationError, digest, validate_dataset
from src.evaluation.retrieval_metrics import describe, ranked_metrics
from src.generation.chains import ResearchAssistant
from src.generation.comparison import ComparisonService, FATAL_CODES
from src.generation.isolation import EvidenceGateway
from src.generation.llm import CodexIntegrationError
from src.generation.prompts import ANSWER_PROMPT, CARD_PROMPT, SYNTHESIS_PROMPT, PROMPT_VERSION, CARD_PROMPT_VERSION, SYNTHESIS_PROMPT_VERSION
from src.retrieval.hybrid import reciprocal_rank_fusion
from src.schemas import RetrievalError, AnswerDraft, CardDraft, ComparisonDraft

MODES = ("bm25", "vector", "hybrid")
LOGGER = logging.getLogger(__name__)


class BudgetExceeded(EvaluationError):
    pass


class MeteredGateway:
    def __init__(self, gateway, maximum):
        self.gateway, self.maximum, self.calls = gateway, maximum, 0

    def as_runnable(self, *, output_schema):
        runnable = self.gateway.as_runnable(output_schema=output_schema)
        def invoke(prompt):
            if self.calls >= self.maximum:
                raise BudgetExceeded("The explicit model-request budget was exhausted.")
            self.calls += 1
            return runnable.invoke(prompt)
        return RunnableLambda(invoke, name="budgeted_evaluation_codex")


def ranked_ids(snapshot, mode, constant):
    if mode == "bm25": return list(dict.fromkeys(snapshot.sparse_ids))
    if mode == "vector": return list(dict.fromkeys(snapshot.dense_ids))
    return reciprocal_rank_fusion(snapshot.sparse_ids, snapshot.dense_ids, constant=constant)


def retrieval_record(question, evidence, mode, constant):
    if question.task == "qa":
        units = [(None, None, evidence)]
    else:
        units = [(paper.paper.paper_id, category, context) for paper in evidence.papers
                 for category, context in paper.contexts.items()]
    records, hits, selected_count, relevant_count = [], set(), 0, 0
    available = {}
    for paper_id, category, context in units:
        labels = [label for label in question.relevant if label.category == category and (paper_id is None or label.paper_id == paper_id)]
        gold = {label.chunk_id for label in labels}
        order = ranked_ids(context.snapshot, mode, constant)
        selected = context.snapshot.documents
        selected_ids = {chunk.chunk_id for chunk in selected}
        hit_ids = selected_ids & gold
        hits.update((label.chunk_id, category) for label in labels if label.chunk_id in hit_ids)
        available.update({chunk.chunk_id: chunk for chunk in selected})
        selected_count += len(selected_ids)
        relevant_count += len(gold)
        records.append({
            "paper_id": paper_id, "category": category, "ranked_ids": order,
            "context_ids": [chunk.chunk_id for chunk in selected],
            "at_k": {str(k): ranked_metrics(order, gold, k=k) for k in (5, 10)},
        })
    required = set(question.required_paper_ids)
    coverage = len({available[key].paper_id for key, _category in hits} & required) / len(required) if required else None
    return {
        "units": records,
        "at_k": {str(k): {metric: describe([unit["at_k"][str(k)][metric] for unit in records])["mean"]
                           for metric in ("precision", "recall", "reciprocal_rank")} for k in (5, 10)},
        "context": {"precision": len(hits) / selected_count if selected_count and relevant_count else (0.0 if relevant_count else None),
                    "recall": len(hits) / relevant_count if relevant_count else None,
                    "required_paper_coverage": coverage, "selected_count": selected_count, "labeled_hits": len(hits)},
    }


def summarize(rows):
    summary = {}
    for mode in MODES:
        all_rows = [row for row in rows if row["mode"] == mode]
        completed = [row for row in all_rows if row.get("retrieval") is not None]
        values = {
            f"{metric}_at_{k}": describe([row["retrieval"]["at_k"][str(k)][metric] for row in completed])
            for k in (5, 10) for metric in ("precision", "recall", "reciprocal_rank")
        }
        values.update({f"context_{metric}": describe([row["retrieval"]["context"][metric] for row in completed])
                       for metric in ("precision", "recall", "required_paper_coverage")})
        values.update({"cases": len(all_rows), "retrieval_failures": sum(row.get("retrieval") is None for row in all_rows),
                       "generation_failures": sum(row["generation_status"] == "failed" for row in all_rows),
                       "generation_budget_exclusions": sum(row["generation_status"] == "budget_exhausted" for row in all_rows),
                       "retrieval_ms": describe([row["retrieval_ms"] for row in completed]),
                       "fresh_generation_ms": describe([row["generation_ms"] for row in all_rows if row["generation_status"] == "generated"]),
                       "case_ms": describe([row["case_ms"] for row in all_rows]),
                       "cache_hits": sum(row["generation_status"] == "cached" for row in all_rows)})
        summary[mode] = values
    return summary


class EvaluationRunner:
    def __init__(self, library, *, gateway=None, retrieval_settings=None, comparison_settings=None):
        self.library = library
        self.gateway = gateway
        self.retrieval_settings = retrieval_settings or RetrievalSettings()
        self.comparison_settings = comparison_settings or ComparisonSettings()

    def run(self, dataset, *, allow_draft=False, generate=False, allow_remote=False,
            max_model_requests=0, split="all", warmup=True):
        if split not in {"all", "dev", "heldout"}:
            raise EvaluationError("Unknown evaluation split.")
        if type(max_model_requests) is not int or max_model_requests < 0 or max_model_requests > 1000:
            raise EvaluationError("Choose an integer model-request cap between zero and 1000.")
        if generate and not allow_remote:
            raise EvaluationError("Generation requires explicit --allow-remote consent for the question and retrieved excerpts.")
        validate_dataset(self.library, dataset, allow_draft=allow_draft)
        questions = [question for question in dataset.questions if split == "all" or question.split == split]
        if not questions:
            raise EvaluationError("The chosen split contains no questions.")
        metered = MeteredGateway(self.gateway or EvidenceGateway(), max_model_requests)
        assistant = ResearchAssistant(self.library, gateway=metered, settings=self.retrieval_settings)
        comparison = ComparisonService(self.library, gateway=metered, settings=self.comparison_settings)
        prompt_identity = digest({"versions": [PROMPT_VERSION, CARD_PROMPT_VERSION, SYNTHESIS_PROMPT_VERSION],
                                  "templates": [prompt.model_dump(mode="json") for prompt in (ANSWER_PROMPT, CARD_PROMPT, SYNTHESIS_PROMPT)]})
        identity = {"dataset_sha256": digest(dataset.model_dump(mode="json")), "model": MODEL,
                    "sdk_version": version("openai-codex"), "prompt_sha256": prompt_identity,
                    "evaluation_protocol_version": 1,
                    "output_schema_sha256": digest([schema.model_json_schema() for schema in (AnswerDraft, CardDraft, ComparisonDraft)]),
                    "retrieval_settings": asdict(self.retrieval_settings), "comparison_settings": asdict(self.comparison_settings)}
        cache = ResultCache(self.library.settings.data_dir / "evaluation" / "answer_cache")
        rows = []
        def retrieve(question, mode):
            if question.task == "qa":
                return assistant.search(question.question, question.paper_ids, mode=mode)
            return comparison.collect(question.question, question.paper_ids, question.categories, mode=mode)
        warm_start = time.perf_counter()
        if warmup:
            for mode in MODES:
                retrieve(questions[0], mode)  # Local only; separate cold/warm-up cost.
        warmup_ms = round((time.perf_counter() - warm_start) * 1000)
        halt_generation = False
        with tracing_context(enabled=False, parent=False, replicas=[]):
            for question in questions:
                for mode in MODES:
                    validate_dataset(self.library, dataset, allow_draft=allow_draft)
                    started = time.perf_counter()
                    row = {"question_id": question.question_id, "mode": mode, "split": question.split,
                           "kind": question.kind, "task": question.task, "answerable": question.answerable,
                           "retrieval": None, "retrieval_ms": None, "generation_ms": None,
                           "generation_status": "not_requested", "answer": None, "error_code": None}
                    try:
                        evidence = retrieve(question, mode)
                        row["retrieval_ms"] = round((time.perf_counter() - started) * 1000)
                        constant = self.retrieval_settings.rrf_constant if question.task == "qa" else self.comparison_settings.rrf_constant
                        row["retrieval"] = retrieval_record(question, evidence, mode, constant)
                        if generate:
                            validator = lambda value: validate_result(self.library, question.task, evidence, value)
                            # Human label/review edits change the report identity, not
                            # the generation prompt. Reuse still-valid answers without
                            # paying to regenerate them just to score new labels.
                            cache_identity = {key: value for key, value in identity.items() if key != "dataset_sha256"}
                            key = digest({**cache_identity, "corpus_version": dataset.corpus_version,
                                          "question": {"text": question.question, "task": question.task,
                                                       "paper_ids": question.paper_ids, "categories": question.categories}, "mode": mode,
                                          "selected_context": [(unit["paper_id"], unit["category"], unit["context_ids"]) for unit in row["retrieval"]["units"]]})
                            generation_start = time.perf_counter()
                            result = cache.get(key, validator)
                            if result is not None:
                                row["generation_status"] = "cached"
                            elif halt_generation:
                                row["generation_status"] = "failed"
                                row["error_code"] = "not_attempted_after_access_failure"
                            else:
                                result = (assistant.answer(evidence, allow_remote=True) if question.task == "qa"
                                          else comparison.compare(evidence, allow_remote=True))
                                if result.status in {"validation_failed", "incomplete"}:
                                    row["generation_status"] = "failed"
                                    row["error_code"] = "invalid_or_incomplete_generation"
                                    if any(failure.code in FATAL_CODES for failure in getattr(result, "failures", [])):
                                        halt_generation = True
                                else:
                                    result = validator(result.model_dump(mode="json"))
                                    cache.put(key, result)
                                    row["generation_status"] = "generated"
                            row["generation_ms"] = round((time.perf_counter() - generation_start) * 1000)
                            if result is not None:
                                row["answer"] = result.model_dump(mode="json")
                    except BudgetExceeded:
                        row["generation_status"], row["error_code"] = "budget_exhausted", "model_request_cap"
                    except CodexIntegrationError as error:
                        row["generation_status"], row["error_code"] = "failed", error.code
                        if error.code in FATAL_CODES:
                            halt_generation = True
                    except RetrievalError:
                        row["error_code"] = "retrieval_or_source_changed"
                        if row["retrieval"] is not None:
                            row["generation_status"] = "failed"
                    except (OSError, ValueError, TypeError):
                        row["error_code"] = "local_artifact_or_validation_failed"
                        if row["retrieval"] is not None:
                            row["generation_status"] = "failed"
                    row["case_ms"] = round((time.perf_counter() - started) * 1000)
                    rows.append(row)
                    if row["error_code"]:
                        LOGGER.warning("evaluation_case_failed code=%s", row["error_code"])
        validate_dataset(self.library, dataset, allow_draft=allow_draft)
        report = {"format_version": 1, "run_id": uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(),
                  "dataset_name": dataset.name, "purpose": dataset.purpose, "label_status": dataset.review_status,
                  "relevance_scope": dataset.relevance_scope, "split": split, "identity": identity,
                  "generation_requested": generate, "application_model_requests": metered.calls,
                  "max_model_requests": max_model_requests, "warmup_ms": warmup_ms,
                  "rows": rows, "summary": summarize(rows)}
        # Keep held-out/development and task strata separate as well as aggregates.
        report["strata"] = {field: {value: summarize([row for row in rows if row[field] == value])
                                    for value in sorted({row[field] for row in rows})}
                            for field in ("split", "kind", "task")}
        report["artifact_sha256"] = digest(report)
        from src.evaluation.faithfulness import answer_checks
        report["answer_checks"] = answer_checks(report)
        report["artifact_sha256"] = digest({key: value for key, value in report.items() if key != "artifact_sha256"})
        return report
