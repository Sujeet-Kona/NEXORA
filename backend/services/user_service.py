from sqlalchemy.orm import Session

from backend.core.exceptions import (
    InvalidUserIdError,
    UserNotFoundError,
)
from backend.db.models import User, UserRole
from backend.repositories.user_repository import (
    get_all_users,
    get_user_by_id,
    update_user_role,
)


def get_users_service(
    db: Session,
) -> list[User]:
    return get_all_users(db)


def get_user_service(
    db: Session,
    user_id: int,
) -> User:
    if user_id <= 0:
        raise InvalidUserIdError(
            "User ID must be a positive integer"
        )

    user = get_user_by_id(
        db,
        user_id,
    )

    if not user:
        raise UserNotFoundError(
            "User not found"
        )

    return user


def update_user_role_service(
    db: Session,
    user_id: int,
    role: UserRole,
) -> User:
    if user_id <= 0:
        raise InvalidUserIdError(
            "User ID must be a positive integer"
        )

    user = get_user_by_id(
        db,
        user_id,
    )

    if not user:
        raise UserNotFoundError(
            "User not found"
        )

    return update_user_role(
        db=db,
        user=user,
        role=role,
    )
