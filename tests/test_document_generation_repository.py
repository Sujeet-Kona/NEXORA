from datetime import datetime, timedelta, timezone

from backend.db.models import DocumentProcessingGeneration
from backend.repositories.document_generation_repository import (
    create_staging_generation,
    get_staging_generation_chunks,
    replace_staging_generation_chunks,
    promote_staging_generation,
    promote_staging_generation_with_vector_readiness,
    validate_staging_generation_vector_readiness,
    retire_failed_staging_generation,
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


def test_promotion_activates_generation_and_clears_attempt_owner(db):
    document = _document(db, "generation-promotion-success@example.com")
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None
    generation_id = create_staging_generation(
        db,
        document.id,
        document.organization_id,
        attempt_id,
    )
    assert generation_id is not None
    replace_staging_generation_chunks(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        [("promotable staged chunk", 1, 1)],
    )
    assert promote_staging_generation(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
    ) is True
    db.commit()
    db.refresh(document)
    assert document.active_generation_id == generation_id
    assert document.status == "ready"
    assert document.processing_attempt_id is None
    assert document.processing_lease_expires_at is None

    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.id == generation_id)
        .one()
    )
    assert generation.status == "active"



def test_stale_attempt_cannot_promote_generation(db):
    from backend.repositories.document_generation_repository import promote_staging_generation


    document = _document(db, "generation-promotion-stale@example.com")
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None
    generation_id = create_staging_generation(
        db,
        document.id,
        document.organization_id,
        attempt_id,
    )
    assert generation_id is not None
    replace_staging_generation_chunks(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        [("stale candidate", 1, 1)],
    )
    db.commit()

    # A newer owner replaces the token before the stale worker promotes.
    document.processing_attempt_id = "newer-attempt-token"
    db.commit()
    assert promote_staging_generation(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
    ) is False
    db.rollback()
    db.refresh(document)
    assert document.active_generation_id is None
    assert document.processing_attempt_id == "newer-attempt-token"
    assert document.status == "processing"



def test_empty_staging_generation_cannot_be_promoted(db):
    from backend.repositories.document_generation_repository import promote_staging_generation


    document = _document(db, "generation-promotion-empty@example.com")
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

    assert promote_staging_generation(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
    ) is False
    db.rollback()
    db.refresh(document)
    assert document.active_generation_id is None
    assert document.status == "processing"


def test_expired_lease_cannot_replace_or_promote_staging_generation(db):
    document = _document(db, "generation-expired-lease@example.com")
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None
    generation_id = create_staging_generation(
        db,
        document.id,
        document.organization_id,
        attempt_id,
    )
    assert generation_id is not None
    replace_staging_generation_chunks(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        [("original staged content", 1, 1)],
    )
    db.commit()

    document.processing_lease_expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    )
    db.commit()

    assert replace_staging_generation_chunks(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        [("expired worker overwrite", 1, 1)],
    ) is None
    assert promote_staging_generation(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
    ) is False
    db.rollback()
    db.refresh(document)

    staged = get_staging_generation_chunks(
        db,
        generation_id,
        document.organization_id,
    )
    assert [row.text for row in staged] == ["original staged content"]
    assert document.active_generation_id is None
    assert document.status == "processing"
    assert document.processing_attempt_id == attempt_id

