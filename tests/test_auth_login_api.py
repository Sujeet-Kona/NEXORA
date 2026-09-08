def test_login_endpoint_returns_access_and_refresh_tokens(client):
    registration_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "login-endpoint@example.com",
            "full_name": "Login Endpoint User",
            "password": "MySecret123!",
        },
    )

    assert registration_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "login-endpoint@example.com",
            "password": "MySecret123!",
        },
    )

    assert login_response.status_code == 200

    body = login_response.json()

    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_endpoint_rejects_wrong_password(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrong-login@example.com",
            "full_name": "Wrong Login",
            "password": "MySecret123!",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrong-login@example.com",
            "password": "WrongPassword!",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid email or password"
    }


def test_login_endpoint_rejects_unknown_email(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "unknown-login@example.com",
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid email or password"
    }


def test_login_endpoint_rejects_invalid_payload(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "not-an-email",
            "password": "",
        },
    )

    assert response.status_code == 422
