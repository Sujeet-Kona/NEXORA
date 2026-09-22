from unittest.mock import Mock

import pytest

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
    get_chunks_for_document,
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


def upload_document(
    client,
    token,
    organization_id,
    filename,
    content,
):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                filename,
                content,
                "application/pdf",
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    return response.json()


def upload_version(
    client,
    token,
    organization_id,
    document_id,
    filename,
    content,
    content_type="application/pdf",
):
    return client.post(
        f"/api/v1/organizations/{organization_id}"
        f"/documents/{document_id}/versions",
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


def stored_file_names(
    tmp_path,
    organization_id,
    document_id,
):
    document_directory = (
        tmp_path
        / "organizations"
        / str(organization_id)
        / "documents"
        / str(document_id)
    )

    if not document_directory.exists():
        return []

    return sorted(
        path.name
        for path in document_directory.iterdir()
    )


def test_created_document_reports_version_one(
    client,
):
    token = register_and_login(
        client,
        "version-created@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Version Created Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": "created.pdf"},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201
    assert response.json()["version"] == 1

    document_id = response.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}"
        f"/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.json()["version"] == 1

    response = client.get(
        f"/api/v1/organizations/{organization_id}/documents",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert [item["version"] for item in response.json()] == [1]


def test_uploaded_document_starts_at_version_one(
    client,
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
        "version-uploaded@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Version Uploaded Company",
    )

    document = upload_document(
        client,
        token,
        organization_id,
        "original.pdf",
        b"%PDF-1.7 original",
    )

    assert document["version"] == 1


def test_upload_version_replaces_file_and_bumps_version(
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
        "version-replace-owner@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Version Replace Company",
    )

    original_content = b"%PDF-1.7 original version"
    replacement_content = b"%PDF-1.7 replacement version content"

    document = upload_document(
        client,
        token,
        organization_id,
        "original.pdf",
        original_content,
    )

    document_id = document["id"]

    response = upload_version(
        client,
        token,
        organization_id,
        document_id,
        "replacement.pdf",
        replacement_content,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["id"] == document_id
    assert body["version"] == 2
    assert body["status"] == "pending"
    assert body["name"] == "replacement.pdf"
    assert body["file_size"] == len(replacement_content)
    assert body["content_type"] == "application/pdf"
    assert body["storage_key"] != document["storage_key"]

    assert not (tmp_path / document["storage_key"]).exists()
    assert (tmp_path / body["storage_key"]).read_bytes() == (
        replacement_content
    )

    assert stored_file_names(
        tmp_path,
        organization_id,
        document_id,
    ) == [body["storage_key"].split("/")[-1]]

    db.expire_all()

    stored_document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    assert stored_document is not None
    assert stored_document.version == 2
    assert stored_document.status == "pending"
    assert stored_document.name == "replacement.pdf"
    assert stored_document.storage_key == body["storage_key"]


def test_upload_version_purges_existing_chunks_and_vectors(
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
        "version-purge-owner@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Version Purge Company",
    )

    document = upload_document(
        client,
        token,
        organization_id,
        "original.pdf",
        b"%PDF-1.7 original",
    )

    document_id = document["id"]

    create_document_chunks(
        db=db,
        document_id=document_id,
        organization_id=organization_id,
        chunks=["first chunk", "second chunk"],
    )

    db.commit()

    qdrant = Mock()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = upload_version(
        client,
        token,
        organization_id,
        document_id,
        "replacement.pdf",
        b"%PDF-1.7 replacement",
    )

    assert response.status_code == 201

    qdrant.delete_document_chunks.assert_called_once_with(
        document_id=document_id,
        organization_id=organization_id,
    )

    db.expire_all()

    assert (
        get_chunks_for_document(
            db=db,
            document_id=document_id,
            organization_id=organization_id,
        )
        == []
    )


def test_upload_version_schedules_background_processing(
    client,
    session_factory,
    recorded_background_tasks,
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
        "version-background-owner@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Version Background Company",
    )

    document = upload_document(
        client,
        token,
        organization_id,
        "original.pdf",
        b"%PDF-1.7 original",
    )

    document_id = document["id"]

    recorded_background_tasks.clear()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: Mock()
    )

    response = upload_version(
        client,
        token,
        organization_id,
        document_id,
        "replacement.pdf",
        b"%PDF-1.7 replacement",
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"

    assert recorded_background_tasks == [
        (document_id, session_factory)
    ]


def test_upload_version_requires_authentication(client):
    response = client.post(
        "/api/v1/organizations/1/documents/1/versions",
        files={
            "file": (
                "replacement.pdf",
                b"%PDF-1.7 replacement",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 401


def test_member_cannot_upload_version(
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

    owner_token = register_and_login(
        client,
        "version-member-owner@example.com",
    )

    member_token = register_and_login(
        client,
        "version-member@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Version Member Company",
    )

    member = get_user(
        db,
        "version-member@example.com",
    )

    add_member(
        db,
        organization_id,
        member.id,
        OrganizationRole.MEMBER,
    )

    document = upload_document(
        client,
        owner_token,
        organization_id,
        "original.pdf",
        b"%PDF-1.7 original",
    )

    document_id = document["id"]

    qdrant = Mock()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = upload_version(
        client,
        member_token,
        organization_id,
        document_id,
        "replacement.pdf",
        b"%PDF-1.7 replacement",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required"
    }

    qdrant.delete_document_chunks.assert_not_called()

    db.expire_all()

    stored_document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    assert stored_document.version == 1
    assert stored_document.name == "original.pdf"

    assert stored_file_names(
        tmp_path,
        organization_id,
        document_id,
    ) == [document["storage_key"].split("/")[-1]]


def test_non_member_cannot_upload_version(
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

    owner_token = register_and_login(
        client,
        "version-outsider-owner@example.com",
    )

    outsider_token = register_and_login(
        client,
        "version-outsider@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Version Outsider Company",
    )

    document = upload_document(
        client,
        owner_token,
        organization_id,
        "original.pdf",
        b"%PDF-1.7 original",
    )

    document_id = document["id"]

    qdrant = Mock()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = upload_version(
        client,
        outsider_token,
        organization_id,
        document_id,
        "replacement.pdf",
        b"%PDF-1.7 replacement",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }

    qdrant.delete_document_chunks.assert_not_called()

    db.expire_all()

    stored_document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    assert stored_document.version == 1


def test_cross_tenant_cannot_upload_version(
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

    owner_a_token = register_and_login(
        client,
        "version-tenant-a@example.com",
    )

    owner_b_token = register_and_login(
        client,
        "version-tenant-b@example.com",
    )

    organization_a = create_organization(
        client,
        owner_a_token,
        "Version Tenant A Company",
    )

    create_organization(
        client,
        owner_b_token,
        "Version Tenant B Company",
    )

    document = upload_document(
        client,
        owner_a_token,
        organization_a,
        "tenant-a.pdf",
        b"%PDF-1.7 tenant a",
    )

    document_id = document["id"]

    qdrant = Mock()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = upload_version(
        client,
        owner_b_token,
        organization_a,
        document_id,
        "replacement.pdf",
        b"%PDF-1.7 replacement",
    )

    assert response.status_code == 403

    qdrant.delete_document_chunks.assert_not_called()

    db.expire_all()

    stored_document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    assert stored_document.version == 1
    assert stored_document.name == "tenant-a.pdf"


def test_upload_version_unknown_document_returns_404(
    client,
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
        "version-unknown@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Version Unknown Company",
    )

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: Mock()
    )

    response = upload_version(
        client,
        token,
        organization_id,
        999999,
        "replacement.pdf",
        b"%PDF-1.7 replacement",
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Document not found"
    }


def test_upload_version_fails_when_vectors_cannot_be_purged(
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
        "version-qdrant-down-owner@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Version Qdrant Down Company",
    )

    document = upload_document(
        client,
        token,
        organization_id,
        "original.pdf",
        b"%PDF-1.7 original",
    )

    document_id = document["id"]

    qdrant = Mock()
    qdrant.delete_document_chunks.side_effect = RuntimeError(
        "Qdrant is unreachable",
    )

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = upload_version(
        client,
        token,
        organization_id,
        document_id,
        "replacement.pdf",
        b"%PDF-1.7 replacement",
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "Existing document vectors could not be purged"
        )
    }

    assert stored_file_names(
        tmp_path,
        organization_id,
        document_id,
    ) == [document["storage_key"].split("/")[-1]]

    assert (tmp_path / document["storage_key"]).exists()

    db.expire_all()

    stored_document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    assert stored_document.version == 1
    assert stored_document.name == "original.pdf"
    assert stored_document.storage_key == document["storage_key"]


def test_upload_version_rejects_invalid_content(
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
        "version-invalid-content@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Version Invalid Content Company",
    )

    document = upload_document(
        client,
        token,
        organization_id,
        "original.pdf",
        b"%PDF-1.7 original",
    )

    document_id = document["id"]

    qdrant = Mock()

    app.dependency_overrides[get_qdrant_repository] = (
        lambda: qdrant
    )

    response = upload_version(
        client,
        token,
        organization_id,
        document_id,
        "replacement.pdf",
        b"this is not actually a pdf",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Uploaded content is not a valid PDF"
    }

    qdrant.delete_document_chunks.assert_not_called()

    assert stored_file_names(
        tmp_path,
        organization_id,
        document_id,
    ) == [document["storage_key"].split("/")[-1]]

    db.expire_all()

    stored_document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    assert stored_document.version == 1
    assert stored_document.name == "original.pdf"
