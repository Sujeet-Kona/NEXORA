def test_refresh_endpoint_rotates_refresh_token(client):
    registration_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh-api@example.com",
            "full_name": "Refresh API User",
            "password": "MySecret123!",
        },
    )

    assert registration_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh-api@example.com",
            "password": "MySecret123!",
        },
    )

    assert login_response.status_code == 200

    old_refresh_token = login_response.json()["refresh_token"]

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": old_refresh_token,
        },
    )

    assert refresh_response.status_code == 200

    body = refresh_response.json()

    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["refresh_token"] != old_refresh_token


def test_refresh_endpoint_rejects_reuse_of_old_token(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh-reuse@example.com",
            "full_name": "Refresh Reuse User",
            "password": "MySecret123!",
        },
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh-reuse@example.com",
            "password": "MySecret123!",
        },
    )

    old_refresh_token = login_response.json()["refresh_token"]

    first_refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": old_refresh_token,
        },
    )

    second_refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": old_refresh_token,
        },
    )

    assert first_refresh_response.status_code == 200
    assert second_refresh_response.status_code == 401
    assert second_refresh_response.json() == {
        "detail": "Invalid refresh token"
    }


def test_refresh_endpoint_rejects_unknown_token(client):
    response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": "unknown-refresh-token",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid refresh token"
    }


def test_refresh_endpoint_rejects_empty_token(client):
    response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": "",
        },
    )

    assert response.status_code == 422
