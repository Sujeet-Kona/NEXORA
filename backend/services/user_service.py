from sqlalchemy.orm import Session

from backend.core.exceptions import (
    InvalidUserIdError,
    UserNotFoundError,
)
from backend.db.models import AuditAction, User, UserRole
from backend.repositories.user_repository import (
    get_all_users,
    get_user_by_id,
    update_user_role,
)
from backend.services.audit_service import record_audit_event


def get_users_service(
    db: Session,
    limit: int,
    offset: int,
) -> list[User]:
    return get_all_users(
        db=db,
        limit=limit,
        offset=offset,
    )


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
    acting_user: User | None = None,
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

    updated_user = update_user_role(
        db=db,
        user=user,
        role=role,
    )

    record_audit_event(
        db,
        organization_id=None,
        actor_user_id=acting_user.id if acting_user else None,
        action=AuditAction.USER_PLATFORM_ROLE_CHANGED,
        resource_type="user",
        resource_id=user_id,
        details={"role": str(role)},
    )

    return updated_user
