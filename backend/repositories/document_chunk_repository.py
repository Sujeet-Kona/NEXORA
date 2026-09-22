from sqlalchemy.orm import Session

from backend.db.models import DocumentChunk


ChunkRecord = tuple[str, int | None, int | None]


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
) -> list[DocumentChunk]:
    if not chunk_ids:
        return []

    return (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.id.in_(chunk_ids),
            DocumentChunk.organization_id == organization_id,
        )
        .all()
    )
