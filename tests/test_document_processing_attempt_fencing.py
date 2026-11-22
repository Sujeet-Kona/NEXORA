from datetime import datetime, timezone

from backend.db.models import Document, DocumentStatus, User
from backend.repositories.document_repository import (
    claim_document_processing_attempt,
    create_document,
    finalize_document_processing_attempt,
    processing_attempt_is_owner,
    renew_document_processing_lease,
)
from backend.services.organization_service import create_organization_service


def _create_pending_document(db, email):
    owner = User(
        email=email,
        full_name="Ownership Fencing Test",
        password_hash="test-hash",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    organization = create_organization_service(
        db=db,
        name=f"Ownership Fencing Org {email}",
        user_id=owner.id,
    )
    return create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="fencing.pdf",
        storage_key="documents/fencing.pdf",
        content_type="application/pdf",
    )


def test_attempt_owner_can_renew_and_finalize(db):
    document = _create_pending_document(
        db,
        "fencing-success@example.com",
    )
    attempt_id = claim_document_processing_attempt(
        db,
        document.id,
        lease_seconds=30,
    )

    assert attempt_id is not None
    assert processing_attempt_is_owner(db, document.id, attempt_id)
    assert renew_document_processing_lease(
        db,
        document.id,
        attempt_id,
        lease_seconds=60,
    )

    assert finalize_document_processing_attempt(
        db,
        document.id,
        attempt_id,
        DocumentStatus.READY,
    )

    db.refresh(document)
    assert document.status == DocumentStatus.READY
    assert document.processing_attempt_id is None
    assert document.processing_lease_expires_at is None
    assert document.failure_reason is None


def test_stale_attempt_cannot_renew_or_finalize(db):
    document = _create_pending_document(
        db,
        "fencing-stale@example.com",
    )
    current_attempt = claim_document_processing_attempt(
        db,
        document.id,
    )
    assert current_attempt is not None

    stale_attempt = "stale-worker-token"

    assert not processing_attempt_is_owner(
        db,
        document.id,
        stale_attempt,
    )
    assert not renew_document_processing_lease(
        db,
        document.id,
        stale_attempt,
    )
    assert not finalize_document_processing_attempt(
        db,
        document.id,
        stale_attempt,
        DocumentStatus.FAILED,
        failure_reason="stale failure",
    )

    db.refresh(document)
    assert document.status == DocumentStatus.PROCESSING
    assert document.processing_attempt_id == current_attempt
    assert document.failure_reason is None


def test_finalization_rejects_non_terminal_status(db):
    document = _create_pending_document(
        db,
        "fencing-invalid-status@example.com",
    )
    attempt_id = claim_document_processing_attempt(
        db,
        document.id,
    )
    assert attempt_id is not None

    try:
        finalize_document_processing_attempt(
            db,
            document.id,
            attempt_id,
            DocumentStatus.PROCESSING,
        )
    except ValueError as exc:
        assert str(exc) == "final status must be READY or FAILED"
    else:
        raise AssertionError("Expected invalid final status to be rejected")

    db.refresh(document)
    assert document.status == DocumentStatus.PROCESSING
    assert document.processing_attempt_id == attempt_id
