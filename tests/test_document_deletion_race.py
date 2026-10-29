from unittest.mock import Mock

from backend.db.models import Document, DocumentStatus
from backend.main import app
from backend.services.providers import get_qdrant_repository


def register_and_login(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Delete Race Owner",
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


def test_delete_rejects_processing_document_without_deleting_row(
    client,
    db,
):
    token = register_and_login(
        client,
        "delete-processing-race@example.com",
    )

    response = client.post(
        "/api/v1/organizations",
        json={"name": "Delete Processing Race"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    organization_id = response.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        json={"name": "processing.pdf"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    document_id = response.json()["id"]

    document = db.query(Document).filter(Document.id == document_id).first()
    assert document is not None
    document.status = DocumentStatus.PROCESSING
    db.commit()

    qdrant = Mock()
    app.dependency_overrides[get_qdrant_repository] = lambda: qdrant

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/documents/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Document cannot be deleted while it is processing"
    }
    qdrant.delete_document_chunks.assert_called_once_with(
        document_id=document_id,
        organization_id=organization_id,
    )

    db.expire_all()
    document = db.query(Document).filter(Document.id == document_id).first()
    assert document is not None
    assert document.status == DocumentStatus.PROCESSING
