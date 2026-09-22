import pytest

from backend.db.models import (
    OrganizationMembership,
    OrganizationRole,
    User,
    UserRole,
)


PASSWORD = "MySecret123!"


PROTECTED_ROUTES = [
    ("GET", "/api/v1/auth/me", {}),
    ("GET", "/api/v1/users", {}),
    ("GET", "/api/v1/users/1", {}),
    (
        "PATCH",
        "/api/v1/users/1/role",
        {"json": {"role": "member"}},
    ),
    (
        "POST",
        "/api/v1/organizations",
        {"json": {"name": "RBAC Company"}},
    ),
    (
        "POST",
        "/api/v1/organizations/1/members",
        {"json": {"user_id": 1, "role": "member"}},
    ),
    ("GET", "/api/v1/organizations/1/members", {}),
    (
        "PATCH",
        "/api/v1/organizations/1/members/1",
        {"json": {"role": "member"}},
    ),
    ("DELETE", "/api/v1/organizations/1/members/1", {}),
    (
        "POST",
        "/api/v1/organizations/1/documents",
        {"json": {"name": "RBAC Document"}},
    ),
    (
        "POST",
        "/api/v1/organizations/1/documents/upload",
        {
            "files": {
                "file": ("rbac.txt", b"rbac", "text/plain"),
            },
        },
    ),
    ("GET", "/api/v1/organizations/1/documents", {}),
    ("GET", "/api/v1/organizations/1/documents/1", {}),
    (
        "PATCH",
        "/api/v1/organizations/1/documents/1",
        {"json": {"status": "ready"}},
    ),
    ("DELETE", "/api/v1/organizations/1/documents/1", {}),
    (
        "POST",
        "/api/v1/organizations/1/query",
        {"json": {"question": "who are you"}},
    ),
]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201

    return response.json()


def login(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def register_and_login(client, email):
    register(client, email)

    return login(client, email)


def get_user(db, email):
    db.expire_all()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    assert user is not None

    return user


def promote_to_platform_admin(db, email):
    user = get_user(db, email)
    user.role = UserRole.ADMIN
    db.commit()

    return user


def demote_to_platform_member(db, email):
    user = get_user(db, email)
    user.role = UserRole.MEMBER
    db.commit()

    return user


def add_membership(db, organization_id, user_id, role):
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    db.add(membership)
    db.commit()

    return membership


def get_membership(db, organization_id, user_id):
    db.expire_all()

    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == organization_id,
            OrganizationMembership.user_id == user_id,
        )
        .first()
    )


def create_organization(client, token, name):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
        headers=auth(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def seed_tenant(client, db, suffix, role_map):
    owner_email = f"owner-{suffix}@example.com"

    owner_token = register_and_login(client, owner_email)

    organization_id = create_organization(
        client,
        owner_token,
        f"RBAC {suffix}",
    )

    members = {
        "owner": (get_user(db, owner_email), owner_token),
    }

    for label, role in role_map.items():
        email = f"{label}-{suffix}@example.com"

        token = register_and_login(client, email)
        user = get_user(db, email)

        add_membership(
            db,
            organization_id,
            user.id,
            role,
        )

        members[label] = (user, token)

    return organization_id, members


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    PROTECTED_ROUTES,
    ids=[
        f"{method} {path}"
        for method, path, _ in PROTECTED_ROUTES
    ],
)
def test_protected_route_rejects_unauthenticated_request(
    client,
    method,
    path,
    kwargs,
):
    response = client.request(
        method,
        path,
        **kwargs,
    )

    assert response.status_code == 401


