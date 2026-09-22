import logging

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import (
    DocumentDeletionFailedError,
    DocumentNotFoundError,
    DocumentUploadFailedError,
    InvalidDocumentStatusTransitionError,
    InvalidDocumentUploadError,
    OrganizationAccessDeniedError,
    OrganizationMembershipRequiredError,
    OrganizationNotFoundError,
)
from backend.core.logging import LOGGER_NAME
from backend.db.models import (
    Document,
    DocumentStatus,
    OrganizationRole,
    User,
)
from backend.repositories.document_chunk_repository import (
    delete_chunks_for_document,
)
from backend.repositories.document_repository import (
    create_document,
    create_document_pending,
    delete_document,
    finalize_document_upload,
    get_document_by_id,
    get_documents_for_organization,
    replace_document_file,
    update_document_status,
)
from backend.repositories.organization_repository import (
    get_membership,
    get_organization_by_id,
)
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.bm25_service import invalidate_bm25_index
from backend.services.storage import LocalStorage


logger = logging.getLogger(LOGGER_NAME)


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ALLOWED_STATUS_TRANSITIONS = {
    DocumentStatus.PENDING: {
        DocumentStatus.PROCESSING,
        DocumentStatus.FAILED,
    },
    DocumentStatus.PROCESSING: {
        DocumentStatus.READY,
        DocumentStatus.FAILED,
    },
    DocumentStatus.READY: set(),
    DocumentStatus.FAILED: {
        DocumentStatus.PENDING,
    },
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


def _validate_upload(
    filename: str,
    content: bytes,
    content_type: str | None,
) -> str:
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

    return safe_name


def _validate_status_transition(
    current_status: DocumentStatus,
    new_status: DocumentStatus,
) -> None:
    if new_status == current_status:
        return

    allowed = ALLOWED_STATUS_TRANSITIONS.get(
        DocumentStatus(current_status),
        set(),
    )

    if new_status not in allowed:
        raise InvalidDocumentStatusTransitionError(
            f"Cannot change document status from "
            f"'{current_status}' to '{new_status}'"
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

    safe_name = _validate_upload(
        filename=filename,
        content=content,
        content_type=content_type,
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


def upload_document_version_service(
    db: Session,
    organization_id: int,
    document_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
    current_user: User,
    qdrant_repository: QdrantRepository,
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

    safe_name = _validate_upload(
        filename=filename,
        content=content,
        content_type=content_type,
    )

    storage = LocalStorage(
        settings.storage_path,
    )

    previous_storage_key = document.storage_key
    new_storage_key = None

    try:
        new_storage_key = storage.save(
            organization_id=organization_id,
            document_id=document.id,
            filename=safe_name,
            content=content,
        )

        try:
            qdrant_repository.delete_document_chunks(
                document_id=document.id,
                organization_id=document.organization_id,
            )
        except Exception as exc:
            raise DocumentDeletionFailedError(
                "Existing document vectors could not be purged"
            ) from exc

        delete_chunks_for_document(
            db=db,
            document_id=document.id,
            organization_id=document.organization_id,
        )

        updated_document = replace_document_file(
            db=db,
            document=document,
            name=safe_name,
            storage_key=new_storage_key,
            file_size=len(content),
            content_type=content_type,
        )

    except DocumentDeletionFailedError:
        db.rollback()

        if new_storage_key:
            storage.delete(new_storage_key)

        raise

    except Exception as exc:
        db.rollback()

        if new_storage_key:
            storage.delete(new_storage_key)

        raise DocumentUploadFailedError(
            "Document upload failed"
        ) from exc

    invalidate_bm25_index(
        organization_id,
    )

    if previous_storage_key:
        try:
            storage.delete(previous_storage_key)
        except Exception:
            logger.warning(
                "Previous document version file could not be deleted",
                extra={"document_id": document.id},
            )

    return updated_document


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
    limit: int,
    offset: int,
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
        limit=limit,
        offset=offset,
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

    _validate_status_transition(
        current_status=document.status,
        new_status=status,
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
    qdrant_repository: QdrantRepository,
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

    try:
        qdrant_repository.delete_document_chunks(
            document_id=document.id,
            organization_id=document.organization_id,
        )
    except Exception as exc:
        raise DocumentDeletionFailedError(
            "Document vectors could not be purged"
        ) from exc

    storage = LocalStorage(
        settings.storage_path,
    )

    storage_key = document.storage_key

    delete_document(
        db=db,
        document=document,
    )

    invalidate_bm25_index(
        organization_id,
    )

    if storage_key:
        storage.delete(storage_key)

