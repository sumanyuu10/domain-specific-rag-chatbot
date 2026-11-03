"""The sole Chroma writer: LlamaIndex embeds and stores each node once."""
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

    def remove(self, paper_id):
        self.collection.delete(where={"paper_id": paper_id})

    def close(self):
        close = getattr(self.client, "close", None)
        if close:
            close()
