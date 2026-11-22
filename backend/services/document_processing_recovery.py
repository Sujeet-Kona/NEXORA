from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.db.models import (
    Document,
    DocumentProcessingGeneration,
    DocumentStatus,
)


STALE_PROCESSING_AFTER = timedelta(minutes=30)
STALE_RECOVERY_REASON = (
    "Previous processing worker expired; document queued for retry"
)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _abandon_staging_generations(
    db: Session,
    document_id: int,
    organization_id: int,
    attempt_id: str | None,
) -> int:
    """Mark this stale attempt's staging generations cleanup-eligible.

    This is a SQL-only state transition. It deliberately does not delete
    vectors/chunks: a separate reconciler must perform generation-scoped,
    verified external cleanup.
    """
    if attempt_id is None:
        return 0

    return (
        db.query(DocumentProcessingGeneration)
        .filter(
            DocumentProcessingGeneration.document_id == document_id,
            DocumentProcessingGeneration.organization_id == organization_id,
            DocumentProcessingGeneration.attempt_id == attempt_id,
            DocumentProcessingGeneration.status == "staging",
        )
        .update(
            {DocumentProcessingGeneration.status: "abandoned"},
            synchronize_session=False,
        )


def recover_stale_processing_documents(db: Session) -> int:
    """Return stale PROCESSING jobs to PENDING and abandon their staging rows.

    Document rows are locked before the attempt token is cleared. Generation
    rows are transitioned only for that document/tenant/attempt. External
    vector cleanup is deferred to a reconciler and is never performed here.
    """
    cutoff = _utc_now_naive() - STALE_PROCESSING_AFTER

    documents = (
        db.query(Document)
        .filter(
            Document.status == DocumentStatus.PROCESSING,
            Document.updated_at < cutoff,
        )
        .with_for_update(skip_locked=True)
        .all()
    )

    for document in documents:
        _abandon_staging_generations(
            db,
            document.id,
            document.organization_id,
            document.processing_attempt_id,
        )
        document.status = DocumentStatus.PENDING
        document.processing_attempt_id = None
        document.processing_lease_expires_at = None
        document.failure_reason = STALE_RECOVERY_REASON

    if documents:
        db.commit()

    return len(documents)


def recover_stale_document_processing(
    db: Session,
    document_id: int,
) -> bool:
    """Lock and reset one stale PROCESSING document before retrying it."""
    cutoff = _utc_now_naive() - STALE_PROCESSING_AFTER
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.updated_at < cutoff,
        )
        .with_for_update(skip_locked=True)
        .first()
    )
    if document is None:
        return False

    _abandon_staging_generations(
        db,
        document.id,
        document.organization_id,
        document.processing_attempt_id,
    )
    document.status = DocumentStatus.PENDING
    document.processing_attempt_id = None
    document.processing_lease_expires_at = None
    document.failure_reason = STALE_RECOVERY_REASON
    db.commit()
    return True
