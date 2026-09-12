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
):
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=OrganizationRole.MEMBER,
    )

    db.add(membership)
    db.commit()


def test_upload_requires_authentication(client):
    response = client.post(
        "/api/v1/organizations/1/documents/upload",
        files={
            "file": (
                "test.pdf",
                b"%PDF-1.7 test",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 401


def test_upload_pdf(client, tmp_path):
    token = register_and_login(
        client,
        "upload-pdf@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Upload PDF Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "policy.pdf",
                b"%PDF-1.7 fake pdf content",
                "application/pdf",
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["organization_id"] == organization_id
    assert body["name"] == "policy.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["file_size"] == len(
        b"%PDF-1.7 fake pdf content"
    )
    assert body["storage_key"]
    assert body["status"] == "pending"


def test_upload_empty_file_rejected(client):
    token = register_and_login(
        client,
        "upload-empty@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Upload Empty Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "empty.pdf",
                b"",
                "application/pdf",
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Uploaded file is empty"
    }


def test_upload_invalid_pdf_content_rejected(client):
    token = register_and_login(
        client,
        "upload-invalid-pdf@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Upload Invalid PDF Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "fake.pdf",
                b"this is not actually a pdf",
                "application/pdf",
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Uploaded content is not a valid PDF"
    }


def test_upload_unsupported_type_rejected(client):
    token = register_and_login(
        client,
        "upload-type@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Upload Type Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "script.exe",
                b"MZfake",
                "application/octet-stream",
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unsupported document type"
    }


def test_non_member_cannot_upload(client):
    owner_token = register_and_login(
        client,
        "upload-owner@example.com",
    )

    outsider_token = register_and_login(
        client,
        "upload-outsider@example.com",
    )

    organization_id = create_organization(
        client,
        owner_token,
        "Private Upload Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "secret.pdf",
                b"%PDF-1.7 private",
                "application/pdf",
            )
        },
        headers={
            "Authorization": f"Bearer {outsider_token}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Organization membership required"
    }


def test_upload_does_not_trust_client_tenant_fields(
    client,
    db,
):
    token = register_and_login(
        client,
        "upload-tenant@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Tenant Upload Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "../../secret.pdf",
                b"%PDF-1.7 safe",
                "application/pdf",
            )
        },
        data={
            "organization_id": "999999",
            "uploaded_by": "999999",
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    body = response.json()

    user = get_user(
        db,
        "upload-tenant@example.com",
    )

    assert body["organization_id"] == organization_id
    assert body["uploaded_by"] == user.id
    assert "../../" not in body["storage_key"]
def test_upload_oversized_file_rejected(client):
    token = register_and_login(
        client,
        "upload-large@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Large Upload Company",
    )

    oversized_content = (
        b"%PDF-1.7"
        + b"x" * (10 * 1024 * 1024)
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "large.pdf",
                oversized_content,
                "application/pdf",
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "Uploaded file exceeds the maximum allowed size"
        )
    }


def test_upload_creates_pending_document(client, db):
    token = register_and_login(
        client,
        "upload-pending@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Pending Upload Company",
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "pending.pdf",
                b"%PDF-1.7 pending",
                "application/pdf",
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201

    document_id = response.json()["id"]

    document = (
        db.query(
            __import__(
                "backend.db.models",
                fromlist=["Document"],
            ).Document
        )
        .filter(
            __import__(
                "backend.db.models",
                fromlist=["Document"],
            ).Document.id == document_id
        )
        .first()
    )

    assert document is not None
    assert document.status == "pending"
    assert document.storage_key is not None
    assert document.file_size > 0
    assert document.content_type == "application/pdf"


def test_upload_file_at_exact_limit_is_accepted(client):
    token = register_and_login(
        client,
        "upload-exact-limit@example.com",
    )

    organization_id = create_organization(
        client,
        token,
        "Exact Limit Company",
    )

    header = b"%PDF-1.7"
    content = header + b"x" * (
        10 * 1024 * 1024 - len(header)
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents/upload",
        files={
            "file": (
                "exact-limit.pdf",
                content,
                "application/pdf",
            )
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201
    assert response.json()["file_size"] == len(content)
