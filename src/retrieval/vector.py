"""Read the existing Chroma collection with explicit local query embeddings."""
import math

from src.schemas import RetrievalError


def search(collection, embeddings, question: str, selected_paper_ids: set[str], k: int):
    if not selected_paper_ids or k <= 0:
        return []
    try:
        if len(embeddings.tokenize(question, special_tokens=True)) > 256:
            raise RetrievalError("The question exceeds MiniLM's 256-token input limit. Shorten it and search again.")
        vector = embeddings.model.get_query_embedding(question)
        result = collection.query(
            query_embeddings=[vector], n_results=k,
            where={"paper_id": {"$in": sorted(selected_paper_ids)}}, include=["distances"],
        )
        return [(chunk_id, 1.0 - float(distance)) for chunk_id, distance in zip(
            result["ids"][0], result["distances"][0],
        ) if math.isfinite(float(distance))]
    except RetrievalError:
        raise
    except Exception as error:
        raise RetrievalError("Local semantic retrieval failed. Check the cached MiniLM model and local index.") from error
