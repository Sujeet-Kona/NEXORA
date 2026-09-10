from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUser
from backend.dependencies.authorization import require_admin
from backend.dependencies.database import get_db
from backend.schemas.user import (
    UserCreate,
    UserResponse,
    UserRoleUpdate,
)
from backend.services.user_service import (
    create_user_service,
    get_user_service,
    get_users_service,
    update_user_role_service,
)


router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.get(
    "",
    response_model=list[UserResponse],
)
def get_users(
    db: Session = Depends(get_db),
):
    return get_users_service(db)


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
)
def create_user_route(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    return create_user_service(
        db=db,
        email=user.email,
        full_name=user.full_name,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    return get_user_service(
        db=db,
        user_id=user_id,
    )


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
)
def update_user_role(
    user_id: int,
    request: UserRoleUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    return update_user_role_service(
        db=db,
        user_id=user_id,
        role=request.role,
    )
