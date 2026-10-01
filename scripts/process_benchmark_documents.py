from backend.db.database import SessionLocal
from backend.db.models import Document
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.document_processing_service import process_document
from backend.services.embedding_service import EmbeddingService


ORGANIZATION_ID = 2


db = SessionLocal()
embedding_service = EmbeddingService()
qdrant_repository = QdrantRepository()

try:
    documents = (
        db.query(Document)
        .filter(
            Document.organization_id == ORGANIZATION_ID,
        )
        .order_by(Document.id)
        .all()
    )

    print("Documents to process:", len(documents))

    for document in documents:
        print("=" * 80)
        print("Processing:", document.id, document.name)

        process_document(
            db=db,
            document_id=document.id,
            embedding_service=embedding_service,
            qdrant_repository=qdrant_repository,
        )

        db.expire(document)

        print("Status:", document.status)

finally:
    db.close()
