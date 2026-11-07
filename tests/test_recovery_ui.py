"""Recovery/source navigation through the real Streamlit app with local fixtures."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from conftest import NoEmbeddings
from src.generation.chains import ResearchAssistant
from test_answer_chain import FakeGateway


def app_for(library, monkeypatch):
    monkeypatch.setenv("RAG_DATA_DIR", str(library.settings.data_dir))
    monkeypatch.setattr("src.ui.documents.get_library", lambda settings: library)
    monkeypatch.setattr("src.ui.chat.ResearchAssistant", lambda service: ResearchAssistant(service, gateway=FakeGateway()))
    return AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()


def test_source_button_opens_correct_paper_and_pdf_page(library, make_pdf, monkeypatch):
    paper = library.ingest(make_pdf(["Attention accuracy is 90 percent.", "The SyntheticQA dataset has 300 examples. Accuracy is 91.2 percent."]), "source.pdf").paper
    app = app_for(library, monkeypatch)
    app.multiselect(key="selected_papers").set_value([paper.paper_id]).run()
    app.chat_input[0].set_value("SyntheticQA dataset examples?").run()
    context = app.session_state['paper_messages'][0]['context']
    page = context.snapshot.documents[0].page_number
    next(button for button in app.button if button.label == "Inspect this PDF page in the paper library").click().run()
    assert not app.exception
    assert app.selectbox(key="inspect_paper").value == paper.paper_id
    assert app.selectbox(key="inspect_page").value == page
    assert len(app.session_state['paper_messages']) == 1


def test_recovery_clears_chat_comparison_and_consent(library, make_pdf, monkeypatch):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    app = app_for(library, monkeypatch)
    app.multiselect(key="selected_papers").set_value([paper.paper_id]).run()
    app.checkbox(key="allow_codex_excerpts").check().run()
    app.chat_input[0].set_value("accuracy?").run()
    assert app.session_state["paper_messages"]
    library.sparse.path.write_bytes(b"corrupt snapshot")
    library.embeddings = NoEmbeddings()
    click(app, "Check and recover local library")
    assert not app.exception and not app.session_state["paper_messages"]
    assert not app.session_state["allow_codex_excerpts"]
    assert app.session_state["comparison_evidence"] is None
    assert not app.session_state["allow_comparison_excerpts"]
    assert any("recovery completed" in item.value for item in app.success)


def test_unavailable_paper_has_restore_guidance_and_explicit_delete(library, make_pdf, monkeypatch):
    paper = library.ingest(make_pdf(), "missing.pdf").paper
    library._pdf_path(paper.paper_id).unlink()
    library.recover()
    app = app_for(library, monkeypatch)
    assert not app.exception
    assert any("original PDF is missing" in item.value for item in app.warning)
    app.checkbox(key=f"unavailable_delete_{paper.paper_id}").check().run()
    click(app, "Delete unavailable paper")
    assert not app.exception
    assert library.catalog.identities() == []


def test_failed_deletion_never_displays_old_chat_and_recovery_remains_accessible(library, make_pdf, monkeypatch):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    app = app_for(library, monkeypatch)
    app.multiselect(key="selected_papers").set_value([paper.paper_id]).run()
    app.chat_input[0].set_value("accuracy?").run()
    original = library.vectors.remove
    def broken(*args): raise OSError("PRIVATE storage failure")
    monkeypatch.setattr(library.vectors, "remove", broken)
    app.checkbox(key=f"delete_{paper.paper_id}").check().run()
    click(app, "Delete paper")
    assert not app.exception and not app.session_state["paper_messages"]
    assert any("needs recovery" in item.value for item in app.error)
    assert all("PRIVATE" not in item.value for item in app.error)
    monkeypatch.setattr(library.vectors, "remove", original)
    click(app, "Check and recover local library")
    assert not app.exception and not library.papers()
    assert not app.session_state["allow_codex_excerpts"]


def test_failed_recovery_clears_previously_visible_chat(library, make_pdf, monkeypatch):
    paper = library.ingest(make_pdf(), "paper.pdf").paper
    app = app_for(library, monkeypatch)
    app.multiselect(key="selected_papers").set_value([paper.paper_id]).run()
    app.checkbox(key="allow_codex_excerpts").check().run()
    app.chat_input[0].set_value("accuracy?").run()
    def broken(*args):
        library._needs_recovery = True
        from src.schemas import IngestionError
        raise IngestionError("Synthetic recovery failure; retry after checking storage.")
    monkeypatch.setattr(library, "recover", broken)
    click(app, "Check and recover local library")
    assert not app.exception and not app.session_state["paper_messages"]
    assert not app.session_state["allow_codex_excerpts"]
    assert not any("S1 ·" in item.value for item in app.text)
    assert any("Synthetic recovery failure" in item.value for item in app.error)
