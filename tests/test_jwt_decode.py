import time

import jwt
import pytest

from backend.core.config import settings
from backend.core.security import (
    create_access_token,
    decode_access_token,
)


def test_decode_access_token_returns_subject():
    token = create_access_token("123")

    payload = decode_access_token(token)

    assert payload["sub"] == "123"


def test_decode_access_token_rejects_wrong_secret():
    token = create_access_token("123")

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            token,
            "this-is-a-different-test-secret-with-32-bytes-or-more",
            algorithms=[settings.jwt_algorithm],
        )


def test_decode_access_token_rejects_expired_token():
    payload = {
        "sub": "123",
        "exp": int(time.time()) - 1,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
