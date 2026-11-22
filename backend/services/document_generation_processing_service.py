"""Attempt-owned document processing with isolated staging generations.

The legacy processor remains available for compatibility, but this service never
mutates legacy chunks or active vectors while a new document generation is built.
Failed candidate artifacts are intentionally retained for a future fenced
reconciler; cleanup is unsafe while external vector writes may still be in flight.
"""

import logging

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import DocumentExtractionError, EmptyDocumentTextError
from backend.core.logging import LOGGER_NAME
from backend.db.models import DocumentStatus
from backend.repositories.document_generation_repository import (
    create_staging_generation,
    promote_staging_generation_with_vector_readiness,
    replace_staging_generation_chunks,
    retire_failed_staging_generation,
    abandon_staging_generation,
)
from backend.repositories.document_repository import (
    claim_document_processing_attempt,
    finalize_document_processing_attempt,
    processing_attempt_is_owner,
    renew_document_processing_lease,
)
from backend.services.document_chunking import split_document
from backend.services.document_extraction import extract_document
from backend.services.embedding_service import EmbeddingService
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.storage import LocalStorage

logger = logging.getLogger(LOGGER_NAME)


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, EmptyDocumentTextError):
        return "Document contains no extractable text"
    if isinstance(exc, DocumentExtractionError):
        return "Document text extraction failed"
    return "Document processing failed"


def _owned(db: Session, document_id: int, attempt_id: str) -> bool:
    return processing_attempt_is_owner(db, document_id, attempt_id)


def _renew(db: Session, document_id: int, attempt_id: str) -> bool:
    return renew_document_processing_lease(db, document_id, attempt_id)


def _abandon_staging_if_owned_by_attempt(
    db: Session,
    generation_id: str | None,
    document_id: int,
    organization_id: int | None,
    attempt_id: str,
) -> None:
    """Best-effort SQL retirement of a stale attempt's inactive staging row."""
    if generation_id is None or organization_id is None:
        return
    try:
        if abandon_staging_generation(
            db, generation_id, document_id, organization_id, attempt_id
        ):
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to abandon stale staging generation",
            extra={"document_id": document_id, "generation_id": generation_id},
        )


def process_document_generation(
    db: Session,
    document_id: int,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
) -> bool:
    """Build and promote a generation only while the worker owns its lease.

    Returns False when the document was not claimable or ownership was lost.
    """
    attempt_id = claim_document_processing_attempt(db, document_id)
    if attempt_id is None:
        return False

    generation_id = None
    organization_id = None
    document = None
    try:
        from backend.db.models import Document

        document = (
            db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )
        if document is None:
            return False
        organization_id = document.organization_id
        document_name = document.name
        content_type = document.content_type
        storage_key = document.storage_key
        version = document.version

        if not storage_key:
            raise DocumentExtractionError("Document has no storage key")

        if not _renew(db, document_id, attempt_id):
            return False

        content = LocalStorage(settings.storage_path).read(storage_key)
        extracted = extract_document(
            filename=document_name,
            content_type=content_type,
            content=content,
        )
        if not extracted.text.strip():
            raise EmptyDocumentTextError("Document contains no extractable text")
        spans = split_document(extracted)
        if not spans:
            raise EmptyDocumentTextError("Document contains no extractable text")

        if not _renew(db, document_id, attempt_id):
            return False

        generation_id = create_staging_generation(
            db,
            document_id,
            organization_id,
            attempt_id,
        )
        if generation_id is None:
            db.rollback()
            if _owned(db, document_id, attempt_id):
                raise RuntimeError("Could not create staging generation")
            return False
        db.commit()

        chunk_records = [
            (chunk.text, chunk.page_start, chunk.page_end)
            for chunk in spans
        ]
        staged = replace_staging_generation_chunks(
            db,
            generation_id,
            document_id,
            organization_id,
            attempt_id,
            chunk_records,
        )
        if staged is None:
            db.rollback()
            if _owned(db, document_id, attempt_id):
                raise RuntimeError("Could not stage generation chunks")
            return False
        db.commit()

        for batch_start in range(0, len(staged), settings.embedding_batch_size):
            if not _renew(db, document_id, attempt_id):
                _abandon_staging_if_owned_by_attempt(
                    db, generation_id, document_id, organization_id, attempt_id
                )
                return False
            batch = staged[batch_start:batch_start + settings.embedding_batch_size]
            vectors = embedding_service.embed_documents([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise RuntimeError("Embedding count does not match staged chunk count")
            records = [
                (
                    generation_id,
                    vector,
                    organization_id,
                    document_id,
                    chunk.chunk_index,
                    version,
                )
                for chunk, vector in zip(batch, vectors)
            ]
            for upsert_start in range(0, len(records), settings.qdrant_upsert_batch_size):
                if not _renew(db, document_id, attempt_id):
                    _abandon_staging_if_owned_by_attempt(
                        db, generation_id, document_id, organization_id, attempt_id
                    )
                    return False
                qdrant_repository.upsert_generation_chunks(
                    records[upsert_start:upsert_start + settings.qdrant_upsert_batch_size]
                )

        if not _renew(db, document_id, attempt_id):
            _abandon_staging_if_owned_by_attempt(
                db, generation_id, document_id, organization_id, attempt_id
            )
            return False

        promoted = promote_staging_generation_with_vector_readiness(
            db,
            generation_id,
            document_id,
            organization_id,
            attempt_id,
            qdrant_repository,
        )
        if not promoted:
            db.rollback()
            if _owned(db, document_id, attempt_id):
                raise RuntimeError("Staging generation failed readiness or promotion")
            _abandon_staging_if_owned_by_attempt(
                db, generation_id, document_id, organization_id, attempt_id
            )
            return False
        # Promotion performs READY and clears the attempt token in this SQL
        # transaction. Stats are committed atomically with the active pointer.
        from backend.db.models import Document
        locked_document = (
            db.query(Document)
            .filter(
                Document.id == document_id,
                Document.organization_id == organization_id,
                Document.active_generation_id == generation_id,
                Document.status == DocumentStatus.READY,
            )
            .with_for_update()
            .first()
        )
        if locked_document is not None:
            locked_document.page_count = extracted.page_count
            locked_document.word_count = extracted.word_count
            locked_document.character_count = extracted.character_count
        db.commit()
        return True

    except Exception as exc:
        db.rollback()
        if generation_id is not None and organization_id is not None:
            try:
                retired = retire_failed_staging_generation(
                    db,
                    generation_id,
                    document_id,
                    organization_id,
                    attempt_id,
                )
                if retired:
                    db.commit()
                else:
                    db.rollback()
            except Exception:
                db.rollback()
                logger.exception(
                    "Failed to retire candidate generation",
                    extra={"document_id": document_id, "generation_id": generation_id},
                )
        # Never change state after ownership/lease loss. Failure finalization
        # itself is guarded by the same token and expiry.
        finalized = finalize_document_processing_attempt(
            db,
            document_id,
            attempt_id,
            DocumentStatus.FAILED,
            _failure_reason(exc),
        )
        if not finalized:
            db.rollback()
        logger.exception(
            "Generation-based document processing failed",
            extra={"document_id": document_id, "generation_id": generation_id},
        )
        return False
