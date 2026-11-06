"""LangChain reads canonical chunks; it never re-ingests the papers."""
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from src.schemas import RetrievalResult


@dataclass(frozen=True)
class RetrievedContext:
    snapshot: RetrievalResult
    documents: list[Document]

def as_runnable(service):
    """Carry canonical provenance alongside actual LangChain Documents."""
    def retrieve(request):
        result = service.retrieve(request["question"], request["paper_ids"], mode=request.get("mode", "hybrid"))
        documents = [Document(page_content=chunk.text, metadata=chunk.metadata()) for chunk in result.documents]
        return RetrievedContext(snapshot=result, documents=documents)
    return RunnableLambda(retrieve, name="selected_paper_hybrid_retriever")
