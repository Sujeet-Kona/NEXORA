from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import get_db
from backend.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationMemberRoleUpdate,
    OrganizationResponse,
)
from backend.services.organization_membership_service import (
    add_organization_member_service,
    list_organization_members_service,
    remove_organization_member_service,
    update_organization_member_role_service,
)
from backend.services.organization_service import (
    create_organization_service,
)


router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
)


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=201,
)
def create_organization(
    request: OrganizationCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    return create_organization_service(
        db=db,
        name=request.name,
        user_id=current_user.id,
    )


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=201,
)
def add_organization_member(
    organization_id: int,
    request: OrganizationMemberCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    return add_organization_member_service(
        db=db,
        organization_id=organization_id,
        user_id=request.user_id,
        role=request.role,
        acting_user=current_user,
    )


@router.get(
    "/{organization_id}/members",
    response_model=list[OrganizationMemberResponse],
)
def list_organization_members(
    organization_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    return list_organization_members_service(
        db=db,
        organization_id=organization_id,
        acting_user=current_user,
    )


@router.patch(
    "/{organization_id}/members/{user_id}",
    response_model=OrganizationMemberResponse,
)
def update_organization_member_role(
    organization_id: int,
    user_id: int,
    request: OrganizationMemberRoleUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    return update_organization_member_role_service(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        role=request.role,
        acting_user=current_user,
    )


@router.delete(
    "/{organization_id}/members/{user_id}",
    status_code=204,
)
def remove_organization_member(
    organization_id: int,
    user_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    remove_organization_member_service(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        acting_user=current_user,
    )

    return Response(status_code=204)
