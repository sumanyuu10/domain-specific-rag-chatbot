"""Run the Streamlit app without a browser or hosted model."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.ui.documents import get_library


def test_empty_app_boots_without_loading_embedding_model(settings, monkeypatch):
    monkeypatch.setenv("RAG_DATA_DIR", str(settings.data_dir))
    get_library.clear()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "AI & Computer Science Research Assistant"
    assert app.button[0].disabled
    assert any("Upload a paper" in item.value for item in app.info)
    assert "model" not in get_library(settings).embeddings.__dict__
    get_library(settings).close()
    get_library.clear()


def test_app_shows_pages_selection_and_deletion(library, make_pdf, monkeypatch):
    paper = library.ingest(make_pdf(), "synthetic.pdf").paper
    monkeypatch.setenv("RAG_DATA_DIR", str(library.settings.data_dir))
    # Use the real prepared indexes, injecting only the already-created service.
    monkeypatch.setattr("src.ui.documents.get_library", lambda settings: library)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert len(app.text) == 2
    assert "91.2" in app.text[1].value
    app.multiselect[0].set_value([paper.paper_id]).run()
    assert app.session_state["selected_papers"] == [paper.paper_id]
    app.checkbox[0].check().run()
    app.button[1].click().run()
    assert not app.exception
    assert library.papers() == []
    assert library.vectors.collection.count() == 0
    assert app.session_state["selected_papers"] == []


def test_upload_action_indexes_valid_files_and_reports_invalid_ones(library, make_pdf, monkeypatch):
    from io import BytesIO
    valid = BytesIO(make_pdf())
    valid.name = "valid.pdf"
    invalid = BytesIO(b"invalid PDF bytes")
    invalid.name = "invalid.pdf"
    monkeypatch.setenv("RAG_DATA_DIR", str(library.settings.data_dir))
    monkeypatch.setattr("src.ui.documents.get_library", lambda settings: library)
    # AppTest has no browser upload transport. Supply the same UploadedFile
    # interface, then exercise the actual button callback and indexing service.
    monkeypatch.setattr("src.ui.documents.st.file_uploader", lambda *args, **kwargs: [invalid, valid])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.button[0].click().run()
    assert not app.exception
    assert len(library.papers()) == 1
    assert library.papers()[0].filename == "valid.pdf"
    assert "corrupt" in app.error[0].value
    assert any("Indexed valid.pdf" in item.value for item in app.success)


def test_app_reports_configuration_error_without_traceback(settings, monkeypatch):
    monkeypatch.setenv("RAG_DATA_DIR", str(settings.data_dir))
    def unavailable(settings):
        from src.schemas import ConfigurationMismatch
        raise ConfigurationMismatch("This collection uses different chunking or embeddings.")
    monkeypatch.setattr("src.ui.documents.get_library", unavailable)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert "different chunking" in app.error[0].value