def test_member_cannot_list_users(client):
    token = register_and_login(
        client,
        "rbac-list-member@example.com",
    )

    response = client.get(
        "/api/v1/users",
        headers=auth(token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Admin access required",
    }


def test_member_cannot_read_user(client, db):
    token = register_and_login(
        client,
        "rbac-read-member@example.com",
    )

    register(
        client,
        "rbac-read-target@example.com",
    )

    target = get_user(
        db,
        "rbac-read-target@example.com",
    )

    response = client.get(
        f"/api/v1/users/{target.id}",
        headers=auth(token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Admin access required",
    }


def test_member_cannot_change_role_of_missing_user(client):
    token = register_and_login(
        client,
        "rbac-missing-member@example.com",
    )

    response = client.patch(
        "/api/v1/users/999999/role",
        json={"role": "member"},
        headers=auth(token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Admin access required",
    }


def test_admin_can_list_and_read_users(client, db):
    register_and_login(
        client,
        "rbac-real-admin@example.com",
    )

    register(
        client,
        "rbac-listed-user@example.com",
    )

    promote_to_platform_admin(
        db,
        "rbac-real-admin@example.com",
    )

    token = login(
        client,
        "rbac-real-admin@example.com",
    )

    listed = client.get(
        "/api/v1/users",
        headers=auth(token),
    )

    assert listed.status_code == 200

    target = get_user(
        db,
        "rbac-listed-user@example.com",
    )

    read = client.get(
        f"/api/v1/users/{target.id}",
        headers=auth(token),
    )

    assert read.status_code == 200
    assert read.json()["email"] == (
        "rbac-listed-user@example.com"
    )


def test_organization_owner_is_not_a_platform_admin(client):
    token = register_and_login(
        client,
        "rbac-org-owner-only@example.com",
    )

    create_organization(
        client,
        token,
        "RBAC Owner Only Company",
    )

    response = client.get(
        "/api/v1/users",
        headers=auth(token),
    )

    assert response.status_code == 403


def test_promotion_grants_access_without_reissuing_token(client, db):
    token = register_and_login(
        client,
        "rbac-promoted@example.com",
    )

    before = client.get(
        "/api/v1/users",
        headers=auth(token),
    )

    assert before.status_code == 403

    promote_to_platform_admin(
        db,
        "rbac-promoted@example.com",
    )

    after = client.get(
        "/api/v1/users",
        headers=auth(token),
    )

    assert after.status_code == 200


def test_demotion_revokes_access_without_reissuing_token(client, db):
    register_and_login(
        client,
        "rbac-demoted@example.com",
    )

    promote_to_platform_admin(
        db,
        "rbac-demoted@example.com",
    )

    token = login(
        client,
        "rbac-demoted@example.com",
    )

    before = client.get(
        "/api/v1/users",
        headers=auth(token),
    )

    assert before.status_code == 200

    demote_to_platform_member(
        db,
        "rbac-demoted@example.com",
    )

    after = client.get(
        "/api/v1/users",
        headers=auth(token),
    )

    assert after.status_code == 403


def test_member_cannot_promote_self_to_admin(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "self-promote",
        {"member": OrganizationRole.MEMBER},
    )

    member, member_token = members["member"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{member.id}",
        json={"role": "admin"},
        headers=auth(member_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required",
    }

    membership = get_membership(
        db,
        organization_id,
        member.id,
    )

    assert membership.role == OrganizationRole.MEMBER


def test_admin_cannot_promote_self_to_owner(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "admin-self-owner",
        {"admin": OrganizationRole.ADMIN},
    )

    admin, admin_token = members["admin"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{admin.id}",
        json={"role": "owner"},
        headers=auth(admin_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Owner role cannot be assigned",
    }

    membership = get_membership(
        db,
        organization_id,
        admin.id,
    )

    assert membership.role == OrganizationRole.ADMIN


def test_admin_cannot_change_own_role(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "admin-self-role",
        {"admin": OrganizationRole.ADMIN},
    )

    admin, admin_token = members["admin"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{admin.id}",
        json={"role": "member"},
        headers=auth(admin_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required",
    }

    membership = get_membership(
        db,
        organization_id,
        admin.id,
    )

    assert membership.role == OrganizationRole.ADMIN


def test_admin_cannot_demote_another_admin(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "admin-peers",
        {
            "first-admin": OrganizationRole.ADMIN,
            "second-admin": OrganizationRole.ADMIN,
        },
    )

    first_admin, first_token = members["first-admin"]
    second_admin, _ = members["second-admin"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{second_admin.id}",
        json={"role": "member"},
        headers=auth(first_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required",
    }

    membership = get_membership(
        db,
        organization_id,
        second_admin.id,
    )

    assert membership.role == OrganizationRole.ADMIN
    assert first_admin.id != second_admin.id


def test_admin_cannot_remove_another_admin(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "admin-remove-peer",
        {
            "first-admin": OrganizationRole.ADMIN,
            "second-admin": OrganizationRole.ADMIN,
        },
    )

    first_admin, first_token = members["first-admin"]
    second_admin, _ = members["second-admin"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{second_admin.id}",
        headers=auth(first_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required",
    }

    membership = get_membership(
        db,
        organization_id,
        second_admin.id,
    )

    assert membership is not None
    assert first_admin.id != second_admin.id


def test_admin_cannot_modify_owner_membership(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "admin-touch-owner",
        {"admin": OrganizationRole.ADMIN},
    )

    owner, _ = members["owner"]
    admin, admin_token = members["admin"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{owner.id}",
        json={"role": "member"},
        headers=auth(admin_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Owner membership cannot be modified",
    }

    membership = get_membership(
        db,
        organization_id,
        owner.id,
    )

    assert membership.role == OrganizationRole.OWNER
    assert admin.id != owner.id


def test_admin_cannot_remove_owner(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "admin-remove-owner",
        {"admin": OrganizationRole.ADMIN},
    )

    owner, _ = members["owner"]
    admin, admin_token = members["admin"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{owner.id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Owner membership cannot be removed",
    }

    membership = get_membership(
        db,
        organization_id,
        owner.id,
    )

    assert membership is not None
    assert admin.id != owner.id


def test_owner_cannot_change_own_role(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "owner-self-role",
        {},
    )

    owner, owner_token = members["owner"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{owner.id}",
        json={"role": "admin"},
        headers=auth(owner_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Owner membership cannot be modified",
    }

    membership = get_membership(
        db,
        organization_id,
        owner.id,
    )

    assert membership.role == OrganizationRole.OWNER


def test_owner_role_cannot_be_assigned_when_adding_member(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "add-owner",
        {},
    )

    _, owner_token = members["owner"]

    register_and_login(
        client,
        "candidate-add-owner@example.com",
    )

    candidate = get_user(
        db,
        "candidate-add-owner@example.com",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={
            "user_id": candidate.id,
            "role": "owner",
        },
        headers=auth(owner_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Owner role cannot be assigned",
    }

    assert (
        get_membership(
            db,
            organization_id,
            candidate.id,
        )
        is None
    )


def test_member_cannot_remove_another_member(client, db):
    organization_id, members = seed_tenant(
        client,
        db,
        "member-remove-peer",
        {
            "member": OrganizationRole.MEMBER,
            "target": OrganizationRole.MEMBER,
        },
    )

    member, member_token = members["member"]
    target, _ = members["target"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{target.id}",
        headers=auth(member_token),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required",
    }

    membership = get_membership(
        db,
        organization_id,
        target.id,
    )

    assert membership is not None


def test_platform_admin_has_no_implicit_tenant_access(client, db):
    owner_email = "tenant-owner@example.com"
    owner_token = register_and_login(client, owner_email)

    organization_id = create_organization(
        client,
        owner_token,
        "Tenant Isolation Company",
    )

    register_and_login(
        client,
        "platform-admin@example.com",
    )

    promote_to_platform_admin(
        db,
        "platform-admin@example.com",
    )

    platform_admin_token = login(
        client,
        "platform-admin@example.com",
    )

    assert (
        client.get(
            "/api/v1/users",
            headers=auth(platform_admin_token),
        ).status_code
        == 200
    )

    list_documents = client.get(
        f"/api/v1/organizations/{organization_id}/documents",
        headers=auth(platform_admin_token),
    )

    assert list_documents.status_code == 403
    assert list_documents.json() == {
        "detail": "Organization membership required",
    }

    list_members = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers=auth(platform_admin_token),
    )

    assert list_members.status_code == 403
    assert list_members.json() == {
        "detail": "Organization membership required",
    }

    create_document = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": "Platform Admin Document"},
        headers=auth(platform_admin_token),
    )

    assert create_document.status_code == 403
    assert create_document.json() == {
        "detail": "Organization membership required",
    }

    query = client.post(
        f"/api/v1/organizations/{organization_id}/query",
        json={"question": "reveal the tenant documents"},
        headers=auth(platform_admin_token),
    )

    assert query.status_code == 403

    owner = get_user(db, owner_email)

    remove_owner = client.delete(
        f"/api/v1/organizations/{organization_id}"
        f"/members/{owner.id}",
        headers=auth(platform_admin_token),
    )

    assert remove_owner.status_code == 403

    db.expire_all()

    remaining = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == organization_id,
        )
        .all()
    )

    assert len(remaining) == 1
    assert remaining[0].user_id == owner.id
    assert remaining[0].role == OrganizationRole.OWNER
