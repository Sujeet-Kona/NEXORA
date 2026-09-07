def test_auth_me_requires_authentication(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_auth_me_accepts_authenticated_user(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "protected-me@example.com",
            "full_name": "Protected User",
            "password": "MySecret123!",
        },
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "protected-me@example.com",
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

    body = response.json()

    assert body["email"] == "protected-me@example.com"
    assert body["full_name"] == "Protected User"
    assert "password" not in body
    assert "password_hash" not in body
