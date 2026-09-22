from unittest.mock import Mock

import pytest

from backend.core.exceptions import DocumentNotFoundError
from backend.db.models import DocumentChunk, DocumentStatus, User
from backend.repositories.document_repository import (
    create_document,
)
from backend.services.document_processing_service import (
    process_document,
)
from backend.services.document_extraction import (
    ExtractedDocument,
    ExtractedPage,
)
from backend.services.organization_service import (
    create_organization_service,
)


def make_extracted_document():
    return ExtractedDocument(
        pages=(
            ExtractedPage(
                page_number=1,
                text="Employee leave policy. " * 100,
            ),
        ),
    )


def make_multipage_extracted_document():
    return ExtractedDocument(
        pages=(
            ExtractedPage(
                page_number=1,
                text="Alpha " * 700,
            ),
            ExtractedPage(
                page_number=2,
                text="Beta " * 700,
            ),
        ),
    )


def create_user(db, email, name):
    user = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def test_missing_document_is_rejected(db):
    embedding = Mock()
    qdrant = Mock()

    with pytest.raises(DocumentNotFoundError):
        process_document(
            db=db,
            document_id=999999,
            embedding_service=embedding,
            qdrant_repository=qdrant,
        )

    embedding.embed_documents.assert_not_called()
    qdrant.upsert_chunks.assert_not_called()


def test_document_transitions_to_processing_then_ready(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-ready@example.com",
        "Processing Ready",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Ready Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="policy.pdf",
        storage_key="documents/policy.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: b"fake pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.extract_document",
        lambda **kwargs: make_extracted_document(),
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.index_document_chunks",
        lambda **kwargs: None,
    )

    embedding = Mock()
    qdrant = Mock()

    process_document(
        db=db,
        document_id=document.id,
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    db.refresh(document)

    assert document.status == DocumentStatus.READY
    assert document.page_count == 1
    assert document.word_count == 300
    assert document.character_count == len(
        ("Employee leave policy. " * 100).strip()
    )


def test_processing_persists_chunk_page_provenance(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-pages@example.com",
        "Processing Pages",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Pages Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="multipage.pdf",
        storage_key="documents/multipage.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: b"fake pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.extract_document",
        lambda **kwargs: make_multipage_extracted_document(),
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.index_document_chunks",
        lambda **kwargs: None,
    )

    embedding = Mock()
    qdrant = Mock()

    process_document(
        db=db,
        document_id=document.id,
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    db.refresh(document)

    assert document.status == DocumentStatus.READY
    assert document.page_count == 2

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    assert len(chunks) >= 3

    for chunk in chunks:
        contains_alpha = "Alpha" in chunk.text
        contains_beta = "Beta" in chunk.text

        assert contains_alpha or contains_beta
        assert chunk.page_start == (
            1 if contains_alpha else 2
        )
        assert chunk.page_end == (
            2 if contains_beta else 1
        )
        assert chunk.page_start <= chunk.page_end


def test_processing_failure_marks_document_failed(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-failed@example.com",
        "Processing Failed",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Failed Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="bad.pdf",
        storage_key="documents/bad.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: b"bad content",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.extract_document",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("extraction failed")
        ),
    )

    embedding = Mock()
    qdrant = Mock()

    with pytest.raises(RuntimeError):
        process_document(
            db=db,
            document_id=document.id,
            embedding_service=embedding,
            qdrant_repository=qdrant,
        )

    db.refresh(document)

    assert document.status == DocumentStatus.FAILED
    assert document.page_count is None
    assert document.word_count is None
    assert document.character_count is None


def test_qdrant_failure_marks_document_failed(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-qdrant-failure@example.com",
        "Processing Qdrant Failure",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Qdrant Failure Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="qdrant-failure.pdf",
        storage_key="documents/qdrant-failure.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: b"fake pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.extract_document",
        lambda **kwargs: make_extracted_document(),
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.index_document_chunks",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("Qdrant unavailable")
        ),
    )

    embedding = Mock()
    qdrant = Mock()

    with pytest.raises(RuntimeError, match="Qdrant unavailable"):
        process_document(
            db=db,
            document_id=document.id,
            embedding_service=embedding,
            qdrant_repository=qdrant,
        )

    db.refresh(document)

    assert document.status == DocumentStatus.FAILED
    assert document.page_count == 1
    assert document.word_count == 300
    assert document.character_count == len(
        ("Employee leave policy. " * 100).strip()
    )
    assert (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .count()
        == 1
    )