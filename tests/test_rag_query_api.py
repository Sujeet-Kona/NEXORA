from unittest.mock import Mock

import pytest

from backend.core.config import settings
from backend.core.exceptions import LLMGenerationError
from backend.db.models import User
from backend.dependencies.rag import (
    get_embedding_service,
    get_ollama_client,
    get_qdrant_repository,
)
from backend.main import app
from backend.repositories.document_chunk_repository import (
    create_document_chunk,
)
from backend.repositories.document_repository import (
    create_document,
)
from backend.services import bm25_service


PASSWORD = "MySecret123!"


@pytest.fixture(autouse=True)
def clear_bm25_cache():
    bm25_service._cache.clear()

    yield

    bm25_service._cache.clear()


def auth_header(token):
    return {
        "Authorization": f"Bearer {token}",
    }


def register_and_login(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def create_organization(client, token, name):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
        headers=auth_header(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def get_user(db, email):
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    assert user is not None

    return user


def build_query_tenant(client, db, email, organization_name):
    token = register_and_login(client, email)

    organization_id = create_organization(
        client,
        token,
        organization_name,
    )

    return {
        "token": token,
        "organization_id": organization_id,
        "user": get_user(db, email),
    }


def stub_query_dependencies(
    monkeypatch,
    points=None,
):
    embedding = Mock()
    embedding.embed_query.return_value = (
        [0.1] * settings.embedding_dimension
    )

    qdrant = Mock()
    qdrant.search.return_value.points = [
        Mock(
            id=chunk_id,
            score=score,
        )
        for chunk_id, score in (points or [])
    ]

    llm = Mock()
    llm.generate.return_value = "stubbed answer"

    class StubReranker:
        def rerank(
            self,
            query,
            chunks,
        ):
            return chunks

    monkeypatch.setattr(
        "backend.services.hybrid_retrieval_service.get_reranker",
        lambda: StubReranker(),
    )

    app.dependency_overrides[get_embedding_service] = (
        lambda: embedding
    )
    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )
    app.dependency_overrides[get_ollama_client] = lambda: llm

    return llm


def post_query(
    client,
    tenant,
    question,
    document_ids=None,
):
    payload = {"question": question}

    if document_ids is not None:
        payload["document_ids"] = document_ids

    return client.post(
        f"/api/v1/organizations/{tenant['organization_id']}"
        "/query",
        json=payload,
        headers=auth_header(tenant["token"]),
    )


def test_query_sources_include_citation_metadata(
    client,
    db,
    monkeypatch,
):
    tenant = build_query_tenant(
        client,
        db,
        "citation-owner@example.com",
        "Citation Company",
    )

    document = create_document(
        db=db,
        organization_id=tenant["organization_id"],
        uploaded_by=tenant["user"].id,
        name="leave-policy.pdf",
    )

    chunk = create_document_chunk(
        db=db,
        document_id=document.id,
        organization_id=tenant["organization_id"],
        chunk_index=1,
        text="Employees receive 20 days of annual leave.",
        page_start=2,
        page_end=3,
    )

    db.commit()
    db.refresh(chunk)

    stub_query_dependencies(
        monkeypatch,
        points=[(chunk.id, 0.93)],
    )

    response = post_query(
        client,
        tenant,
        "How many annual leave days?",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == "stubbed answer"
    assert body["sources"] == [
        {
            "citation_index": 1,
            "chunk_id": chunk.id,
            "document_id": document.id,
            "document_name": "leave-policy.pdf",
            "chunk_index": 1,
            "score": 0.93,
            "page_start": 2,
            "page_end": 3,
        }
    ]


def test_query_assigns_sequential_citation_index_in_retrieval_order(
    client,
    db,
    monkeypatch,
):
    tenant = build_query_tenant(
        client,
        db,
        "citation-order-owner@example.com",
        "Citation Order Company",
    )

    document = create_document(
        db=db,
        organization_id=tenant["organization_id"],
        uploaded_by=tenant["user"].id,
        name="handbook.pdf",
    )

    first = create_document_chunk(
        db=db,
        document_id=document.id,
        organization_id=tenant["organization_id"],
        chunk_index=0,
        text="First annual leave clause.",
    )

    second = create_document_chunk(
        db=db,
        document_id=document.id,
        organization_id=tenant["organization_id"],
        chunk_index=1,
        text="Second annual leave clause.",
    )

    db.commit()
    db.refresh(first)
    db.refresh(second)

    stub_query_dependencies(
        monkeypatch,
        points=[
            (second.id, 0.99),
            (first.id, 0.80),
        ],
    )

    response = post_query(
        client,
        tenant,
        "annual leave clauses",
    )

    assert response.status_code == 200

    sources = response.json()["sources"]

    assert [
        source["citation_index"] for source in sources
    ] == [1, 2]

    assert [
        source["chunk_id"] for source in sources
    ] == [second.id, first.id]


def test_query_sources_report_missing_pages_as_null(
    client,
    db,
    monkeypatch,
):
    tenant = build_query_tenant(
        client,
        db,
        "unmapped-owner@example.com",
        "Unmapped Company",
    )

    document = create_document(
        db=db,
        organization_id=tenant["organization_id"],
        uploaded_by=tenant["user"].id,
        name="unmapped.pdf",
    )

    chunk = create_document_chunk(
        db=db,
        document_id=document.id,
        organization_id=tenant["organization_id"],
        chunk_index=0,
        text="Unmapped annual leave clause.",
    )

    db.commit()
    db.refresh(chunk)

    stub_query_dependencies(
        monkeypatch,
        points=[(chunk.id, 0.61)],
    )

    response = post_query(
        client,
        tenant,
        "annual leave clause",
    )

    assert response.status_code == 200

    sources = response.json()["sources"]

    assert len(sources) == 1
    assert sources[0]["document_name"] == "unmapped.pdf"
    assert sources[0]["page_start"] is None
    assert sources[0]["page_end"] is None


def test_query_on_organization_without_documents_returns_empty_sources(
    client,
    db,
    monkeypatch,
):
    tenant = build_query_tenant(
        client,
        db,
        "empty-corpus-owner@example.com",
        "Empty Corpus Company",
    )

    llm = stub_query_dependencies(monkeypatch)

    response = post_query(
        client,
        tenant,
        "What is the annual leave policy?",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["sources"] == []
    assert body["answer"] == (
        "The available documents do not contain "
        "enough information to answer this question."
    )

    llm.generate.assert_not_called()


def test_query_filters_sources_by_document_ids(
    client,
    db,
    monkeypatch,
):
    tenant = build_query_tenant(
        client,
        db,
        "document-filter-owner@example.com",
        "Document Filter Company",
    )

    document = create_document(
        db=db,
        organization_id=tenant["organization_id"],
        uploaded_by=tenant["user"].id,
        name="leave-policy.pdf",
    )

    other_document = create_document(
        db=db,
        organization_id=tenant["organization_id"],
        uploaded_by=tenant["user"].id,
        name="security-policy.pdf",
    )

    chunk = create_document_chunk(
        db=db,
        document_id=document.id,
        organization_id=tenant["organization_id"],
        chunk_index=0,
        text="Employees receive 20 days of annual leave.",
    )

    other_chunk = create_document_chunk(
        db=db,
        document_id=other_document.id,
        organization_id=tenant["organization_id"],
        chunk_index=0,
        text="Passwords must rotate every 90 days.",
    )

    db.commit()
    db.refresh(chunk)
    db.refresh(other_chunk)

    stub_query_dependencies(
        monkeypatch,
        points=[
            (chunk.id, 0.95),
            (other_chunk.id, 0.90),
        ],
    )

    response = post_query(
        client,
        tenant,
        "How many annual leave days?",
        document_ids=[other_document.id],
    )

    assert response.status_code == 200

    sources = response.json()["sources"]

    assert [
        source["document_id"]
        for source in sources
    ] == [other_document.id]


def test_query_rejects_empty_document_ids(
    client,
    db,
    monkeypatch,
):
    tenant = build_query_tenant(
        client,
        db,
        "empty-document-filter@example.com",
        "Empty Document Filter Company",
    )

    llm = stub_query_dependencies(monkeypatch)

    response = post_query(
        client,
        tenant,
        "How many annual leave days?",
        document_ids=[],
    )

    assert response.status_code == 422

    llm.generate.assert_not_called()


def test_query_cannot_reach_foreign_document_ids(
    client,
    db,
    monkeypatch,
):
    tenant_a = build_query_tenant(
        client,
        db,
        "document-scope-a@example.com",
        "Document Scope Company A",
    )

    tenant_b = build_query_tenant(
        client,
        db,
        "document-scope-b@example.com",
        "Document Scope Company B",
    )

    document_b = create_document(
        db=db,
        organization_id=tenant_b["organization_id"],
        uploaded_by=tenant_b["user"].id,
        name="company-b-secret.pdf",
    )

    chunk_b = create_document_chunk(
        db=db,
        document_id=document_b.id,
        organization_id=tenant_b["organization_id"],
        chunk_index=0,
        text="PRIVATE COMPANY B DATA",
    )

    db.commit()
    db.refresh(chunk_b)

    stub_query_dependencies(
        monkeypatch,
        points=[(chunk_b.id, 0.99)],
    )

    response = post_query(
        client,
        tenant_a,
        "How many annual leave days?",
        document_ids=[document_b.id],
    )

    assert response.status_code == 200

    body = response.json()

    assert body["sources"] == []
    assert body["answer"] == (
        "The available documents do not contain "
        "enough information to answer this question."
    )


def test_query_respects_configured_retrieval_top_k(
    client,
    db,
    monkeypatch,
):
    tenant = build_query_tenant(
        client,
        db,
        "top-k-owner@example.com",
        "Top K Company",
    )

    document = create_document(
        db=db,
        organization_id=tenant["organization_id"],
        uploaded_by=tenant["user"].id,
        name="leave-policy.pdf",
    )

    chunks = [
        create_document_chunk(
            db=db,
            document_id=document.id,
            organization_id=tenant["organization_id"],
            chunk_index=index,
            text=f"annual leave clause number {index}",
        )
        for index in range(3)
    ]

    db.commit()

    for chunk in chunks:
        db.refresh(chunk)

    stub_query_dependencies(
        monkeypatch,
        points=[
            (chunk.id, 0.9 - index / 10)
            for index, chunk in enumerate(chunks)
        ],
    )

    monkeypatch.setattr(settings, "retrieval_top_k", 1)

    response = post_query(
        client,
        tenant,
        "annual leave clause",
    )

    assert response.status_code == 200
    assert len(response.json()["sources"]) == 1

    monkeypatch.setattr(settings, "retrieval_top_k", 3)

    response = post_query(
        client,
        tenant,
        "annual leave clause",
    )

    assert response.status_code == 200
    assert len(response.json()["sources"]) == 3


def test_query_returns_503_when_llm_provider_fails(
    client,
    db,
    monkeypatch,
):
    tenant = build_query_tenant(
        client,
        db,
        "llm-failure@example.com",
        "LLM Failure Company",
    )

    document = create_document(
        db=db,
        organization_id=tenant["organization_id"],
        uploaded_by=tenant["user"].id,
        name="leave-policy.pdf",
    )

    chunk = create_document_chunk(
        db=db,
        document_id=document.id,
        organization_id=tenant["organization_id"],
        chunk_index=0,
        text="Employees receive 20 days of annual leave.",
    )

    db.commit()
    db.refresh(chunk)

    llm = stub_query_dependencies(
        monkeypatch,
        points=[(chunk.id, 0.93)],
    )

    llm.generate.side_effect = LLMGenerationError(
        "Ollama model 'missing-model' was not found"
    )

    response = post_query(
        client,
        tenant,
        "How many annual leave days?",
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "LLM provider request failed"
    }
