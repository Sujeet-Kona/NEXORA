from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import InvalidCredentialsError
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
)
from backend.repositories.refresh_token_repository import (
    get_refresh_token_by_hash,
    rotate_refresh_token,
    revoke_refresh_token,
)


def refresh_access_token_service(
    db: Session,
    refresh_token: str,
) -> tuple[str, str]:
    token_hash = hash_refresh_token(refresh_token)

    stored_token = get_refresh_token_by_hash(
        db,
        token_hash,
    )

    if not stored_token:
        raise InvalidCredentialsError(
            "Invalid refresh token"
        )

    if stored_token.revoked_at is not None:
        raise InvalidCredentialsError(
            "Invalid refresh token"
        )

    now = datetime.now(timezone.utc)

    expires_at = stored_token.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc,
        )

    if expires_at <= now:
        raise InvalidCredentialsError(
            "Invalid refresh token"
        )

    user = stored_token.user

    if not user:
        raise InvalidCredentialsError(
            "Invalid refresh token"
        )

    new_refresh_token = create_refresh_token()

    new_token_hash = hash_refresh_token(
        new_refresh_token,
    )

    new_expires_at = now + timedelta(
        days=settings.refresh_token_expire_days,
    )

    rotate_refresh_token(
        db=db,
        current_refresh_token=stored_token,
        new_user_id=user.id,
        new_token_hash=new_token_hash,
        new_expires_at=new_expires_at,
        revoked_at=now,
    )

    new_access_token = create_access_token(
        str(user.id),
    )

    return new_access_token, new_refresh_token


def logout_user_service(
    db: Session,
    refresh_token: str,
) -> None:
    token_hash = hash_refresh_token(refresh_token)

    stored_token = get_refresh_token_by_hash(
        db,
        token_hash,
    )

    if not stored_token:
        raise InvalidCredentialsError(
            "Invalid refresh token"
        )

    if stored_token.revoked_at is not None:
        raise InvalidCredentialsError(
            "Invalid refresh token"
        )

    revoke_refresh_token(
        db=db,
        refresh_token=stored_token,
        revoked_at=datetime.now(timezone.utc),
    )
