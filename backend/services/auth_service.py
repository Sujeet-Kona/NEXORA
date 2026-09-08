from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
)
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from backend.db.models import User
from backend.repositories.refresh_token_repository import (
    create_refresh_token as create_refresh_token_record,
)
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


def login_user_service(
    db: Session,
    email: str,
    password: str,
) -> tuple[str, str]:
    user = get_user_by_email(
        db,
        email,
    )

    if not user or not user.password_hash:
        raise InvalidCredentialsError(
            "Invalid email or password"
        )

    if not verify_password(
        password,
        user.password_hash,
    ):
        raise InvalidCredentialsError(
            "Invalid email or password"
        )

    access_token = create_access_token(
        str(user.id),
    )

    refresh_token = create_refresh_token()

    refresh_token_hash = hash_refresh_token(
        refresh_token,
    )

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            days=settings.refresh_token_expire_days,
        )
    )

    create_refresh_token_record(
        db=db,
        user_id=user.id,
        token_hash=refresh_token_hash,
        expires_at=expires_at,
    )

    return access_token, refresh_token
