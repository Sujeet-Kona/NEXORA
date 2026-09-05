from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import (
    InvalidUserIdError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from backend.db.models import User
from backend.repositories.user_repository import (
    create_user,
    get_all_users,
    get_user_by_email,
    get_user_by_id,
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


def create_user_service(
    db: Session,
    email: str,
    full_name: str,
) -> User:
    existing_user = get_user_by_email(
        db,
        email,
    )

    if existing_user:
        raise UserAlreadyExistsError(
            "Email already registered"
        )

    try:
        return create_user(
            db=db,
            email=email,
            full_name=full_name,
        )
    except IntegrityError as exc:
        raise UserAlreadyExistsError(
            "Email already registered"
        ) from exc
