import fitz
import pytest

from backend.core.exceptions import (
    DocumentNotFoundError,
    OrganizationMembershipRequiredError,
)
from backend.db.models import User
from backend.repositories.document_chunk_repository import (
    get_chunks_for_document,
)
from backend.repositories.document_repository import (
    create_document,
)
from backend.services.document_chunk_service import (
    chunk_document_service,
    list_document_chunks_service,
)
from backend.services.document_service import (
    create_document_service,
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


def make_pdf() -> bytes:
    pdf = fitz.open()
    page = pdf.new_page()

    page.insert_text(
        (72, 72),
        "Nexora chunking test policy.",
    )

    content = pdf.tobytes()

    pdf.close()

    return content


def test_chunk_document_requires_membership(db):
    owner = create_user(
        db,
        "chunk-owner@example.com",
        "Chunk Owner",
    )

    outsider = create_user(
        db,
        "chunk-outsider@example.com",
        "Chunk Outsider",
    )

    organization = create_organization_service(
        db=db,
        name="Chunk Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="policy.pdf",
    )

    with pytest.raises(
        OrganizationMembershipRequiredError
    ):
        chunk_document_service(
            db=db,
            organization_id=organization.id,
            document_id=document.id,
            current_user=outsider,
        )


def test_list_chunks_is_tenant_scoped(db):
    owner_a = create_user(
        db,
        "chunk-a@example.com",
        "Chunk A",
    )

    owner_b = create_user(
        db,
        "chunk-b@example.com",
        "Chunk B",
    )

    organization_a = create_organization_service(
        db=db,
        name="Chunk Company A",
        user_id=owner_a.id,
    )

    organization_b = create_organization_service(
        db=db,
        name="Chunk Company B",
        user_id=owner_b.id,
    )

    document = create_document(
        db=db,
        organization_id=organization_a.id,
        uploaded_by=owner_a.id,
        name="private.pdf",
    )

    with pytest.raises(DocumentNotFoundError):
        list_document_chunks_service(
            db=db,
            organization_id=organization_b.id,
            document_id=document.id,
            current_user=owner_b,
        )


def test_chunk_document_persists_chunks(db, tmp_path):
    owner = create_user(
        db,
        "chunk-persist@example.com",
        "Chunk Persist",
    )

    organization = create_organization_service(
        db=db,
        name="Chunk Persist Company",
        user_id=owner.id,
    )

    from backend.core.config import settings
    from backend.services.storage import LocalStorage

    storage = LocalStorage(
        settings.storage_path,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="policy.pdf",
        storage_key=None,
        file_size=None,
        content_type="application/pdf",
    )

    pdf_content = make_pdf()

    storage_key = storage.save(
        organization_id=organization.id,
        document_id=document.id,
        filename="policy.pdf",
        content=pdf_content,
    )

    document.storage_key = storage_key
    document.file_size = len(pdf_content)
    db.commit()
    db.refresh(document)

    chunks = chunk_document_service(
        db=db,
        organization_id=organization.id,
        document_id=document.id,
        current_user=owner,
    )

    assert len(chunks) >= 1
    assert chunks[0].document_id == document.id
    assert chunks[0].organization_id == organization.id
    assert chunks[0].chunk_index == 0
    assert "Nexora chunking test policy." in chunks[0].text


