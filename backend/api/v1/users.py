from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies.authorization import AdminUser
from backend.dependencies.database import get_db
from backend.dependencies.pagination import Pagination
from backend.schemas.user import (
    UserResponse,
    UserRoleUpdate,
)
from backend.services.user_service import (
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
    admin: AdminUser,
    pagination: Pagination,
    db: Session = Depends(get_db),
):
    return get_users_service(
        db=db,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: int,
    admin: AdminUser,
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
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    return update_user_role_service(
        db=db,
        user_id=user_id,
        role=request.role,
        acting_user=admin,
    )
