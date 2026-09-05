from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import UserAlreadyExistsError
from backend.db.models import User
from backend.repositories.user_repository import (
    create_user,
    get_user_by_email,
)


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
