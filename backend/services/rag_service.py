from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.generation_service import generate_answer
from backend.services.llm.base import LLMClient
from backend.services.retrieval_service import (
    RetrievedChunk,
    retrieve_chunks,
)


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
    retrieve_fn: Callable = retrieve_chunks,
) -> RAGResponse:
    chunks = retrieve_fn(
        db=db,
        organization_id=organization_id,
        query=question,
        embedding_service=embedding_service,
        qdrant_repository=qdrant_repository,
        limit=retrieval_limit,
    )

    generated = generate_answer(
        question=question,
        chunks=chunks,
        llm_client=llm_client,
    )

    return RAGResponse(
        answer=generated.answer,
        sources=generated.sources,
    )
