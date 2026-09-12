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
) -> list[Document]:
    return (
        db.query(Document)
        .filter(
            Document.organization_id == organization_id,
        )
        .order_by(Document.id)
        .all()
    )


def update_document_status(
    db: Session,
    document: Document,
    status: DocumentStatus,
) -> Document:
    document.status = status
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
