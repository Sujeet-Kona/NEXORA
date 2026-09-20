from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.llm.base import LLMClient
from backend.services.rag_graph_service import rag_graph
from backend.services.retrieval_service import RetrievedChunk
from backend.services.embedding_service import EmbeddingService


@dataclass(frozen=True)
class RAGResponse:
    answer: str
    sources: list[RetrievedChunk]


def answer_question(
    *,
    db: Session,
    organization_id: int,
    question: str,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    llm_client: LLMClient,
    retrieval_limit: int = 5,
    retrieve_fn: Callable = None,
) -> RAGResponse:
    if not question.strip():
        raise ValueError(
            "Question cannot be empty"
        )

    state = {
        "db": db,
        "organization_id": organization_id,
        "question": question.strip(),
        "embedding_service": embedding_service,
        "qdrant_repository": qdrant_repository,
        "llm_client": llm_client,
        "retrieval_limit": retrieval_limit,
    }

    if retrieve_fn is not None:
        state["retrieve_fn"] = retrieve_fn

    result = rag_graph.invoke(state)

    return RAGResponse(
        answer=result["answer"],
        sources=result["chunks"],
    )
