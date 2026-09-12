from unittest.mock import Mock

import pytest

from backend.core.exceptions import DocumentNotFoundError
from backend.db.models import User
from backend.repositories.document_repository import (
    create_document,
)
from backend.services.document_indexing_service import (
    index_document_chunks,
)
from backend.services.organization_service import (
    create_organization_service,
)


def create_user(
    db,
    email,
    name,
):
    user = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def test_index_document_returns_zero_for_missing_chunks(db):
    owner = create_user(
        db,
        "index-empty@example.com",
        "Index Empty",
    )

    organization = create_organization_service(
        db=db,
        name="Index Empty Company",
        user_id=owner.id,
    )

    create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="empty.pdf",
    )

    embedding = Mock()
    qdrant = Mock()

    result = index_document_chunks(
        db=db,
        organization_id=organization.id,
        document_id=1,
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    assert result == 0
    embedding.embed_documents.assert_not_called()
    qdrant.upsert_chunks.assert_not_called()


def test_index_document_batches_embeddings(
    db,
    monkeypatch,
):
    owner = create_user(
        db,
        "index-batch@example.com",
        "Index Batch",
    )

    organization = create_organization_service(
        db=db,
        name="Index Batch Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="batch.pdf",
    )

    from backend.db.models import DocumentChunk

    chunks = [
        DocumentChunk(
            document_id=document.id,
            organization_id=organization.id,
            chunk_index=index,
            text=f"chunk {index}",
        )
        for index in range(3)
    ]

    db.add_all(chunks)
    db.commit()

    embedding = Mock()

    embedding.embed_documents.side_effect = [
        [[1.0] * 1024, [2.0] * 1024],
        [[3.0] * 1024],
    ]

    qdrant = Mock()

    monkeypatch.setattr(
        "backend.core.config.settings.embedding_batch_size",
        2,
    )

    result = index_document_chunks(
        db=db,
        organization_id=organization.id,
        document_id=document.id,
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    assert result == 3
    assert embedding.embed_documents.call_count == 2
    assert qdrant.upsert_chunks.call_count == 2


def test_index_document_rejects_wrong_organization(
    db,
):
    owner = create_user(
        db,
        "index-owner@example.com",
        "Index Owner",
    )

    outsider = create_user(
        db,
        "index-outsider@example.com",
        "Index Outsider",
    )

    organization = create_organization_service(
        db=db,
        name="Index Tenant Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="tenant.pdf",
    )

    embedding = Mock()
    qdrant = Mock()

    with pytest.raises(
        DocumentNotFoundError
    ):
        index_document_chunks(
            db=db,
            organization_id=organization.id + 1000,
            document_id=document.id,
            embedding_service=embedding,
            qdrant_repository=qdrant,
        )

    embedding.embed_documents.assert_not_called()
    qdrant.upsert_chunks.assert_not_called()


def test_indexed_payload_comes_from_chunk(
    db,
):
    owner = create_user(
        db,
        "index-payload@example.com",
        "Index Payload",
    )

    organization = create_organization_service(
        db=db,
        name="Index Payload Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="payload.pdf",
    )

    from backend.db.models import DocumentChunk

    chunk = DocumentChunk(
        document_id=document.id,
        organization_id=organization.id,
        chunk_index=7,
        text="payload test",
    )

    db.add(chunk)
    db.commit()
    db.refresh(chunk)

    embedding = Mock()
    embedding.embed_documents.return_value = [
        [1.0] * 1024
    ]

    qdrant = Mock()

    index_document_chunks(
        db=db,
        organization_id=organization.id,
        document_id=document.id,
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    qdrant.upsert_chunks.assert_called_once()

    record = qdrant.upsert_chunks.call_args.args[0][0]

    assert record == (
        chunk.id,
        [1.0] * 1024,
        organization.id,
        document.id,
        7,
    )
def test_index_document_reindexes_existing_vectors(db):
    owner = create_user(
        db,
        "index-reindex@example.com",
        "Index Reindex",
    )

    organization = create_organization_service(
        db=db,
        name="Index Reindex Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="reindex.pdf",
    )

    from backend.db.models import DocumentChunk

    chunks = [
        DocumentChunk(
            document_id=document.id,
            organization_id=organization.id,
            chunk_index=index,
            text=f"chunk {index}",
        )
        for index in range(2)
    ]

    db.add_all(chunks)
    db.commit()

    embedding = Mock()
    embedding.embed_documents.return_value = [
        [1.0] * 1024,
        [2.0] * 1024,
    ]

    qdrant = Mock()

    result = index_document_chunks(
        db=db,
        organization_id=organization.id,
        document_id=document.id,
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    assert result == 2

    qdrant.delete_document_chunks.assert_called_once_with(
        document_id=document.id,
        organization_id=organization.id,
    )

    qdrant.upsert_chunks.assert_called_once()
