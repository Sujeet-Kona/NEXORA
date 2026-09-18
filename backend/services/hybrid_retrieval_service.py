from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from sqlalchemy.orm import Session

from backend.db.models import DocumentChunk
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.retrieval_service import (
    RetrievedChunk,
    retrieve_chunks,
)


@dataclass(frozen=True)
class HybridCandidate:
    chunk: RetrievedChunk
    rrf_score: float


class Reranker:
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ):
        self.model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        pairs = [
            [query, chunk.text]
            for chunk in chunks
        ]

        scores = self.model.predict(pairs)

        ranked = sorted(
            zip(chunks, scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )

        return [
            chunk
            for chunk, _ in ranked
        ]


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker

    if _reranker is None:
        _reranker = Reranker()

    return _reranker


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _bm25_search(
    db: Session,
    organization_id: int,
    query: str,
    limit: int,
) -> list[RetrievedChunk]:
    index = get_bm25_index(
        db=db,
        organization_id=organization_id,
    )

    results = index.search(
        query=query,
        limit=limit,
    )

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            organization_id=chunk.organization_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            score=float(score),
        )
        for chunk, score in results
    ]

def _rrf_fuse(
    dense: list[RetrievedChunk],
    lexical: list[RetrievedChunk],
    k: int = 60,
) -> list[HybridCandidate]:
    scores: dict[int, float] = {}
    chunks: dict[int, RetrievedChunk] = {}

    for rank, chunk in enumerate(dense, start=1):
        scores[chunk.chunk_id] = (
            scores.get(chunk.chunk_id, 0.0)
            + 1.0 / (k + rank)
        )
        chunks[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(lexical, start=1):
        scores[chunk.chunk_id] = (
            scores.get(chunk.chunk_id, 0.0)
            + 1.0 / (k + rank)
        )
        chunks.setdefault(chunk.chunk_id, chunk)

    ranked_ids = sorted(
        chunks,
        key=lambda chunk_id: scores[chunk_id],
        reverse=True,
    )

    return [
        HybridCandidate(
            chunk=chunks[chunk_id],
            rrf_score=scores[chunk_id],
        )
        for chunk_id in ranked_ids
    ]


def hybrid_retrieve_chunks(
    *,
    db: Session,
    organization_id: int,
    query: str,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    dense_limit: int = 10,
    lexical_limit: int = 10,
    rerank_limit: int = 8,
    final_limit: int = 2,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    if not query.strip():
        raise ValueError("Query cannot be empty")

    if limit is not None:
        if limit <= 0:
            raise ValueError("Limit must be greater than zero")
        final_limit = limit

    if final_limit <= 0:
        raise ValueError(
            "Final limit must be greater than zero"
        )

    dense = retrieve_chunks(
        db=db,
        organization_id=organization_id,
        query=query,
        embedding_service=embedding_service,
        qdrant_repository=qdrant_repository,
        limit=dense_limit,
    )

    lexical = _bm25_search(
        db=db,
        organization_id=organization_id,
        query=query,
        limit=lexical_limit,
    )

    fused = _rrf_fuse(
        dense=dense,
        lexical=lexical,
    )

    candidates = [
        candidate.chunk
        for candidate in fused[:rerank_limit]
    ]

    reranked = get_reranker().rerank(
        query=query,
        chunks=candidates,
    )

    return reranked[:final_limit]


