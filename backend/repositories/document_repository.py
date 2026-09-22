from sqlalchemy.orm import Session

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
    document.name = name
    document.storage_key = storage_key
    document.file_size = file_size
    document.content_type = content_type
    document.version = document.version + 1
    document.status = DocumentStatus.PENDING
    document.failure_reason = None

    db.commit()
    db.refresh(document)

    return document


def delete_document(
    db: Session,
    document: Document,
) -> None:
    db.delete(document)
    db.commit()

def get_document_by_id_unscoped(
    db: Session,
    document_id: int,
) -> Document | None:
    return (
        db.query(Document)
        .filter(
            Document.id == document_id,
        )
        .first()
    )
