from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import (
    DocumentNotFoundError,
    DocumentUploadFailedError,
    InvalidDocumentUploadError,
    OrganizationAccessDeniedError,
    OrganizationMembershipRequiredError,
    OrganizationNotFoundError,
)
from backend.db.models import (
    Document,
    DocumentStatus,
    OrganizationRole,
    User,
)
from backend.repositories.document_repository import (
    create_document,
    create_document_pending,
    delete_document,
    finalize_document_upload,
    get_document_by_id,
    get_documents_for_organization,
    update_document_status,
)
from backend.repositories.organization_repository import (
    get_membership,
    get_organization_by_id,
)
from backend.services.storage import LocalStorage


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _get_organization_membership(
    db: Session,
    organization_id: int,
    user_id: int,
):
    membership = get_membership(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if not membership:
        raise OrganizationMembershipRequiredError(
            "Organization membership required"
        )

    return membership


def _require_admin_or_owner(
    membership,
) -> None:
    if membership.role not in {
        OrganizationRole.ADMIN,
        OrganizationRole.OWNER,
    }:
        raise OrganizationAccessDeniedError(
            "Organization admin access required"
        )


def create_document_service(
    db: Session,
    organization_id: int,
    name: str,
    current_user: User,
    storage_key: str | None = None,
    file_size: int | None = None,
    content_type: str | None = None,
) -> Document:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    _get_organization_membership(
        db=db,
        organization_id=organization_id,
        user_id=current_user.id,
    )

    return create_document(
        db=db,
        organization_id=organization_id,
        uploaded_by=current_user.id,
        name=name.strip(),
        storage_key=storage_key,
        file_size=file_size,
        content_type=content_type,
    )


def upload_document_service(
    db: Session,
    organization_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
    current_user: User,
) -> Document:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    _get_organization_membership(
        db=db,
        organization_id=organization_id,
        user_id=current_user.id,
    )

    safe_name = filename.strip()

    if not safe_name:
        raise InvalidDocumentUploadError(
            "Filename cannot be empty"
        )

    if len(content) == 0:
        raise InvalidDocumentUploadError(
            "Uploaded file is empty"
        )

    if len(content) > settings.max_upload_size_bytes:
        raise InvalidDocumentUploadError(
            "Uploaded file exceeds the maximum allowed size"
        )

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidDocumentUploadError(
            "Unsupported document type"
        )

    if content_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise InvalidDocumentUploadError(
                "Uploaded content is not a valid PDF"
            )

    if (
        content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        if not content.startswith(b"PK"):
            raise InvalidDocumentUploadError(
                "Uploaded content is not a valid DOCX file"
            )

    storage = LocalStorage(
        settings.storage_path,
    )

    document = create_document_pending(
        db=db,
        organization_id=organization_id,
        uploaded_by=current_user.id,
        name=safe_name,
    )

    storage_key = None

    try:
        storage_key = storage.save(
            organization_id=organization_id,
            document_id=document.id,
            filename=safe_name,
            content=content,
        )

        return finalize_document_upload(
            db=db,
            document=document,
            storage_key=storage_key,
            file_size=len(content),
            content_type=content_type,
        )

    except Exception as exc:
        db.rollback()

        if storage_key:
            storage.delete(storage_key)

        raise DocumentUploadFailedError(
            "Document upload failed"
        ) from exc


def get_document_service(
    db: Session,
    organization_id: int,
    document_id: int,
    current_user: User,
) -> Document:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    _get_organization_membership(
        db=db,
        organization_id=organization_id,
        user_id=current_user.id,
    )

    document = get_document_by_id(
        db=db,
        document_id=document_id,
        organization_id=organization_id,
    )

    if not document:
        raise DocumentNotFoundError(
            "Document not found"
        )

    return document


def list_documents_service(
    db: Session,
    organization_id: int,
    current_user: User,
) -> list[Document]:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    _get_organization_membership(
        db=db,
        organization_id=organization_id,
        user_id=current_user.id,
    )

    return get_documents_for_organization(
        db=db,
        organization_id=organization_id,
    )


def update_document_status_service(
    db: Session,
    organization_id: int,
    document_id: int,
    status: DocumentStatus,
    current_user: User,
) -> Document:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    membership = _get_organization_membership(
        db=db,
        organization_id=organization_id,
        user_id=current_user.id,
    )

    _require_admin_or_owner(membership)

    document = get_document_by_id(
        db=db,
        document_id=document_id,
        organization_id=organization_id,
    )

    if not document:
        raise DocumentNotFoundError(
            "Document not found"
        )

    return update_document_status(
        db=db,
        document=document,
        status=status,
    )


def delete_document_service(
    db: Session,
    organization_id: int,
    document_id: int,
    current_user: User,
) -> None:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    membership = _get_organization_membership(
        db=db,
        organization_id=organization_id,
        user_id=current_user.id,
    )

    _require_admin_or_owner(membership)

    document = get_document_by_id(
        db=db,
        document_id=document_id,
        organization_id=organization_id,
    )

    if not document:
        raise DocumentNotFoundError(
            "Document not found"
        )

    storage = LocalStorage(
        settings.storage_path,
    )

    storage_key = document.storage_key

    delete_document(
        db=db,
        document=document,
    )

    if storage_key:
        storage.delete(storage_key)
