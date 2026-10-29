import pytest

from backend.core.exceptions import DocumentUploadFailedError
from backend.db.models import DocumentStatus, User
from backend.repositories.document_repository import (
    create_document,
    get_document_by_id,
    replace_document_file,
)
from backend.services.organization_service import create_organization_service


def create_owner(db, email):
    user = User(
        email=email,
        full_name=email.split("@")[0],
        password_hash="test-hash",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_document_version_replacement_is_blocked_while_processing(db):
    owner = create_owner(db, "processing-version-guard@example.com")
    organization = create_organization_service(
        db=db,
        name="Processing Version Guard Company",
        user_id=owner.id,
    )
    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="policy.pdf",
        storage_key="documents/policy.pdf",
        content_type="application/pdf",
    )
    document.status = DocumentStatus.PROCESSING
    db.commit()
    db.refresh(document)

    with pytest.raises(DocumentUploadFailedError, match="processing"):
        replace_document_file(
            db=db,
            document=document,
            name="new-policy.pdf",
            storage_key="documents/new-policy.pdf",
            file_size=10,
            content_type="application/pdf",
        )

    db.refresh(document)
    assert document.status == DocumentStatus.PROCESSING
    assert document.version == 1
    assert document.storage_key == "documents/policy.pdf"


def test_document_version_replacement_uses_fresh_locked_status(db):
    owner = create_owner(db, "stale-version-guard@example.com")
    organization = create_organization_service(
        db=db,
        name="Stale Version Guard Company",
        user_id=owner.id,
    )
    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="policy.pdf",
        storage_key="documents/policy.pdf",
        content_type="application/pdf",
    )

    # Keep a detached PENDING object to represent a caller that loaded the
    # document before a concurrent worker claimed it for processing.
    stale_document = document
    db.expunge(stale_document)

    processing_document = get_document_by_id(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
    )
    assert processing_document is not None
    processing_document.status = DocumentStatus.PROCESSING
    db.commit()

    with pytest.raises(DocumentUploadFailedError, match="processing"):
        replace_document_file(
            db=db,
            document=stale_document,
            name="new-policy.pdf",
            storage_key="documents/new-policy.pdf",
            file_size=10,
            content_type="application/pdf",
        )

    fresh = get_document_by_id(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
    )
    assert fresh is not None
    assert fresh.status == DocumentStatus.PROCESSING
    assert fresh.version == 1
    assert fresh.storage_key == "documents/policy.pdf"
