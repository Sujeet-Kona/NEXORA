from dataclasses import dataclass

from sentence_transformers import CrossEncoder
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.retrieval_service import RetrievedChunk
from backend.services.retrievers import (
    DenseRetriever,
    LexicalRetriever,
    Retriever,
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


def _rrf_fuse(
    rankings: list[list[RetrievedChunk]],
    k: int = 60,
) -> list[HybridCandidate]:
    scores: dict[int, float] = {}
    chunks: dict[int, RetrievedChunk] = {}

    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
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
    retrievers: list[Retriever] | None = None,
    dense_limit: int | None = None,
    lexical_limit: int | None = None,
    rerank_limit: int | None = None,
    final_limit: int | None = None,
    limit: int | None = None,
    document_ids: list[int] | None = None,
) -> list[RetrievedChunk]:
    if not query.strip():
        raise ValueError("Query cannot be empty")

    if retrievers is None:
        retrievers = [
            DenseRetriever(
                embedding_service,
                qdrant_repository,
                limit=dense_limit,
            ),
            LexicalRetriever(limit=lexical_limit),
        ]
    elif dense_limit is not None or lexical_limit is not None:
        raise ValueError(
            "dense_limit and lexical_limit only apply to "
            "the default retrievers; configure limits on "
            "the passed retrievers instead"
        )

    if rerank_limit is None:
        rerank_limit = settings.retrieval_rerank_top_k

    if limit is not None:
        if limit <= 0:
            raise ValueError("Limit must be greater than zero")
        final_limit = limit

    if final_limit is None:
        final_limit = settings.retrieval_top_k

    if final_limit <= 0:
        raise ValueError(
            "Final limit must be greater than zero"
        )

    rankings = [
        retriever.retrieve(
            db=db,
            organization_id=organization_id,
            query=query,
            document_ids=document_ids,
        )
        for retriever in retrievers
    ]

    fused = _rrf_fuse(rankings)

    candidates = [
        candidate.chunk
        for candidate in fused[:rerank_limit]
    ]

    reranked = get_reranker().rerank(
        query=query,
        chunks=candidates,
    )

    return reranked[:final_limit]