class _VectorCountStub:
    def __init__(self, count=None, error=None):
        self.count = count
        self.error = error
        self.calls = []

    def count_generation_chunks(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.count


def _staged_generation_for_readiness(db, email):
    document = _document(db, email)
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None
    generation_id = create_staging_generation(
        db, document.id, document.organization_id, attempt_id
    )
    assert generation_id is not None
    replace_staging_generation_chunks(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        [("chunk one", 1, 1), ("chunk two", 2, 2)],
    )
    db.commit()
    return document, attempt_id, generation_id


def test_vector_readiness_requires_exact_staged_chunk_count(db):
    document, attempt_id, generation_id = _staged_generation_for_readiness(
        db, "generation-readiness-match@example.com"
    )
    vector_repository = _VectorCountStub(count=2)

    assert validate_staging_generation_vector_readiness(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        vector_repository,
    ) is True
    assert vector_repository.calls == [{
        "generation_id": generation_id,
        "document_id": document.id,
        "organization_id": document.organization_id,
    }]


def test_vector_readiness_rejects_incomplete_or_extra_vectors(db):
    document, attempt_id, generation_id = _staged_generation_for_readiness(
        db, "generation-readiness-mismatch@example.com"
    )
    for vector_count in (1, 3, 0):
        assert validate_staging_generation_vector_readiness(
            db,
            generation_id,
            document.id,
            document.organization_id,
            attempt_id,
            _VectorCountStub(count=vector_count),
        ) is False


def test_vector_readiness_fails_closed_on_vector_store_error(db):
    document, attempt_id, generation_id = _staged_generation_for_readiness(
        db, "generation-readiness-error@example.com"
    )
    assert validate_staging_generation_vector_readiness(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        _VectorCountStub(error=RuntimeError("vector store unavailable")),
    ) is False

def test_readiness_gated_promotion_rejects_vector_count_mismatch(db):
    document, attempt_id, generation_id = _staged_generation_for_readiness(
        db, "generation-gated-promotion-reject@example.com"
    )
    assert promote_staging_generation_with_vector_readiness(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        _VectorCountStub(count=1),
    ) is False
    db.refresh(document)
    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.id == generation_id)
        .one()
    )
    assert document.active_generation_id is None
    assert document.status == "processing"
    assert generation.status == "staging"


def test_readiness_gated_promotion_activates_when_counts_match(db):
    document, attempt_id, generation_id = _staged_generation_for_readiness(
        db, "generation-gated-promotion-accept@example.com"
    )
    assert promote_staging_generation_with_vector_readiness(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        _VectorCountStub(count=2),
    ) is True
    db.commit()
    db.refresh(document)
    assert document.active_generation_id == generation_id
    assert document.status == "ready"
    assert document.processing_attempt_id is None
    assert document.processing_lease_expires_at is None

def test_readiness_gated_promotion_fails_closed_on_vector_store_error(db):
    document, attempt_id, generation_id = _staged_generation_for_readiness(
        db, "generation-gated-promotion-error@example.com"
    )
    assert promote_staging_generation_with_vector_readiness(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        _VectorCountStub(error=RuntimeError("qdrant unavailable")),
    ) is False
    db.refresh(document)
    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.id == generation_id)
        .one()
    )
    assert document.active_generation_id is None
    assert document.status == "processing"
    assert generation.status == "staging"

def test_failed_candidate_retirement_preserves_active_generation(db):
    document = _document(db, "generation-failed-candidate-preserves-active@example.com")
    first_attempt = claim_document_processing_attempt(db, document.id)
    assert first_attempt is not None
    active_candidate = create_staging_generation(
        db, document.id, document.organization_id, first_attempt
    )
    assert active_candidate is not None
    replace_staging_generation_chunks(
        db, active_candidate, document.id, document.organization_id,
        first_attempt, [("known good generation", 1, 1)]
    )
    assert promote_staging_generation(
        db, active_candidate, document.id, document.organization_id, first_attempt
    ) is True
    db.commit()

    # A new attempt starts for replacement processing; the previous generation
    # remains active while this candidate is being built.
    replacement_attempt = claim_document_processing_attempt(db, document.id)
    assert replacement_attempt is not None
    failed_candidate = create_staging_generation(
        db, document.id, document.organization_id, replacement_attempt
    )
    assert failed_candidate is not None
    replace_staging_generation_chunks(
        db, failed_candidate, document.id, document.organization_id,
        replacement_attempt, [("replacement partial content", 1, 1)]
    )
    db.commit()

    assert retire_failed_staging_generation(
        db, failed_candidate, document.id, document.organization_id,
        replacement_attempt
    ) is True
    db.commit()
    db.refresh(document)
    generations = (
        db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.document_id == document.id)
        .all()
    )
    statuses = {generation.id: generation.status for generation in generations}
    assert document.active_generation_id == active_candidate
    assert statuses[active_candidate] == "active"
    assert statuses[failed_candidate] == "failed"
    assert document.status == "processing"
