from backend.db.models import User, UserRole


def test_update_user_role_requires_authentication(client):
    response = client.patch(
        "/api/v1/users/1/role",
        json={"role": "admin"},
    )

    assert response.status_code == 401


def test_member_cannot_update_user_role(client):
    registration_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "member-role@example.com",
            "full_name": "Member Role User",
            "password": "MySecret123!",
        },
    )

    assert registration_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "member-role@example.com",
            "password": "MySecret123!",
        },
    )

    token = login_response.json()["access_token"]

    response = client.patch(
        "/api/v1/users/1/role",
        json={"role": "admin"},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Admin access required"
    }


def test_admin_can_update_user_role(client, db):
    admin_registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "role-admin@example.com",
            "full_name": "Role Admin",
            "password": "MySecret123!",
        },
    )

    target_registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "role-target@example.com",
            "full_name": "Role Target",
            "password": "MySecret123!",
        },
    )

    assert admin_registration.status_code == 201
    assert target_registration.status_code == 201

    admin = (
        db.query(User)
        .filter(User.email == "role-admin@example.com")
        .first()
    )

    target = (
        db.query(User)
        .filter(User.email == "role-target@example.com")
        .first()
    )

    assert admin is not None
    assert target is not None

    admin.role = UserRole.ADMIN
    db.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "role-admin@example.com",
            "password": "MySecret123!",
        },
    )

    token = login_response.json()["access_token"]

    response = client.patch(
        f"/api/v1/users/{target.id}/role",
        json={"role": "admin"},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == target.id
    assert body["role"] == "admin"


def test_update_user_role_rejects_invalid_role(client, db):
    admin_registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-role-admin@example.com",
            "full_name": "Invalid Role Admin",
            "password": "MySecret123!",
        },
    )

    assert admin_registration.status_code == 201

    admin = (
        db.query(User)
        .filter(User.email == "invalid-role-admin@example.com")
        .first()
    )

    assert admin is not None

    admin.role = UserRole.ADMIN
    db.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "invalid-role-admin@example.com",
            "password": "MySecret123!",
        },
    )

    token = login_response.json()["access_token"]

    response = client.patch(
        "/api/v1/users/1/role",
        json={"role": "superadmin"},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 422


def test_update_user_role_returns_404_for_missing_user(client, db):
    admin_registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "missing-target-admin@example.com",
            "full_name": "Missing Target Admin",
            "password": "MySecret123!",
        },
    )

    assert admin_registration.status_code == 201

    admin = (
        db.query(User)
        .filter(
            User.email == "missing-target-admin@example.com"
        )
        .first()
    )

    assert admin is not None

    admin.role = UserRole.ADMIN
    db.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "missing-target-admin@example.com",
            "password": "MySecret123!",
        },
    )

    token = login_response.json()["access_token"]

    response = client.patch(
        "/api/v1/users/999999/role",
        json={"role": "member"},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "User not found"
    }
