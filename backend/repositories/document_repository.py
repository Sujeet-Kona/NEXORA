from sqlalchemy.orm import Session

from backend.core.exceptions import (
    DocumentUploadFailedError,
    InvalidDocumentStatusTransitionError,
)
from backend.db.models import Document, DocumentStatus


def create_document(
    db: Session,
    organization_id: int,
    uploaded_by: int,
    name: str,
    storage_key: str | None = None,
    file_size: int | None = None,
    content_type: str | None = None,
) -> Document:
    document = Document(
        organization_id=organization_id,
        uploaded_by=uploaded_by,
        name=name,
        storage_key=storage_key,
        file_size=file_size,
        content_type=content_type,
        status=DocumentStatus.PENDING,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def create_document_pending(
    db: Session,
    organization_id: int,
    uploaded_by: int,
    name: str,
) -> Document:
    document = Document(
        organization_id=organization_id,
        uploaded_by=uploaded_by,
        name=name,
        status=DocumentStatus.PENDING,
    )

    db.add(document)
    db.flush()

    return document


def finalize_document_upload(
    db: Session,
    document: Document,
    storage_key: str,
    file_size: int,
    content_type: str,
) -> Document:
    document.storage_key = storage_key
    document.file_size = file_size
    document.content_type = content_type

    db.commit()
    db.refresh(document)

    return document


def get_document_by_id(
    db: Session,
    document_id: int,
    organization_id: int,
) -> Document | None:
    return (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
        .first()
    )


def get_document_by_id_for_update(
    db: Session,
    document_id: int,
    organization_id: int,
) -> Document | None:
    """Load an organization-scoped document while claiming its DB row."""
    return (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )


def get_documents_for_organization(
    db: Session,
    organization_id: int,
    limit: int,
    offset: int,
) -> list[Document]:
    return (
        db.query(Document)
        .filter(
            Document.organization_id == organization_id,
        )
        .order_by(Document.id)
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_document_names(
    db: Session,
    document_ids: list[int],
    organization_id: int,
) -> dict[int, str]:
    if not document_ids:
        return {}

    rows = (
        db.query(
            Document.id,
            Document.name,
        )
        .filter(
            Document.id.in_(document_ids),
            Document.organization_id == organization_id,
        )
        .all()
    )

    return {
        document_id: name
        for document_id, name in rows
    }


def update_document_status(
    db: Session,
    document: Document,
    status: DocumentStatus,
) -> Document:
    document.status = status
    db.commit()
    db.refresh(document)

    return document


def update_document_failure(
    db: Session,
    document: Document,
    failure_reason: str,
) -> Document:
    document.status = DocumentStatus.FAILED
    document.failure_reason = failure_reason

    db.commit()
    db.refresh(document)

    return document


def update_document_extraction_stats(
    db: Session,
    document: Document,
    page_count: int,
    word_count: int,
    character_count: int,
) -> Document:
    document.page_count = page_count
    document.word_count = word_count
    document.character_count = character_count

    db.flush()

    return document


def replace_document_file(
    db: Session,
    document: Document,
    name: str,
    storage_key: str,
    file_size: int,
    content_type: str,
) -> Document:
    # Re-read under a PostgreSQL row lock. The caller may have loaded a stale
    # ORM object while background processing concurrently changed the status.
    # Locking here makes the PROCESSING check authoritative at the mutation
    # point and serializes replacement with the processing claim.
    locked_document = get_document_by_id_for_update(
        db=db,
        document_id=document.id,
        organization_id=document.organization_id,
    )

    if not locked_document:
        raise DocumentUploadFailedError(
            "Document no longer exists"
        )

    if locked_document.status == DocumentStatus.PROCESSING:
        raise DocumentUploadFailedError(
            "Document cannot be replaced while it is processing"
        )

    locked_document.name = name
    locked_document.storage_key = storage_key
    locked_document.file_size = file_size
    locked_document.content_type = content_type
    locked_document.version = locked_document.version + 1
    locked_document.status = DocumentStatus.PENDING
    locked_document.failure_reason = None

    db.commit()
    db.refresh(locked_document)

    return locked_document


def delete_document(
    db: Session,
    document: Document,
) -> None:
    # Deletion must claim the same row used by the processing worker. Without
    # this lock, a delete could race with indexing and leave orphaned vectors.
    locked_document = (
        db.query(Document)
        .filter(Document.id == document.id)
        .with_for_update()
        .first()
    )

    if not locked_document:
        return

    if locked_document.status == DocumentStatus.PROCESSING:
        raise InvalidDocumentStatusTransitionError(
            "Document cannot be deleted while it is processing"
        )

    db.delete(locked_document)
    db.commit()


def get_document_by_id_unscoped(
    db: Session,
    document_id: int,
) -> Document | None:
    # Processing uses this lookup as the claim point for BackgroundTasks.
    # PostgreSQL's row lock makes the PENDING/FAILED -> PROCESSING transition
    # safe when duplicate workers race for the same document.
    return (
        db.query(Document)
        .filter(
            Document.id == document_id,
        )
        .with_for_update()
        .first()
    )
