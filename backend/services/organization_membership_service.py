from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import (
    OrganizationAccessDeniedError,
    OrganizationMembershipAlreadyExistsError,
    OrganizationMembershipRequiredError,
    OrganizationNotFoundError,
    UserNotFoundError,
)
from backend.db.models import (
    OrganizationMembership,
    OrganizationRole,
    User,
)
from backend.repositories.organization_repository import (
    create_organization_membership,
    get_membership,
    get_organization_by_id,
)
from backend.repositories.user_repository import get_user_by_id


def add_organization_member_service(
    db: Session,
    organization_id: int,
    user_id: int,
    role: OrganizationRole,
    acting_user: User,
) -> OrganizationMembership:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    acting_membership = get_membership(
        db=db,
        organization_id=organization_id,
        user_id=acting_user.id,
    )

    if not acting_membership:
        raise OrganizationMembershipRequiredError(
            "Organization membership required"
        )

    if acting_membership.role not in {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
    }:
        raise OrganizationAccessDeniedError(
            "Organization admin access required"
        )

    target_user = get_user_by_id(
        db,
        user_id,
    )

    if not target_user:
        raise UserNotFoundError(
            "User not found"
        )

    existing_membership = get_membership(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if existing_membership:
        raise OrganizationMembershipAlreadyExistsError(
            "User is already a member"
        )

    membership = create_organization_membership(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )

    try:
        db.commit()
        db.refresh(membership)
    except IntegrityError as exc:
        db.rollback()
        raise OrganizationMembershipAlreadyExistsError(
            "User is already a member"
        ) from exc

    return membership
