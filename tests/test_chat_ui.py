"""Streamlit search/consent/citation flow using the real local service."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.generation.chains import ResearchAssistant
from src.generation.llm import CodexIntegrationError
from test_answer_chain import FakeGateway


def prepare(library, make_pdf, monkeypatch, gateway):
    paper = library.ingest(make_pdf(), "evidence.pdf").paper
    monkeypatch.setenv("RAG_DATA_DIR", str(library.settings.data_dir))
    monkeypatch.setattr("src.ui.documents.get_library", lambda settings: library)
    monkeypatch.setattr("src.ui.chat.ResearchAssistant", lambda service: ResearchAssistant(service, gateway=gateway))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.multiselect[0].set_value([paper.paper_id]).run()
    return app, paper


def test_search_is_local_and_generation_requires_consent(library, make_pdf, monkeypatch):
    gateway = FakeGateway()
    app, paper = prepare(library, make_pdf, monkeypatch, gateway)
    app.chat_input[0].set_value("What accuracy was reported?").run()
    assert not app.exception and not gateway.prompts
    generate = next(button for button in app.button if button.label == "Generate cited answer")
    assert generate.disabled
    app.checkbox(key="allow_codex_excerpts").check().run()
    next(button for button in app.button if button.label == "Generate cited answer").click().run()
    assert not app.exception and len(gateway.prompts) == 1
    assert any("Accuracy was 91.2" in item.value for item in app.text)
    assert any("S1 · evidence.pdf · PDF page 1" in item.value for item in app.text)


def test_sdk_error_keeps_local_evidence_visible(library, make_pdf, monkeypatch):
    gateway = FakeGateway([CodexIntegrationError("authentication_required", "A Codex sign-in is required.")])
    app, _paper = prepare(library, make_pdf, monkeypatch, gateway)
    app.checkbox(key="allow_codex_excerpts").check().run()
    app.chat_input[0].set_value("What accuracy was reported?").run()
    next(button for button in app.button if button.label == "Generate cited answer").click().run()
    assert not app.exception
    assert any("sign-in" in item.value for item in app.error)
    assert any("91.2" in item.value for item in app.text)


def test_selection_change_clears_old_answers_and_consent(library, make_pdf, monkeypatch):
    gateway = FakeGateway()
    app, paper = prepare(library, make_pdf, monkeypatch, gateway)
    app.checkbox(key="allow_codex_excerpts").check().run()
    app.chat_input[0].set_value("accuracy?").run()
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert app.session_state["paper_messages"] == []
    assert app.session_state["allow_codex_excerpts"] is False


def test_library_deletion_invalidates_chat_evidence(library, make_pdf, monkeypatch):
    app, paper = prepare(library, make_pdf, monkeypatch, FakeGateway())
    app.chat_input[0].set_value("accuracy?").run()
    assert len(app.session_state["paper_messages"]) == 1
    library.delete(paper.paper_id)
    app.run()
    assert not app.exception
    assert app.session_state["paper_messages"] == []
