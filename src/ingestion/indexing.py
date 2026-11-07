"""The sole Chroma writer: LlamaIndex embeds and stores each node once."""
import math

import chromadb
from chromadb.config import Settings as ChromaSettings
from llama_index.core.ingestion import IngestionPipeline
from llama_index.vector_stores.chroma import ChromaVectorStore


class VectorIndex:
    def __init__(self, settings):
        self.client = chromadb.PersistentClient(
            path=str(settings.data_dir / "chroma"),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="papers_" + settings.fingerprint[:24], embedding_function=None,
            metadata={"pipeline_version": settings.fingerprint},
            configuration={"hnsw": {"space": "cosine"}},
        )
        self.store = ChromaVectorStore(chroma_collection=self.collection)

    def add(self, nodes, embeddings):
        IngestionPipeline(transformations=[embeddings.model], vector_store=self.store).run(nodes=nodes)

    def remove(self, paper_id, chunk_ids=()):
        # Canonical IDs also remove records whose vector metadata was damaged.
        if chunk_ids:
            self.collection.delete(ids=list(chunk_ids))
        self.collection.delete(where={"paper_id": paper_id})

    def close(self):
        close = getattr(self.client, "close", None)
        if close:
            close()

    def audit(self, chunks):
        """Compare documents, source metadata and vector shape to canonical rows."""
        expected = {chunk.chunk_id: chunk for chunk in chunks}
        seen, damaged, extra = set(), [], []
        # Limit memory when examining a twelve-paper collection.
        for offset in range(0, self.collection.count(), 256):
            batch = self.collection.get(limit=256, offset=offset, include=["documents", "metadatas", "embeddings"])
            for index, chunk_id in enumerate(batch["ids"]):
                chunk = expected.get(chunk_id)
                seen.add(chunk_id)
                if chunk is None:
                    extra.append(chunk_id)
                    continue
                metadata = batch["metadatas"][index] or {}
                vector = batch["embeddings"][index]
                if (batch["documents"][index] != chunk.text
                        or any(metadata.get(key) != value for key, value in chunk.metadata().items())
                        or vector is None or len(vector) != 384
                        or not all(math.isfinite(float(value)) for value in vector)
                        or not math.isclose(sum(float(value) ** 2 for value in vector), 1, abs_tol=.01)):
                    damaged.append(chunk)
        damaged.extend(chunk for key, chunk in expected.items() if key not in seen)
        return damaged, extra

    def repair(self, chunks, embeddings):
        from llama_index.core.schema import TextNode
        nodes = []
        for chunk in chunks:
            metadata = chunk.metadata()
            nodes.append(TextNode(
                id_=chunk.chunk_id, text=chunk.text, metadata=metadata,
                excluded_embed_metadata_keys=list(metadata), excluded_llm_metadata_keys=list(metadata),
            ))
        # The pinned LlamaIndex store uses Chroma add(), which keeps existing
        # IDs. Remove only the damaged derived entries before re-adding them.
        # If interrupted, canonical records remain and the next check retries.
        self.collection.delete(ids=[chunk.chunk_id for chunk in chunks])
        self.add(nodes, embeddings)
