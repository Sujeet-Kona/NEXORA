"""Repository primitives for isolated document-processing generations."""

from uuid import uuid4

from sqlalchemy.orm import Session

from backend.db.models import (
    Document,
    DocumentGenerationChunk,
    DocumentProcessingGeneration,
    DocumentStatus,
)
from backend.repositories.document_chunk_repository import ChunkRecord


def create_staging_generation(
    db: Session,
    document_id: int,
    organization_id: int,
    attempt_id: str,
) -> str | None:
    """Create a staging generation only for the current processing owner.

    This helper does not commit. The caller controls the transaction boundary.
    """
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
        )
        .with_for_update()
        .first()
    )
    if document is None:
        return None

    generation_id = str(uuid4())
    db.add(
        DocumentProcessingGeneration(
            id=generation_id,
            document_id=document_id,
            organization_id=organization_id,
            attempt_id=attempt_id,
            status="staging",
        )
    )
    db.flush()
    return generation_id


def replace_staging_generation_chunks(
    db: Session,
    generation_id: str,
    document_id: int,
    organization_id: int,
    attempt_id: str,
    chunks: list[ChunkRecord],
) -> list[DocumentGenerationChunk] | None:
    """Replace staging chunks only when both generation and attempt still match.

    Returns None for a stale/mismatched owner without mutating staged chunks.
    Caller must commit or roll back to release the document lock.
    """
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
        )
        .with_for_update()
        .first()
    )
    if document is None:
        return None

    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(
            DocumentProcessingGeneration.id == generation_id,
            DocumentProcessingGeneration.document_id == document_id,
            DocumentProcessingGeneration.organization_id == organization_id,
            DocumentProcessingGeneration.attempt_id == attempt_id,
            DocumentProcessingGeneration.status == "staging",
        )
        .first()
    )
    if generation is None:
        return None

    (
        db.query(DocumentGenerationChunk)
        .filter(DocumentGenerationChunk.generation_id == generation_id)
        .delete(synchronize_session=False)
    )

    records = [
        DocumentGenerationChunk(
            generation_id=generation_id,
            document_id=document_id,
            organization_id=organization_id,
            chunk_index=index,
            text=text,
            page_start=page_start,
            page_end=page_end,
        )
        for index, (text, page_start, page_end) in enumerate(chunks)
    ]
    db.add_all(records)
    db.flush()
    return records


def get_staging_generation_chunks(
    db: Session,
    generation_id: str,
    organization_id: int,
) -> list[DocumentGenerationChunk]:
    """Read staged chunks scoped by generation and tenant."""
    return (
        db.query(DocumentGenerationChunk)
        .filter(
            DocumentGenerationChunk.generation_id == generation_id,
            DocumentGenerationChunk.organization_id == organization_id,
        )
        .order_by(DocumentGenerationChunk.chunk_index)
        .all()
    )


def promote_staging_generation(
    db: Session,
    generation_id: str,
    document_id: int,
    organization_id: int,
    attempt_id: str,
) -> bool:
    """Atomically activate a non-empty generation for the current owner.


    The caller owns the transaction and must commit on success. A stale or
    invalid attempt returns False without changing document/generation state.
    """
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
        )
        .with_for_update()
        .first()
    )
    if document is None:
        return False


    generation = (\n        db.query(DocumentProcessingGeneration)
        .filter(
            DocumentProcessingGeneration.id == generation_id,
            DocumentProcessingGeneration.document_id == document_id,
            DocumentProcessingGeneration.organization_id == organization_id,
            DocumentProcessingGeneration.attempt_id == attempt_id,
            DocumentProcessingGeneration.status == "staging",
        )
        .with_for_update()
        .first()
    )
    if generation is None:
        return False


    staged_chunk_count = (
        db.query(DocumentGenerationChunk.id)
        .filter(
            DocumentGenerationChunk.generation_id == generation_id,
            DocumentGenerationChunk.document_id == document_id,
            DocumentGenerationChunk.organization_id == organization_id,
        )
        .count()
    )
    if staged_chunk_count == 0:
        return False



    previous_generation_id = document.active_generation_id
    if previous_generation_id and previous_generation_id != generation_id:
        (
            db.query(DocumentProcessingGeneration)
            .filter(
                DocumentProcessingGeneration.id == previous_generation_id,
                DocumentProcessingGeneration.document_id == document_id,
                DocumentProcessingGeneration.organization_id == organization_id,
                DocumentProcessingGeneration.status == "active",
            )
            .update(
                {DocumentProcessingGeneration.status: "retired"},
                synchronize_session=False,
            )
        )


    generation.status = "active"
    document.active_generation_id = generation_id
    document.status = DocumentStatus.READY
    document.failure_reason = None
    document.processing_attempt_id = None
    document.processing_lease_expires_at = None
    db.flush()
    return True
