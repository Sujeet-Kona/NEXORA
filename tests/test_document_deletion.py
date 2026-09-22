from pathlib import Path
from unittest.mock import Mock

import pytest
from qdrant_client import QdrantClient

from backend.core.config import settings
from backend.db.models import (
    Document,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from backend.dependencies.rag import get_qdrant_repository
from backend.main import app
from backend.repositories.document_chunk_repository import (
    create_document_chunks,
    delete_chunks_for_document,
    get_chunks_for_document,
)
from backend.repositories.document_repository import (
    create_document,
)
from backend.repositories.qdrant_repository import (
    QdrantRepository,
)
from backend.services.document_service import (
    delete_document_service,
)
from backend.services.organization_service import (
    create_organization_service,
)
from backend.services.retrieval_service import (
    retrieve_chunks,
)


@pytest.fixture(autouse=True)
def recorded_background_tasks(monkeypatch):
    recorded = []

    def fake_process_document_background(
        document_id,
        session_factory,
    ):
        recorded.append((document_id, session_factory))

    monkeypatch.setattr(
        "backend.api.v1.documents.process_document_background",
        fake_process_document_background,
    )

    return recorded


def register_and_login(
    client,
    email,
):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


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
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def add_member(
    db,
    organization_id,
    user_id,
    role=OrganizationRole.MEMBER,
):
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    db.add(membership)
    db.commit()

    return membership


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


def upload_document(
    client,
    token,
    organization_id,
    filename,
    content=b"%PDF-1.7 content",
    content_type="application/pdf",
):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                filename,
                content,
                content_type,
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    return response.json()


def test_delete_requires_authentication(client):
    response = client.delete(
        "/api/v1/organizations/1/documents/1",
    )

    assert response.status_code == 401


def test_delete_purges_vectors_before_removing_document_row(
    client,
    db,
    session_factory,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "storage_path",
        str(tmp_path),
    )

    token = register_and_login(
        client,
        "delete-order-owner@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Delete Order Company",
    )

    document = upload_document(
        client,
        token,
        organization_id,
        "order.pdf",
    )

    row_present_at_purge_time = []

    def probe(
        document_id,
        organization_id,
    ):
        session = session_factory()

        try:
            row = (
                session.query(Document)
                .filter(Document.id == document_id)
                .first()
            )

            row_present_at_purge_time.append(
                row is not None
            )
        finally:
            session.close()

    qdrant = Mock()
    qdrant.delete_document_chunks.side_effect = probe

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = client.delete(
        f"/api/v1/organizations/{organization_id}"
        f"/documents/{document['id']}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 204
    assert response.content == b""

    qdrant.delete_document_chunks.assert_called_once_with(
        document_id=document["id"],
        organization_id=organization_id,
    )

    assert row_present_at_purge_time == [True]

    db.expire_all()

    assert (
        db.query(Document)
        .filter(Document.id == document["id"])
        .first()
        is None
    )

    assert not Path(
        tmp_path,
        document["storage_key"],
    ).exists()


def test_delete_fails_when_vectors_cannot_be_purged(
    client,
    db,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "storage_path",
        str(tmp_path),
    )

    token = register_and_login(
        client,
        "delete-qdrant-down@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Delete Qdrant Down Company",
    )

    document = upload_document(
        client,
        token,
        organization_id,
        "down.pdf",
    )

    qdrant = Mock()
    qdrant.delete_document_chunks.side_effect = RuntimeError(
        "Qdrant is unreachable",
    )

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = client.delete(
        f"/api/v1/organizations/{organization_id}"
        f"/documents/{document['id']}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Document vectors could not be purged"
    }

    db.expire_all()

    row = (
        db.query(Document)
        .filter(Document.id == document["id"])
        .first()
    )

    assert row is not None

    assert Path(
        tmp_path,
        document["storage_key"],
    ).exists()


def test_member_cannot_delete_document_and_nothing_is_purged(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "delete-member-owner@example.com",
    )

    member_token = register_and_login(
        client,
        "delete-member@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Delete Member Company",
    )

    owner = get_user(
        db,
        "delete-member-owner@example.com",
    )

    member = get_user(
        db,
        "delete-member@example.com",
    )

    add_member(
        db,
        organization_id,
        member.id,
        OrganizationRole.MEMBER,
    )

    document = create_document(
        db=db,
        organization_id=organization_id,
        uploaded_by=owner.id,
        name="member-delete.pdf",
    )

    document_id = document.id

    qdrant = Mock()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = client.delete(
        f"/api/v1/organizations/{organization_id}"
        f"/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {member_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required"
    }

    qdrant.delete_document_chunks.assert_not_called()

    db.expire_all()

    assert (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
        is not None
    )


def test_non_member_cannot_delete_document_and_nothing_is_purged(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "delete-outsider-owner@example.com",
    )

    outsider_token = register_and_login(
        client,
        "delete-outsider@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Delete Outsider Company",
    )

    owner = get_user(
        db,
        "delete-outsider-owner@example.com",
    )

    document = create_document(
        db=db,
        organization_id=organization_id,
        uploaded_by=owner.id,
        name="outsider-delete.pdf",
    )

    document_id = document.id

    qdrant = Mock()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = client.delete(
        f"/api/v1/organizations/{organization_id}"
        f"/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {outsider_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }

    qdrant.delete_document_chunks.assert_not_called()

    db.expire_all()

    assert (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
        is not None
    )


def test_cross_tenant_delete_never_reaches_the_vector_store(
    client,
    db,
):
    owner_a_token = register_and_login(
        client,
        "delete-tenant-a@example.com",
    )

    owner_b_token = register_and_login(
        client,
        "delete-tenant-b@example.com",
    )

    organization_a = create_organization(
        client,
        owner_a_token,
        "Delete Tenant A Company",
    )

    create_organization(
        client,
        owner_b_token,
        "Delete Tenant B Company",
    )

    owner_a = get_user(
        db,
        "delete-tenant-a@example.com",
    )

    document = create_document(
        db=db,
        organization_id=organization_a,
        uploaded_by=owner_a.id,
        name="tenant-a.pdf",
    )

    document_id = document.id

    qdrant = Mock()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = client.delete(
        f"/api/v1/organizations/{organization_a}"
        f"/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {owner_b_token}",
        },
    )

    assert response.status_code == 403

    qdrant.delete_document_chunks.assert_not_called()

    db.expire_all()

    assert (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
        is not None
    )


def test_deleted_document_vectors_stop_starving_retrieval(
    db,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "storage_path",
        str(tmp_path),
    )

    owner = create_user(
        db,
        "vector-purge-owner@example.com",
        "Vector Purge Owner",
    )

    organization = create_organization_service(
        db=db,
        name="Vector Purge Company",
        user_id=owner.id,
    )

    removed_document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="removed.pdf",
    )

    kept_document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="kept.pdf",
    )

    removed_document_id = removed_document.id
    kept_document_id = kept_document.id

    removed_chunks = create_document_chunks(
        db=db,
        document_id=removed_document_id,
        organization_id=organization.id,
        chunks=[
            f"removed chunk {index}"
            for index in range(5)
        ],
    )

    kept_chunks = create_document_chunks(
        db=db,
        document_id=kept_document_id,
        organization_id=organization.id,
        chunks=["kept chunk"],
    )

    db.commit()

    qdrant_repository = QdrantRepository(
        client=QdrantClient(":memory:"),
        is_local=True,
    )

    qdrant_repository.ensure_collection()

    def unit_vector(position: int) -> list[float]:
        vector = [0.0] * settings.embedding_dimension
        vector[position] = 1.0

        return vector

    removed_vector = unit_vector(0)

    kept_vector = unit_vector(0)
    kept_vector[1] = 1.0

    qdrant_repository.upsert_chunks(
        [
            (
                chunk.id,
                removed_vector,
                organization.id,
                removed_document_id,
                chunk.chunk_index,
            )
            for chunk in removed_chunks
        ]
    )

    qdrant_repository.upsert_chunks(
        [
            (
                kept_chunks[0].id,
                kept_vector,
                organization.id,
                kept_document_id,
                kept_chunks[0].chunk_index,
            )
        ]
    )

    delete_chunks_for_document(
        db=db,
        document_id=removed_document_id,
        organization_id=organization.id,
    )

    db.commit()

    embedding_service = Mock()
    embedding_service.embed_query.return_value = (
        removed_vector
    )

    starved = retrieve_chunks(
        db=db,
        organization_id=organization.id,
        query="anything",
        embedding_service=embedding_service,
        qdrant_repository=qdrant_repository,
        limit=5,
    )

    assert starved == []

    delete_document_service(
        db=db,
        organization_id=organization.id,
        document_id=removed_document_id,
        current_user=owner,
        qdrant_repository=qdrant_repository,
    )

    assert (
        get_chunks_for_document(
            db=db,
            document_id=removed_document_id,
            organization_id=organization.id,
        )
        == []
    )

    retrieved = retrieve_chunks(
        db=db,
        organization_id=organization.id,
        query="anything",
        embedding_service=embedding_service,
        qdrant_repository=qdrant_repository,
        limit=5,
    )

    assert [chunk.text for chunk in retrieved] == [
        "kept chunk"
    ]

    assert retrieved[0].document_id == kept_document_id

    remaining = qdrant_repository.search(
        query_vector=removed_vector,
        organization_id=organization.id,
        limit=10,
    )

    assert len(remaining.points) == 1
    assert (
        remaining.points[0].payload["document_id"]
        == kept_document_id
    )
