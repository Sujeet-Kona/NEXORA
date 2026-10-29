from datetime import datetime, timedelta, timezone

from backend.db.models import DocumentStatus, User
from backend.repositories.document_repository import create_document
from backend.services.document_processing_recovery import (
    STALE_PROCESSING_AFTER,
    recover_stale_document_processing,
    recover_stale_processing_documents,
)
from backend.services.organization_service import create_organization_service


def create_processing_document(db, email):
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
        name="Recovery Company",
        user_id=user.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="policy.pdf",
    )
    document.status = DocumentStatus.PROCESSING
    document.updated_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - STALE_PROCESSING_AFTER
        - timedelta(minutes=1)
    )
    db.commit()
    db.refresh(document)
    return document


def test_stale_processing_document_is_recovered(db):
    document = create_processing_document(
        db,
        "recovery-single@example.com",
    )

    assert recover_stale_document_processing(
        db,
        document.id,
    ) is True

    db.expire_all()
    recovered = db.get(type(document), document.id)

    assert recovered is not None
    assert recovered.status == DocumentStatus.PENDING
    assert recovered.failure_reason == (
        "Previous processing worker expired; document queued for retry"
    )


def test_fresh_processing_document_is_not_recovered(db):
    document = create_processing_document(
        db,
        "recovery-fresh@example.com",
    )
    document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    assert recover_stale_document_processing(
        db,
        document.id,
    ) is False

    db.expire_all()
    fresh = db.get(type(document), document.id)
    assert fresh is not None
    assert fresh.status == DocumentStatus.PROCESSING


def test_startup_recovery_handles_multiple_stale_documents(db):
    first = create_processing_document(
        db,
        "recovery-many-one@example.com",
    )
    second = create_processing_document(
        db,
        "recovery-many-two@example.com",
    )

    assert recover_stale_processing_documents(db) == 2

    db.expire_all()
    assert db.get(type(first), first.id).status == DocumentStatus.PENDING
    assert db.get(type(second), second.id).status == DocumentStatus.PENDING
