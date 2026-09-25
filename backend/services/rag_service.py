from dataclasses import dataclass
import time
from typing import Callable, Iterator

from sqlalchemy.orm import Session

from backend.core.exceptions import LLMGenerationError
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.generation_service import (
    NO_CONTEXT_ANSWER,
    finalize_streamed_answer,
    stream_answer,
)
from backend.services.hybrid_retrieval_service import (
    hybrid_retrieve_chunks,
)
from backend.services.llm.base import LLMClient
from backend.services.rag_graph_service import rag_graph
from backend.services.retrieval_service import RetrievedChunk


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
    document_ids: list[int] | None = None,
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
        "document_ids": document_ids,
    }

    if retrieve_fn is not None:
        state["retrieve_fn"] = retrieve_fn

    result = rag_graph.invoke(state)

    return RAGResponse(
        answer=result["answer"],
        sources=result["chunks"],
    )


def stream_answer_question(
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
) -> Iterator[dict]:
    """Retrieve eagerly, then return a generator of stream events.

    Retrieval runs at call time so its failures surface as normal
    exceptions (handled by the API error middleware) rather than
    breaking an already-opened stream. The returned generator emits
    ``token`` deltas, then a terminal ``done`` event (sanitized
    answer, sources, timing) or an ``error`` event.
    """
    if not question.strip():
        raise ValueError(
            "Question cannot be empty"
        )

    start = time.perf_counter()

    chunks = retrieve_fn(
        db=db,
        organization_id=organization_id,
        query=question.strip(),
        embedding_service=embedding_service,
        qdrant_repository=qdrant_repository,
        limit=retrieval_limit,
        document_ids=document_ids,
    )

    return _stream_events(
        question=question,
        chunks=chunks,
        llm_client=llm_client,
        start=start,
    )


def _stream_events(
    *,
    question: str,
    chunks: list[RetrievedChunk],
    llm_client: LLMClient,
    start: float,
) -> Iterator[dict]:
    ttft_ms: float | None = None

    if not chunks:
        ttft_ms = (time.perf_counter() - start) * 1000

        yield {"type": "token", "delta": NO_CONTEXT_ANSWER}
        yield {
            "type": "done",
            "answer": NO_CONTEXT_ANSWER,
            "sources": [],
            "timing": {
                "ttft_ms": ttft_ms,
                "total_ms": (
                    (time.perf_counter() - start) * 1000
                ),
            },
        }
        return

    collected: list[str] = []

    try:
        for delta in stream_answer(
            question=question,
            chunks=chunks,
            llm_client=llm_client,
        ):
            if not delta:
                continue

            if ttft_ms is None:
                ttft_ms = (
                    (time.perf_counter() - start) * 1000
                )

            collected.append(delta)

            yield {"type": "token", "delta": delta}
    except LLMGenerationError:
        yield {
            "type": "error",
            "detail": "LLM provider request failed",
        }
        return

    raw_answer = "".join(collected)

    if not raw_answer.strip():
        yield {
            "type": "error",
            "detail": "LLM provider request failed",
        }
        return

    answer = finalize_streamed_answer(raw_answer, chunks)

    total_ms = (time.perf_counter() - start) * 1000

    yield {
        "type": "done",
        "answer": answer,
        "sources": list(chunks),
        "timing": {
            "ttft_ms": (
                ttft_ms if ttft_ms is not None else total_ms
            ),
            "total_ms": total_ms,
        },
    }
