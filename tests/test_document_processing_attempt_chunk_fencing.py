from backend.db.models import DocumentChunk, DocumentStatus
from backend.repositories.document_chunk_repository import (
    create_document_chunks,
    replace_document_chunks_for_attempt,
)
from backend.repositories.document_repository import (
    claim_document_processing_attempt,
    create_document,
)
from tests.document_processing_service_cases import (
    create_organization_service,
    create_user,
)


def _document(db, email):
    user = create_user(db, email, "Chunk Ownership Test")
    organization = create_organization_service(
        db=db,
        name=f"Chunk Ownership Org {email}",
        user_id=user.id,
    )
    return create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="chunks.pdf",
        storage_key="documents/chunks.pdf",
        content_type="application/pdf",
    )


def _texts(db, document_id):
    return [
        row.text
        for row in (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
    ]


def test_stale_attempt_cannot_replace_existing_chunks(db):
    document = _document(db, "chunk-owner-stale@example.com")
    create_document_chunks(
        db,
        document.id,
        document.organization_id,
        [("previous indexed text", 1, 1)],
    )
    db.commit()

    current_attempt = claim_document_processing_attempt(db, document.id)
    assert current_attempt is not None

    stale_result = replace_document_chunks_for_attempt(
        db=db,
        document_id=document.id,
        organization_id=document.organization_id,
        attempt_id="stale-attempt",
        chunks=[("stale replacement", 1, 1)],
    )
    assert stale_result is None
    assert _texts(db, document.id) == ["previous indexed text"]

    current_result = replace_document_chunks_for_attempt(
        db=db,
        document_id=document.id,
        organization_id=document.organization_id,
        attempt_id=current_attempt,
        chunks=[("current attempt text", 1, 1)],
    )
    assert current_result is not None
    db.commit()

    assert _texts(db, document.id) == ["current attempt text"]
    db.refresh(document)
    assert document.status == DocumentStatus.PROCESSING
    assert document.processing_attempt_id == current_attempt


def test_attempt_chunk_replacement_can_write_empty_chunks(db):
    document = _document(db, "chunk-owner-empty@example.com")
    create_document_chunks(
        db,
        document.id,
        document.organization_id,
        [("old chunk", 1, 1)],
    )
    db.commit()

    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None

    result = replace_document_chunks_for_attempt(
        db=db,
        document_id=document.id,
        organization_id=document.organization_id,
        attempt_id=attempt_id,
        chunks=[],
    )
    assert result == []
    db.commit()

    assert _texts(db, document.id) == []
