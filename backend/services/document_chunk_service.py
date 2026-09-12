from sqlalchemy.orm import Session

from backend.core.exceptions import (
    DocumentNotFoundError,
    OrganizationMembershipRequiredError,
)
from backend.db.models import Document, User
from backend.repositories.document_chunk_repository import (
    create_document_chunks,
    get_chunks_for_document,
)
from backend.repositories.document_repository import (
    get_document_by_id,
)
from backend.repositories.organization_repository import (
    get_membership,
)
from backend.services.document_chunking import split_text
from backend.services.document_extraction import extract_text


def _require_document_access(
    db: Session,
    document: Document,
    current_user: User,
) -> None:
    membership = get_membership(
        db=db,
        organization_id=document.organization_id,
        user_id=current_user.id,
    )

    if not membership:
        raise OrganizationMembershipRequiredError(
            "Organization membership required"
        )


def chunk_document_service(
    db: Session,
    organization_id: int,
    document_id: int,
    current_user: User,
) -> list:
    document = get_document_by_id(
        db=db,
        document_id=document_id,
        organization_id=organization_id,
    )

    if not document:
        raise DocumentNotFoundError(
            "Document not found"
        )

    _require_document_access(
        db=db,
        document=document,
        current_user=current_user,
    )

    if not document.storage_key:
        return []

    from backend.services.storage import LocalStorage
    from backend.core.config import settings

    storage = LocalStorage(
        settings.storage_path,
    )

    content = storage.read(
        document.storage_key,
    )

    extracted_text = extract_text(
        filename=document.name,
        content_type=document.content_type,
        content=content,
    )

    chunks = split_text(extracted_text)

    return create_document_chunks(
        db=db,
        document_id=document.id,
        organization_id=document.organization_id,
        chunks=chunks,
    )


def list_document_chunks_service(
    db: Session,
    organization_id: int,
    document_id: int,
    current_user: User,
) -> list:
    document = get_document_by_id(
        db=db,
        document_id=document_id,
        organization_id=organization_id,
    )

    if not document:
        raise DocumentNotFoundError(
            "Document not found"
        )

    _require_document_access(
        db=db,
        document=document,
        current_user=current_user,
    )

    return get_chunks_for_document(
        db=db,
        document_id=document.id,
        organization_id=document.organization_id,
    )
