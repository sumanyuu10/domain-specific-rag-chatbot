"""Token-aware LlamaIndex chunking with deterministic, page-scoped IDs."""
import hashlib

from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import MetadataMode

from src.schemas import ChunkRecord, IngestionError


def prepare_chunks(documents, settings, embeddings):
    splitter = SentenceSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
        tokenizer=embeddings.tokenize, include_prev_next_rel=False,
    )
    nodes = IngestionPipeline(transformations=[splitter]).run(documents=documents)
    counts, chunks, accepted_nodes = {}, [], []
    for node in nodes:
        page = int(node.metadata["page_number"])
        ordinal = counts.get(page, 0)
        counts[page] = ordinal + 1
        identity = f'{node.metadata["paper_id"]}:{settings.fingerprint}:{page}:{ordinal}'
        node.id_ = hashlib.sha256(identity.encode()).hexdigest()
        node.metadata.update(chunk_id=node.id_, chunk_ordinal=ordinal, pipeline_version=settings.fingerprint)
        node.excluded_embed_metadata_keys = list(node.metadata)
        node.excluded_llm_metadata_keys = list(node.metadata)
        content = node.get_content(metadata_mode=MetadataMode.EMBED)
        if len(embeddings.tokenize(content, special_tokens=True)) > settings.embedding_max_tokens:
            raise IngestionError("A chunk exceeded MiniLM's input limit; no truncated embedding was accepted.")
        if content.strip():
            chunks.append(ChunkRecord(text=node.text, **node.metadata))
            accepted_nodes.append(node)
    if not chunks:
        raise IngestionError("Text extraction produced no usable chunks.")
    return accepted_nodes, chunks
