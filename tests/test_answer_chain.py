"""Actual LangChain composition, fake model responses, real canonical sources."""
import json

from langchain_core.runnables import RunnableLambda
from langsmith.run_helpers import get_tracing_context
import pytest

from src.config import MODEL
from src.generation.chains import ResearchAssistant
from src.generation.llm import CodexIntegrationError, GenerationResult
from src.schemas import RetrievalError


def valid_answer(source="S1"):
    return json.dumps({"status": "answered", "claims": [{"text": "Accuracy was 91.2 percent.", "source_ids": [source]}], "missing_information": []})


class FakeGateway:
    def __init__(self, answers=None, *, callback=None):
        self.answers = answers if answers is not None else [valid_answer()]
        self.prompts = []
        self.callback = callback
        self.tracing = []

    def as_runnable(self, *, output_schema):
        assert output_schema["additionalProperties"] is False
        def generate(prompt):
            self.tracing.append(get_tracing_context()["enabled"])
            self.prompts.append(prompt.to_string())
            if self.callback: self.callback()
            answer = self.answers[min(len(self.prompts) - 1, len(self.answers) - 1)]
            if isinstance(answer, Exception): raise answer
            return GenerationResult(text=answer, model=MODEL, authentication="chatgpt", status="completed", item_types=("agentMessage",), duration_ms=1)
        return RunnableLambda(generate)


@pytest.fixture
def prepared(library, make_pdf):
    paper = library.ingest(make_pdf(), "evidence.pdf").paper
    gateway = FakeGateway()
    assistant = ResearchAssistant(library, gateway=gateway)
    return assistant, assistant.search("What accuracy was reported?", [paper.paper_id]), gateway


def test_answer_has_canonical_paper_page_and_passage(prepared):
    assistant, context, gateway = prepared
    answer = assistant.answer(context, allow_remote=True)
    assert answer.status == "answered" and len(gateway.prompts) == 1
    citation = answer.citations[0]
    assert citation.filename == "evidence.pdf" and citation.page_number == 1
    assert citation.passage == context.documents[0].page_content
    assert citation.chunk_id == context.documents[0].metadata["chunk_id"]
    assert "untrusted data" in gateway.prompts[0]
    assert gateway.tracing == [False]


def test_remote_permission_is_required(prepared):
    assistant, context, gateway = prepared
    with pytest.raises(RetrievalError, match="Allow sending"):
        assistant.answer(context)
    assert not gateway.prompts


@pytest.mark.parametrize("bad", ["not JSON", valid_answer("S99"), json.dumps({"status": "answered", "claims": [], "missing_information": []})])
def test_invalid_output_gets_one_bounded_repair(prepared, bad):
    assistant, context, gateway = prepared
    gateway.answers = [bad, valid_answer()]
    answer = assistant.answer(context, allow_remote=True)
    assert answer.status == "answered" and answer.repaired
    assert len(gateway.prompts) == 2
    assert "previous output failed" in gateway.prompts[1]
    assert bad not in gateway.prompts[1]  # Invalid model output isn't new evidence.


def test_unrepairable_answer_is_withheld(prepared):
    assistant, context, gateway = prepared
    gateway.answers = [valid_answer("S99")]
    answer = assistant.answer(context, allow_remote=True)
    assert answer.status == "validation_failed"
    assert answer.claims == [] and answer.citations == [] and len(gateway.prompts) == 2


def test_model_acknowledges_missing_information(prepared):
    assistant, context, gateway = prepared
    gateway.answers = [json.dumps({"status": "insufficient_evidence", "claims": [], "missing_information": ["Carbon emissions were not supplied in the passages."]})]
    answer = assistant.answer(context, allow_remote=True)
    assert answer.status == "insufficient_evidence" and answer.citations == []
    assert len(gateway.prompts) == 1


def test_empty_local_retrieval_never_calls_llm(prepared):
    assistant, context, gateway = prepared
    empty = assistant.search("unfindableterm", context.snapshot.selected_paper_ids, mode="bm25")
    answer = assistant.answer(empty, allow_remote=True)
    assert answer.status == "insufficient_evidence" and not gateway.prompts


def test_sdk_failure_is_not_retried_or_replaced(prepared):
    assistant, context, gateway = prepared
    gateway.answers = [CodexIntegrationError("sdk_failure", "Codex unavailable")]
    with pytest.raises(CodexIntegrationError): assistant.answer(context, allow_remote=True)
    assert len(gateway.prompts) == 1


@pytest.mark.parametrize("when", ["before", "during"])
def test_deleted_evidence_cannot_be_used_for_an_answer(prepared, when):
    assistant, context, gateway = prepared
    delete = lambda: assistant.library.delete(context.snapshot.selected_paper_ids[0])
    if when == "before": delete()
    else: gateway.callback = delete
    with pytest.raises(RetrievalError, match="library changed"):
        assistant.answer(context, allow_remote=True)
    assert len(gateway.prompts) == (0 if when == "before" else 1)


def test_tampered_context_is_rejected_before_network(prepared):
    assistant, context, gateway = prepared
    context.documents[0].metadata["page_number"] = 999
    with pytest.raises(RetrievalError, match="metadata changed"):
        assistant.answer(context, allow_remote=True)
    assert not gateway.prompts


def test_inherited_tracing_is_disabled_for_private_evidence(prepared, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    assistant, context, gateway = prepared
    assistant.search("accuracy", context.snapshot.selected_paper_ids)
    assistant.answer(context, allow_remote=True)
    assert gateway.tracing == [False]


def test_model_cannot_supply_authoritative_quotations_or_paper_labels(prepared):
    assistant, context, gateway = prepared
    draft = json.loads(valid_answer())
    draft["citations"] = [{"paper": "invented.pdf", "page": 999, "passage": "fake"}]
    gateway.answers = [json.dumps(draft), valid_answer()]
    answer = assistant.answer(context, allow_remote=True)
    assert answer.repaired and answer.citations[0].filename == "evidence.pdf"
