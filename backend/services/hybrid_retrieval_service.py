from dataclasses import dataclass, replace
import logging
import math

from sentence_transformers import CrossEncoder
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import LOGGER_NAME
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.retrieval_service import RetrievedChunk
from backend.services.retrievers import (
    DenseRetriever,
    LexicalRetriever,
    Retriever,
)


logger = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True)
class HybridCandidate:
    chunk: RetrievedChunk
    rrf_score: float


def _sigmoid(logit: float) -> float:
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))

    exponent = math.exp(logit)
    return exponent / (1.0 + exponent)


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
        *,
        min_relevance: float | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        if min_relevance is None:
            min_relevance = settings.retrieval_min_relevance
        elif not 0.0 <= min_relevance <= 1.0:
            raise ValueError(
                "min_relevance must be between 0.0 and 1.0"
            )

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

        grounded = []

        for chunk, logit in ranked:
            raw_logit = float(logit)
            relevance = _sigmoid(raw_logit)
            kept = relevance >= min_relevance

            # Cross-encoder logits are ranking scores, not calibrated
            # probabilities. The sigmoid is monotonic, but its output
            # must not be interpreted as a probability of relevance.
            logger.debug(
                (
                    "Cross-encoder candidate chunk_id=%d pages=%s-%s "
                    "raw_logit=%.6f sigmoid_score=%.6f "
                    "threshold=%.6f kept=%s"
                ),
                chunk.chunk_id,
                chunk.page_start,
                chunk.page_end,
                raw_logit,
                relevance,
                min_relevance,
                kept,
            )

            if not kept:
                continue

            grounded.append(
                replace(chunk, score=relevance)
            )

        if ranked and not grounded:
            logger.warning(
                (
                    "Cross-encoder filtered all %d candidates "
                    "at min_relevance=%.6f"
                ),
                len(ranked),
                min_relevance,
            )

        return grounded


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
    if k <= 0:
        raise ValueError(
            "RRF constant k must be strictly positive"
        )

    scores: dict[int, float] = {}
    chunks: dict[int, RetrievedChunk] = {}

    for ranking in rankings:
        # Each retriever is weighted equally; we sum their rank scores.
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
    min_relevance: float | None = None,
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

    if rerank_limit <= 0:
        raise ValueError(
            "rerank_limit must be greater than zero"
        )

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

    # A rerank candidate pool smaller than the final answer pool means
    # the cross-encoder cannot improve ranking and would silently drop
    # results. Warn and widen the pool transparently.
    if rerank_limit < final_limit:
        logger.warning(
            "rerank_limit=%d < final_limit=%d; cross-encoder cannot "
            "improve diversity. Widening rerank pool automatically.",
            rerank_limit,
            final_limit,
        )
        rerank_limit = final_limit

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

    if not candidates:
        # Nothing to rerank; the cross-encoder has nothing meaningful to
        # do. Skip the (expensive) empty forward pass.
        return []

    reranker = get_reranker()
    if min_relevance is None:
        reranked = reranker.rerank(
            query=query,
            chunks=candidates,
        )
    else:
        reranked = reranker.rerank(
            query=query,
            chunks=candidates,
            min_relevance=min_relevance,
        )

    return reranked[:final_limit]
