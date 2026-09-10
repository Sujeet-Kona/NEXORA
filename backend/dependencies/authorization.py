from fastapi import HTTPException, status

from backend.db.models import User, UserRole


def require_admin(
    current_user: User,
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user
