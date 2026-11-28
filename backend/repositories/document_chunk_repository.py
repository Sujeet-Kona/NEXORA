from sqlalchemy.orm import Session

from backend.db.models import Document, DocumentChunk, DocumentStatus


ChunkRecord = tuple[str, int | None, int | None]


def create_document_chunks(
    db: Session,
    document_id: int,
    organization_id: int,
    chunks: list[ChunkRecord],
) -> list[DocumentChunk]:
    records = [
        DocumentChunk(
            document_id=document_id,
            organization_id=organization_id,
            chunk_index=index,
            text=text,
            page_start=page_start,
            page_end=page_end,
        )
        for index, (
            text,
            page_start,
            page_end,
        ) in enumerate(chunks)
    ]

    db.add_all(records)
    db.flush()

    return records


def get_chunks_for_document(
    db: Session,
    document_id: int,
    organization_id: int,
) -> list[DocumentChunk]:
    return (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.organization_id == organization_id,
        )
        .order_by(DocumentChunk.chunk_index)
        .all()
    )


def get_chunks_for_organization(
    db: Session,
    organization_id: int,
) -> list[DocumentChunk]:
    # Only chunks of READY documents are searchable: chunks are written
    # before embedding finishes, so PENDING/PROCESSING/FAILED documents
    # must not be visible to lexical retrieval.
    return (
        db.query(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(
            DocumentChunk.organization_id == organization_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.READY,
        )
        .order_by(
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
        )
        .all()
    )


def delete_chunks_for_document(
    db: Session,
    document_id: int,
    organization_id: int,
) -> None:
    (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.organization_id == organization_id,
        )
        .delete(synchronize_session=False)
    )

def replace_document_chunks(
    db: Session,
    document_id: int,
    organization_id: int,
    chunks: list[ChunkRecord],
) -> list[DocumentChunk]:
    (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.organization_id == organization_id,
        )
        .delete(synchronize_session=False)
    )

    records = [
        DocumentChunk(
            document_id=document_id,
            organization_id=organization_id,
            chunk_index=index,
            text=text,
            page_start=page_start,
            page_end=page_end,
        )
        for index, (
            text,
            page_start,
            page_end,
        ) in enumerate(chunks)
    ]

    db.add_all(records)
    db.flush()

    return records

def get_chunks_by_ids_for_organization(
    db: Session,
    chunk_ids: list[int],
    organization_id: int,
    document_ids: list[int] | None = None,
) -> list[DocumentChunk]:
    if not chunk_ids:
        return []

    # Dense hits are re-hydrated from PostgreSQL, which is the
    # authoritative gate for document status (READY only).
    query = (
        db.query(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(
            DocumentChunk.id.in_(chunk_ids),
            DocumentChunk.organization_id == organization_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.READY,
        )
    )

    if document_ids is not None:
        query = query.filter(
            DocumentChunk.document_id.in_(document_ids)
        )

    return query.all()


def replace_document_chunks_for_attempt(
    db: Session,
    document_id: int,
    organization_id: int,
    attempt_id: str,
    chunks: list[ChunkRecord],
) -> list[DocumentChunk] | None:
    """Replace chunks only while the caller still owns the locked document row.

    The document row lock is held until the caller commits or rolls back,
    preventing ownership recovery/claim transitions from interleaving with
    this chunk replacement. A stale attempt receives None and performs no
    mutation.
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

    (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.organization_id == organization_id,
        )
        .delete(synchronize_session=False)
    )

    records = [
        DocumentChunk(
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
