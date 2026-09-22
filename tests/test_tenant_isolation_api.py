from unittest.mock import Mock

import pytest

from backend.core.config import settings
from backend.db.models import (
    OrganizationMembership,
    OrganizationRole,
    User,
)
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


def register_and_login(
    client,
    email,
):
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


def auth_header(token):
    return {
        "Authorization": f"Bearer {token}",
    }


def get_user(db, email):
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    assert user is not None

    return user


def create_organization(
    client,
    token,
    name,
):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
        headers=auth_header(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def create_document_via_api(
    client,
    token,
    organization_id,
    name,
):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": name},
        headers=auth_header(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def add_member(
    client,
    owner_token,
    organization_id,
    user_id,
    role=OrganizationRole.MEMBER,
):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": user_id,
            "role": role,
        },
        headers=auth_header(owner_token),
    )

    assert response.status_code == 201

    return response.json()


def build_two_tenants(
    client,
    db,
    suffix,
):
    email_a = f"iso-a-{suffix}@example.com"
    email_b = f"iso-b-{suffix}@example.com"

    token_a = register_and_login(
        client,
        email_a,
    )

    token_b = register_and_login(
        client,
        email_b,
    )

    return {
        "email_a": email_a,
        "email_b": email_b,
        "token_a": token_a,
        "token_b": token_b,
        "user_a": get_user(db, email_a),
        "user_b": get_user(db, email_b),
        "org_a": create_organization(
            client,
            token_a,
            f"Isolation A {suffix}",
        ),
        "org_b": create_organization(
            client,
            token_b,
            f"Isolation B {suffix}",
        ),
    }


def register_outsider(
    client,
    db,
    suffix,
):
    """A third tenant with no membership in either of the others."""

    email = f"iso-c-{suffix}@example.com"

    token = register_and_login(
        client,
        email,
    )

    return {
        "email": email,
        "token": token,
        "user": get_user(db, email),
        "org": create_organization(
            client,
            token,
            f"Isolation C {suffix}",
        ),
    }


def test_outsider_cannot_list_organization_documents(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "list",
    )

    response = client.get(
        f"/api/v1/organizations/{tenants['org_a']}/documents",
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }


