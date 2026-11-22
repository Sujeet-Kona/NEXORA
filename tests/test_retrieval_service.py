from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from backend.db.models import (
    Document,
    DocumentChunk,
    DocumentStatus,
    User,
)
from backend.repositories.document_repository import create_document
from backend.services.organization_service import (
    create_organization_service,
)
from backend.services.retrieval_service import (
    retrieve_chunks,
    retrieve_active_generation_chunks,
)

from backend.services.retrievers import ActiveGenerationLexicalRetriever


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
    page_start=None,
    page_end=None,
):
    chunk = DocumentChunk(
        document_id=document_id,
        organization_id=organization_id,
        chunk_index=chunk_index,
        text=text,
        page_start=page_start,
        page_end=page_end,
    )

    db.add(chunk)
    db.query(Document).filter(Document.id == document_id).update(
        {"status": DocumentStatus.READY}
    )
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


def test_retrieve_chunks_returns_page_provenance_and_document_name(
    db,
):
    owner = create_user(
        db,
        "retrieve-citation@example.com",
        "Retrieve Citation",
    )

    organization = create_organization_service(
        db=db,
        name="Retrieve Citation Company",
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
        chunk_index=4,
        text="Employees receive 20 days of annual leave.",
        page_start=2,
        page_end=3,
    )

    embedding = Mock()
    embedding.embed_query.return_value = [1.0] * 1024

    qdrant = Mock()
    qdrant.search.return_value.points = [
        Mock(
            id=chunk.id,
            score=0.88,
        )
    ]

    results = retrieve_chunks(
        db=db,
        organization_id=organization.id,
        query="annual leave",
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    assert len(results) == 1
    assert results[0].chunk_index == 4
    assert results[0].document_name == "leave-policy.pdf"
    assert results[0].page_start == 2
    assert results[0].page_end == 3


def test_retrieve_chunks_keeps_foreign_document_names_hidden(
    db,
):
    owner_a = create_user(
        db,
        "retrieve-name-a@example.com",
        "Retrieve Name A",
    )

    owner_b = create_user(
        db,
        "retrieve-name-b@example.com",
        "Retrieve Name B",
    )

    organization_a = create_organization_service(
        db=db,
        name="Retrieve Name Company A",
        user_id=owner_a.id,
    )

    organization_b = create_organization_service(
        db=db,
        name="Retrieve Name Company B",
        user_id=owner_b.id,
    )

    document_b = create_document(
        db=db,
        organization_id=organization_b.id,
        uploaded_by=owner_b.id,
        name="company-b-secret.pdf",
    )

    chunk = create_chunk(
        db=db,
        document_id=document_b.id,
        organization_id=organization_a.id,
        chunk_index=0,
        text="misowned chunk",
        page_start=1,
        page_end=1,
    )

    embedding = Mock()
    embedding.embed_query.return_value = [1.0] * 1024

    qdrant = Mock()
    qdrant.search.return_value.points = [
        Mock(
            id=chunk.id,
            score=0.77,
        )
    ]

    results = retrieve_chunks(
        db=db,
        organization_id=organization_a.id,
        query="misowned chunk",
        embedding_service=embedding,
        qdrant_repository=qdrant,
    )

    # A chunk whose document belongs to another organization is
    # dropped outright, so neither its text nor the foreign document
    # name can reach the caller.
    assert results == []


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
        document_ids=None,
    )


def test_retrieve_chunks_filters_by_document_ids(db):
    owner = create_user(
        db,
        "retrieve-documents@example.com",
        "Retrieve Documents",
    )

    organization = create_organization_service(
        db=db,
        name="Retrieve Documents Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="leave-policy.pdf",
    )

    other_document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="security-policy.pdf",
    )

    chunk = create_chunk(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
        chunk_index=0,
        text="annual leave policy",
    )

    other_chunk = create_chunk(
        db=db,
        document_id=other_document.id,
        organization_id=organization.id,
        chunk_index=0,
        text="password rotation policy",
    )

    embedding = Mock()
    embedding.embed_query.return_value = [1.0] * 1024

    qdrant = Mock()
    qdrant.search.return_value.points = [
        Mock(
            id=chunk.id,
            score=0.95,
        ),
        Mock(
            id=other_chunk.id,
            score=0.90,
        ),
    ]

    results = retrieve_chunks(
        db=db,
        organization_id=organization.id,
        query="annual leave policy",
        embedding_service=embedding,
        qdrant_repository=qdrant,
        document_ids=[document.id],
    )

    assert [result.chunk_id for result in results] == [chunk.id]

    qdrant.search.assert_called_once_with(
        query_vector=[1.0] * 1024,
        organization_id=organization.id,
        limit=5,
        document_ids=[document.id],
    )


