from fastapi import APIRouter, Depends
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
from backend.services.rag_service import answer_question


router = APIRouter(
    prefix="/organizations",
    tags=["rag"],
)


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
        sources=[
            RAGSourceResponse(
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                document_name=source.document_name,
                chunk_index=source.chunk_index,
                score=source.score,
                page_start=source.page_start,
                page_end=source.page_end,
            )
            for source in result.sources
        ],
    )
