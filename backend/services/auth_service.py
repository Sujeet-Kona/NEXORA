from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import (
    InvalidCredentialsError,
    TooManyLoginAttemptsError,
    UserAlreadyExistsError,
)
from backend.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from backend.db.models import AuditAction, User
from backend.repositories.refresh_token_repository import (
    create_refresh_token as create_refresh_token_record,
)
from backend.repositories.user_repository import (
    create_user,
    get_user_by_email,
)
from backend.services.audit_service import record_audit_event
from backend.services.login_throttle import LoginThrottle


login_throttle = LoginThrottle(
    max_attempts=settings.login_max_failed_attempts,
    lockout_seconds=settings.login_lockout_seconds,
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
    throttle: LoginThrottle | None = None,
) -> tuple[str, str]:
    throttle = throttle or login_throttle

    throttle_key = email.strip().lower()

    if throttle.is_locked(throttle_key):
        raise TooManyLoginAttemptsError(
            "Too many login attempts. Try again later.",
            retry_after=throttle.seconds_until_unlock(
                throttle_key,
            ),
        )

    user = get_user_by_email(
        db,
        email,
    )

    password_hash_to_check = (
        user.password_hash
        if user and user.password_hash
        else DUMMY_PASSWORD_HASH
    )

    password_matches = verify_password(
        password,
        password_hash_to_check,
    )

    if not user or not user.password_hash or not password_matches:
        throttle.register_failure(throttle_key)

        record_audit_event(
            db,
            organization_id=None,
            actor_user_id=user.id if user else None,
            action=AuditAction.LOGIN_FAILURE,
            resource_type="session",
            success=False,
        )

        raise InvalidCredentialsError(
            "Invalid email or password"
        )

    throttle.reset(throttle_key)

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

    record_audit_event(
        db,
        organization_id=None,
        actor_user_id=user.id,
        action=AuditAction.LOGIN_SUCCESS,
        resource_type="session",
        success=True,
    )

    return access_token, refresh_token
