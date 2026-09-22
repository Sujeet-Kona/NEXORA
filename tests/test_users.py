import pytest
from fastapi.testclient import TestClient

from backend.db.models import User, UserRole
from backend.main import app


PASSWORD = "MySecret123!"


def register_user(client, email, full_name):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": full_name,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201

    return response.json()


def login(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def auth_headers(token):
    return {
        "Authorization": f"Bearer {token}",
    }


def promote_to_admin(db, email):
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    assert user is not None

    user.role = UserRole.ADMIN
    db.commit()
    db.refresh(user)

    return user


def admin_token(client, db, email):
    register_user(
        client,
        email,
        "Admin User",
    )

    promote_to_admin(
        db,
        email,
    )

    return login(
        client,
        email,
    )


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_legacy_unversioned_user_endpoints_are_removed(client):
    list_response = client.get("/users")
    detail_response = client.get("/users/1")
    create_response = client.post(
        "/users",
        json={
            "email": "legacy@example.com",
            "full_name": "Legacy User",
        },
    )

    assert list_response.status_code == 404
    assert detail_response.status_code == 404
    assert create_response.status_code == 404


def test_list_users_requires_authentication(client):
    response = client.get("/api/v1/users")

    assert response.status_code == 401


def test_list_users_requires_admin(client, db):
    register_user(
        client,
        "member-list@example.com",
        "Member List",
    )

    member_token = login(
        client,
        "member-list@example.com",
    )

    response = client.get(
        "/api/v1/users",
        headers=auth_headers(member_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Admin access required"
    }


def test_admin_can_list_users(client, db):
    register_user(
        client,
        "list-member@example.com",
        "List Member",
    )

    token = admin_token(
        client,
        db,
        "list-admin@example.com",
    )

    response = client.get(
        "/api/v1/users",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    emails = {
        user["email"]
        for user in response.json()
    }

    assert emails == {
        "list-admin@example.com",
        "list-member@example.com",
    }


def test_get_user_requires_authentication(client):
    response = client.get("/api/v1/users/1")

    assert response.status_code == 401


def test_get_user_requires_admin(client, db):
    register_user(
        client,
        "member-get@example.com",
        "Member Get",
    )

    member_token = login(
        client,
        "member-get@example.com",
    )

    response = client.get(
        "/api/v1/users/1",
        headers=auth_headers(member_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Admin access required"
    }


def test_admin_can_get_user(client, db):
    target = register_user(
        client,
        "get-target@example.com",
        "Get Target",
    )

    token = admin_token(
        client,
        db,
        "get-admin@example.com",
    )

    response = client.get(
        f"/api/v1/users/{target['id']}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == target["id"]
    assert body["email"] == "get-target@example.com"
    assert body["full_name"] == "Get Target"
    assert body["role"] == "member"


def test_get_user_not_found_returns_404(client, db):
    token = admin_token(
        client,
        db,
        "missing-admin@example.com",
    )

    response = client.get(
        "/api/v1/users/9999",
        headers=auth_headers(token),
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "User not found"
    }


@pytest.mark.parametrize("user_id", [0, -1])
def test_invalid_user_id_returns_400(client, db, user_id):
    token = admin_token(
        client,
        db,
        "invalid-id-admin@example.com",
    )

    response = client.get(
        f"/api/v1/users/{user_id}",
        headers=auth_headers(token),
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "User ID must be a positive integer"
    }


def test_non_integer_user_id_returns_422(client, db):
    token = admin_token(
        client,
        db,
        "non-integer-admin@example.com",
    )

    response = client.get(
        "/api/v1/users/not-an-integer",
        headers=auth_headers(token),
    )

    assert response.status_code == 422


def test_unexpected_error_returns_500_and_logs(
    client,
    db,
    monkeypatch,
):
    token = admin_token(
        client,
        db,
        "error-admin@example.com",
    )

    def broken_get_users_service(db):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(
        "backend.api.v1.users.get_users_service",
        broken_get_users_service,
    )

    logged_messages = []

    def fake_logger_exception(message, **kwargs):
        logged_messages.append(message)

    monkeypatch.setattr(
        "backend.main.logger.exception",
        fake_logger_exception,
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as test_client:
        response = test_client.get(
            "/api/v1/users",
            headers=auth_headers(token),
        )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error"
    }

    assert "Unhandled application error" in logged_messages
