from typing import Annotated

from fastapi import Depends, HTTPException, status

from backend.db.models import User, UserRole
from backend.dependencies.auth import CurrentUser


def require_admin(
    current_user: User,
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user


def get_current_admin(
    current_user: CurrentUser,
) -> User:
    return require_admin(current_user)


AdminUser = Annotated[User, Depends(get_current_admin)]
