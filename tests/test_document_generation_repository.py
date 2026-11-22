from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from backend.db.models import Document, DocumentProcessingGeneration, DocumentStatus
from backend.repositories.document_generation_repository import (
    create_staging_generation,
    get_staging_generation_chunks,
    replace_staging_generation_chunks,
    promote_staging_generation,
    promote_staging_generation_with_vector_readiness,
    validate_staging_generation_vector_readiness,
    retire_failed_staging_generation,
    cleanup_failed_generation_artifacts,
    list_abandoned_generation_cleanup_candidates,
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
    def __init__(self, count=None, error=None, indexes=None):
        self.count = count
        self.error = error
        self.indexes = indexes
        self.calls = []

    def count_generation_chunks(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.count

    def list_generation_chunk_indexes(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.indexes is not None:
            return self.indexes
        return list(range(self.count or 0))


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


def test_vector_readiness_rejects_same_count_with_wrong_chunk_indexes(db):
    document, attempt_id, generation_id = _staged_generation_for_readiness(
        db, "generation-readiness-index-mismatch@example.com"
    )
    vector_repository = _VectorCountStub(count=2, indexes=[0, 2])

    assert validate_staging_generation_vector_readiness(
        db,
        generation_id,
        document.id,
        document.organization_id,
        attempt_id,
        vector_repository,
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

    # Simulate the document-version upload transition before a replacement
    # processing attempt: READY -> PENDING, preserving the active generation.
    db.query(Document).filter(Document.id == document.id).update(
        {Document.status: DocumentStatus.PENDING},
        synchronize_session=False,
    )
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

class _CleanupVectorStub:
    def __init__(self, initial_count=0, remaining_after_delete=0, error=None):
        self.count = initial_count
        self.remaining_after_delete = remaining_after_delete
        self.error = error
        self.delete_calls = []
        self.count_calls = []

    def delete_generation_chunks(self, **kwargs):
        self.delete_calls.append(kwargs)
        if self.error:
            raise self.error
        self.count = self.remaining_after_delete

    def count_generation_chunks(self, **kwargs):
        self.count_calls.append(kwargs)
        if self.error:
            raise self.error
        return self.count


def _failed_candidate(db, email):
    document = _document(db, email)
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None
    generation_id = create_staging_generation(
        db, document.id, document.organization_id, attempt_id
    )
    assert generation_id is not None
    replace_staging_generation_chunks(
        db, generation_id, document.id, document.organization_id, attempt_id,
        [("failed candidate chunk", 1, 1)]
    )
    assert retire_failed_staging_generation(
        db, generation_id, document.id, document.organization_id, attempt_id
    )
    db.commit()
    return document, attempt_id, generation_id


def test_cleanup_failed_candidate_is_scoped_and_retry_safe(db):
    document, attempt_id, generation_id = _failed_candidate(
        db, "generation-cleanup-retry-safe@example.com"
    )
    vector_store = _CleanupVectorStub(initial_count=1, remaining_after_delete=0)
    args = (db, generation_id, document.id, document.organization_id, attempt_id, vector_store)

    assert cleanup_failed_generation_artifacts(*args) is True
    db.commit()
    assert cleanup_failed_generation_artifacts(*args) is True
    db.commit()
    assert len(vector_store.delete_calls) == 2
    assert len(vector_store.count_calls) == 2
    assert all(call == {
        "generation_id": generation_id,
        "document_id": document.id,
        "organization_id": document.organization_id,
    } for call in vector_store.delete_calls)
    assert get_staging_generation_chunks(db, generation_id, document.organization_id) == []


def test_cleanup_rejects_active_generation(db):
    document = _document(db, "generation-cleanup-active-protection@example.com")
    attempt_id = claim_document_processing_attempt(db, document.id)
    assert attempt_id is not None
    generation_id = create_staging_generation(
        db, document.id, document.organization_id, attempt_id
    )
    assert generation_id is not None
    replace_staging_generation_chunks(
        db, generation_id, document.id, document.organization_id, attempt_id,
        [("active content", 1, 1)]
    )
    assert promote_staging_generation(
        db, generation_id, document.id, document.organization_id, attempt_id
    )
    db.commit()
    vector_store = _CleanupVectorStub(initial_count=1)
    assert cleanup_failed_generation_artifacts(
        db, generation_id, document.id, document.organization_id, attempt_id, vector_store
    ) is False
    assert vector_store.delete_calls == []


def test_cleanup_fails_closed_when_vector_delete_verification_fails(db):
    document, attempt_id, generation_id = _failed_candidate(
        db, "generation-cleanup-vector-error@example.com"
    )
    vector_store = _CleanupVectorStub(error=RuntimeError("qdrant unavailable"))
    assert cleanup_failed_generation_artifacts(
        db, generation_id, document.id, document.organization_id, attempt_id, vector_store
    ) is False
    db.rollback()
    assert get_staging_generation_chunks(db, generation_id, document.organization_id)

def test_cleanup_retains_sql_chunks_when_vector_count_is_nonzero(db):
    document, attempt_id, generation_id = _failed_candidate(
        db, "generation-cleanup-count-not-zero@example.com"
    )
    vector_store = _CleanupVectorStub(initial_count=1, remaining_after_delete=1)
    assert cleanup_failed_generation_artifacts(
        db, generation_id, document.id, document.organization_id, attempt_id, vector_store
    ) is False
    db.rollback()
    assert get_staging_generation_chunks(db, generation_id, document.organization_id)


def test_cleanup_rejects_stale_attempt_without_vector_deletion(db):
    document, attempt_id, generation_id = _failed_candidate(
        db, "generation-cleanup-stale-owner@example.com"
    )
    document.processing_attempt_id = "superseding-attempt"
    db.commit()
    vector_store = _CleanupVectorStub(initial_count=1)
    assert cleanup_failed_generation_artifacts(
        db, generation_id, document.id, document.organization_id, attempt_id, vector_store
    ) is False
    assert vector_store.delete_calls == []

def test_abandoned_cleanup_discovery_excludes_active_generation_and_is_bounded(db):
    active_document, active_attempt, active_generation = _staged_generation_for_readiness(
        db, "generation-discovery-active-exclusion@example.com"
    )
    # Mark the staged generation abandoned and point the document at it to
    # simulate an inconsistent state; discovery must still exclude active IDs.
    active_document.active_generation_id = active_generation
    db.query(DocumentProcessingGeneration).filter(
        DocumentProcessingGeneration.id == active_generation
    ).update({"status": "abandoned"})
    db.commit()

    first_document, first_attempt, first_generation = _failed_candidate(
        db, "generation-discovery-first@example.com"
    )
    second_document, second_attempt, second_generation = _failed_candidate(
        db, "generation-discovery-second@example.com"
    )
    db.query(DocumentProcessingGeneration).filter(
        DocumentProcessingGeneration.id.in_([first_generation, second_generation])
    ).update({"status": "abandoned"}, synchronize_session=False)
    db.commit()

    # Both cleanup candidates have a NULL active-generation pointer. Discovery
    # must retain them (NULL-safe inequality) while excluding the active ID.
    db.refresh(first_document)
    db.refresh(second_document)
    assert first_document.active_generation_id is None
    assert second_document.active_generation_id is None

    bounded_candidates = list_abandoned_generation_cleanup_candidates(db, limit=1)
    assert len(bounded_candidates) == 1
    assert bounded_candidates[0].id in {first_generation, second_generation}
    assert bounded_candidates[0].id != active_generation

    all_candidates = list_abandoned_generation_cleanup_candidates(db, limit=10)
    assert {candidate.id for candidate in all_candidates} == {
        first_generation,
        second_generation,
    }
    assert active_generation not in {candidate.id for candidate in all_candidates}
    assert list_abandoned_generation_cleanup_candidates(db, limit=0) == []
    assert list_abandoned_generation_cleanup_candidates(db, limit=-1) == []


def test_generation_database_constraint_prevents_tenant_mismatch(db):
    document, attempt_id, generation_id = _staged_generation_for_readiness(
        db, "generation-discovery-tenant-mismatch@example.com"
    )
    other_user = create_user(db, "generation-discovery-other-tenant@example.com", "Other Org")
    other_organization = create_organization_service(
        db=db,
        name="Generation Discovery Other Org",
        user_id=other_user.id,
    )

    with pytest.raises(IntegrityError):
        db.query(DocumentProcessingGeneration).filter(
            DocumentProcessingGeneration.id == generation_id
        ).update(
            {
                DocumentProcessingGeneration.status: "abandoned",
                DocumentProcessingGeneration.organization_id: other_organization.id,
            },
            synchronize_session=False,
        )
    db.rollback()

    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.id == generation_id)
        .one()
    )
    assert generation.organization_id == document.organization_id
    assert generation.status == "staging"
