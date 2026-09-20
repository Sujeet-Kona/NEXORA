from backend.db.database import SessionLocal
from backend.services.document_processing_service import process_document
from backend.services.embedding_service import EmbeddingService
from backend.repositories.qdrant_repository import QdrantRepository


def process_document_background(
    document_id: int,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
) -> None:
    db = SessionLocal()

    try:
        process_document(
            db=db,
            document_id=document_id,
            embedding_service=embedding_service,
            qdrant_repository=qdrant_repository,
        )
    finally:
        db.close()
