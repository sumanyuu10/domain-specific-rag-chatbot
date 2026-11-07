"""Comparison evidence preview, consent, tables and original PDF sources."""
from filelock import Timeout
import streamlit as st

from src.generation.comparison import ComparisonService
from src.retrieval.comparison import CATEGORY_QUERIES
from src.schemas import RetrievalError
from src.ui.sources import source_navigation, stale_source_error


def render_comparison_result(result, labels):
    if result.status in {"incomplete", "validation_failed"}:
        st.warning("The comparison was withheld because one or more requests failed. Validated cards remain available.")
    elif result.status == "insufficient_evidence":
        st.info("The retrieved passages did not support the requested comparison categories.")
    source_labels = {citation.source_id: f"C{number}" for number, citation in enumerate(result.citations, 1)}
    references = lambda ids: ", ".join(source_labels[source] for source in ids)
    if result.cells:
        rows = []
        for category in result.categories:
            row = {"Category": category.title()}
            for paper_id in result.selected_paper_ids:
                cell = next(cell for cell in result.cells if cell.paper_id == paper_id and cell.category == category)
                row[labels[paper_id]] = (
                    cell.text + " [" + references(cell.source_ids) + "]" if cell.status == "supported"
                    else "Not found in retrieved passages: " + cell.text
                )
            rows.append(row)
        st.dataframe(rows, hide_index=True, width="stretch")
    for kind, heading in (("agreement", "Supported agreements"), ("disagreement", "Supported disagreements"),
                          ("not_directly_comparable", "Comparison limits")):
        relations = [item for item in result.relationships if item.kind == kind]
        if relations:
            st.write(heading)
            for relation in relations:
                st.text(relation.text)
                st.caption("Sources: " + references(relation.source_ids))
    if result.result_comparability:
        with st.expander("Experimental comparability"):
            for assessment in result.result_comparability:
                st.text(" / ".join(labels[paper_id] for paper_id in assessment.paper_ids))
                st.text(assessment.status.replace("_", " ").capitalize() + ": " + assessment.reason)
    for failure in result.failures:
        paper = labels.get(failure.paper_id, "Synthesis")
        st.error(paper + ": " + failure.message)
    if result.cards:
        with st.expander("Validated paper cards"):
            for card in result.cards:
                st.text(labels[card.paper_id])
                for section in card.sections:
                    st.caption(section.category.title())
                    for entry in section.entries:
                        st.text(entry.text + " [" + references(entry.source_ids) + "]")
                        if entry.experiment is not None:
                            st.text(" · ".join(f"{field}: {value or 'not established'}" for field, value in entry.experiment.model_dump().items()))
                    if section.missing_information:
                        st.text("Gap in retrieved passages: " + section.missing_information)
    if result.citations:
        with st.expander("Comparison source passages"):
            for citation in result.citations:
                st.text(f"{source_labels[citation.source_id]} · {citation.filename} · PDF page {citation.page_number}")
                st.text(citation.passage)
                source_navigation(citation.paper_id, citation.page_number, key=f"comparison_source_{citation.source_id}")
    st.caption(
        f"Validated card cache reused for {len(result.cached_paper_ids)} papers. "
        "Citations establish traceability; inspect the passages for claim support."
    )


def render_comparison(library, *, service_factory=None):
    st.subheader("Compare selected papers")
    selected = sorted(st.session_state.get("selected_papers", []))
    with library.lock:
        version = library.catalog.corpus_version()
        papers = {paper.paper_id: paper for paper in library.catalog.papers()}
    if len(selected) < 2 or not set(selected) <= set(papers):
        st.session_state.comparison_scope = None
        st.session_state.comparison_evidence = None
        st.session_state.comparison_result = None
        st.session_state.allow_comparison_excerpts = False
        st.info("Select at least two currently indexed papers above to build a cited comparison.")
        return
    focus = st.text_input("Comparison focus (optional)", max_chars=1000, key="comparison_focus")
    categories = st.multiselect(
        "Comparison categories", options=list(CATEGORY_QUERIES), default=list(CATEGORY_QUERIES),
        format_func=str.title, key="comparison_categories",
    )
    scope = (version, tuple(selected), " ".join(focus.split()), tuple(categories))
    if st.session_state.get("comparison_scope") != scope:
        st.session_state.comparison_scope = scope
        st.session_state.comparison_evidence = None
        st.session_state.comparison_result = None
        st.session_state.allow_comparison_excerpts = False
    labels = {paper_id: f"P{number} · {papers[paper_id].filename}" for number, paper_id in enumerate(selected, 1)}
    service = (service_factory or ComparisonService)(library)
    st.caption("Each paper receives a separate evidence budget. Collect passages locally before generating cards and a comparison.")
    if st.button("Collect comparison evidence", disabled=not categories):
        try:
            with st.status("Collecting evidence from each selected paper", expanded=True) as status:
                def progress(_stage, paper_id, category):
                    st.text(labels[paper_id] + " · " + category.title())
                evidence = service.collect(focus, selected, categories, progress=progress)
                status.update(label="Comparison evidence collected", state="complete")
            st.session_state.comparison_evidence = evidence
            st.session_state.comparison_result = None
        except (RetrievalError, Timeout) as error:
            st.error(str(error) if isinstance(error, RetrievalError) else "The library is busy. Try again shortly.")
    evidence = st.session_state.get("comparison_evidence")
    if evidence is None:
        return
    with st.expander("Preview comparison passages"):
        for paper in evidence.papers:
            st.text(labels[paper.paper.paper_id])
            for category, context in paper.contexts.items():
                st.caption(category.title())
                if not context.documents:
                    st.text("No usable candidate passages.")
                for chunk in context.snapshot.documents:
                    st.text(f"{chunk.filename} · PDF page {chunk.page_number}")
                    st.text(chunk.text)
    permitted = st.checkbox(
        "Allow sending this comparison focus and the retrieved passages to GPT-6.1 Sol through my signed-in Codex account",
        key="allow_comparison_excerpts",
    )
    st.caption("Generation normally needs one card request per uncached paper plus one synthesis request. Failed requests have at most one retry or repair.")
    previous = st.session_state.get("comparison_result")
    button_label = "Retry failed comparison requests" if previous and previous.failures else "Generate comparison"
    if st.button(button_label, disabled=not permitted):
        try:
            with st.status("Generating validated paper cards and comparison", expanded=True) as status:
                def progress(stage, paper_id, _category):
                    st.text((labels[paper_id] + " · " if paper_id else "") + stage.replace("_", " "))
                result = service.compare(evidence, allow_remote=permitted, progress=progress)
                st.session_state.comparison_result = result
                status.update(label="Comparison complete" if not result.failures else "Comparison needs a retry",
                              state="complete" if not result.failures else "error")
        except (RetrievalError, Timeout) as error:
            st.error(str(error) if isinstance(error, RetrievalError) else "The library is busy. Collect evidence again.")
            st.session_state.comparison_evidence = None
            st.session_state.comparison_result = None
            stale_source_error(str(error) if isinstance(error, RetrievalError) else "The library is busy. Collect evidence again.")
        else:
            st.rerun()
    result = st.session_state.get("comparison_result")
    if result is not None:
        render_comparison_result(result, labels)
