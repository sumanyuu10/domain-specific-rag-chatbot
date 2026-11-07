"""Source navigation and session invalidation, shared by chat and comparison."""
import streamlit as st


def invalidate_sources():
    st.session_state.paper_messages = []
    st.session_state.comparison_evidence = None
    st.session_state.comparison_result = None
    # Consent widgets may already have rendered. Reset them at the next run,
    # before widget construction, rather than mutating an active widget.
    st.session_state.source_reset_pending = True


def prepare_session(library):
    with library.lock:
        version = library.catalog.corpus_version()
    if st.session_state.get("source_reset_pending") or st.session_state.get("source_corpus") != version:
        invalidate_sources()
        st.session_state.allow_codex_excerpts = False
        st.session_state.allow_comparison_excerpts = False
        st.session_state.source_reset_pending = False
        st.session_state.source_corpus = version
    location = st.session_state.pop("source_location", None)
    if location:
        paper_id, page = location
        if paper_id in {paper.paper_id for paper in library.papers()}:
            st.session_state.inspect_paper = paper_id
            st.session_state.inspect_page = page


def source_navigation(paper_id, page_number, *, key):
    if st.button("Inspect this PDF page in the paper library", key=key):
        st.session_state.source_location = (paper_id, page_number)
        st.rerun()


def stale_source_error(message):
    invalidate_sources()
    st.session_state.source_error_notice = message
    st.rerun()
