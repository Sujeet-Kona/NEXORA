from unittest.mock import Mock

import pytest

from backend.db.models import (
    AuditAction,
    AuditLog,
)
from backend.dependencies.rag import get_qdrant_repository
from backend.main import app


PASSWORD = "MySecret123!"


@pytest.fixture(autouse=True)
def mock_qdrant():
    app.dependency_overrides[get_qdrant_repository] = (
        lambda: Mock()
    )

    yield

    app.dependency_overrides.pop(get_qdrant_repository, None)


def register(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def login(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def create_organization(client, token, name):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
        headers=auth_header(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def add_member(client, token, organization_id, user_id, role):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": user_id, "role": role},
        headers=auth_header(token),
    )

    assert response.status_code == 201

    return response


def list_audit(client, token, organization_id):
    return client.get(
        f"/api/v1/organizations/{organization_id}/audit-logs",
        headers=auth_header(token),
    )


def seed_tenant(client, owner_email, member_email, org_name):
    owner_id = register(client, owner_email)
    owner_token = login(client, owner_email)
    organization_id = create_organization(
        client, owner_token, org_name
    )
    member_id = register(client, member_email)

    add_member(
        client,
        owner_token,
        organization_id,
        member_id,
        "member",
    )

    member_token = login(client, member_email)

    return {
        "owner_id": owner_id,
        "owner_token": owner_token,
        "member_id": member_id,
        "member_token": member_token,
        "organization_id": organization_id,
    }


def test_owner_sees_only_own_tenant_audit_logs(client, db):
    tenant_a = seed_tenant(
        client, "a-owner@example.com", "a-member@example.com",
        "Tenant A",
    )
    tenant_b = seed_tenant(
        client, "b-owner@example.com", "b-member@example.com",
        "Tenant B",
    )

    response_a = list_audit(
        client, tenant_a["owner_token"], tenant_a["organization_id"]
    )

    assert response_a.status_code == 200

    body_a = response_a.json()

    assert body_a
    assert all(
        entry["organization_id"] == tenant_a["organization_id"]
        for entry in body_a
    )

    response_b = list_audit(
        client, tenant_b["owner_token"], tenant_b["organization_id"]
    )

    body_b = response_b.json()

    ids_a = {entry["id"] for entry in body_a}
    ids_b = {entry["id"] for entry in body_b}

    assert ids_a.isdisjoint(ids_b)


def test_other_tenant_owner_cannot_read_audit_logs(client, db):
    tenant_a = seed_tenant(
        client, "a2-owner@example.com", "a2-member@example.com",
        "Tenant A2",
    )
    tenant_b = seed_tenant(
        client, "b2-owner@example.com", "b2-member@example.com",
        "Tenant B2",
    )

    response = list_audit(
        client, tenant_b["owner_token"], tenant_a["organization_id"]
    )

    assert response.status_code == 403


def test_member_without_admin_role_cannot_read_audit_logs(
    client, db
):
    tenant_a = seed_tenant(
        client, "a3-owner@example.com", "a3-member@example.com",
        "Tenant A3",
    )

    response = list_audit(
        client,
        tenant_a["member_token"],
        tenant_a["organization_id"],
    )

    assert response.status_code == 403


def test_cross_tenant_resource_ids_do_not_leak_records(client, db):
    tenant_a = seed_tenant(
        client, "a4-owner@example.com", "a4-member@example.com",
        "Tenant A4",
    )
    tenant_b = seed_tenant(
        client, "b4-owner@example.com", "b4-member@example.com",
        "Tenant B4",
    )

    tenant_a_rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.organization_id
            == tenant_a["organization_id"]
        )
        .all()
    )

    assert tenant_a_rows

    response_b = list_audit(
        client, tenant_b["owner_token"], tenant_b["organization_id"]
    )

    body_b = response_b.json()

    leaked = [
        entry
        for entry in body_b
        if entry["organization_id"]
        == tenant_a["organization_id"]
    ]

    assert leaked == []

    # Even addressing tenant A's id directly is refused for tenant B.
    direct = list_audit(
        client, tenant_b["owner_token"], tenant_a["organization_id"]
    )

    assert direct.status_code == 403


def test_document_delete_audit_stays_in_owning_tenant(client, db):
    tenant_a = seed_tenant(
        client, "a5-owner@example.com", "a5-member@example.com",
        "Tenant A5",
    )
    tenant_b = seed_tenant(
        client, "b5-owner@example.com", "b5-member@example.com",
        "Tenant B5",
    )

    create_response = client.post(
        f"/api/v1/organizations/{tenant_a['organization_id']}/documents",
        json={"name": "tenant-a-doc"},
        headers=auth_header(tenant_a["owner_token"]),
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/api/v1/organizations/{tenant_a['organization_id']}/documents/{document_id}",
        headers=auth_header(tenant_a["owner_token"]),
    )

    assert delete_response.status_code == 204

    entry = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == AuditAction.DOCUMENT_DELETED,
            AuditLog.resource_id == document_id,
        )
        .order_by(AuditLog.id.desc())
        .first()
    )

    assert entry is not None
    assert entry.organization_id == tenant_a["organization_id"]

    body_a = list_audit(
        client, tenant_a["owner_token"], tenant_a["organization_id"]
    ).json()

    assert any(
        row["id"] == entry.id
        and row["action"] == "document.deleted"
        for row in body_a
    )

    body_b = list_audit(
        client, tenant_b["owner_token"], tenant_b["organization_id"]
    ).json()

    assert all(row["id"] != entry.id for row in body_b)
