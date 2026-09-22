from dataclasses import dataclass
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.generation_service import generate_answer
from backend.services.hybrid_retrieval_service import hybrid_retrieve_chunks
from backend.services.llm.base import LLMClient
from backend.services.retrieval_service import RetrievedChunk


@dataclass(frozen=True)
class RAGResponse:
    answer: str
    sources: list[RetrievedChunk]


class RAGState(TypedDict, total=False):
    db: Session
    organization_id: int
    question: str
    embedding_service: EmbeddingService
    qdrant_repository: QdrantRepository
    llm_client: LLMClient
    retrieval_limit: int
    document_ids: list[int] | None
    retrieve_fn: Callable
    chunks: list[RetrievedChunk]
    answer: str


def _retrieve_node(
    state: RAGState,
) -> dict:
    retrieve_fn = state.get(
        "retrieve_fn",
        hybrid_retrieve_chunks,
    )

    chunks = retrieve_fn(
        db=state["db"],
        organization_id=state["organization_id"],
        query=state["question"],
        embedding_service=state["embedding_service"],
        qdrant_repository=state["qdrant_repository"],
        limit=state.get("retrieval_limit", 5),
        document_ids=state.get("document_ids"),
    )

    return {"chunks": chunks}


def _generate_node(
    state: RAGState,
) -> dict:
    generated = generate_answer(
        question=state["question"],
        chunks=state["chunks"],
        llm_client=state["llm_client"],
    )

    return {
        "answer": generated.answer,
    }


def build_rag_graph():
    graph = StateGraph(RAGState)

    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("generate", _generate_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


rag_graph = build_rag_graph()


def answer_question(
    *,
    db: Session,
    organization_id: int,
    question: str,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    llm_client: LLMClient,
    retrieval_limit: int = 5,
    document_ids: list[int] | None = None,
    retrieve_fn: Callable = hybrid_retrieve_chunks,
) -> RAGResponse:
    if not question.strip():
        raise ValueError(
            "Question cannot be empty"
        )

    result = rag_graph.invoke(
        {
            "db": db,
            "organization_id": organization_id,
            "question": question.strip(),
            "embedding_service": embedding_service,
            "qdrant_repository": qdrant_repository,
            "llm_client": llm_client,
            "retrieval_limit": retrieval_limit,
            "document_ids": document_ids,
            "retrieve_fn": retrieve_fn,
        }
    )

    return RAGResponse(
        answer=result["answer"],
        sources=result["chunks"],
    )
