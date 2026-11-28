from datetime import datetime, timezone

import logging

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import (
    DocumentExtractionError,
    DocumentNotFoundError,
    EmptyDocumentTextError,
)
from backend.core.logging import LOGGER_NAME
from backend.db.models import (
    Document,
    DocumentProcessingGeneration,
    DocumentStatus,
)
from backend.repositories.document_chunk_repository import (
    delete_chunks_for_document,
    replace_document_chunks,
)
from backend.repositories.document_repository import (
    get_document_by_id,
    get_document_by_id_unscoped,
    update_document_extraction_stats,
    update_document_failure,
    update_document_status,
)
from backend.services.bm25_service import invalidate_bm25_index
from backend.services.document_chunking import split_document
from backend.services.document_extraction import extract_document
from backend.services.document_indexing_service import index_document_chunks
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


def _claim_legacy_document_processing(db: Session, document) -> bool:
    """Atomically claim only documents that have never entered generation processing.

    The legacy processor has no attempt lease or external-write fence. It must
    not run on generation-managed documents, and it must not race the generation
    worker's PENDING claim.
    """
    generation_exists = (
        db.query(DocumentProcessingGeneration.id)
        .filter(
            DocumentProcessingGeneration.document_id == document.id,
            DocumentProcessingGeneration.organization_id == document.organization_id,
        )
        .exists()
    )
    claimed = (
        db.query(Document)
        .filter(
            Document.id == document.id,
            Document.organization_id == document.organization_id,
            Document.status == DocumentStatus.PENDING,
            Document.active_generation_id.is_(None),
            Document.processing_attempt_id.is_(None),
            Document.processing_lease_expires_at.is_(None),
            ~generation_exists,
        )
        .update(
            {
                Document.status: DocumentStatus.PROCESSING,
                Document.failure_reason: None,
                Document.updated_at: datetime.now(timezone.utc).replace(tzinfo=None),
            },
            synchronize_session=False,
        )
    )
    if claimed != 1:
        db.rollback()
        return False
    db.commit()
    db.refresh(document)
    return True


def process_document(
    db: Session,
    document_id: int,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
) -> None:
    document = get_document_by_id_unscoped(
        db=db,
        document_id=document_id,
    )

    if not document:
        raise DocumentNotFoundError(
            "Document not found"
        )

    current_status = DocumentStatus(document.status)

    if current_status == DocumentStatus.PROCESSING:
        logger.warning(
            "Document %d is already PROCESSING; skipping duplicate "
            "processing invocation",
            document.id,
            extra={"document_id": document.id},
        )
        return

    if current_status == DocumentStatus.READY:
        logger.info(
            "Document %d is already READY; skipping processing "
            "(re-upload to re-index)",
            document.id,
            extra={"document_id": document.id},
        )
        return

    # FAILED documents must be explicitly reset to PENDING before a retry.
    # This keeps retry intent visible and prevents an accidental worker
    # invocation from silently bypassing the documented state machine.
    if current_status == DocumentStatus.FAILED:
        logger.warning(
            "Document %d is FAILED; reset it to PENDING before retrying",
            document.id,
            extra={"document_id": document.id},
        )
        return

    if current_status != DocumentStatus.PENDING:
        logger.warning(
            "Document %d has unsupported processing status=%s",
            document.id,
            current_status.value,
            extra={
                "document_id": document.id,
                "from_status": current_status.value,
            },
        )
        return

    if not _claim_legacy_document_processing(db, document):
        logger.warning(
            "Legacy processing claim rejected for document %d",
            document.id,
            extra={"document_id": document.id},
        )
        return

    try:
        if not document.storage_key:
            raise DocumentExtractionError(
                "Document has no storage key"
            )

        storage = LocalStorage(settings.storage_path)

        content = storage.read(document.storage_key)

        extracted_document = extract_document(
            filename=document.name,
            content_type=document.content_type,
            content=content,
        )

        if not extracted_document.text.strip():
            raise EmptyDocumentTextError(
                "Document contains no extractable text"
            )

        chunks = split_document(extracted_document)

        replace_document_chunks(
            db=db,
            document_id=document.id,
            organization_id=document.organization_id,
            chunks=[
                (
                    chunk.text,
                    chunk.page_start,
                    chunk.page_end,
                )
                for chunk in chunks
            ],
        )

        update_document_extraction_stats(
            db=db,
            document=document,
            page_count=extracted_document.page_count,
            word_count=extracted_document.word_count,
            character_count=extracted_document.character_count,
        )

        db.commit()

        invalidate_bm25_index(document.organization_id)

        # Refresh updated_at immediately before the external embedding/indexing
        # work. This acts as a conservative processing lease heartbeat so the
        # startup recovery job does not mistake a live job for a crashed one.
        update_document_status(
            db=db,
            document=document,
            status=DocumentStatus.PROCESSING,
        )

        index_document_chunks(
            db=db,
            organization_id=document.organization_id,
            document_id=document.id,
            embedding_service=embedding_service,
            qdrant_repository=qdrant_repository,
        )

        update_document_status(
            db=db,
            document=document,
            status=DocumentStatus.READY,
        )

        invalidate_bm25_index(document.organization_id)

    except Exception as exc:
        db.rollback()

        organization_id = document.organization_id

        refreshed_document = get_document_by_id(
            db=db,
            document_id=document_id,
            organization_id=organization_id,
        )

        if refreshed_document:
            update_document_failure(
                db=db,
                document=refreshed_document,
                failure_reason=_failure_reason(exc),
            )

            # Chunks are committed before indexing, so a failure mid-pipeline
            # would otherwise leave a FAILED document searchable. Purge the
            # committed rows, drop the cached BM25 corpus, and best-effort
            # remove any vectors written.
            delete_chunks_for_document(
                db=db,
                document_id=document_id,
                organization_id=organization_id,
            )
            db.commit()

            invalidate_bm25_index(organization_id)

            try:
                qdrant_repository.delete_legacy_document_chunks(
                    document_id=document_id,
                    organization_id=organization_id,
                )
            except Exception:
                logger.warning(
                    "Failed to purge vectors for document %d during error cleanup",
                    document_id,
                )

        raise
