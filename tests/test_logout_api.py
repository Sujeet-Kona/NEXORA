def test_logout_endpoint_revokes_refresh_token(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout-api@example.com",
            "full_name": "Logout API User",
            "password": "MySecret123!",
        },
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "logout-api@example.com",
            "password": "MySecret123!",
        },
    )

    refresh_token = login_response.json()["refresh_token"]

    logout_response = client.post(
        "/api/v1/auth/logout",
        json={
            "refresh_token": refresh_token,
        },
    )

    assert logout_response.status_code == 204
    assert logout_response.content == b""

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": refresh_token,
        },
    )

    assert refresh_response.status_code == 401
    assert refresh_response.json() == {
        "detail": "Invalid refresh token"
    }


def test_logout_endpoint_rejects_unknown_token(client):
    response = client.post(
        "/api/v1/auth/logout",
        json={
            "refresh_token": "unknown-logout-token",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid refresh token"
    }


def test_logout_endpoint_rejects_empty_token(client):
    response = client.post(
        "/api/v1/auth/logout",
        json={
            "refresh_token": "",
        },
    )

    assert response.status_code == 422
