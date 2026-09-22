import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.core.logging import LOGGER_NAME
from backend.dependencies.rag import (
    get_embedding_service,
    get_qdrant_repository,
)
from backend.services.document_processing_service import process_document


logger = logging.getLogger(LOGGER_NAME)


def process_document_background(
    document_id: int,
    session_factory: Callable[[], Session],
) -> None:
    db = session_factory()

    try:
        process_document(
            db=db,
            document_id=document_id,
            embedding_service=get_embedding_service(),
            qdrant_repository=get_qdrant_repository(),
        )
    except Exception:
        logger.exception(
            "Background document processing failed",
            extra={"document_id": document_id},
        )
    finally:
        db.close()
