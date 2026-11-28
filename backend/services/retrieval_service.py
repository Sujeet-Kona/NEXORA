from dataclasses import dataclass
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from backend.repositories.document_generation_repository import (
    get_active_generation_chunks,
)
from backend.repositories.document_chunk_repository import (
    get_chunks_by_ids_for_organization,
)
from backend.repositories.document_repository import (
    get_document_names,
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
    page_start: int | None
    page_end: int | None
    document_name: str | None
    generation_id: str | None = None


def retrieve_chunks(
    db: Session,
    organization_id: int,
    query: str,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    limit: int = 5,
    document_ids: list[int] | None = None,
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
        document_ids=document_ids,
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
        document_ids=document_ids,
    )

    chunks_by_id = {
        chunk.id: chunk
        for chunk in chunks
    }

    document_names = get_document_names(
        db=db,
        document_ids=[
            chunk.document_id
            for chunk in chunks
        ],
        organization_id=organization_id,
    )

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
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                document_name=document_names.get(
                    chunk.document_id
                ),
            )
        )

    return results


def retrieve_active_generation_chunks(
    db: Session,
    organization_id: int,
    query: str,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    limit: int = 5,
    document_ids: list[int] | None = None,
) -> list[RetrievedChunk]:
    """Retrieve dense hits only from SQL-verified active generations."""
    if not query.strip():
        raise ValueError("Query cannot be empty")
    if limit <= 0:
        raise ValueError("Limit must be greater than zero")

    active_chunks = get_active_generation_chunks(
        db=db,
        organization_id=organization_id,
        document_ids=document_ids,
    )
    if not active_chunks:
        return []

    active_keys = {
        (chunk.generation_id, chunk.chunk_index): chunk
        for chunk in active_chunks
    }
    generation_ids = sorted({chunk.generation_id for chunk in active_chunks})
    query_vector = embedding_service.embed_query(query)
    search_result = qdrant_repository.search_generation(
        query_vector=query_vector,
        organization_id=organization_id,
        generation_ids=generation_ids,
        limit=limit,
        document_ids=document_ids,
    )
    points = search_result.points
    if not points:
        return []

    hydrated = []
    for point in points:
        payload = point.payload
        if not isinstance(payload, dict):
            continue

        generation_id = payload.get("generation_id")
        chunk_index = payload.get("chunk_index")
        if (
            not isinstance(generation_id, str)
            or not generation_id
            or isinstance(chunk_index, bool)
            or not isinstance(chunk_index, int)
            or chunk_index < 0
        ):
            continue

        chunk = active_keys.get((generation_id, chunk_index))
        if chunk is None:
            continue

        payload_organization_id = payload.get("organization_id")
        payload_document_id = payload.get("document_id")
        if (
            isinstance(payload_organization_id, bool)
            or not isinstance(payload_organization_id, int)
            or payload_organization_id != organization_id
            or isinstance(payload_document_id, bool)
            or not isinstance(payload_document_id, int)
            or payload_document_id != chunk.document_id
        ):
            continue

        try:
            expected_point_id = str(
                uuid5(UUID(generation_id), str(chunk_index))
            )
        except (ValueError, TypeError):
            continue
        if str(point.id) != expected_point_id:
            continue

        hydrated.append((chunk, float(point.score)))

    if not hydrated:
        return []
    document_names = get_document_names(
        db=db,
        document_ids=[chunk.document_id for chunk, _ in hydrated],
        organization_id=organization_id,
    )
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            organization_id=chunk.organization_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            score=score,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            document_name=document_names.get(chunk.document_id),
            generation_id=chunk.generation_id,
        )
        for chunk, score in hydrated
    ]
