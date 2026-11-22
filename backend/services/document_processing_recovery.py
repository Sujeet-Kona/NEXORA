from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.db.models import Document, DocumentStatus
from backend.repositories.document_repository import (
    get_document_by_id_unscoped,
)


STALE_PROCESSING_AFTER = timedelta(minutes=30)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def recover_stale_processing_documents(db: Session) -> int:
    """Return crashed PROCESSING jobs to PENDING so they can be retried.

    BackgroundTasks are in-process work, so a process crash can otherwise
    leave a document permanently stuck in PROCESSING. The 30-minute lease is
    deliberately conservative; normal processing refreshes ``updated_at``
    before expensive indexing work. Each row is locked before it is reset so
    recovery cannot race another worker's claim.
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

    recovered = 0

    for document in documents:
        document.status = DocumentStatus.PENDING
        document.failure_reason = (
            "Previous processing worker expired; document queued for retry"
        )
        recovered += 1

    if recovered:
        db.commit()

    return recovered


def recover_stale_document_processing(
    db: Session,
    document_id: int,
) -> bool:
    """Reset one stale PROCESSING document to PENDING before retrying it."""
    document = get_document_by_id_unscoped(
        db=db,
        document_id=document_id,
    )

    if not document or document.status != DocumentStatus.PROCESSING:
        return False

    cutoff = _utc_now_naive() - STALE_PROCESSING_AFTER

    if document.updated_at >= cutoff:
        return False

    document.status = DocumentStatus.PENDING
    document.failure_reason = (
        "Previous processing worker expired; document queued for retry"
    )
    db.commit()
    return True
