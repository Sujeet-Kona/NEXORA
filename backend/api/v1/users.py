from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.exceptions import (
    InvalidUserIdError,
    UserNotFoundError,
)
from backend.dependencies.database import get_db
from backend.repositories.user_repository import (
    get_all_users,
    get_user_by_id,
)
from backend.schemas.user import UserCreate, UserResponse
from backend.services.user_service import create_user_service


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
    return get_all_users(db)


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
    if user_id <= 0:
        raise InvalidUserIdError(
            "User ID must be a positive integer"
        )

    user = get_user_by_id(db, user_id)

    if not user:
        raise UserNotFoundError("User not found")

    return user
