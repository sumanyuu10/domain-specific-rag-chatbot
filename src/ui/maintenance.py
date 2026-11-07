"""Explicit local recovery and unavailable-paper guidance; no model requests."""
from filelock import Timeout
import streamlit as st

from src.ingestion.recovery import ISSUES
from src.schemas import IngestionError
from src.ui.sources import invalidate_sources


def render_maintenance(library):
    with st.sidebar:
        st.subheader("Local library recovery")
        st.caption("Checks saved sources and repairs derived indexes. Healthy papers are reused. Repairing missing vectors may load the local MiniLM model; no passages are sent to Codex.")
        if library.recovery_events:
            with st.expander("Most recent recovery"):
                for event in library.recovery_events:
                    st.info(event)
        if st.button("Check and recover local library", on_click=invalidate_sources):
            invalidate_sources()
            try:
                with st.spinner("Checking local sources and indexes…"):
                    events = library.recover()
            except (IngestionError, Timeout) as error:
                st.error(str(error) if isinstance(error, IngestionError) else "The library is busy. Wait for the current operation and retry.")
            else:
                st.session_state.recovery_notice = "Local library checks passed." if not events else "Local library recovery completed."
                st.rerun()
        notice = st.session_state.pop("recovery_notice", None)
        if notice:
            st.success(notice)
        issues = library.catalog.issues()
        if issues:
            st.warning("Unavailable papers are excluded from search and comparisons. Their saved records remain local and count toward the paper limit.")
            by_id = {issue["paper_id"]: issue for issue in issues}
            selected = st.selectbox("Unavailable paper", list(by_id), format_func=lambda key: by_id[key]["filename"])
            st.warning(ISSUES.get(by_id[selected]["reason"], "Restore a backup or delete and upload this paper again."))
            confirmed = st.checkbox("Delete this unavailable paper and its remaining local records", key=f"unavailable_delete_{selected}")
            if st.button("Delete unavailable paper", disabled=not confirmed, on_click=invalidate_sources):
                invalidate_sources()
                try:
                    library.delete(selected)
                except (IngestionError, Timeout) as error:
                    st.error(str(error) if isinstance(error, IngestionError) else "The library is busy. Retry shortly.")
                else:
                    st.rerun()
