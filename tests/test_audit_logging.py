from unittest.mock import Mock

import pytest

from backend.core.config import settings
from backend.db.models import (
    AuditAction,
    AuditLog,
    User,
    UserRole,
)
from backend.dependencies.rag import get_qdrant_repository
from backend.main import app
from backend.services.audit_service import record_audit_event


PASSWORD = "MySecret123!"


def register(client, email, password=PASSWORD):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": password,
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def login(client, email, password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


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


def latest_audit(db, action):
    return (
        db.query(AuditLog)
        .filter(AuditLog.action == action)
        .order_by(AuditLog.id.desc())
        .first()
    )


def get_user(db, email):
    user = (
        db.query(User).filter(User.email == email).first()
    )

    assert user is not None

    return user


# --- login events -------------------------------------------------------


def test_successful_login_records_audit(client, db):
    register(client, "login-ok@example.com")

    response = login(client, "login-ok@example.com")

    assert response.status_code == 200

    entry = latest_audit(db, AuditAction.LOGIN_SUCCESS)

    assert entry is not None
    assert entry.success is True
    assert entry.actor_user_id == get_user(
        db, "login-ok@example.com"
    ).id
    assert entry.organization_id is None
    assert entry.resource_type == "session"


def test_request_id_propagates_into_audit(client, db):
    register(client, "login-rid@example.com")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "login-rid@example.com",
            "password": PASSWORD,
        },
        headers={"X-Request-ID": "fixed-request-id-123"},
    )

    assert response.status_code == 200

    request_id = response.headers["X-Request-ID"]

    assert request_id == "fixed-request-id-123"

    entry = latest_audit(db, AuditAction.LOGIN_SUCCESS)

    assert entry is not None
    assert entry.request_id == request_id


def test_failed_login_records_audit_without_secrets(client, db):
    register(client, "login-bad@example.com")

    wrong_password = "TotallyWrong999!"

    response = login(
        client,
        "login-bad@example.com",
        password=wrong_password,
    )

    assert response.status_code == 401

    entry = latest_audit(db, AuditAction.LOGIN_FAILURE)

    assert entry is not None
    assert entry.success is False
    assert entry.actor_user_id == get_user(
        db, "login-bad@example.com"
    ).id
    assert entry.organization_id is None
    assert entry.details is None
    assert entry.request_id == response.headers["X-Request-ID"]

    serialized = repr(
        (
            entry.action,
            entry.details,
            entry.resource_type,
            entry.request_id,
        )
    )

    assert wrong_password not in serialized
    assert PASSWORD not in serialized
    assert "login-bad@example.com" not in serialized


def test_failed_login_unknown_user_has_null_actor(client, db):
    response = login(client, "ghost@example.com")

    assert response.status_code == 401

    entry = latest_audit(db, AuditAction.LOGIN_FAILURE)

    assert entry is not None
    assert entry.success is False
    assert entry.actor_user_id is None


# --- document events ----------------------------------------------------


def test_document_upload_records_audit(
    client,
    db,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))

    recorded = []

    monkeypatch.setattr(
        "backend.api.v1.documents.process_document_background",
        lambda document_id, session_factory: recorded.append(
            document_id
        ),
    )

    register(client, "uploader@example.com")
    token = login(client, "uploader@example.com").json()[
        "access_token"
    ]
    organization_id = create_organization(
        client, token, "Uploader Org"
    )

    content = b"%PDF-1.7 fake content"

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={"file": ("policy.pdf", content, "application/pdf")},
        headers=auth_header(token),
    )

    assert response.status_code == 201

    document_id = response.json()["id"]

    entry = latest_audit(db, AuditAction.DOCUMENT_UPLOADED)

    assert entry is not None
    assert entry.organization_id == organization_id
    assert entry.actor_user_id == get_user(
        db, "uploader@example.com"
    ).id
    assert entry.resource_type == "document"
    assert entry.resource_id == document_id
    assert entry.details["version"] == 1
    assert entry.details["content_type"] == "application/pdf"
    assert entry.details["file_size"] == len(content)

    assert content.decode() not in repr(entry.details)


def test_document_status_change_records_audit(client, db):
    register(client, "status@example.com")
    token = login(client, "status@example.com").json()[
        "access_token"
    ]
    organization_id = create_organization(
        client, token, "Status Org"
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": "status-doc"},
        headers=auth_header(token),
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        json={"status": "processing"},
        headers=auth_header(token),
    )

    assert patch_response.status_code == 200

    entry = latest_audit(db, AuditAction.DOCUMENT_STATUS_CHANGED)

    assert entry is not None
    assert entry.organization_id == organization_id
    assert entry.resource_id == document_id
    assert entry.details == {"status": "processing"}


def test_document_delete_records_audit(client, db):
    app.dependency_overrides[get_qdrant_repository] = (
        lambda: Mock()
    )

    register(client, "deleter@example.com")
    token = login(client, "deleter@example.com").json()[
        "access_token"
    ]
    organization_id = create_organization(
        client, token, "Deleter Org"
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": "delete-doc"},
        headers=auth_header(token),
    )

    document_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        headers=auth_header(token),
    )

    assert delete_response.status_code == 204

    entry = latest_audit(db, AuditAction.DOCUMENT_DELETED)

    assert entry is not None
    assert entry.organization_id == organization_id
    assert entry.resource_type == "document"
    assert entry.resource_id == document_id


