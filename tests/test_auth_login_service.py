import pytest

from backend.core.exceptions import InvalidCredentialsError
from backend.core.security import verify_password
from backend.db.models import Base
from backend.services.auth_service import (
    login_user_service,
    register_user_service,
)


def test_login_user_service_returns_jwt_for_valid_credentials(db):
    user = register_user_service(
        db=db,
        email="login@example.com",
        full_name="Login User",
        password="MySecret123!",
    )

    token = login_user_service(
        db=db,
        email="login@example.com",
        password="MySecret123!",
    )

    assert isinstance(token, str)
    assert token
    assert user.password_hash is not None
    assert verify_password(
        "MySecret123!",
        user.password_hash,
    )


def test_login_user_service_rejects_unknown_email(db):
    with pytest.raises(InvalidCredentialsError) as exc_info:
        login_user_service(
            db=db,
            email="missing@example.com",
            password="MySecret123!",
        )

    assert str(exc_info.value) == "Invalid email or password"


def test_login_user_service_rejects_wrong_password(db):
    register_user_service(
        db=db,
        email="wrong-password@example.com",
        full_name="Wrong Password",
        password="MySecret123!",
    )

    with pytest.raises(InvalidCredentialsError) as exc_info:
        login_user_service(
            db=db,
            email="wrong-password@example.com",
            password="WrongPassword!",
        )

    assert str(exc_info.value) == "Invalid email or password"


def test_login_user_service_rejects_user_without_password_hash(db):
    from backend.db.models import User

    user = User(
        email="legacy@example.com",
        full_name="Legacy User",
        password_hash=None,
    )

    db.add(user)
    db.commit()

    with pytest.raises(InvalidCredentialsError) as exc_info:
        login_user_service(
            db=db,
            email="legacy@example.com",
            password="MySecret123!",
        )

    assert str(exc_info.value) == "Invalid email or password"
