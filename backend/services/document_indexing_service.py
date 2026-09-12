from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import DocumentNotFoundError
from backend.repositories.document_chunk_repository import (
    get_chunks_for_document,
)
from backend.repositories.document_repository import (
    get_document_by_id,
)
from backend.repositories.qdrant_repository import (
    QdrantRepository,
)
from backend.services.embedding_service import (
    EmbeddingService,
)


def index_document_chunks(
    db: Session,
    organization_id: int,
    document_id: int,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
) -> int:
    document = get_document_by_id(
        db=db,
        document_id=document_id,
        organization_id=organization_id,
    )

    if not document:
        raise DocumentNotFoundError(
            "Document not found"
        )

    chunks = get_chunks_for_document(
        db=db,
        document_id=document.id,
        organization_id=document.organization_id,
    )

    qdrant_repository.delete_document_chunks(
        document_id=document.id,
        organization_id=document.organization_id,
    )

    if not chunks:
        return 0

    total_indexed = 0

    for start in range(
        0,
        len(chunks),
        settings.embedding_batch_size,
    ):
        batch = chunks[
            start:start + settings.embedding_batch_size
        ]

        texts = [
            chunk.text
            for chunk in batch
        ]

        vectors = embedding_service.embed_documents(
            texts
        )

        if len(vectors) != len(batch):
            raise ValueError(
                "Embedding count does not match chunk count"
            )

        for vector in vectors:
            if len(vector) != settings.embedding_dimension:
                raise ValueError(
                    "Embedding dimension does not match configuration"
                )

        records = [
            (
                chunk.id,
                vector,
                chunk.organization_id,
                chunk.document_id,
                chunk.chunk_index,
            )
            for chunk, vector in zip(
                batch,
                vectors,
            )
        ]

        for start_index in range(
            0,
            len(records),
            settings.qdrant_upsert_batch_size,
        ):
            qdrant_repository.upsert_chunks(
                records[
                    start_index:
                    start_index + settings.qdrant_upsert_batch_size
                ]
            )

            total_indexed += min(
                settings.qdrant_upsert_batch_size,
                len(records) - start_index,
            )

    return total_indexed

