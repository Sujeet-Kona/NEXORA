import jwt
import pytest

from backend.core.config import settings
from backend.core.exceptions import InvalidCredentialsError
from backend.core.security import (
    hash_refresh_token,
    verify_password,
)
from backend.db.models import RefreshToken, User
from backend.repositories.refresh_token_repository import (
    get_refresh_token_by_hash,
)
from backend.services.auth_service import (
    login_user_service,
    register_user_service,
)


def test_login_user_service_returns_access_and_refresh_tokens(db):
    user = register_user_service(
        db=db,
        email="login@example.com",
        full_name="Login User",
        password="MySecret123!",
    )

    access_token, refresh_token = login_user_service(
        db=db,
        email="login@example.com",
        password="MySecret123!",
    )

    assert access_token
    assert refresh_token
    assert user.password_hash is not None

    payload = jwt.decode(
        access_token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == str(user.id)

    stored_token = get_refresh_token_by_hash(
        db=db,
        token_hash=hash_refresh_token(refresh_token),
    )

    assert stored_token is not None
    assert stored_token.user_id == user.id
    assert stored_token.revoked_at is None


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
