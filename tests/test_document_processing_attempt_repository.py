from datetime import datetime, timedelta, timezone

from backend.db.models import Document, DocumentStatus, User
from backend.repositories.document_repository import (
    claim_document_processing_attempt,
    finalize_document_processing_attempt,
    processing_attempt_is_owner,
    renew_document_processing_lease,
    create_document,
)
from backend.services.organization_service import create_organization_service


def _pending_document(db, email):
    user = User(
        email=email,
        full_name=email.split("@")[0],
        password_hash="test-hash",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    organization = create_organization_service(
        db=db,
        name=f"Attempt Repository Org {email}",
        user_id=user.id,
    )
    return create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="attempt.pdf",
    )


def test_claim_attempt_is_single_owner_and_sets_lease(db):
    document = _pending_document(db, "attempt-claim-single-owner@example.com")

    first_token = claim_document_processing_attempt(db, document.id)
    assert first_token is not None
    assert claim_document_processing_attempt(db, document.id) is None

    db.refresh(document)
    assert document.status == DocumentStatus.PROCESSING
    assert document.processing_attempt_id == first_token
    assert document.processing_lease_expires_at is not None
    assert processing_attempt_is_owner(db, document.id, first_token) is True


def test_lease_renewal_only_succeeds_for_current_unexpired_owner(db):
    document = _pending_document(db, "attempt-lease-renewal@example.com")
    token = claim_document_processing_attempt(db, document.id)
    assert token is not None

    db.refresh(document)
    before = document.processing_lease_expires_at
    assert renew_document_processing_lease(db, document.id, token, lease_seconds=3600)
    db.refresh(document)
    assert document.processing_lease_expires_at > before
    assert processing_attempt_is_owner(db, document.id, token) is True

    assert renew_document_processing_lease(
        db, document.id, "stale-token", lease_seconds=600
    ) is False


def test_expired_attempt_cannot_renew_or_finalize(db):
    document = _pending_document(db, "attempt-expired-owner@example.com")
    token = claim_document_processing_attempt(db, document.id)
    assert token is not None

    db.query(Document).filter(Document.id == document.id).update(
        {
            Document.processing_lease_expires_at:
                datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(seconds=1)
        },
        synchronize_session=False,
    )
    db.commit()

    assert processing_attempt_is_owner(db, document.id, token) is False
    assert renew_document_processing_lease(
        db, document.id, token, lease_seconds=600
    ) is False
    assert finalize_document_processing_attempt(
        db, document.id, token, DocumentStatus.READY
    ) is False

    db.refresh(document)
    assert document.status == DocumentStatus.PROCESSING
    assert document.processing_attempt_id == token


def test_finalization_requires_matching_attempt_and_clears_lease(db):
    document = _pending_document(db, "attempt-finalize-token@example.com")
    token = claim_document_processing_attempt(db, document.id)
    assert token is not None

    assert finalize_document_processing_attempt(
        db, document.id, "wrong-token", DocumentStatus.READY
    ) is False
    db.refresh(document)
    assert document.status == DocumentStatus.PROCESSING
    assert document.processing_attempt_id == token

    assert finalize_document_processing_attempt(
        db, document.id, token, DocumentStatus.READY
    ) is True
    db.refresh(document)
    assert document.status == DocumentStatus.READY
    assert document.processing_attempt_id is None
    assert document.processing_lease_expires_at is None
    assert document.failure_reason is None
