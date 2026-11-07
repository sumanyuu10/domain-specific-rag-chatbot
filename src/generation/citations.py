"""Validate provenance against canonical records; never trust model-written labels."""
from src.schemas import AnswerDraft, RetrievalError, SourceCitation


class CitationValidationError(ValueError):
    pass


def source_map(context):
    return {f"S{number}": chunk for number, chunk in enumerate(context.snapshot.documents, 1)}


def validate_context(library, context):
    library.ensure_available(RetrievalError)
    snapshot = context.snapshot
    if library.catalog.corpus_version() != snapshot.corpus_version:
        raise RetrievalError("The paper library changed. Search again before generating an answer.")
    selected = set(snapshot.selected_paper_ids)
    ready = {paper.paper_id for paper in library.catalog.papers()}
    if not selected or not selected <= ready or len(context.documents) != len(snapshot.documents):
        raise RetrievalError("The selected evidence is no longer available. Search again.")
    for chunk, document in zip(snapshot.documents, context.documents):
        canonical = library.catalog.chunk(chunk.chunk_id)
        if (canonical != chunk or chunk.paper_id not in selected or document.page_content != chunk.text
                or document.metadata != chunk.metadata()):
            raise RetrievalError("Source content or metadata changed. Search again.")


def validate_answer(text: str, library, context):
    try:
        draft = AnswerDraft.model_validate_json(text)
    except (ValueError, TypeError) as error:
        raise CitationValidationError("Invalid structured answer") from error
    sources = source_map(context)
    used = []
    for claim in draft.claims:
        if any(source_id not in sources for source_id in claim.source_ids):
            raise CitationValidationError("Citation outside current retrieved evidence")
        claim.source_ids = list(dict.fromkeys(claim.source_ids))
        used.extend(claim.source_ids)
    validate_context(library, context)
    citations = []
    for source_id in dict.fromkeys(used):
        chunk = sources[source_id]
        citations.append(SourceCitation(
            source_id=source_id, chunk_id=chunk.chunk_id, paper_id=chunk.paper_id,
            filename=chunk.filename, display_title=chunk.display_title,
            page_number=chunk.page_number, passage=chunk.text,
        ))
    return draft, citations
