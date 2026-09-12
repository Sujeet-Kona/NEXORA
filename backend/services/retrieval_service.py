from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.repositories.document_chunk_repository import (
    get_chunks_by_ids_for_organization,
)
from backend.repositories.qdrant_repository import (
    QdrantRepository,
)
from backend.services.embedding_service import (
    EmbeddingService,
)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    organization_id: int
    chunk_index: int
    text: str
    score: float


def retrieve_chunks(
    db: Session,
    organization_id: int,
    query: str,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    limit: int = 5,
) -> list[RetrievedChunk]:
    if not query.strip():
        raise ValueError("Query cannot be empty")

    if limit <= 0:
        raise ValueError(
            "Limit must be greater than zero"
        )

    query_vector = embedding_service.embed_query(
        query
    )

    search_result = qdrant_repository.search(
        query_vector=query_vector,
        organization_id=organization_id,
        limit=limit,
    )

    if not search_result.points:
        return []

    point_ids = [
        int(point.id)
        for point in search_result.points
    ]

    chunks = get_chunks_by_ids_for_organization(
        db=db,
        chunk_ids=point_ids,
        organization_id=organization_id,
    )

    chunks_by_id = {
        chunk.id: chunk
        for chunk in chunks
    }

    results = []

    for point in search_result.points:
        chunk = chunks_by_id.get(int(point.id))

        if chunk is None:
            continue

        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                organization_id=chunk.organization_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                score=float(point.score),
            )
        )

    return results
