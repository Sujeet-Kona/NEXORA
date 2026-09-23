from typing import Protocol

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.repositories.document_repository import (
    get_document_names,
)
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.bm25_service import get_bm25_index
from backend.services.embedding_service import EmbeddingService
from backend.services.retrieval_service import (
    RetrievedChunk,
    retrieve_chunks,
)


class Retriever(Protocol):
    def retrieve(
        self,
        *,
        db: Session,
        organization_id: int,
        query: str,
        document_ids: list[int] | None = None,
    ) -> list[RetrievedChunk]: ...


class DenseRetriever:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        qdrant_repository: QdrantRepository,
        limit: int | None = None,
    ):
        self.embedding_service = embedding_service
        self.qdrant_repository = qdrant_repository
        self.limit = (
            limit
            if limit is not None
            else settings.retrieval_dense_top_k
        )

    def retrieve(
        self,
        *,
        db: Session,
        organization_id: int,
        query: str,
        document_ids: list[int] | None = None,
    ) -> list[RetrievedChunk]:
        return retrieve_chunks(
            db=db,
            organization_id=organization_id,
            query=query,
            embedding_service=self.embedding_service,
            qdrant_repository=self.qdrant_repository,
            limit=self.limit,
            document_ids=document_ids,
        )


class LexicalRetriever:
    def __init__(self, limit: int | None = None):
        self.limit = (
            limit
            if limit is not None
            else settings.retrieval_lexical_top_k
        )

    def retrieve(
        self,
        *,
        db: Session,
        organization_id: int,
        query: str,
        document_ids: list[int] | None = None,
    ) -> list[RetrievedChunk]:
        index = get_bm25_index(
            db=db,
            organization_id=organization_id,
        )

        results = index.search(
            query=query,
            limit=self.limit,
            document_ids=document_ids,
        )

        if not results:
            return []

        document_names = get_document_names(
            db=db,
            document_ids=[
                chunk.document_id
                for chunk, _ in results
            ],
            organization_id=organization_id,
        )

        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                organization_id=chunk.organization_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                score=float(score),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                document_name=document_names.get(
                    chunk.document_id
                ),
            )
            for chunk, score in results
        ]