def test_retrieve_chunks_document_filter_is_tenant_scoped(db):
    owner_a = create_user(
        db,
        "retrieve-document-scope-a@example.com",
        "Retrieve Document Scope A",
    )

    owner_b = create_user(
        db,
        "retrieve-document-scope-b@example.com",
        "Retrieve Document Scope B",
    )

    organization_a = create_organization_service(
        db=db,
        name="Retrieve Document Scope Company A",
        user_id=owner_a.id,
    )

    organization_b = create_organization_service(
        db=db,
        name="Retrieve Document Scope Company B",
        user_id=owner_b.id,
    )

    document_b = create_document(
        db=db,
        organization_id=organization_b.id,
        uploaded_by=owner_b.id,
        name="company-b-secret.pdf",
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
        document_ids=[document_b.id],
    )

    assert results == []


def test_active_generation_dense_retrieval_hydrates_only_active_sql_chunks(
    db, monkeypatch,
):
    generation_id = "active-generation-uuid"
    active = SimpleNamespace(
        id=91,
        generation_id=generation_id,
        document_id=12,
        organization_id=4,
        chunk_index=3,
        text="Active generation content",
        page_start=2,
        page_end=3,
    )
    inactive = SimpleNamespace(
        id=92,
        generation_id="retired-generation-uuid",
        document_id=12,
        organization_id=4,
        chunk_index=3,
        text="Must not hydrate retired generation",
        page_start=2,
        page_end=3,
    )
    monkeypatch.setattr(
        "backend.services.retrieval_service.get_active_generation_chunks",
        lambda **kwargs: [active],
    )
    monkeypatch.setattr(
        "backend.services.retrieval_service.get_document_names",
        lambda **kwargs: {12: "active.pdf"},
    )
    embedding = Mock()
    embedding.embed_query.return_value = [0.25] * 1024
    qdrant = Mock()
    qdrant.search_generation.return_value.points = [
        SimpleNamespace(
            id="uuid-point-active",
            score=0.91,
            payload={"generation_id": generation_id, "chunk_index": 3},
        ),
        SimpleNamespace(
            id="uuid-point-retired",
            score=0.99,
            payload={"generation_id": inactive.generation_id, "chunk_index": 3},
        ),
    ]

    results = retrieve_active_generation_chunks(
        db=db,
        organization_id=4,
        query="active content",
        embedding_service=embedding,
        qdrant_repository=qdrant,
        limit=2,
    )

    assert len(results) == 1
    assert results[0].chunk_id == active.id
    assert results[0].generation_id == generation_id
    assert results[0].text == active.text
    assert results[0].document_name == "active.pdf"
    assert results[0].score == 0.91
    qdrant.search_generation.assert_called_once_with(
        query_vector=[0.25] * 1024,
        organization_id=4,
        generation_ids=[generation_id],
        limit=2,
        document_ids=None,
    )


def test_active_generation_dense_retrieval_skips_embedding_without_active_chunks(
    db, monkeypatch,
):
    monkeypatch.setattr(
        "backend.services.retrieval_service.get_active_generation_chunks",
        lambda **kwargs: [],
    )
    embedding = Mock()
    qdrant = Mock()
    assert retrieve_active_generation_chunks(
        db=db,
        organization_id=4,
        query="valid query",
        embedding_service=embedding,
        qdrant_repository=qdrant,
    ) == []
    embedding.embed_query.assert_not_called()
    qdrant.search_generation.assert_not_called()


def test_active_generation_lexical_retriever_hydrates_generation_provenance(
    monkeypatch,
):
    chunks = [
        __import__("types").SimpleNamespace(
            id=101,
            document_id=7,
            organization_id=2,
            chunk_index=0,
            text="annual leave policy details",
            page_start=2,
            page_end=4,
            generation_id="active-gen",
        ),
        __import__("types").SimpleNamespace(
            id=102,
            document_id=7,
            organization_id=2,
            chunk_index=1,
            text="password security controls",
            page_start=5,
            page_end=6,
            generation_id="active-gen",
        ),
    ]
    monkeypatch.setattr(
        "backend.services.retrievers.get_active_generation_chunks",
        lambda **kwargs: chunks,
    )
    monkeypatch.setattr(
        "backend.services.retrievers.get_document_names",
        lambda **kwargs: {7: "policy.pdf"},
    )

    results = ActiveGenerationLexicalRetriever(limit=3).retrieve(
        db=None,
        organization_id=2,
        query="annual leave",
    )

    assert len(results) == 1
    assert results[0].chunk_id == 101
    assert results[0].generation_id == "active-gen"
    assert results[0].document_name == "policy.pdf"
    assert results[0].page_start == 2
    assert results[0].page_end == 4


def test_active_generation_lexical_retriever_returns_empty_without_chunks(
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.services.retrievers.get_active_generation_chunks",
        lambda **kwargs: [],
    )
    result = ActiveGenerationLexicalRetriever().retrieve(
        db=None,
        organization_id=2,
        query="annual leave",
    )
    assert result == []
