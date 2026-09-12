from unittest.mock import Mock

import pytest

from backend.db.models import DocumentChunk, User
from backend.repositories.document_repository import create_document
from backend.services.organization_service import (
    create_organization_service,
)
from backend.services.retrieval_service import (
    retrieve_chunks,
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


def create_chunk(
    db,
    document_id,
    organization_id,
    chunk_index,
    text,
):
    chunk = DocumentChunk(
        document_id=document_id,
        organization_id=organization_id,
        chunk_index=chunk_index,
        text=text,
    )

    db.add(chunk)
    db.commit()
    db.refresh(chunk)

    return chunk


def test_retrieve_chunks_returns_matching_chunk(db):
    owner = create_user(
        db,
        "retrieve-owner@example.com",
        "Retrieve Owner",
    )

    organization = create_organization_service(
        db=db,
        name="Retrieve Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="leave-policy.pdf",
    )

    chunk = create_chunk(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
        chunk_index=0,
        text="Employees receive 20 days of annual leave.",
    )

    embedding = Mock()
    embedding.embed_query.return_value = [1.0] * 1024

    qdrant = Mock()
    qdrant.search.return_value.points = [
        Mock(
            id=chunk.id,
            score=0.95,
        )
    ]

    results = retrieve_chunks(
        db=db,
        organization_id=organization.id,
        query="How many leave days?",
        embedding_service=embedding,
        qdrant_repository=qdrant,
        limit=5,
    )

    assert len(results) == 1
    assert results[0].chunk_id == chunk.id
    assert results[0].document_id == document.id
    assert results[0].organization_id == organization.id
    assert results[0].text == (
        "Employees receive 20 days of annual leave."
    )
    assert results[0].score == 0.95


def test_retrieve_chunks_returns_empty_when_no_results(db):
    embedding = Mock()
    embedding.embed_query.return_value = [1.0] * 1024

    qdrant = Mock()
    qdrant.search.return_value.points = []

    results = retrieve_chunks(
        db=db,
        organization_id=1,
        query="leave policy",
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    assert results == []


def test_retrieve_chunks_rejects_empty_query(db):
    embedding = Mock()
    qdrant = Mock()

    with pytest.raises(
        ValueError,
        match="Query cannot be empty",
    ):
        retrieve_chunks(
            db=db,
            organization_id=1,
            query="   ",
            embedding_service=embedding,
            qdrant_repository=qdrant,
        )

    embedding.embed_query.assert_not_called()
    qdrant.search.assert_not_called()


def test_retrieve_chunks_rejects_invalid_limit(db):
    embedding = Mock()
    qdrant = Mock()

    with pytest.raises(
        ValueError,
        match="Limit must be greater than zero",
    ):
        retrieve_chunks(
            db=db,
            organization_id=1,
            query="leave policy",
            embedding_service=embedding,
            qdrant_repository=qdrant,
            limit=0,
        )

    embedding.embed_query.assert_not_called()
    qdrant.search.assert_not_called()


def test_retrieve_chunks_is_tenant_scoped(db):
    owner_a = create_user(
        db,
        "retrieve-a@example.com",
        "Retrieve A",
    )

    owner_b = create_user(
        db,
        "retrieve-b@example.com",
        "Retrieve B",
    )

    organization_a = create_organization_service(
        db=db,
        name="Retrieve Company A",
        user_id=owner_a.id,
    )

    organization_b = create_organization_service(
        db=db,
        name="Retrieve Company B",
        user_id=owner_b.id,
    )

    document_b = create_document(
        db=db,
        organization_id=organization_b.id,
        uploaded_by=owner_b.id,
        name="private.pdf",
    )

    chunk_b = create_chunk(
        db=db,
        document_id=document_b.id,
        organization_id=organization_b.id,
        chunk_index=0,
        text="PRIVATE COMPANY B DATA",
    )

    embedding = Mock()
    embedding.embed_query.return_value = [1.0] * 1024

    qdrant = Mock()
    qdrant.search.return_value.points = [
        Mock(
            id=chunk_b.id,
            score=0.99,
        )
    ]

    results = retrieve_chunks(
        db=db,
        organization_id=organization_a.id,
        query="private information",
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    assert results == []

    qdrant.search.assert_called_once_with(
        query_vector=[1.0] * 1024,
        organization_id=organization_a.id,
        limit=5,
    )
