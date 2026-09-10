from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import get_db
from backend.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationResponse,
)
from backend.services.organization_membership_service import (
    add_organization_member_service,
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

