from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUser
from backend.dependencies.database import get_db
from backend.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
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
