from sqlalchemy.orm import Session

from backend.db.models import Document, DocumentChunk, DocumentStatus


def create_document_chunk(
    db: Session,
    document_id: int,
    organization_id: int,
    chunk_index: int,
    text: str,
    page_start: int | None = None,
    page_end: int | None = None,
) -> DocumentChunk:
    chunk = DocumentChunk(
        document_id=document_id,
        organization_id=organization_id,
        chunk_index=chunk_index,
        text=text,
        page_start=page_start,
        page_end=page_end,
    )

    db.add(chunk)

    # Retrieval only sees chunks of READY documents, so fixtures that
    # create searchable chunks mark the parent document READY.
    db.query(Document).filter(Document.id == document_id).update(
        {"status": DocumentStatus.READY}
    )

    return chunk