# --- membership / role events ------------------------------------------


def test_membership_lifecycle_records_audit(client, db):
    owner_id = register(client, "owner@example.com")
    owner_token = login(client, "owner@example.com").json()[
        "access_token"
    ]
    organization_id = create_organization(
        client, owner_token, "Member Org"
    )

    member_id = register(client, "member@example.com")

    add_response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": member_id, "role": "member"},
        headers=auth_header(owner_token),
    )

    assert add_response.status_code == 201

    added = latest_audit(db, AuditAction.MEMBER_ADDED)

    assert added is not None
    assert added.organization_id == organization_id
    assert added.actor_user_id == owner_id
    assert added.details == {
        "role": "member",
        "target_user_id": member_id,
    }

    role_response = client.patch(
        f"/api/v1/organizations/{organization_id}/members/{member_id}",
        json={"role": "admin"},
        headers=auth_header(owner_token),
    )

    assert role_response.status_code == 200

    changed = latest_audit(db, AuditAction.MEMBER_ROLE_CHANGED)

    assert changed is not None
    assert changed.organization_id == organization_id
    assert changed.details == {
        "role": "admin",
        "target_user_id": member_id,
    }

    remove_response = client.delete(
        f"/api/v1/organizations/{organization_id}/members/{member_id}",
        headers=auth_header(owner_token),
    )

    assert remove_response.status_code == 204

    removed = latest_audit(db, AuditAction.MEMBER_REMOVED)

    assert removed is not None
    assert removed.organization_id == organization_id
    assert removed.details == {"target_user_id": member_id}


def test_platform_role_change_records_audit(client, db):
    admin_id = register(client, "platform-admin@example.com")

    admin_user = get_user(db, "platform-admin@example.com")
    admin_user.role = UserRole.ADMIN
    db.commit()

    admin_token = login(
        client, "platform-admin@example.com"
    ).json()["access_token"]

    target_id = register(client, "platform-target@example.com")

    response = client.patch(
        f"/api/v1/users/{target_id}/role",
        json={"role": "admin"},
        headers=auth_header(admin_token),
    )

    assert response.status_code == 200

    entry = latest_audit(
        db, AuditAction.USER_PLATFORM_ROLE_CHANGED
    )

    assert entry is not None
    assert entry.organization_id is None
    assert entry.actor_user_id == admin_id
    assert entry.resource_type == "user"
    assert entry.resource_id == target_id
    assert entry.details == {"role": "admin"}


# --- details allowlist --------------------------------------------------


def test_record_audit_event_strips_unsafe_details(db):
    record_audit_event(
        db,
        organization_id=None,
        actor_user_id=None,
        action=AuditAction.DOCUMENT_UPLOADED,
        resource_type="document",
        resource_id=1,
        details={
            "version": 2,
            "file_size": 10,
            "password": "hunter2",
            "password_hash": "abc",
            "token": "jwt-value",
            "refresh_token": "rt-value",
            "authorization": "Bearer x",
            "body": {"secret": "value"},
        },
    )

    entry = latest_audit(db, AuditAction.DOCUMENT_UPLOADED)

    assert entry is not None
    assert entry.details == {"version": 2, "file_size": 10}

    serialized = repr(entry.details)

    for forbidden in (
        "hunter2",
        "jwt-value",
        "rt-value",
        "Bearer",
        "secret",
    ):
        assert forbidden not in serialized


# --- read endpoint authorization ---------------------------------------


def _seed_org_with_audit(client, db, owner_email):
    register(client, owner_email)
    token = login(client, owner_email).json()["access_token"]
    organization_id = create_organization(
        client, token, f"{owner_email} Org"
    )
    member_id = register(client, f"m-{owner_email}")

    client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": member_id, "role": "member"},
        headers=auth_header(token),
    )

    return token, organization_id, member_id


def test_owner_can_list_audit_logs(client, db):
    token, organization_id, _ = _seed_org_with_audit(
        client, db, "owner-read@example.com"
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/audit-logs",
        headers=auth_header(token),
    )

    assert response.status_code == 200

    body = response.json()

    assert body
    assert all(
        entry["organization_id"] == organization_id
        for entry in body
    )
    assert any(
        entry["action"] == "membership.member_added"
        for entry in body
    )


def test_member_cannot_list_audit_logs(client, db):
    _, organization_id, member_id = _seed_org_with_audit(
        client, db, "owner-gate@example.com"
    )

    member_token = login(client, "m-owner-gate@example.com").json()[
        "access_token"
    ]

    response = client.get(
        f"/api/v1/organizations/{organization_id}/audit-logs",
        headers=auth_header(member_token),
    )

    assert response.status_code == 403


def test_non_member_cannot_list_audit_logs(client, db):
    _, organization_id, _ = _seed_org_with_audit(
        client, db, "owner-nm@example.com"
    )

    register(client, "outsider@example.com")
    outsider_token = login(client, "outsider@example.com").json()[
        "access_token"
    ]

    response = client.get(
        f"/api/v1/organizations/{organization_id}/audit-logs",
        headers=auth_header(outsider_token),
    )

    assert response.status_code == 403


def test_audit_logs_require_authentication(client):
    response = client.get(
        "/api/v1/organizations/1/audit-logs",
    )

    assert response.status_code in {401, 403}
