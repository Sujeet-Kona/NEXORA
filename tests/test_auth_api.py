def test_register_user_endpoint(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "register@example.com",
            "full_name": "Register User",
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["email"] == "register@example.com"
    assert body["full_name"] == "Register User"
    assert "password" not in body
    assert "password_hash" not in body


def test_register_duplicate_email_returns_409(client):
    payload = {
        "email": "register-duplicate@example.com",
        "full_name": "First User",
        "password": "MySecret123!",
    }

    first_response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    second_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": payload["email"],
            "full_name": "Second User",
            "password": "AnotherSecret123!",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Email already registered"
    }


def test_register_invalid_email_returns_422(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "full_name": "Invalid User",
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 422


def test_register_short_password_returns_422(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "short-password@example.com",
            "full_name": "Short Password",
            "password": "short",
        },
    )

    assert response.status_code == 422
