import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.core.logging import LOGGER_NAME
from backend.services.document_processing_recovery import (
    recover_stale_document_processing,
)
from backend.services.providers import (
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
        recovered = recover_stale_document_processing(
            db=db,
            document_id=document_id,
        )

        if recovered:
            logger.warning(
                "Recovered stale document processing job",
                extra={"document_id": document_id},
            )

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
