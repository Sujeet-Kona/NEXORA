from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from backend.db.models import Document, DocumentStatus, User
from backend.dependencies.database import get_session_factory
from backend.main import app, recover_stale_processing_jobs
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

    stale_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - STALE_PROCESSING_AFTER
        - timedelta(minutes=1)
    )

    db.execute(
        update(Document)
        .where(Document.id == document.id)
        .values(
            status=DocumentStatus.PROCESSING,
            processing_attempt_id="stale-attempt-token",
            processing_lease_expires_at=stale_at + STALE_PROCESSING_AFTER,
            updated_at=stale_at,
        )
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
    recovered = db.get(Document, document.id)

    assert recovered is not None
    assert recovered.status == DocumentStatus.PENDING
    assert recovered.failure_reason == (
        "Previous processing worker expired; document queued for retry"
    )
    assert recovered.processing_attempt_id is None
    assert recovered.processing_lease_expires_at is None


def test_fresh_processing_document_is_not_recovered(db):
    document = create_processing_document(
        db,
        "recovery-fresh@example.com",
    )
    db.execute(
        update(Document)
        .where(Document.id == document.id)
        .values(
            status=DocumentStatus.PROCESSING,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    db.commit()

    assert recover_stale_document_processing(
        db,
        document.id,
    ) is False

    db.expire_all()
    fresh = db.get(Document, document.id)
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
    recovered_first = db.get(Document, first.id)
    recovered_second = db.get(Document, second.id)
    assert recovered_first.status == DocumentStatus.PENDING
    assert recovered_second.status == DocumentStatus.PENDING
    assert recovered_first.processing_attempt_id is None
    assert recovered_first.processing_lease_expires_at is None
    assert recovered_second.processing_attempt_id is None
    assert recovered_second.processing_lease_expires_at is None


def test_startup_recovery_resolves_overridden_session_factory(
    db,
    session_factory,
    monkeypatch,
):
    document = create_processing_document(
        db,
        "recovery-startup@example.com",
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_session_factory,
        lambda: session_factory,
    )

    recover_stale_processing_jobs()

    db.expire_all()
    recovered = db.get(Document, document.id)

    assert recovered is not None
    assert recovered.status == DocumentStatus.PENDING


def test_document_processing_attempt_fields_round_trip(db):
    document = create_processing_document(
        db,
        "recovery-attempt-schema@example.com",
    )

    attempt_id = "12345678-1234-1234-1234-123456789abc"
    lease_expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)

    db.execute(
        update(Document)
        .where(Document.id == document.id)
        .values(
            processing_attempt_id=attempt_id,
            processing_lease_expires_at=lease_expiry,
        )
    )
    db.commit()

    db.expire_all()
    persisted = db.get(Document, document.id)

    assert persisted is not None
    assert persisted.processing_attempt_id == attempt_id
    assert persisted.processing_lease_expires_at == lease_expiry
