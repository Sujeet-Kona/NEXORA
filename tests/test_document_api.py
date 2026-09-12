from backend.db.models import (
    Document,
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


def test_create_document_requires_authentication(client):
    response = client.post(
        "/api/v1/organizations/1/documents",
        json={
            "name": "test.pdf",
        },
    )

    assert response.status_code == 401


def test_member_can_create_document(client):
    token = register_and_login(
        client,
        "document-api-create@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Document API Create Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "engineering.pdf",
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["organization_id"] == organization_id
    assert body["name"] == "engineering.pdf"
    assert body["status"] == "pending"


def test_non_member_cannot_create_document(client):
    owner_token = register_and_login(
        client,
        "document-api-owner@example.com",
    )

    outsider_token = register_and_login(
        client,
        "document-api-outsider@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Private Document API Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "secret.pdf",
        },
        headers={
            "Authorization": f"Bearer {outsider_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }


def test_member_can_list_documents(client):
    token = register_and_login(
        client,
        "document-api-list@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Document List API Company",
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "one.pdf",
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert create_response.status_code == 201

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "two.pdf",
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert create_response.status_code == 201

    response = client.get(
        f"/api/v1/organizations/{organization_id}/documents",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 2
    assert {
        document["name"]
        for document in body
    } == {
        "one.pdf",
        "two.pdf",
    }


def test_member_can_get_own_organization_document(client):
    token = register_and_login(
        client,
        "document-api-get@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Document Get API Company",
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "architecture.pdf",
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == document_id


def test_other_organization_cannot_get_document(
    client,
    db,
):
    token_a = register_and_login(
        client,
        "document-api-company-a@example.com",
    )

    token_b = register_and_login(
        client,
        "document-api-company-b@example.com",
    )

    organization_a = create_organization(
        client,
        token_a,
        "Document Security Company A",
    )

    organization_b = create_organization(
        client,
        token_b,
        "Document Security Company B",
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_a}/documents",
        json={
            "name": "company-a-private.pdf",
        },
        headers={
            "Authorization": f"Bearer {token_a}",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_b}/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {token_b}",
        },
    )

    assert response.status_code == 404


def test_member_cannot_update_document_status(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "document-api-update-owner@example.com",
    )

    member_token = register_and_login(
        client,
        "document-api-update-member@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Document Update Company",
    )

    member = get_user(
        db,
        "document-api-update-member@example.com",
    )

    add_member(
        db,
        organization_id,
        member.id,
        OrganizationRole.MEMBER,
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "update.pdf",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        json={
            "status": "ready",
        },
        headers={
            "Authorization": f"Bearer {member_token}",
        },
    )

    assert response.status_code == 403


def test_admin_can_update_document_status(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "document-api-admin-owner@example.com",
    )

    admin_token = register_and_login(
        client,
        "document-api-admin@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Document Admin Company",
    )

    admin = get_user(
        db,
        "document-api-admin@example.com",
    )

    add_member(
        db,
        organization_id,
        admin.id,
        OrganizationRole.ADMIN,
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "admin-update.pdf",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        json={
            "status": "ready",
        },
        headers={
            "Authorization": f"Bearer {admin_token}",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_member_cannot_delete_document(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "document-api-delete-owner@example.com",
    )

    member_token = register_and_login(
        client,
        "document-api-delete-member@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Document Delete Company",
    )

    member = get_user(
        db,
        "document-api-delete-member@example.com",
    )

    add_member(
        db,
        organization_id,
        member.id,
        OrganizationRole.MEMBER,
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "delete.pdf",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {member_token}",
        },
    )

    assert response.status_code == 403


def test_admin_can_delete_document(
    client,
    db,
):
    owner_token = register_and_login(
        client,
        "document-api-real-owner@example.com",
    )

    admin_token = register_and_login(
        client,
        "document-api-real-admin@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Document Admin Delete Company",
    )

    admin = get_user(
        db,
        "document-api-real-admin@example.com",
    )

    add_member(
        db,
        organization_id,
        admin.id,
        OrganizationRole.ADMIN,
    )

    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={
            "name": "admin-delete.pdf",
        },
        headers={
            "Authorization": f"Bearer {owner_token}",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {admin_token}",
        },
    )

    assert response.status_code == 204
    assert response.content == b""
