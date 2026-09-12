from sqlalchemy.orm import Session

from backend.core.exceptions import (
    DocumentNotFoundError,
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
    delete_document,
    get_document_by_id,
    get_documents_for_organization,
    update_document_status,
)
from backend.repositories.organization_repository import (
    get_membership,
    get_organization_by_id,
)


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
    )


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

    delete_document(
        db=db,
        document=document,
    )
