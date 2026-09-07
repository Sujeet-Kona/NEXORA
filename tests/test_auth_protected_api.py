import jwt

from backend.core.config import settings
from backend.core.security import create_access_token


def test_protected_me_requires_authentication(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_protected_me_accepts_valid_token(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "protected@example.com",
            "full_name": "Protected User",
            "password": "MySecret123!",
        },
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "protected@example.com",
            "password": "MySecret123!",
        },
    )

    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "protected@example.com"


def test_protected_me_rejects_invalid_token(client):
    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer this-is-not-a-valid-jwt",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid authentication credentials"
    }


def test_protected_me_rejects_token_signed_with_wrong_secret(client):
    token = jwt.encode(
        {"sub": "123"},
        "this-is-a-different-test-secret-with-32-bytes-or-more",
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid authentication credentials"
    }


def test_protected_me_rejects_token_for_missing_user(client):
    token = create_access_token("999999")

    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid authentication credentials"
    }

def test_protected_me_rejects_expired_token(client):
    import time
    import jwt

    from backend.core.config import settings

    token = jwt.encode(
        {
            "sub": "123",
            "exp": int(time.time()) - 1,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid authentication credentials"
    }