def test_document_list_does_not_leak_other_tenant_documents(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "leak",
    )

    document_a = create_document_via_api(
        client,
        tenants["token_a"],
        tenants["org_a"],
        "company-a-private.pdf",
    )

    document_b = create_document_via_api(
        client,
        tenants["token_b"],
        tenants["org_b"],
        "company-b-private.pdf",
    )

    response = client.get(
        f"/api/v1/organizations/{tenants['org_b']}/documents",
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 200

    returned_ids = {
        document["id"]
        for document in response.json()
    }

    assert returned_ids == {document_b}
    assert document_a not in returned_ids


def test_outsider_cannot_read_document_through_foreign_organization_path(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "read",
    )

    document_a = create_document_via_api(
        client,
        tenants["token_a"],
        tenants["org_a"],
        "company-a-secret-name.pdf",
    )

    response = client.get(
        (
            f"/api/v1/organizations/{tenants['org_b']}"
            f"/documents/{document_a}"
        ),
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 404
    assert "company-a-secret-name" not in response.text


def test_outsider_cannot_read_document_from_foreign_organization(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "readguard",
    )

    document_a = create_document_via_api(
        client,
        tenants["token_a"],
        tenants["org_a"],
        "company-a-guarded.pdf",
    )

    response = client.get(
        (
            f"/api/v1/organizations/{tenants['org_a']}"
            f"/documents/{document_a}"
        ),
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 403


def test_outsider_cannot_update_document_status(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "patch",
    )

    document_a = create_document_via_api(
        client,
        tenants["token_a"],
        tenants["org_a"],
        "company-a-patch.pdf",
    )

    response = client.patch(
        (
            f"/api/v1/organizations/{tenants['org_a']}"
            f"/documents/{document_a}"
        ),
        json={"status": "ready"},
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 403

    verify = client.get(
        (
            f"/api/v1/organizations/{tenants['org_a']}"
            f"/documents/{document_a}"
        ),
        headers=auth_header(tenants["token_a"]),
    )

    assert verify.status_code == 200
    assert verify.json()["status"] == "pending"


def test_outsider_cannot_delete_document(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "delete",
    )

    document_a = create_document_via_api(
        client,
        tenants["token_a"],
        tenants["org_a"],
        "company-a-delete.pdf",
    )

    response = client.delete(
        (
            f"/api/v1/organizations/{tenants['org_a']}"
            f"/documents/{document_a}"
        ),
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 403

    verify = client.get(
        (
            f"/api/v1/organizations/{tenants['org_a']}"
            f"/documents/{document_a}"
        ),
        headers=auth_header(tenants["token_a"]),
    )

    assert verify.status_code == 200


def test_delete_under_foreign_organization_path_is_not_found(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "deletepath",
    )

    document_a = create_document_via_api(
        client,
        tenants["token_a"],
        tenants["org_a"],
        "company-a-delete-path.pdf",
    )

    response = client.delete(
        (
            f"/api/v1/organizations/{tenants['org_b']}"
            f"/documents/{document_a}"
        ),
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 404

    verify = client.get(
        (
            f"/api/v1/organizations/{tenants['org_a']}"
            f"/documents/{document_a}"
        ),
        headers=auth_header(tenants["token_a"]),
    )

    assert verify.status_code == 200


def test_outsider_cannot_list_organization_members(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "members",
    )

    response = client.get(
        f"/api/v1/organizations/{tenants['org_a']}/members",
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }


def test_outsider_cannot_add_organization_member(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "addmember",
    )

    response = client.post(
        f"/api/v1/organizations/{tenants['org_a']}/members",
        json={
            "user_id": tenants["user_b"].id,
            "role": "member",
        },
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 403

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == tenants["org_a"],
            OrganizationMembership.user_id
            == tenants["user_b"].id,
        )
        .first()
    )

    assert membership is None


def test_outsider_cannot_update_member_role(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "updaterole",
    )

    outsider = register_outsider(
        client,
        db,
        "updaterole",
    )

    member = add_member(
        client,
        tenants["token_a"],
        tenants["org_a"],
        tenants["user_b"].id,
    )

    response = client.patch(
        (
            f"/api/v1/organizations/{tenants['org_a']}"
            f"/members/{member['user_id']}"
        ),
        json={"role": "admin"},
        headers=auth_header(outsider["token"]),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.id == member["id"],
        )
        .first()
    )

    assert membership.role == OrganizationRole.MEMBER


def test_outsider_cannot_remove_organization_member(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "removemember",
    )

    outsider = register_outsider(
        client,
        db,
        "removemember",
    )

    member = add_member(
        client,
        tenants["token_a"],
        tenants["org_a"],
        tenants["user_b"].id,
    )

    response = client.delete(
        (
            f"/api/v1/organizations/{tenants['org_a']}"
            f"/members/{member['user_id']}"
        ),
        headers=auth_header(outsider["token"]),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.id == member["id"],
        )
        .first()
    )

    assert membership is not None


def test_outsider_cannot_query_knowledge_base(
    client,
    db,
):
    tenants = build_two_tenants(
        client,
        db,
        "query",
    )

    embedding = Mock()
    embedding.embed_query.return_value = (
        [0.1] * settings.embedding_dimension
    )

    qdrant = Mock()
    qdrant.search.return_value.points = []

    llm = Mock()

    app.dependency_overrides[get_embedding_service] = (
        lambda: embedding
    )
    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )
    app.dependency_overrides[get_ollama_client] = lambda: llm

    response = client.post(
        f"/api/v1/organizations/{tenants['org_a']}/query",
        json={"question": "what is the leave policy?"},
        headers=auth_header(tenants["token_b"]),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }

    embedding.embed_query.assert_not_called()
    qdrant.search.assert_not_called()
    llm.generate.assert_not_called()


def test_query_never_reaches_llm_with_other_organization_content(
    client,
    db,
    monkeypatch,
):
    tenants = build_two_tenants(
        client,
        db,
        "queryleak",
    )

    document_a = create_document(
        db=db,
        organization_id=tenants["org_a"],
        uploaded_by=tenants["user_a"].id,
        name="company-a.pdf",
    )

    document_b = create_document(
        db=db,
        organization_id=tenants["org_b"],
        uploaded_by=tenants["user_b"].id,
        name="company-b.pdf",
    )

    create_document_chunk(
        db=db,
        document_id=document_a.id,
        organization_id=tenants["org_a"],
        chunk_index=0,
        text="COMPANY-A-PUBLIC annual leave policy",
    )

    chunk_b = create_document_chunk(
        db=db,
        document_id=document_b.id,
        organization_id=tenants["org_b"],
        chunk_index=0,
        text="COMPANY-B-SECRET salary data",
    )

    db.commit()

    embedding = Mock()
    embedding.embed_query.return_value = (
        [0.1] * settings.embedding_dimension
    )

    qdrant = Mock()
    qdrant.search.return_value.points = [
        Mock(
            id=chunk_b.id,
            score=0.99,
        )
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

    response = client.post(
        f"/api/v1/organizations/{tenants['org_a']}/query",
        json={"question": "annual leave policy"},
        headers=auth_header(tenants["token_a"]),
    )

    assert response.status_code == 200

    body = response.json()

    returned_chunk_ids = {
        source["chunk_id"]
        for source in body["sources"]
    }

    assert chunk_b.id not in returned_chunk_ids

    if llm.generate.called:
        prompt = llm.generate.call_args.kwargs["user_prompt"]

        assert "COMPANY-B-SECRET" not in prompt

    assert "COMPANY-B-SECRET" not in body["answer"]
