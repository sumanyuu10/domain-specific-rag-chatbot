"""Deterministic model doubles for synthetic comparison integration tests."""
import json

from langchain_core.runnables import RunnableLambda
from langsmith.run_helpers import get_tracing_context

from src.config import MODEL
from src.generation.llm import GenerationResult


def card_payload(request):
    sections = []
    passages = {item["source_id"]: item["passage"] for item in request["passages"]}
    for category in request["categories"]:
        sources = category["source_ids"]
        entries = []
        if sources:
            entries = [{
                "text": passages[sources[0]][:500], "source_ids": [sources[0]],
                "experiment": {
                    "task": "classification", "dataset": "SyntheticQA", "split": "held-out test",
                    "metric": "accuracy percent", "value": "91.2", "settings": "fixed sample budget",
                } if category["category"] == "results" else None,
            }]
        sections.append({
            "category": category["category"], "status": "supported" if entries else "missing",
            "entries": entries, "missing_information": None if entries else "No supporting passages were retrieved.",
        })
    return {"sections": sections}


def synthesis_payload(request):
    cells = [{
        "paper_id": card["paper_id"], "category": section["category"],
        "entry_indices": [0] if section["entries"] else [],
    } for card in request["cards"] for section in card["sections"]]
    relationships = []
    if "methodology" in request["categories"] and len(request["cards"]) >= 2:
        cards = request["cards"][:2]
        sections = [next(section for section in card["sections"] if section["category"] == "methodology") for card in cards]
        if all(section["entries"] for section in sections):
            relationships.append({
                "kind": "agreement", "category": "methodology", "text": "Both supplied studies describe a transformer method.",
                "paper_ids": [card["paper_id"] for card in cards],
                "source_ids": [section["entries"][0]["source_ids"][0] for section in sections],
            })
    return {"cells": cells, "relationships": relationships}


class FakeComparisonGateway:
    def __init__(self, transform=None):
        self.calls = []
        self.transform = transform
        self.tracing = []

    def as_runnable(self, *, output_schema):
        kind = "card" if output_schema["title"] == "CardDraft" else "synthesis"
        def invoke(prompt):
            text = prompt.to_string()
            request = json.loads(text.split("Request JSON:\n", 1)[1].rsplit("\nValidation instruction:", 1)[0])
            self.calls.append((kind, request))
            self.tracing.append(get_tracing_context()["enabled"])
            result = card_payload(request) if kind == "card" else synthesis_payload(request)
            if self.transform:
                result = self.transform(kind, request, result)
            return GenerationResult(
                text=result if isinstance(result, str) else json.dumps(result), model=MODEL,
                authentication="chatgpt", status="completed", item_types=("agentMessage",), duration_ms=1,
            )
        return RunnableLambda(invoke)
