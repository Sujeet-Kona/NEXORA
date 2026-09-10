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


def test_list_members_requires_authentication(client):
    response = client.get(
        "/api/v1/organizations/1/members"
    )

    assert response.status_code == 401


def test_member_can_list_members(client, db):
    owner_token = register_and_login(
        client,
        "list-api-owner@example.com",
    )

    member_token = register_and_login(
        client,
        "list-api-member@example.com",
    )

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "List API Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["id"]

    member = (
        db.query(User)
        .filter(
            User.email == "list-api-member@example.com"
        )
        .first()
    )

    assert member is not None

    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=member.id,
        role=OrganizationRole.MEMBER,
    )

    db.add(membership)
    db.commit()

    response = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers={
            "Authorization": f"Bearer {member_token}",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 2
    assert {
        item["user_id"]
        for item in body
    } == {
        member.id,
        db.query(User)
        .filter(
            User.email == "list-api-owner@example.com"
        )
        .first()
        .id,
    }


def test_update_member_role_requires_authentication(client):
    response = client.patch(
        "/api/v1/organizations/1/members/1",
        json={"role": "admin"},
    )

    assert response.status_code == 401


def test_owner_can_promote_member_to_admin(client, db):
    owner_token = register_and_login(
        client,
        "promote-api-owner@example.com",
    )

    register_and_login(
        client,
        "promote-api-member@example.com",
    )

    member = (
        db.query(User)
        .filter(
            User.email == "promote-api-member@example.com"
        )
        .first()
    )

    assert member is not None

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Promote API Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["id"]

    add_response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": member.id,
            "role": "member",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert add_response.status_code == 201

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/members/{member.id}",
        json={"role": "admin"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_admin_cannot_promote_member_to_owner(client, db):
    owner_token = register_and_login(
        client,
        "owner-owner-api@example.com",
    )

    admin_token = register_and_login(
        client,
        "owner-admin-api@example.com",
    )

    member_token = register_and_login(
        client,
        "owner-member-api@example.com",
    )

    admin = (
        db.query(User)
        .filter(
            User.email == "owner-admin-api@example.com"
        )
        .first()
    )

    member = (
        db.query(User)
        .filter(
            User.email == "owner-member-api@example.com"
        )
        .first()
    )

    assert admin is not None
    assert member is not None

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Owner Protection Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    organization_id = create_response.json()["id"]

    admin_membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=admin.id,
        role=OrganizationRole.ADMIN,
    )

    member_membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=member.id,
        role=OrganizationRole.MEMBER,
    )

    db.add_all([
        admin_membership,
        member_membership,
    ])
    db.commit()

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/members/{member.id}",
        json={"role": "owner"},
        headers={
            "Authorization": f"Bearer {admin_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Owner role cannot be assigned"
    }

    assert member_token


def test_member_cannot_change_member_role(client, db):
    owner_token = register_and_login(
        client,
        "member-change-owner@example.com",
    )

    member_token = register_and_login(
        client,
        "member-change-member@example.com",
    )

    target_token = register_and_login(
        client,
        "member-change-target@example.com",
    )

    member = (
        db.query(User)
        .filter(
            User.email == "member-change-member@example.com"
        )
        .first()
    )

    target = (
        db.query(User)
        .filter(
            User.email == "member-change-target@example.com"
        )
        .first()
    )

    assert member is not None
    assert target is not None
    assert target_token

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Member Change Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    organization_id = create_response.json()["id"]

    db.add_all([
        OrganizationMembership(
            organization_id=organization_id,
            user_id=member.id,
            role=OrganizationRole.MEMBER,
        ),
        OrganizationMembership(
            organization_id=organization_id,
            user_id=target.id,
            role=OrganizationRole.MEMBER,
        ),
    ])
    db.commit()

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/members/{target.id}",
        json={"role": "admin"},
        headers={
            "Authorization": f"Bearer {member_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required"
    }


def test_delete_member_requires_authentication(client):
    response = client.delete(
        "/api/v1/organizations/1/members/1"
    )

    assert response.status_code == 401


def test_owner_can_remove_member(client, db):
    owner_token = register_and_login(
        client,
        "remove-api-owner@example.com",
    )

    register_and_login(
        client,
        "remove-api-member@example.com",
    )

    member = (
        db.query(User)
        .filter(
            User.email == "remove-api-member@example.com"
        )
        .first()
    )

    assert member is not None

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Remove API Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    organization_id = create_response.json()["id"]

    add_response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": member.id,
            "role": "member",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert add_response.status_code == 201

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/members/{member.id}",
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert response.status_code == 204
    assert response.content == b""

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == organization_id,
            OrganizationMembership.user_id
            == member.id,
        )
        .first()
    )

    assert membership is None


def test_owner_cannot_remove_owner(client, db):
    owner_token = register_and_login(
        client,
        "protected-owner-api@example.com",
    )

    owner = (
        db.query(User)
        .filter(
            User.email == "protected-owner-api@example.com"
        )
        .first()
    )

    assert owner is not None

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Protected Owner API Company"},
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    organization_id = create_response.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/members/{owner.id}",
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Owner membership cannot be removed"
    }
