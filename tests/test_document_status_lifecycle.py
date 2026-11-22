from backend.db.models import (
    Document,
    DocumentStatus,
    OrganizationMembership,
    OrganizationRole,
    User,
)


def register_and_login(client, email):
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
        json={"email": email, "password": "MySecret123!"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def get_user(db, email):
    user = db.query(User).filter(User.email == email).first()
    assert user is not None
    return user


def create_organization(client, token, name):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_document(client, token, organization_id):
    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": "lifecycle.pdf"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def patch_status(client, token, organization_id, document_id, status):
    return client.patch(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        json={"status": status},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_manual_pending_to_processing_is_rejected(client):
    token = register_and_login(client, "lifecycle-processing@example.com")
    organization_id = create_organization(client, token, "Lifecycle Processing")
    document_id = create_document(client, token, organization_id)

    response = patch_status(client, token, organization_id, document_id, "processing")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Cannot change document status from 'pending' to 'processing'"
    )


def test_manual_pending_to_failed_is_rejected(client):
    token = register_and_login(client, "lifecycle-failed@example.com")
    organization_id = create_organization(client, token, "Lifecycle Failed")
    document_id = create_document(client, token, organization_id)

    response = patch_status(client, token, organization_id, document_id, "failed")
    assert response.status_code == 409


def test_failed_to_pending_is_allowed(client, db):
    token = register_and_login(client, "lifecycle-retry@example.com")
    organization_id = create_organization(client, token, "Lifecycle Retry")
    document_id = create_document(client, token, organization_id)

    db.query(Document).filter(Document.id == document_id).update(
        {Document.status: DocumentStatus.FAILED},
    )
    db.commit()

    response = patch_status(client, token, organization_id, document_id, "pending")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_repeating_pending_status_is_allowed(client):
    token = register_and_login(client, "lifecycle-idempotent@example.com")
    organization_id = create_organization(client, token, "Lifecycle Idempotent")
    document_id = create_document(client, token, organization_id)

    response = patch_status(client, token, organization_id, document_id, "pending")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_ready_to_pending_is_rejected(client, db):
    token = register_and_login(client, "lifecycle-ready@example.com")
    organization_id = create_organization(client, token, "Lifecycle Ready")
    document_id = create_document(client, token, organization_id)

    db.query(Document).filter(Document.id == document_id).update(
        {Document.status: DocumentStatus.READY},
    )
    db.commit()

    response = patch_status(client, token, organization_id, document_id, "pending")
    assert response.status_code == 409


def test_member_is_denied_before_transition_validation(client, db):
    owner_token = register_and_login(client, "lifecycle-member-owner@example.com")
    member_token = register_and_login(client, "lifecycle-member@example.com")
    organization_id = create_organization(client, owner_token, "Lifecycle Member")

    member = get_user(db, "lifecycle-member@example.com")
    db.add(
        OrganizationMembership(
            organization_id=organization_id,
            user_id=member.id,
            role=OrganizationRole.MEMBER,
        )
    )
    db.commit()

    document_id = create_document(client, owner_token, organization_id)
    response = patch_status(
        client, member_token, organization_id, document_id, "processing"
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Organization admin access required"}

def test_unknown_status_value_is_rejected_by_schema(client):
    token = register_and_login(client, "lifecycle-unknown-status@example.com")
    organization_id = create_organization(client, token, "Lifecycle Unknown Status")
    document_id = create_document(client, token, organization_id)

    response = patch_status(
        client,
        token,
        organization_id,
        document_id,
        "not-a-status",
    )

    assert response.status_code == 422
