def _register_and_login(client, email, name):
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": name,
            "password": "StrongPass123!",
        },
    )
    assert registered.status_code == 201

    logged_in = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPass123!",
        },
    )
    assert logged_in.status_code == 200
    return logged_in.json()["access_token"]


def test_list_organizations_requires_authentication(client):
    response = client.get("/api/v1/organizations")
    assert response.status_code == 401


def test_list_organizations_returns_only_callers_memberships(client):
    first_token = _register_and_login(
        client,
        "workspace-first@example.com",
        "Workspace First",
    )
    second_token = _register_and_login(
        client,
        "workspace-second@example.com",
        "Workspace Second",
    )

    first_created = client.post(
        "/api/v1/organizations",
        json={"name": "First private workspace"},
        headers={"Authorization": f"Bearer {first_token}"},
    )
    second_created = client.post(
        "/api/v1/organizations",
        json={"name": "Second private workspace"},
        headers={"Authorization": f"Bearer {second_token}"},
    )

    assert first_created.status_code == 201
    assert second_created.status_code == 201

    first_list = client.get(
        "/api/v1/organizations?limit=200&offset=0",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    second_list = client.get(
        "/api/v1/organizations?limit=200&offset=0",
        headers={"Authorization": f"Bearer {second_token}"},
    )

    assert first_list.status_code == 200
    assert second_list.status_code == 200
    assert [item["id"] for item in first_list.json()] == [
        first_created.json()["id"]
    ]
    assert [item["id"] for item in second_list.json()] == [
        second_created.json()["id"]
    ]


def test_frontend_is_served_without_shadowing_api_docs(client):
    page = client.get("/")
    stylesheet = client.get("/static/styles.css")
    script = client.get("/static/app.js")
    docs = client.get("/docs")

    assert page.status_code == 200
    assert "NEXORA" in page.text
    assert stylesheet.status_code == 200
    assert "prefers-reduced-motion" in stylesheet.text
    assert script.status_code == 200
    assert "textContent" in script.text
    assert docs.status_code == 200
