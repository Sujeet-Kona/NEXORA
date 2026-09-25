import json
from typing import Iterable, Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import get_db
from backend.dependencies.organization_authorization import (
    require_organization_member,
)
from backend.dependencies.rag import (
    get_embedding_service,
    get_ollama_client,
    get_qdrant_repository,
)
from backend.repositories.qdrant_repository import QdrantRepository
from backend.schemas.rag import (
    RAGQueryRequest,
    RAGQueryResponse,
    RAGSourceResponse,
)
from backend.services.embedding_service import EmbeddingService
from backend.services.llm.ollama_client import OllamaLLMClient
from backend.services.rag_service import (
    answer_question,
    stream_answer_question,
)
from backend.services.retrieval_service import RetrievedChunk


router = APIRouter(
    prefix="/organizations",
    tags=["rag"],
)


def _build_sources(
    sources: Iterable[RetrievedChunk],
) -> list[RAGSourceResponse]:
    return [
        RAGSourceResponse(
            citation_index=citation_index,
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            document_name=source.document_name,
            chunk_index=source.chunk_index,
            score=source.score,
            page_start=source.page_start,
            page_end=source.page_end,
        )
        for citation_index, source in enumerate(
            sources,
            start=1,
        )
    ]


@router.post(
    "/{organization_id}/query",
    response_model=RAGQueryResponse,
)
def query_knowledge_base(
    organization_id: int,
    request: RAGQueryRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    embedding_service: EmbeddingService = Depends(
        get_embedding_service,
    ),
    qdrant_repository: QdrantRepository = Depends(
        get_qdrant_repository,
    ),
    llm_client: OllamaLLMClient = Depends(
        get_ollama_client,
    ),
):
    require_organization_member(
        db=db,
        organization_id=organization_id,
        current_user=current_user,
    )

    result = answer_question(
        db=db,
        organization_id=organization_id,
        question=request.question,
        embedding_service=embedding_service,
        qdrant_repository=qdrant_repository,
        llm_client=llm_client,
        retrieval_limit=settings.retrieval_top_k,
        document_ids=request.document_ids,
    )

    return RAGQueryResponse(
        answer=result.answer,
        sources=_build_sources(result.sources),
    )


def _sse_payload(event: dict) -> dict:
    event_type = event["type"]

    if event_type == "token":
        return {"delta": event["delta"]}

    if event_type == "error":
        return {"detail": event["detail"]}

    return {
        "answer": event["answer"],
        "sources": [
            source.model_dump()
            for source in _build_sources(event["sources"])
        ],
        "timing": event["timing"],
    }


def _sse_stream(events: Iterator[dict]) -> Iterator[str]:
    for event in events:
        yield "event: {}\ndata: {}\n\n".format(
            event["type"],
            json.dumps(_sse_payload(event)),
        )


@router.post(
    "/{organization_id}/query/stream",
)
def query_knowledge_base_stream(
    organization_id: int,
    request: RAGQueryRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    embedding_service: EmbeddingService = Depends(
        get_embedding_service,
    ),
    qdrant_repository: QdrantRepository = Depends(
        get_qdrant_repository,
    ),
    llm_client: OllamaLLMClient = Depends(
        get_ollama_client,
    ),
):
    require_organization_member(
        db=db,
        organization_id=organization_id,
        current_user=current_user,
    )

    events = stream_answer_question(
        db=db,
        organization_id=organization_id,
        question=request.question,
        embedding_service=embedding_service,
        qdrant_repository=qdrant_repository,
        llm_client=llm_client,
        retrieval_limit=settings.retrieval_top_k,
        document_ids=request.document_ids,
    )

    return StreamingResponse(
        _sse_stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
