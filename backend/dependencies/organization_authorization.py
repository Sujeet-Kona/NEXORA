from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db.models import OrganizationMembership, OrganizationRole, User
from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import get_db
from backend.repositories.organization_repository import get_membership


def get_organization_membership(
    db: Session,
    organization_id: int,
    current_user: User,
) -> OrganizationMembership:
    membership = get_membership(
        db=db,
        organization_id=organization_id,
        user_id=current_user.id,
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization membership required",
        )

    return membership


def require_organization_member(
    db: Session,
    organization_id: int,
    current_user: User,
) -> User:
    get_organization_membership(
        db=db,
        organization_id=organization_id,
        current_user=current_user,
    )

    return current_user


def require_organization_admin(
    db: Session,
    organization_id: int,
    current_user: User,
) -> User:
    membership = get_organization_membership(
        db=db,
        organization_id=organization_id,
        current_user=current_user,
    )

    if membership.role not in {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin access required",
        )

    return current_user


def require_organization_owner(
    db: Session,
    organization_id: int,
    current_user: User,
) -> User:
    membership = get_organization_membership(
        db=db,
        organization_id=organization_id,
        current_user=current_user,
    )

    if membership.role != OrganizationRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization owner access required",
        )

    return current_user


def require_organization_member_dependency(
    organization_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    return require_organization_member(
        db=db,
        organization_id=organization_id,
        current_user=current_user,
    )


CurrentOrganizationMember = Annotated[
    User,
    Depends(require_organization_member_dependency),
]
