from backend.db.database import SessionLocal
from backend.db.models import DocumentChunk

ORGANIZATION_ID = 2

db = SessionLocal()

try:
    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.organization_id == ORGANIZATION_ID
        )
        .order_by(
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
        )
        .all()
    )

    print("Total benchmark chunks:", len(chunks))

    for chunk in chunks:
        print("=" * 80)
        print("Document ID:", chunk.document_id)
        print("Chunk ID:", chunk.id)
        print("Chunk index:", chunk.chunk_index)
        print("Characters:", len(chunk.text))
        print()
        print(chunk.text[:500])

finally:
    db.close()
