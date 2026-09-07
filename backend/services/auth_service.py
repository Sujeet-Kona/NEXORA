from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import UserAlreadyExistsError
from backend.core.security import hash_password
from backend.db.models import User
from backend.repositories.user_repository import (
    create_user,
    get_user_by_email,
)


def register_user_service(
    db: Session,
    email: str,
    full_name: str,
    password: str,
) -> User:
    existing_user = get_user_by_email(
        db,
        email,
    )

    if existing_user:
        raise UserAlreadyExistsError(
            "Email already registered"
        )

    password_hash = hash_password(password)

    try:
        return create_user(
            db=db,
            email=email,
            full_name=full_name,
            password_hash=password_hash,
        )
    except IntegrityError as exc:
        raise UserAlreadyExistsError(
            "Email already registered"
        ) from exc
