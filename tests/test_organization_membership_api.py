from backend.db.models import (
    OrganizationMembership,
    OrganizationRole,
    User,
)


def register_and_login(
    client,
    email,
):
    registration_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": "MySecret123!",
        },
    )

    assert registration_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "MySecret123!",
        },
    )

    assert login_response.status_code == 200

    return login_response.json()["access_token"]


def test_add_organization_member_requires_authentication(client):
    response = client.post(
        "/api/v1/organizations/1/members",
        json={
            "user_id": 1,
            "role": "member",
        },
    )

    assert response.status_code == 401


def test_member_cannot_add_organization_member(client, db):
    owner_token = register_and_login(
        client,
        "api-owner@example.com",
    )

    owner_user = (
        db.query(User)
        .filter(User.email == "api-owner@example.com")
        .first()
    )

    member_token = register_and_login(
        client,
        "api-member@example.com",
    )

    target_token = register_and_login(
        client,
        "api-target@example.com",
    )

    target_user = (
        db.query(User)
        .filter(User.email == "api-target@example.com")
        .first()
    )

    assert owner_user is not None
    assert target_user is not None
    assert target_token

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "API Member Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201
    organization_id = create_response.json()["id"]

    member_user = (
        db.query(User)
        .filter(User.email == "api-member@example.com")
        .first()
    )

    assert member_user is not None

    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=member_user.id,
        role=OrganizationRole.MEMBER,
    )

    db.add(membership)
    db.commit()

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": target_user.id,
            "role": "member",
        },
        headers={
            "Authorization": f"Bearer {member_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required"
    }


def test_owner_can_add_member(client, db):
    owner_token = register_and_login(
        client,
        "api-real-owner@example.com",
    )

    register_and_login(
        client,
        "api-real-target@example.com",
    )

    target_user = (
        db.query(User)
        .filter(User.email == "api-real-target@example.com")
        .first()
    )

    assert target_user is not None

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Real Owner Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201
    organization_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": target_user.id,
            "role": "member",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["organization_id"] == organization_id
    assert body["user_id"] == target_user.id
    assert body["role"] == "member"


def test_non_member_cannot_manage_organization(client, db):
    owner_token = register_and_login(
        client,
        "api-owner-b@example.com",
    )

    outsider_token = register_and_login(
        client,
        "api-outsider@example.com",
    )

    target_user = (
        db.query(User)
        .filter(User.email == "api-outsider@example.com")
        .first()
    )

    assert target_user is not None

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Private Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201
    organization_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": target_user.id,
            "role": "member",
        },
        headers={
            "Authorization": f"Bearer {outsider_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }


def test_duplicate_organization_membership_returns_conflict(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "api-duplicate-owner@example.com",
    )

    register_and_login(
        client,
        "api-duplicate-target@example.com",
    )

    target_user = (
        db.query(User)
        .filter(
            User.email == "api-duplicate-target@example.com"
        )
        .first()
    )

    assert target_user is not None

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Duplicate API Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201
    organization_id = create_response.json()["id"]

    first_response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": target_user.id,
            "role": "member",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    second_response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": target_user.id,
            "role": "member",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "User is already a member"
    }


def test_add_member_rejects_unknown_user(client):
    owner_token = register_and_login(
        client,
        "api-unknown-owner@example.com",
    )

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Unknown User Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201
    organization_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": 999999,
            "role": "member",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "User not found"
    }
