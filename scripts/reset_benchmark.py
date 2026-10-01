from backend.db.database import SessionLocal
from backend.db.models import Document, DocumentChunk
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.storage import LocalStorage
from backend.core.config import settings


ORGANIZATION_ID = 2


db = SessionLocal()
qdrant = QdrantRepository()
storage = LocalStorage(settings.storage_path)

try:
    documents = (
        db.query(Document)
        .filter(
            Document.organization_id == ORGANIZATION_ID
        )
        .order_by(Document.id)
        .all()
    )

    print("Documents to remove:", len(documents))

    for document in documents:
        print("=" * 80)
        print("Removing:", document.id, document.name)

        # Remove vectors first.
        qdrant.delete_document_chunks(
            document_id=document.id,
            organization_id=ORGANIZATION_ID,
        )

        # Remove stored file.
        if document.storage_key:
            storage.delete(document.storage_key)

        # Remove document row.
        db.delete(document)

    db.commit()

    remaining_chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.organization_id
            == ORGANIZATION_ID
        )
        .count()
    )

    remaining_documents = (
        db.query(Document)
        .filter(
            Document.organization_id
            == ORGANIZATION_ID
        )
        .count()
    )

    print("=" * 80)
    print("Remaining benchmark documents:", remaining_documents)
    print("Remaining benchmark chunks:", remaining_chunks)

finally:
    db.close()
