"""Document management, research chat and comparison entry point."""
import logging

from filelock import Timeout
import streamlit as st

from src.config import IngestionSettings
from src.ingestion.pipeline import PaperLibrary
from src.schemas import IngestionError
from src.ui.chat import render_chat
from src.ui.comparison import render_comparison
from src.ui.maintenance import render_maintenance
from src.ui.sources import invalidate_sources, prepare_session


@st.cache_resource(show_spinner=False)
def get_library(settings: IngestionSettings) -> PaperLibrary:
    # Healthy saved libraries keep the model lazy; damaged vectors may need repair.
    return PaperLibrary(settings)


def render_library(library: PaperLibrary):
    st.caption(
        "Local PDF library and hybrid research chat. Uploading and indexing stay local. "
        "Answer generation sends only the question and retrieved passages when you permit it below."
    )
    st.write(
        "Upload up to 12 selectable-text research PDFs, at most 25 MB and 200 pages "
        "each. The first upload downloads the public MiniLM model; embeddings run on your CPU."
    )
    files = st.file_uploader("Research papers", type=["pdf"], accept_multiple_files=True)
    if st.button("Index uploaded papers", disabled=not files):
        if len(files) > library.settings.max_papers:
            st.error(f"Select at most {library.settings.max_papers} files per batch.")
        else:
            with st.status("Processing uploaded PDFs", expanded=True) as status:
                failed = False
                for uploaded in files:
                    st.write(uploaded.name)
                    try:
                        result = library.ingest(uploaded.getvalue(), uploaded.name, progress=st.write)
                        if result.duplicate:
                            st.info(f"Already indexed: {result.paper.filename}")
                        else:
                            st.success(f"Indexed {result.paper.filename}: {result.paper.chunk_count} chunks.")
                    except (IngestionError, Timeout) as error:
                        failed = True
                        st.error(str(error) if isinstance(error, IngestionError) else "The library is busy. Retry shortly.")
                status.update(label="Finished with errors" if failed else "Indexing complete", state="error" if failed else "complete")

    library.ensure_available()
    papers = library.papers()
    st.subheader(f"Paper library ({len(papers)}/{library.settings.max_papers})")
    by_id = {paper.paper_id: paper for paper in papers}
    # Keep only live IDs even after deleting the final paper.
    st.session_state.selected_papers = [
        item for item in st.session_state.get("selected_papers", []) if item in by_id
    ]
    if not papers:
        st.info("Upload a paper to create your first local index.")
        return
    st.dataframe([{
        "Paper": paper.display_title, "File": paper.filename,
        "Pages": paper.page_count, "Chunks": paper.chunk_count,
    } for paper in papers], hide_index=True, width="stretch")
    st.multiselect(
        "Select papers for questions and comparisons", options=list(by_id),
        format_func=lambda item: by_id[item].filename, key="selected_papers",
    )
    selected = st.selectbox(
        "Inspect a paper", options=list(by_id), format_func=lambda item: by_id[item].filename, key="inspect_paper",
    )
    paper = by_id[selected]
    if paper.warnings:
        with st.expander("Extraction warnings"):
            for warning in paper.warnings:
                st.write(warning)
    pages = library.pages(selected)
    if pages:
        valid_pages = [page.page_number for page in pages]
        if st.session_state.get("inspect_page") not in valid_pages:
            st.session_state.inspect_page = valid_pages[0]
        page_number = st.selectbox("PDF page number", options=valid_pages, key="inspect_page")
        page = next(page for page in pages if page.page_number == page_number)
        st.caption("Page numbers refer to PDF file positions, starting at 1; printed labels may differ.")
        original, cleaned = st.tabs(["Original extracted text", "Cleaned indexed text"])
        with original:
            st.text(page.original_text or "No selectable text on this page.")
        with cleaned:
            st.text(page.cleaned_text or "No indexed text on this page.")
    confirmed = st.checkbox("Delete this paper and its local PDF, pages, chunks, vectors, and BM25 entries", key=f"delete_{selected}")
    if st.button("Delete paper", disabled=not confirmed, on_click=invalidate_sources):
        invalidate_sources()
        try:
            library.delete(selected)
        except (IngestionError, Timeout) as error:
            st.error(str(error) if isinstance(error, IngestionError) else "The library is busy. Retry shortly.")
        else:
            st.rerun()


def main():
    st.set_page_config(page_title="Research paper library", layout="wide")
    st.title("AI & Computer Science Research Assistant")
    library = None
    try:
        library = get_library(IngestionSettings.from_environment())
        library.ensure_available()
        prepare_session(library)
        notice = st.session_state.pop("source_error_notice", None)
        if notice:
            st.error(notice)
        render_library(library)
        library.ensure_available()
        st.divider()
        render_chat(library)
        st.divider()
        render_comparison(library)
    except IngestionError as error:
        invalidate_sources()
        st.error(str(error))
    except Timeout:
        st.error("The local library is busy. Wait for the current upload or deletion, then reload.")
    except Exception:
        invalidate_sources()
        # Never expose document text or private paths in browser tracebacks/logs.
        logging.getLogger(__name__).error("Local library operation failed; no document content logged.")
        st.error("The local library could not be opened or updated. Check disk space and folder permissions, then restart.")

    finally:
        if library is not None:
            try:
                render_maintenance(library)
            except Exception:
                logging.getLogger(__name__).error("library_maintenance_unavailable")
                st.sidebar.error("Recovery controls could not load. Check storage permissions or restore a backup, then restart.")
        else:
            if st.sidebar.button("Retry opening local library"):
                get_library.clear()
                st.rerun()
