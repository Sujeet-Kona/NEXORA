from unittest.mock import patch

from backend.db.models import (
    Document,
    DocumentStatus,
    User,
)
from backend.repositories.document_repository import (
    create_document,
    delete_document,
    get_document_by_id,
    get_documents_for_organization,
    replace_document_file,
    update_document_extraction_stats,
    update_document_failure,
)
from backend.services.organization_service import (
    create_organization_service,
)


def create_user(
    db,
    email,
    name,
):
    user = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def test_create_document(db):
    user = create_user(
        db,
        "document-create@example.com",
        "Document Create",
    )

    organization = create_organization_service(
        db=db,
        name="Document Company",
        user_id=user.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="engineering.pdf",
    )

    assert document.id is not None
    assert document.organization_id == organization.id
    assert document.uploaded_by == user.id
    assert document.name == "engineering.pdf"
    assert document.status == DocumentStatus.PENDING


def test_get_document_requires_correct_organization(
    db,
):
    user_a = create_user(
        db,
        "document-a@example.com",
        "Document A",
    )

    user_b = create_user(
        db,
        "document-b@example.com",
        "Document B",
    )

    organization_a = create_organization_service(
        db=db,
        name="Company A",
        user_id=user_a.id,
    )

    organization_b = create_organization_service(
        db=db,
        name="Company B",
        user_id=user_b.id,
    )

    document = create_document(
        db=db,
        organization_id=organization_a.id,
        uploaded_by=user_a.id,
        name="private-a.pdf",
    )

    found = get_document_by_id(
        db=db,
        document_id=document.id,
        organization_id=organization_a.id,
    )

    assert found is not None

    cross_tenant = get_document_by_id(
        db=db,
        document_id=document.id,
        organization_id=organization_b.id,
    )

    assert cross_tenant is None


def test_get_documents_for_organization_is_tenant_scoped(
    db,
):
    user_a = create_user(
        db,
        "document-list-a@example.com",
        "Document List A",
    )

    user_b = create_user(
        db,
        "document-list-b@example.com",
        "Document List B",
    )

    organization_a = create_organization_service(
        db=db,
        name="List Company A",
        user_id=user_a.id,
    )

    organization_b = create_organization_service(
        db=db,
        name="List Company B",
        user_id=user_b.id,
    )

    document_a = create_document(
        db=db,
        organization_id=organization_a.id,
        uploaded_by=user_a.id,
        name="a.pdf",
    )

    document_b = create_document(
        db=db,
        organization_id=organization_b.id,
        uploaded_by=user_b.id,
        name="b.pdf",
    )

    documents = get_documents_for_organization(
        db=db,
        organization_id=organization_a.id,
    )

    assert [document.id for document in documents] == [
        document_a.id
    ]
    assert document_b.id not in {
        document.id for document in documents
    }


def test_delete_document(db):
    user = create_user(
        db,
        "document-delete@example.com",
        "Document Delete",
    )

    organization = create_organization_service(
        db=db,
        name="Delete Company",
        user_id=user.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="delete.pdf",
    )

    delete_document(
        db=db,
        document=document,
    )

    found = get_document_by_id(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
    )

    assert found is None

def test_create_document_stores_file_metadata(db):
    user = create_user(
        db,
        "document-metadata@example.com",
        "Document Metadata",
    )

    organization = create_organization_service(
        db=db,
        name="Metadata Company",
        user_id=user.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="policy.pdf",
        storage_key="organizations/1/documents/1/file.pdf",
        file_size=12345,
        content_type="application/pdf",
    )

    assert document.storage_key == (
        "organizations/1/documents/1/file.pdf"
    )
    assert document.file_size == 12345
    assert document.content_type == "application/pdf"


def test_create_document_starts_without_extraction_stats(db):
    user = create_user(
        db,
        "document-stats-default@example.com",
        "Document Stats Default",
    )

    organization = create_organization_service(
        db=db,
        name="Stats Default Company",
        user_id=user.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="unprocessed.pdf",
    )

    assert document.page_count is None
    assert document.word_count is None
    assert document.character_count is None


def test_update_document_extraction_stats_flushes_without_commit(
    db,
):
    user = create_user(
        db,
        "document-stats-update@example.com",
        "Document Stats Update",
    )

    organization = create_organization_service(
        db=db,
        name="Stats Update Company",
        user_id=user.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="processed.pdf",
    )

    with patch.object(db, "commit") as commit:
        update_document_extraction_stats(
            db=db,
            document=document,
            page_count=3,
            word_count=120,
            character_count=800,
        )

    assert commit.call_count == 0
    assert document.page_count == 3
    assert document.word_count == 120
    assert document.character_count == 800

    db.expire_all()

    stored_document = (
        db.query(Document)
        .filter(Document.id == document.id)
        .first()
    )

    assert stored_document.page_count == 3
    assert stored_document.word_count == 120
    assert stored_document.character_count == 800


def test_update_document_failure_sets_status_and_reason(db):
    user = create_user(
        db,
        "document-failure-reason@example.com",
        "Document Failure Reason",
    )

    organization = create_organization_service(
        db=db,
        name="Failure Reason Company",
        user_id=user.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="broken.pdf",
    )

    assert document.failure_reason is None

    updated = update_document_failure(
        db=db,
        document=document,
        failure_reason="Document processing failed",
    )

    assert updated.status == DocumentStatus.FAILED
    assert updated.failure_reason == "Document processing failed"

    db.expire_all()

    stored_document = (
        db.query(Document)
        .filter(Document.id == document.id)
        .first()
    )

    assert stored_document.status == DocumentStatus.FAILED
    assert (
        stored_document.failure_reason
        == "Document processing failed"
    )


def test_replace_document_file_resets_status_and_failure_reason(
    db,
):
    user = create_user(
        db,
        "document-version-reset@example.com",
        "Document Version Reset",
    )

    organization = create_organization_service(
        db=db,
        name="Version Reset Company",
        user_id=user.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=user.id,
        name="policy.pdf",
        storage_key="organizations/1/documents/1/policy.pdf",
        file_size=100,
        content_type="application/pdf",
    )

    update_document_failure(
        db=db,
        document=document,
        failure_reason="Document text extraction failed",
    )

    db.refresh(document)

    assert document.failure_reason == (
        "Document text extraction failed"
    )

    updated = replace_document_file(
        db=db,
        document=document,
        name="policy-v2.pdf",
        storage_key="organizations/1/documents/1/policy-v2.pdf",
        file_size=200,
        content_type="application/pdf",
    )

    assert updated.version == 2
    assert updated.status == DocumentStatus.PENDING
    assert updated.failure_reason is None
    assert updated.name == "policy-v2.pdf"
