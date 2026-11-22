from datetime import datetime, timezone

import pytest

from backend.db.models import DocumentStatus
from backend.repositories.document_repository import (
    claim_document_processing_attempt,
    create_document,
)
from tests.document_processing_service_cases import (
    create_organization_service,
    create_user,
)


def _pending_document(db, email: str):
    user = create_user(db, email, "Attempt Claim Test")
    organization = create_organization_service(
        db=db,
        name=f"Attempt Claim Org {email}",
        user_id=user.id,
    )
    return create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="claim.pdf",
        storage_key="documents/claim.pdf",
        content_type="application/pdf",
    )


def test_atomic_claim_sets_processing_attempt_and_lease(db):
    document = _pending_document(db, "attempt-claim-success@example.com")

    attempt_id = claim_document_processing_attempt(
        db=db,
        document_id=document.id,
        lease_seconds=90,
    )

    db.refresh(document)
    assert attempt_id is not None
    assert document.status == DocumentStatus.PROCESSING
    assert document.processing_attempt_id == attempt_id
    assert document.processing_lease_expires_at is not None
    assert document.processing_lease_expires_at > datetime.now(timezone.utc).replace(
        tzinfo=None
    )


def test_second_claim_cannot_take_processing_document(db):
    document = _pending_document(db, "attempt-claim-duplicate@example.com")

    first_attempt = claim_document_processing_attempt(
        db=db,
        document_id=document.id,
    )
    second_attempt = claim_document_processing_attempt(
        db=db,
        document_id=document.id,
    )

    db.refresh(document)
    assert first_attempt is not None
    assert second_attempt is None
    assert document.processing_attempt_id == first_attempt
    assert document.status == DocumentStatus.PROCESSING


@pytest.mark.parametrize("lease_seconds", [0, -1])
def test_claim_rejects_nonpositive_lease(db, lease_seconds):
    with pytest.raises(ValueError, match="lease_seconds must be positive"):
        claim_document_processing_attempt(
            db=None,
            document_id=1,
            lease_seconds=lease_seconds,
        )
