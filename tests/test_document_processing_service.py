from unittest.mock import Mock

import pytest

from backend.core.exceptions import (
    DocumentExtractionError,
    DocumentNotFoundError,
    EmptyDocumentTextError,
)
from backend.db.models import DocumentChunk, DocumentStatus, User
from backend.services import bm25_service
from backend.repositories.document_chunk_repository import (
    create_document_chunks,
)
from backend.repositories.document_repository import (
    create_document,
    update_document_failure,
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


def make_blank_extracted_document():
    return ExtractedDocument(
        pages=(
            ExtractedPage(
                page_number=1,
                text="   ",
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


def test_blank_extraction_marks_document_failed_with_reason(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-blank@example.com",
        "Processing Blank",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Blank Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="scanned.pdf",
        storage_key="documents/scanned.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: b"fake pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.extract_document",
        lambda **kwargs: make_blank_extracted_document(),
    )

    embedding = Mock()
    qdrant = Mock()

    with pytest.raises(EmptyDocumentTextError):
        process_document(
            db=db,
            document_id=document.id,
            embedding_service=embedding,
            qdrant_repository=qdrant,
        )

    db.refresh(document)

    assert document.status == DocumentStatus.FAILED
    assert document.failure_reason == (
        "Document contains no extractable text"
    )
    assert document.page_count is None
    assert document.word_count is None
    assert document.character_count is None

    assert (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .count()
        == 0
    )

    embedding.embed_documents.assert_not_called()


def test_extraction_error_records_extraction_failure_reason(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-extraction-error@example.com",
        "Processing Extraction Error",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Extraction Error Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="corrupt.pdf",
        storage_key="documents/corrupt.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.LocalStorage.read",
        lambda self, key: b"not a real pdf",
    )

    monkeypatch.setattr(
        "backend.services.document_processing_service.extract_document",
        lambda **kwargs: (_ for _ in ()).throw(
            DocumentExtractionError(
                "Failed to extract PDF text"
            )
        ),
    )

    embedding = Mock()
    qdrant = Mock()

    with pytest.raises(DocumentExtractionError):
        process_document(
            db=db,
            document_id=document.id,
            embedding_service=embedding,
            qdrant_repository=qdrant,
        )

    db.refresh(document)

    assert document.status == DocumentStatus.FAILED
    assert document.failure_reason == (
        "Document text extraction failed"
    )


def test_reprocessing_clears_previous_failure_reason(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-retry@example.com",
        "Processing Retry",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Retry Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="retry.pdf",
        storage_key="documents/retry.pdf",
        content_type="application/pdf",
    )

    update_document_failure(
        db=db,
        document=document,
        failure_reason="Document text extraction failed",
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
    assert document.failure_reason is None


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
    assert document.failure_reason == "Document processing failed"
    assert "extraction failed" not in document.failure_reason
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

    # A document that failed during indexing must not stay
    # searchable: its committed chunks and vectors are purged.
    assert (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .count()
        == 0
    )

    qdrant.delete_document_chunks.assert_called_once_with(
        document_id=document.id,
        organization_id=organization.id,
    )

def test_failed_processing_invalidates_organization_bm25_cache(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-bm25-cache@example.com",
        "Processing BM25 Cache",
    )

    organization = create_organization_service(
        db=db,
        name="Processing BM25 Cache Company",
        user_id=owner.id,
    )

    existing = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="existing.pdf",
        storage_key="documents/existing.pdf",
        content_type="application/pdf",
    )
    existing.status = DocumentStatus.READY

    create_document_chunks(
        db=db,
        document_id=existing.id,
        organization_id=organization.id,
        chunks=[
            ("existing annual leave policy", 1, 1),
        ],
    )
    db.commit()

    cached = bm25_service.get_bm25_index(
        db=db,
        organization_id=organization.id,
    )

    assert [
        chunk.id
        for chunk, _score in cached.search(
            query="annual leave",
            limit=5,
        )
    ] == [
        chunk.id
        for chunk in (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == existing.id,
            )
            .all()
        )
    ]

    failed = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="failed.pdf",
        storage_key="documents/failed.pdf",
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

    with pytest.raises(RuntimeError, match="Qdrant unavailable"):
        process_document(
            db=db,
            document_id=failed.id,
            embedding_service=Mock(),
            qdrant_repository=Mock(),
        )

    rebuilt = bm25_service.get_bm25_index(
        db=db,
        organization_id=organization.id,
    )

    rebuilt_ids = {
        chunk.id
        for chunk, _score in rebuilt.search(
            query="annual leave",
            limit=5,
        )
    }

    existing_chunk_ids = {
        chunk.id
        for chunk in (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == existing.id,
            )
            .all()
        )
    }

    failed_chunk_ids = {
        chunk.id
        for chunk in (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == failed.id,
            )
            .all()
        )
    }

    assert rebuilt_ids == existing_chunk_ids
    assert rebuilt_ids.isdisjoint(failed_chunk_ids)


def test_cleanup_failure_does_not_mask_original_processing_error(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "processing-cleanup-failure@example.com",
        "Processing Cleanup Failure",
    )

    organization = create_organization_service(
        db=db,
        name="Processing Cleanup Failure Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="cleanup-failure.pdf",
        storage_key="documents/cleanup-failure.pdf",
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
            RuntimeError("embedding/index failure")
        ),
    )

    qdrant = Mock()
    qdrant.delete_document_chunks.side_effect = RuntimeError(
        "cleanup Qdrant failure"
    )

    with pytest.raises(
        RuntimeError,
        match="embedding/index failure",
    ):
        process_document(
            db=db,
            document_id=document.id,
            embedding_service=Mock(),
            qdrant_repository=qdrant,
        )

    db.refresh(document)

    assert document.status == DocumentStatus.FAILED
    assert document.failure_reason == "Document processing failed"

    assert (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .count()
        == 0
    )

    qdrant.delete_document_chunks.assert_called_once_with(
        document_id=document.id,
        organization_id=organization.id,
    )
