from backend.db.models import DocumentGenerationChunk, DocumentProcessingGeneration
from backend.repositories.document_generation_repository import (
    create_staging_generation,
    get_staging_generation_chunks,
    replace_staging_generation_chunks,
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
    user = create_user(db, email, "Generation Staging Test")
    organization = create_organization_service(
        db=db,
        name=f"Generation Staging Org {email}",
        user_id=user.id,
    )
    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="staging.pdf",
        storage_key="documents/staging.pdf",
        content_type="application/pdf",
    )
    return document


def test_staging_generation_requires_current_attempt_owner(db):
    document = _document(db, "generation-stale-owner@example.com")
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None

    assert create_staging_generation(
        db,
        document.id,
        document.organization_id,
        "wrong-token",
    ) is None

    generation_id = create_staging_generation(
        db,
        document.id,
        document.organization_id,
        attempt_id,
    )
    assert generation_id is not None
    db.commit()

    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.id == generation_id)
        .one()
    )
    assert generation.attempt_id == attempt_id
    assert generation.status == "staging"
    assert generation.document_id == document.id
    assert generation.organization_id == document.organization_id


def test_staging_chunks_are_generation_and_attempt_scoped(db):
    document = _document(db, "generation-chunk-scope@example.com")
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None
    generation_id = create_staging_generation(
        db,
        document.id,
        document.organization_id,
        attempt_id,
    )
    assert generation_id is not None
    db.commit()

    stale = replace_staging_generation_chunks(
        db,
        generation_id,
        document.id,
        document.organization_id,
        "stale-token",
        [("stale text", 1, 1)],
    )
    assert stale is None
    assert get_staging_generation_chunks(
        db,
        generation_id,
        document.organization_id,
    ) == []

    written = replace_staging_generation_chunks(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        [("first staged chunk", 1, 2), ("second staged chunk", 3, 3)],
    )
    assert written is not None
    db.commit()

    staged = get_staging_generation_chunks(
        db,
        generation_id,
        document.organization_id,
    )
    assert [(row.chunk_index, row.text, row.page_start, row.page_end) for row in staged] == [
        (0, "first staged chunk", 1, 2),
        (1, "second staged chunk", 3, 3),
    ]


def test_staging_chunk_read_is_tenant_scoped(db):
    document = _document(db, "generation-tenant-a@example.com")
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None
    generation_id = create_staging_generation(
        db,
        document.id,
        document.organization_id,
        attempt_id,
    )
    assert generation_id is not None
    db.commit()

    replace_staging_generation_chunks(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        [("tenant private text", 1, 1)],
    )
    db.commit()

    assert get_staging_generation_chunks(
        db,
        generation_id,
        organization_id=document.organization_id + 10000,
    ) == []
