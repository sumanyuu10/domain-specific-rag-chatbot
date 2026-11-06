"""Actual Streamlit comparison consent, table/source display and invalidation."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.generation.comparison import ComparisonService
from comparison_helpers import FakeComparisonGateway


def prepare(library, make_pdf, monkeypatch, gateway):
    ids = [library.ingest(make_pdf(title=f"Study {number}"), f"paper-{number}.pdf").paper.paper_id for number in range(2)]
    monkeypatch.setenv("RAG_DATA_DIR", str(library.settings.data_dir))
    monkeypatch.setattr("src.ui.documents.get_library", lambda settings: library)
    monkeypatch.setattr("src.ui.comparison.ComparisonService", lambda service: ComparisonService(service, gateway=gateway))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.multiselect(key="selected_papers").set_value(ids).run()
    return app, ids


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()


def test_preview_is_local_and_generation_needs_comparison_consent(library, make_pdf, monkeypatch):
    gateway = FakeComparisonGateway()
    app, _ids = prepare(library, make_pdf, monkeypatch, gateway)
    click(app, "Collect comparison evidence")
    assert not app.exception and not gateway.calls
    assert next(button for button in app.button if button.label == "Generate comparison").disabled
    app.checkbox(key="allow_comparison_excerpts").check().run()
    click(app, "Generate comparison")
    assert not app.exception and len(gateway.calls) == 3
    assert len(app.dataframe) == 2
    assert app.session_state["comparison_result"].status == "completed"
    assert any("PDF page 1" in item.value and "C1" in item.value for item in app.text)


def test_focus_changes_clear_comparison_and_consent(library, make_pdf, monkeypatch):
    app, _ids = prepare(library, make_pdf, monkeypatch, FakeComparisonGateway())
    click(app, "Collect comparison evidence")
    app.checkbox(key="allow_comparison_excerpts").check().run()
    app.text_input(key="comparison_focus").set_value("Compare only the training data").run()
    assert not app.exception
    assert app.session_state["comparison_evidence"] is None
    assert app.session_state["comparison_result"] is None
    assert app.session_state["allow_comparison_excerpts"] is False


def test_paper_deletion_invalidates_displayed_comparison(library, make_pdf, monkeypatch):
    app, ids = prepare(library, make_pdf, monkeypatch, FakeComparisonGateway())
    click(app, "Collect comparison evidence")
    app.checkbox(key="allow_comparison_excerpts").check().run()
    click(app, "Generate comparison")
    library.delete(ids[0])
    app.run()
    assert not app.exception
    assert app.session_state["comparison_result"] is None
    assert app.session_state["allow_comparison_excerpts"] is False


def test_failed_requests_can_be_retried_without_regenerating_valid_cards(library, make_pdf, monkeypatch):
    failing = []
    def transform(kind, request, result):
        from src.generation.llm import CodexIntegrationError
        if kind == "card" and request["paper"]["filename"] == "paper-0.pdf" and failing:
            raise CodexIntegrationError("timeout", "Synthetic timeout")
        return result
    gateway = FakeComparisonGateway(transform)
    app, _ids = prepare(library, make_pdf, monkeypatch, gateway)
    failing.append(True)
    click(app, "Collect comparison evidence")
    app.checkbox(key="allow_comparison_excerpts").check().run()
    click(app, "Generate comparison")
    assert not app.exception and app.session_state["comparison_result"].status == "incomplete"
    failing.clear()
    click(app, "Retry failed comparison requests")
    assert not app.exception and app.session_state["comparison_result"].status == "completed"
    assert len(app.session_state["comparison_result"].cached_paper_ids) == 1


def test_source_change_during_generation_withholds_previous_comparison(library, make_pdf, monkeypatch):
    gateway = FakeComparisonGateway()
    app, ids = prepare(library, make_pdf, monkeypatch, gateway)
    click(app, "Collect comparison evidence")
    app.checkbox(key="allow_comparison_excerpts").check().run()
    click(app, "Generate comparison")
    assert app.session_state["comparison_result"].status == "completed"
    def transform(kind, request, result):
        library.delete(ids[0])
        return result
    gateway.transform = transform
    click(app, "Generate comparison")
    assert not app.exception
    assert app.session_state["comparison_result"] is None
    assert app.session_state["comparison_evidence"] is None
    assert any("library changed" in item.value for item in app.error)
