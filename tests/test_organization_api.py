from backend.db.models import OrganizationMembership, OrganizationRole, User


def test_create_organization_requires_authentication(client):
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "No Auth Company",
        },
    )

    assert response.status_code == 401


def test_create_organization_creates_owner_membership(client, db):
    registration_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "organization-api@example.com",
            "full_name": "Organization API User",
            "password": "MySecret123!",
        },
    )

    assert registration_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "organization-api@example.com",
            "password": "MySecret123!",
        },
    )

    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "My Company",
        },
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["name"] == "My Company"
    assert body["id"] is not None

    user = (
        db.query(User)
        .filter(
            User.email == "organization-api@example.com"
        )
        .first()
    )

    assert user is not None

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == body["id"],
            OrganizationMembership.user_id
            == user.id,
        )
        .first()
    )

    assert membership is not None
    assert membership.role == OrganizationRole.OWNER


def test_create_organization_does_not_accept_client_role(
    client,
):
    registration_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "organization-role@example.com",
            "full_name": "Organization Role User",
            "password": "MySecret123!",
        },
    )

    assert registration_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "organization-role@example.com",
            "password": "MySecret123!",
        },
    )

    token = login_response.json()["access_token"]

    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "Secure Company",
            "role": "admin",
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    assert response.json()["name"] == "Secure Company"
