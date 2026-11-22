from types import SimpleNamespace
import pytest

from backend.core.config import settings
from backend.db.models import DocumentProcessingGeneration, DocumentStatus
from backend.repositories.document_generation_repository import (
    create_staging_generation,
    get_active_generation_chunks,
    promote_staging_generation,
    replace_staging_generation_chunks,
)
from backend.repositories.document_repository import claim_document_processing_attempt
from backend.repositories.document_repository import create_document
from backend.services.document_generation_processing_service import (
    process_document_generation,
)
from tests.document_processing_service_cases import (
    create_organization_service,
    create_user,
)


def _pending_document(db, email):
    user = create_user(db, email, "Generation Worker Test")
    organization = create_organization_service(
        db=db,
        name=f"Generation Worker Org {email}",
        user_id=user.id,
    )
    return create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="worker.pdf",
        storage_key="organizations/worker.pdf",
        content_type="application/pdf",
    )


class _VectorRepository:
    def __init__(self, fail_upsert=False):
        self.records = []
        self.fail_upsert = fail_upsert

    def upsert_generation_chunks(self, records):
        if self.fail_upsert:
            raise RuntimeError("Qdrant write failed")
        self.records.extend(records)

    def list_generation_chunk_indexes(self, **scope):
        return sorted(record[4] for record in self.records)


class _Embeddings:
    def embed_documents(self, texts):
        return [[0.1] * settings.embedding_dimension for _ in texts]


def _stub_extraction(monkeypatch):
    monkeypatch.setattr(
        "backend.services.document_generation_processing_service.LocalStorage.read",
        lambda self, key: b"fake bytes",
    )
    extracted = SimpleNamespace(
        text="extractable document text",
        page_count=1,
        word_count=3,
        character_count=len("extractable document text"),
    )
    spans = [
        SimpleNamespace(text="first chunk", page_start=1, page_end=1),
        SimpleNamespace(text="second chunk", page_start=1, page_end=1),
    ]
    monkeypatch.setattr(
        "backend.services.document_generation_processing_service.extract_document",
        lambda **kwargs: extracted,
    )
    monkeypatch.setattr(
        "backend.services.document_generation_processing_service.split_document",
        lambda document: spans,
    )


def test_attempt_owned_generation_processing_promotes_ready_document(
    db,
    monkeypatch,
):
    document = _pending_document(db, "generation-worker-success@example.com")
    _stub_extraction(monkeypatch)
    vectors = _VectorRepository()

    result = process_document_generation(
        db,
        document.id,
        _Embeddings(),
        vectors,
    )

    db.refresh(document)
    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.id == document.active_generation_id)
        .one()
    )
    assert result is True
    assert document.status == DocumentStatus.READY
    assert document.processing_attempt_id is None
    assert document.processing_lease_expires_at is None
    assert document.active_generation_id == generation.id
    assert generation.status == "active"
    assert len(vectors.records) == 2
    assert document.page_count == 1
    assert document.word_count == 3
    assert document.character_count == len("extractable document text")


def test_generation_processing_failure_preserves_no_active_generation(
    db,
    monkeypatch,
):
    document = _pending_document(db, "generation-worker-failure@example.com")
    _stub_extraction(monkeypatch)
    vectors = _VectorRepository(fail_upsert=True)

    result = process_document_generation(
        db,
        document.id,
        _Embeddings(),
        vectors,
    )

    db.refresh(document)
    failed_generation = (
        db.query(DocumentProcessingGeneration)
        .filter(
            DocumentProcessingGeneration.document_id == document.id,
        )
        .one()
    )
    assert result is False
    assert document.status == DocumentStatus.FAILED
    assert document.active_generation_id is None
    assert document.processing_attempt_id is None
    assert failed_generation.status == "failed"


def test_generation_processing_does_not_claim_ready_document(db):
    document = _pending_document(db, "generation-worker-not-claimable@example.com")
    document.status = DocumentStatus.READY
    db.commit()
    vectors = _VectorRepository()

    result = process_document_generation(
        db,
        document.id,
        _Embeddings(),
        vectors,
    )

    db.refresh(document)
    assert result is False
    assert document.status == DocumentStatus.READY
    assert vectors.records == []


def test_failed_replacement_keeps_previous_active_generation_retrievable(
    db,
    monkeypatch,
):
    document = _pending_document(
        db,
        "generation-worker-replacement-failure@example.com",
    )
    previous_attempt = claim_document_processing_attempt(db, document.id)
    assert previous_attempt is not None
    previous_generation = create_staging_generation(
        db,
        document.id,
        document.organization_id,
        previous_attempt,
    )
    assert previous_generation is not None
    replace_staging_generation_chunks(
        db,
        previous_generation,
        document.id,
        document.organization_id,
        previous_attempt,
        [("previous active policy content", 1, 1)],
    )
    assert promote_staging_generation(
        db,
        previous_generation,
        document.id,
        document.organization_id,
        previous_attempt,
    )
    db.commit()

    document.storage_key = "organizations/replacement.pdf"
    document.version = 2
    document.status = DocumentStatus.PENDING
    db.commit()
    monkeypatch.setattr(
        "backend.services.document_generation_processing_service.LocalStorage.read",
        lambda self, key: (_ for _ in ()).throw(
            FileNotFoundError("Replacement file unavailable")
        ),
    )

    result = process_document_generation(
        db,
        document.id,
        _Embeddings(),
        _VectorRepository(),
    )

    db.refresh(document)
    active_chunks = get_active_generation_chunks(
        db,
        organization_id=document.organization_id,
        document_ids=[document.id],
    )
    assert result is False
    assert document.status == DocumentStatus.FAILED
    assert document.active_generation_id == previous_generation
    assert [(chunk.text, chunk.generation_id) for chunk in active_chunks] == [
        ("previous active policy content", previous_generation),
    ]


def test_generation_index_parity_failure_finalizes_owned_attempt(
    db,
    monkeypatch,
):
    document = _pending_document(
        db,
        "generation-worker-parity-failure@example.com",
    )
    _stub_extraction(monkeypatch)

    class MissingVectorIndex(_VectorRepository):
        def list_generation_chunk_indexes(self, **scope):
            return []

    vectors = MissingVectorIndex()
    result = process_document_generation(
        db,
        document.id,
        _Embeddings(),
        vectors,
    )

    db.refresh(document)
    generation = (
        db.query(DocumentProcessingGeneration)
        .filter(DocumentProcessingGeneration.document_id == document.id)
        .one()
    )
    assert result is False
    assert document.status == DocumentStatus.FAILED
    assert document.processing_attempt_id is None
    assert document.processing_lease_expires_at is None
    assert generation.status == "failed"
    assert len(vectors.records) == 2
