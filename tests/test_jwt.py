from datetime import datetime, timezone

import jwt

from backend.core.config import settings
from backend.core.security import create_access_token


def test_create_access_token_contains_subject():
    token = create_access_token("123")

    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == "123"


def test_create_access_token_contains_expiration():
    token = create_access_token("123")

    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert "exp" in payload
    assert payload["exp"] > datetime.now(timezone.utc).timestamp()


def test_create_access_token_cannot_be_verified_with_wrong_secret():
    token = create_access_token("123")

    try:
        jwt.decode(
            token,
            "this-is-a-different-test-secret-with-32-bytes-or-more",
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError:
        return

    raise AssertionError("Token was accepted with the wrong secret")

