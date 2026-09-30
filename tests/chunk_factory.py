from sqlalchemy.orm import Session

from backend.db.models import DocumentChunk


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

    return chunk
