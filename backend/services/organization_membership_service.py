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
    delete_membership,
    get_membership,
    get_organization_by_id,
    get_organization_members,
    update_membership_role,
)
from backend.repositories.user_repository import get_user_by_id


def _get_acting_membership(
    db: Session,
    organization_id: int,
    acting_user: User,
) -> OrganizationMembership:
    membership = get_membership(
        db=db,
        organization_id=organization_id,
        user_id=acting_user.id,
    )

    if not membership:
        raise OrganizationMembershipRequiredError(
            "Organization membership required"
        )

    return membership


def _require_admin_or_owner(
    membership: OrganizationMembership,
) -> None:
    if membership.role not in {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
    }:
        raise OrganizationAccessDeniedError(
            "Organization admin access required"
        )


def _require_owner(
    membership: OrganizationMembership,
) -> None:
    if membership.role != OrganizationRole.OWNER:
        raise OrganizationAccessDeniedError(
            "Organization owner access required"
        )


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

    acting_membership = _get_acting_membership(
        db,
        organization_id,
        acting_user,
    )

    _require_admin_or_owner(acting_membership)

    if role == OrganizationRole.OWNER:
        raise OrganizationAccessDeniedError(
            "Owner role cannot be assigned"
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


def list_organization_members_service(
    db: Session,
    organization_id: int,
    acting_user: User,
) -> list[OrganizationMembership]:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    _get_acting_membership(
        db,
        organization_id,
        acting_user,
    )

    return get_organization_members(
        db,
        organization_id,
    )


def update_organization_member_role_service(
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

    acting_membership = _get_acting_membership(
        db,
        organization_id,
        acting_user,
    )

    _require_admin_or_owner(acting_membership)

    if role == OrganizationRole.OWNER:
        raise OrganizationAccessDeniedError(
            "Owner role cannot be assigned"
        )

    target_membership = get_membership(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if not target_membership:
        raise UserNotFoundError(
            "User not found in organization"
        )

    if target_membership.role == OrganizationRole.OWNER:
        raise OrganizationAccessDeniedError(
            "Owner membership cannot be modified"
        )

    if (
        acting_membership.role == OrganizationRole.ADMIN
        and target_membership.role == OrganizationRole.ADMIN
    ):
        raise OrganizationAccessDeniedError(
            "Organization admin access required"
        )

    return update_membership_role(
        db=db,
        membership=target_membership,
        role=role,
    )


def remove_organization_member_service(
    db: Session,
    organization_id: int,
    user_id: int,
    acting_user: User,
) -> None:
    organization = get_organization_by_id(
        db,
        organization_id,
    )

    if not organization:
        raise OrganizationNotFoundError(
            "Organization not found"
        )

    acting_membership = _get_acting_membership(
        db,
        organization_id,
        acting_user,
    )

    _require_admin_or_owner(acting_membership)

    target_membership = get_membership(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if not target_membership:
        raise UserNotFoundError(
            "User not found in organization"
        )

    if target_membership.role == OrganizationRole.OWNER:
        raise OrganizationAccessDeniedError(
            "Owner membership cannot be removed"
        )

    if (
        acting_membership.role == OrganizationRole.ADMIN
        and target_membership.role == OrganizationRole.ADMIN
    ):
        raise OrganizationAccessDeniedError(
            "Organization admin access required"
        )

    delete_membership(
        db=db,
        membership=target_membership,
    )
