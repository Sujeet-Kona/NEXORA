from dataclasses import dataclass
import time
from typing import Callable, Iterator

from sqlalchemy.orm import Session

from backend.core.exceptions import LLMGenerationError
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.generation_service import (
    NO_CONTEXT_ANSWER,
    StreamedCitationFilter,
    finalize_streamed_answer,
    generate_answer,
    stream_answer,
    usable_chunks,
)
from backend.services.hybrid_retrieval_service import hybrid_retrieve_chunks
from backend.services.llm.base import LLMClient
from backend.services.retrieval_service import RetrievedChunk


@dataclass(frozen=True)
class RAGResponse:
    answer: str
    sources: list[RetrievedChunk]


def answer_question(*, db: Session, organization_id: int, question: str, embedding_service: EmbeddingService, qdrant_repository: QdrantRepository, llm_client: LLMClient, retrieval_limit: int = 5, document_ids: list[int] | None = None, retrieve_fn: Callable = hybrid_retrieve_chunks) -> RAGResponse:
    if not question.strip():
        raise ValueError("Question cannot be empty")

    normalized_question = question.strip()
    retrieval_start = time.perf_counter()
    chunks = retrieve_fn(db=db, organization_id=organization_id, query=normalized_question, embedding_service=embedding_service, qdrant_repository=qdrant_repository, limit=retrieval_limit, document_ids=document_ids)
    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    generation_start = time.perf_counter()
    generated = generate_answer(question=normalized_question, chunks=chunks, llm_client=llm_client)
    generation_ms = (time.perf_counter() - generation_start) * 1000

    return RAGResponse(answer=generated.answer, sources=generated.sources)


def stream_answer_question(*, db: Session, organization_id: int, question: str, embedding_service: EmbeddingService, qdrant_repository: QdrantRepository, llm_client: LLMClient, retrieval_limit: int = 5, document_ids: list[int] | None = None, retrieve_fn: Callable = hybrid_retrieve_chunks) -> Iterator[dict]:
    """Retrieve eagerly, then return a generator of stream events."""
    if not question.strip():
        raise ValueError("Question cannot be empty")

    start = time.perf_counter()
    retrieval_start = time.perf_counter()
    chunks = retrieve_fn(db=db, organization_id=organization_id, query=question.strip(), embedding_service=embedding_service, qdrant_repository=qdrant_repository, limit=retrieval_limit, document_ids=document_ids)
    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    return _stream_events(question=question, chunks=chunks, llm_client=llm_client, start=start, retrieval_ms=retrieval_ms)


def _stream_events(*, question: str, chunks: list[RetrievedChunk], llm_client: LLMClient, start: float, retrieval_ms: float) -> Iterator[dict]:
    ttft_ms: float | None = None
    chunks = usable_chunks(chunks)

    if not chunks:
        ttft_ms = (time.perf_counter() - start) * 1000
        yield {"type": "token", "delta": NO_CONTEXT_ANSWER}
        yield {"type": "done", "answer": NO_CONTEXT_ANSWER, "sources": [], "timing": {"retrieval_ms": retrieval_ms, "generation_ms": 0.0, "ttft_ms": ttft_ms, "total_ms": (time.perf_counter() - start) * 1000}}
        return

    collected: list[str] = []
    citation_filter = StreamedCitationFilter(len(chunks))
    generation_start = time.perf_counter()

    try:
        for delta in stream_answer(question=question, chunks=chunks, llm_client=llm_client):
            if not delta:
                continue
            if ttft_ms is None:
                ttft_ms = (time.perf_counter() - start) * 1000
            collected.append(delta)
            safe_delta = citation_filter.feed(delta)
            if safe_delta:
                yield {"type": "token", "delta": safe_delta}
    except LLMGenerationError:
        yield {"type": "error", "detail": "LLM provider request failed"}
        return

    remainder = citation_filter.flush()
    if remainder:
        yield {"type": "token", "delta": remainder}

    raw_answer = "".join(collected)
    if not raw_answer.strip():
        yield {"type": "error", "detail": "LLM provider request failed"}
        return

    answer = finalize_streamed_answer(raw_answer, chunks)
    generation_ms = (time.perf_counter() - generation_start) * 1000
    total_ms = (time.perf_counter() - start) * 1000

    yield {"type": "done", "answer": answer, "sources": list(chunks), "timing": {"retrieval_ms": retrieval_ms, "generation_ms": generation_ms, "ttft_ms": ttft_ms if ttft_ms is not None else total_ms, "total_ms": total_ms}}
