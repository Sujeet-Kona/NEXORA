from unittest.mock import Mock

from backend.db.models import Document, DocumentStatus, User
from backend.repositories.document_repository import create_document
from backend.services.document_processing_worker import (
    process_document_background,
)
from backend.core.config import settings
from backend.services.document_extraction import (
    ExtractedDocument,
    ExtractedPage,
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


def get_document(db, document_id):
    db.expire_all()

    document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    assert document is not None

    return document


def make_extracted_document():
    return ExtractedDocument(
        pages=(
            ExtractedPage(
                page_number=1,
                text="Employee leave policy. " * 100,
            ),
        ),
    )


def stub_rag_services(monkeypatch):
    embedding = Mock()
    embedding.embed_documents.side_effect = lambda texts: [
        [0.0] * settings.embedding_dimension for _ in texts
    ]
    vector_repo = Mock()
    indexed_records = []
    vector_repo.upsert_generation_chunks.side_effect = lambda records: indexed_records.extend(records)
    vector_repo.list_generation_chunk_indexes.side_effect = lambda **kwargs: sorted(
        record[4] for record in indexed_records
    )
    monkeypatch.setattr(
        "backend.services.document_processing_worker.get_embedding_service",
        lambda: embedding,
    )
    monkeypatch.setattr(
        "backend.services.document_processing_worker.get_qdrant_repository",
        lambda: vector_repo,
    )
    monkeypatch.setattr(
        "backend.services.document_generation_processing_service.LocalStorage.read",
        lambda self, key: b"fake pdf",
    )
    monkeypatch.setattr(
        "backend.services.document_generation_processing_service.extract_document",
        lambda **kwargs: make_extracted_document(),
    )
    monkeypatch.setattr(
        "backend.services.document_generation_processing_service.split_document",
        lambda document: [
            Mock(text="employee leave policy chunk", page_start=1, page_end=1),
            Mock(text="another policy chunk", page_start=1, page_end=1),
        ],
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
        "backend.services.document_generation_processing_service.LocalStorage.read",
        lambda self, key: b"fake pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_generation_processing_service.extract_document",
        lambda **kwargs: make_extracted_document(),
    )

    process_document_background(
        document.id,
        session_factory,
    )

    processed_document = get_document(
        db,
        document.id,
    )

    assert processed_document.status == DocumentStatus.READY
    assert processed_document.page_count == 1
    assert processed_document.word_count == 300
    assert processed_document.character_count == len(
        ("Employee leave policy. " * 100).strip()
    )


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
        "backend.services.document_generation_processing_service.LocalStorage.read",
        lambda self, key: (_ for _ in ()).throw(
            FileNotFoundError("Stored file not found")
        ),
    )

    logged_messages = record_worker_errors(monkeypatch)

    process_document_background(
        document.id,
        session_factory,
    )

    assert get_document(
        db,
        document.id,
    ).status == DocumentStatus.FAILED
    assert logged_messages == []


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

    assert logged_messages == []


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
