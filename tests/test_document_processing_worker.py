from unittest.mock import Mock

from backend.db.models import Document, DocumentStatus, User
from backend.repositories.document_repository import create_document
from backend.services.document_processing_worker import (
    process_document_background,
)
from backend.services.organization_service import (
    create_organization_service,
)


def create_owner(db, email):
    user = User(
        email=email,
        full_name=email.split("@")[0],
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def create_pending_document(db, email):
    owner = create_owner(db, email)

    organization = create_organization_service(
        db=db,
        name="Worker Company",
        user_id=owner.id,
    )

    return create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="policy.pdf",
        storage_key="documents/policy.pdf",
        content_type="application/pdf",
    )


def get_document_status(db, document_id):
    db.expire_all()

    document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    assert document is not None

    return document.status


def stub_rag_services(monkeypatch):
    monkeypatch.setattr(
        "backend.services.document_processing_worker.get_embedding_service",
        lambda: Mock(),
    )

    monkeypatch.setattr(
        "backend.services.document_processing_worker.get_qdrant_repository",
        lambda: Mock(),
    )


def record_worker_errors(monkeypatch):
    logged_messages = []

    def fake_logger_exception(message, **kwargs):
        logged_messages.append(message)

    monkeypatch.setattr(
        "backend.services.document_processing_worker.logger.exception",
        fake_logger_exception,
    )

    return logged_messages


def test_background_processing_marks_document_ready(
    db,
    session_factory,
    monkeypatch,
):
    document = create_pending_document(
        db,
        "worker-ready@example.com",
    )

    stub_rag_services(monkeypatch)

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: b"fake pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.extract_text",
        lambda **kwargs: "Employee leave policy. " * 100,
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.index_document_chunks",
        lambda **kwargs: None,
    )

    process_document_background(
        document.id,
        session_factory,
    )

    assert get_document_status(
        db,
        document.id,
    ) == DocumentStatus.READY


def test_background_processing_failure_is_contained(
    db,
    session_factory,
    monkeypatch,
):
    document = create_pending_document(
        db,
        "worker-failure@example.com",
    )

    stub_rag_services(monkeypatch)

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: (_ for _ in ()).throw(
            FileNotFoundError("Stored file not found")
        ),
    )

    logged_messages = record_worker_errors(monkeypatch)

    process_document_background(
        document.id,
        session_factory,
    )

    assert get_document_status(
        db,
        document.id,
    ) == DocumentStatus.FAILED
    assert logged_messages == [
        "Background document processing failed"
    ]


def test_background_processing_missing_document_is_contained(
    db,
    session_factory,
    monkeypatch,
):
    stub_rag_services(monkeypatch)

    logged_messages = record_worker_errors(monkeypatch)

    process_document_background(
        999999,
        session_factory,
    )

    assert logged_messages == [
        "Background document processing failed"
    ]


def test_background_processing_closes_session(monkeypatch):
    session = Mock()

    stub_rag_services(monkeypatch)

    monkeypatch.setattr(
        "backend.services.document_processing_worker.process_document",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )

    record_worker_errors(monkeypatch)

    process_document_background(
        1,
        lambda: session,
    )

    session.close.assert_called_once_with()
