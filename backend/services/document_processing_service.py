from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import (
    DocumentExtractionError,
    DocumentNotFoundError,
)
from backend.db.models import DocumentStatus
from backend.repositories.document_chunk_repository import (
    replace_document_chunks,
)
from backend.repositories.document_repository import (
    get_document_by_id,
    get_document_by_id_unscoped,
    update_document_extraction_stats,
    update_document_status,
)
from backend.services.bm25_service import invalidate_bm25_index
from backend.services.document_chunking import split_text
from backend.services.document_extraction import extract_document
from backend.services.document_indexing_service import (
    index_document_chunks,
)
from backend.services.embedding_service import EmbeddingService
from backend.repositories.qdrant_repository import (
    QdrantRepository,
)
from backend.services.storage import LocalStorage


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

    update_document_status(
        db=db,
        document=document,
        status=DocumentStatus.PROCESSING,
    )

    try:
        if not document.storage_key:
            raise DocumentExtractionError(
                "Document has no storage key"
            )

        storage = LocalStorage(
            settings.storage_path,
        )

        content = storage.read(
            document.storage_key,
        )

        extracted_document = extract_document(
            filename=document.name,
            content_type=document.content_type,
            content=content,
        )

        chunks = split_text(extracted_document.text)

        replace_document_chunks(
            db=db,
            document_id=document.id,
            organization_id=document.organization_id,
            chunks=chunks,
        )

        update_document_extraction_stats(
            db=db,
            document=document,
            page_count=extracted_document.page_count,
            word_count=extracted_document.word_count,
            character_count=extracted_document.character_count,
        )

        db.commit()

        invalidate_bm25_index(
            document.organization_id,
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

    except Exception:
        db.rollback()

        refreshed_document = get_document_by_id(
            db=db,
            document_id=document_id,
            organization_id=document.organization_id,
        )

        if refreshed_document:
            update_document_status(
                db=db,
                document=refreshed_document,
                status=DocumentStatus.FAILED,
            )

        raise





