"""Repository primitives for isolated document-processing generations."""

from datetime import datetime, timezone
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
            Document.processing_lease_expires_at > now,
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
            Document.processing_lease_expires_at > now,
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
            Document.processing_lease_expires_at > now,
        )
        .with_for_update()
        .first()
    )
    if document is None:
        return False


    generation = (
        db.query(DocumentProcessingGeneration)
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

def validate_staging_generation_vector_readiness(
    db: Session,
    generation_id: str,
    document_id: int,
    organization_id: int,
    attempt_id: str,
    vector_repository,
) -> bool:
    """Fail closed unless staged SQL chunks and generation vectors match.

    This is a readiness primitive only. Promotion remains a separate SQL
    transaction, and callers must not treat this check as a cross-store
    transaction or bypass the current-owner checks during promotion.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    document = (
        db.query(Document.id)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
            Document.processing_lease_expires_at > now,
        )
        .first()
    )
    if document is None:
        return False

    generation = (
        db.query(DocumentProcessingGeneration.id)
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
        return False

    staged_count = (
        db.query(DocumentGenerationChunk.id)
        .filter(
            DocumentGenerationChunk.generation_id == generation_id,
            DocumentGenerationChunk.document_id == document_id,
            DocumentGenerationChunk.organization_id == organization_id,
        )
        .count()
    )
    if staged_count <= 0:
        return False

    try:
        vector_count = vector_repository.count_generation_chunks(
            generation_id=generation_id,
            document_id=document_id,
            organization_id=organization_id,
        )
    except Exception:
        # Vector-store failures must never allow promotion readiness.
        return False

    return vector_count == staged_count

def promote_staging_generation_with_vector_readiness(
    db: Session,
    generation_id: str,
    document_id: int,
    organization_id: int,
    attempt_id: str,
    vector_repository,
) -> bool:
    """Gate SQL promotion on exact staged SQL/vector count parity.

    This does not create a cross-store transaction. The caller must ensure
    generation-scoped vector writes/cleanup are serialized with this operation,
    and commit the SQL transaction only when True is returned.
    """
    if not validate_staging_generation_vector_readiness(
        db,
        generation_id,
        document_id,
        organization_id,
        attempt_id,
        vector_repository,
    ):
        return False

    return promote_staging_generation(
        db,
        generation_id,
        document_id,
        organization_id,
        attempt_id,
    )

def retire_failed_staging_generation(
    db: Session,
    generation_id: str,
    document_id: int,
    organization_id: int,
    attempt_id: str,
) -> bool:
    """Mark a failed candidate generation as failed without affecting active data.

    SQL changes are transaction-controlled by the caller. This function never
    deletes or retires the document's active generation and only targets a
    staging generation owned by the given attempt.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
            Document.processing_lease_expires_at > now,
        )
        .with_for_update()
        .first()
    )
    if document is None:
        return False

    generation = (
        db.query(DocumentProcessingGeneration)
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

    generation.status = "failed"
    db.flush()
    return True

def cleanup_failed_generation_artifacts(
    db: Session,
    generation_id: str,
    document_id: int,
    organization_id: int,
    attempt_id: str,
    vector_repository,
) -> bool:
    """Idempotently clean artifacts for a failed, non-active candidate.

    The current processing owner and lease are required. Vector deletion is
    generation/document/tenant scoped and is verified by an exact count before
    SQL chunks are removed. Caller owns SQL commit/rollback.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.processing_attempt_id == attempt_id,
            Document.processing_lease_expires_at > now,
            Document.active_generation_id != generation_id,
        )
        .with_for_update()
        .first()
    )
    if document is None:
        return False

    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(
            DocumentProcessingGeneration.id == generation_id,
            DocumentProcessingGeneration.document_id == document_id,
            DocumentProcessingGeneration.organization_id == organization_id,
            DocumentProcessingGeneration.attempt_id == attempt_id,
            DocumentProcessingGeneration.status == "failed",
        )
        .with_for_update()
        .first()
    )
    if generation is None:
        return False

    try:
        vector_repository.delete_generation_chunks(
            generation_id=generation_id,
            document_id=document_id,
            organization_id=organization_id,
        )
        remaining_vectors = vector_repository.count_generation_chunks(
            generation_id=generation_id,
            document_id=document_id,
            organization_id=organization_id,
        )
    except Exception:
        return False
    if remaining_vectors != 0:
        return False

    (
        db.query(DocumentGenerationChunk)
        .filter(
            DocumentGenerationChunk.generation_id == generation_id,
            DocumentGenerationChunk.document_id == document_id,
            DocumentGenerationChunk.organization_id == organization_id,
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    return True

def list_abandoned_generation_cleanup_candidates(
    db: Session,
    limit: int = 100,
) -> list[DocumentProcessingGeneration]:
    """List inactive abandoned generations for a future cleanup reconciler.

    This is discovery only: it does not lock rows, delete artifacts, or
    claim cleanup ownership. A cleanup worker must introduce a durable claim
    and stale-worker write fencing before performing external deletion.
    """
    if limit <= 0:
        return []

    return (
        db.query(DocumentProcessingGeneration)
        .join(
            Document,
            Document.id == DocumentProcessingGeneration.document_id,
        )
        .filter(
            DocumentProcessingGeneration.status == "abandoned",
            Document.organization_id
            == DocumentProcessingGeneration.organization_id,
            Document.active_generation_id
            != DocumentProcessingGeneration.id,
        )
        .order_by(
            DocumentProcessingGeneration.created_at.asc(),
            DocumentProcessingGeneration.id.asc(),
        )
        .limit(limit)
        .all()
    )
