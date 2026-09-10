import pytest
from fastapi import HTTPException

from backend.db.models import User, UserRole
from backend.dependencies.authorization import require_admin


def test_require_admin_allows_admin():
    user = User(
        id=1,
        email="admin@example.com",
        full_name="Admin User",
        role=UserRole.ADMIN,
    )

    assert require_admin(user) is user


def test_require_admin_rejects_member():
    user = User(
        id=2,
        email="member@example.com",
        full_name="Member User",
        role=UserRole.MEMBER,
    )

    with pytest.raises(HTTPException) as exc_info:
        require_admin(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin access required"
