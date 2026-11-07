"""Local retrieval preview and explicitly permitted cited generation."""
from filelock import Timeout
import streamlit as st

from src.generation.chains import ResearchAssistant
from src.generation.llm import CodexIntegrationError
from src.schemas import RetrievalError
from src.ui.sources import source_navigation, stale_source_error


def render_sources(context, *, prefix="preview"):
    with st.expander("Retrieved passages", expanded=False):
        for number, chunk in enumerate(context.snapshot.documents, 1):
            st.text(f"S{number} · {chunk.filename} · PDF page {chunk.page_number}")
            st.text(chunk.text)
            source_navigation(chunk.paper_id, chunk.page_number, key=f"{prefix}_{number}")


def render_answer(answer, *, prefix="answer"):
    if answer.status == "answered":
        for claim in answer.claims:
            st.text(claim.text)
            st.caption("Sources: " + ", ".join(claim.source_ids))
    elif answer.status == "validation_failed":
        st.warning("The answer failed source or format validation and was withheld.")
    else:
        st.info("The retrieved passages do not contain enough evidence to answer this question.")
    for gap in answer.missing_information:
        st.text(gap)
    if answer.citations:
        with st.expander("Validated citations"):
            for citation in answer.citations:
                st.text(f"{citation.source_id} · {citation.filename} · PDF page {citation.page_number}")
                st.text(citation.passage)
                source_navigation(citation.paper_id, citation.page_number, key=f"{prefix}_{citation.source_id}")
        st.caption("Source checks validate traceability. Review the passage to check whether it supports the claim.")
    st.caption(f"Retrieval: {answer.retrieval_ms} ms · Answer generation/validation: {answer.total_ms} ms")


def render_chat(library, *, assistant_factory=None):
    st.subheader("Ask your selected papers")
    selected = sorted(st.session_state.get("selected_papers", []))
    with library.lock:
        version = library.catalog.corpus_version()
    scope = (version, tuple(selected))
    if st.session_state.get("chat_scope") != scope:
        st.session_state.chat_scope = scope
        st.session_state.paper_messages = []
        st.session_state.allow_codex_excerpts = False
    if not selected:
        st.info("Select at least one paper above to search its content.")
        return
    assistant = (assistant_factory or ResearchAssistant)(library)
    st.caption("Search runs locally. Preview the passages before requesting an answer. Use the comparison panel below for a balanced multi-paper comparison.")
    permitted = st.checkbox(
        "Allow sending my question and retrieved passages to GPT-6.1 Sol through my signed-in Codex account",
        key="allow_codex_excerpts",
    )
    question = st.chat_input("Ask a question about the selected papers", max_chars=2000)
    if question:
        try:
            with st.spinner("Searching the selected papers locally…"):
                context = assistant.search(
                    question, selected,
                    recent_user_questions=[item["question"] for item in st.session_state.paper_messages],
                )
            st.session_state.paper_messages.append({"question": question, "context": context, "answer": None})
            st.session_state.paper_messages = st.session_state.paper_messages[-6:]
        except (RetrievalError, Timeout) as error:
            st.error(str(error) if isinstance(error, RetrievalError) else "The library is busy. Try again shortly.")
    for number, message in enumerate(st.session_state.paper_messages):
        with st.chat_message("user"):
            st.text(message["question"])
        with st.chat_message("assistant"):
            context = message["context"]
            render_sources(context, prefix=f"chat_preview_{number}")
            if message["answer"] is not None:
                render_answer(message["answer"], prefix=f"chat_answer_{number}")
            elif not context.documents:
                st.info("No usable passages were found in the selected papers. Try a more specific question.")
            elif number == len(st.session_state.paper_messages) - 1:
                if st.button("Generate cited answer", disabled=not permitted, key=f"generate_{number}"):
                    try:
                        with st.spinner("Generating and validating a cited answer…"):
                            message["answer"] = assistant.answer(context, allow_remote=permitted)
                    except (CodexIntegrationError, RetrievalError, Timeout) as error:
                        st.error(str(error) if not isinstance(error, Timeout) else "The library is busy. Search again shortly.")
                        if isinstance(error, RetrievalError):
                            stale_source_error(str(error))
                        st.info("The local passages remain available. No replacement model was used.")
                    else:
                        render_answer(message["answer"], prefix=f"chat_answer_{number}")
