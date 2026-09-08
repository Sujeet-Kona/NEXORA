import pytest
from pydantic import ValidationError

from backend.schemas.auth import (
    AuthLoginRequest,
    TokenResponse,
)


def test_login_request_accepts_valid_payload():
    request = AuthLoginRequest(
        email="alice@example.com",
        password="MySecret123!",
    )

    assert request.email == "alice@example.com"
    assert request.password == "MySecret123!"


def test_login_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        AuthLoginRequest(
            email="not-an-email",
            password="MySecret123!",
        )


def test_login_request_rejects_empty_password():
    with pytest.raises(ValidationError):
        AuthLoginRequest(
            email="alice@example.com",
            password="",
        )


def test_token_response_defaults_to_bearer():
    response = TokenResponse(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
    )

    assert response.access_token == "test-access-token"
    assert response.refresh_token == "test-refresh-token"
    assert response.token_type == "bearer"
