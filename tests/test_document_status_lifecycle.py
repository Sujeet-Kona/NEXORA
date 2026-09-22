from backend.db.models import (
    OrganizationMembership,
    OrganizationRole,
    User,
)


def register_and_login(
    client,
    email,
):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "MySecret123!",
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def get_user(db, email):
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    assert user is not None

    return user


def create_organization(
    client,
    token,
    name,
):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def add_member(
    db,
    organization_id,
    user_id,
    role=OrganizationRole.MEMBER,
):
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    db.add(membership)
    db.commit()

    return membership


def create_document(
    client,
    token,
    organization_id,
    name="lifecycle.pdf",
):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": name},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def patch_status(
    client,
    token,
    organization_id,
    document_id,
    status,
):
    return client.patch(
        f"/api/v1/organizations/{organization_id}"
        f"/documents/{document_id}",
        json={"status": status},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )


def test_pending_to_processing_is_allowed(client):
    token = register_and_login(
        client,
        "lifecycle-pending-processing@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Pending Processing Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "processing",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processing"


def test_processing_to_ready_is_allowed(client):
    token = register_and_login(
        client,
        "lifecycle-processing-ready@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Processing Ready Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    assert patch_status(
        client,
        token,
        organization_id,
        document_id,
        "processing",
    ).status_code == 200

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "ready",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_pending_to_failed_is_allowed(client):
    token = register_and_login(
        client,
        "lifecycle-pending-failed@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Pending Failed Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "failed",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_failed_to_pending_is_allowed(client):
    token = register_and_login(
        client,
        "lifecycle-failed-pending@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Failed Pending Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    assert patch_status(
        client,
        token,
        organization_id,
        document_id,
        "failed",
    ).status_code == 200

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "pending",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_pending_to_ready_is_rejected(client):
    token = register_and_login(
        client,
        "lifecycle-skip-processing@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Skip Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "ready",
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Cannot change document status from "
            "'pending' to 'ready'"
        )
    }


def test_ready_to_pending_is_rejected(client):
    token = register_and_login(
        client,
        "lifecycle-ready-pending@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Ready Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    assert patch_status(
        client,
        token,
        organization_id,
        document_id,
        "processing",
    ).status_code == 200

    assert patch_status(
        client,
        token,
        organization_id,
        document_id,
        "ready",
    ).status_code == 200

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "pending",
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Cannot change document status from "
            "'ready' to 'pending'"
        )
    }


def test_ready_to_processing_is_rejected(client):
    token = register_and_login(
        client,
        "lifecycle-ready-processing@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Ready Processing Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    assert patch_status(
        client,
        token,
        organization_id,
        document_id,
        "processing",
    ).status_code == 200

    assert patch_status(
        client,
        token,
        organization_id,
        document_id,
        "ready",
    ).status_code == 200

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "processing",
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Cannot change document status from "
            "'ready' to 'processing'"
        )
    }


def test_repeating_the_same_status_is_allowed(client):
    token = register_and_login(
        client,
        "lifecycle-idempotent@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Idempotent Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "pending",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_unknown_status_value_is_rejected(client):
    token = register_and_login(
        client,
        "lifecycle-unknown-status@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Lifecycle Unknown Status Company",
    )

    document_id = create_document(
        client,
        token,
        organization_id,
    )

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "archived",
    )

    assert response.status_code == 422


def test_member_is_denied_before_transition_validation(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "lifecycle-member-owner@example.com",
    )

    member_token = register_and_login(
        client,
        "lifecycle-member@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Lifecycle Member Company",
    )

    member = get_user(
        db,
        "lifecycle-member@example.com",
    )

    add_member(
        db,
        organization_id,
        member.id,
        OrganizationRole.MEMBER,
    )

    document_id = create_document(
        client,
        owner_token,
        organization_id,
        name="member-lifecycle.pdf",
    )

    response = patch_status(
        client,
        member_token,
        organization_id,
        document_id,
        "ready",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization admin access required"
    }
