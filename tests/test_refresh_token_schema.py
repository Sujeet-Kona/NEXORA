import pytest
from pydantic import ValidationError

from backend.schemas.auth import RefreshTokenRequest


def test_refresh_token_request_accepts_valid_token():
    request = RefreshTokenRequest(
        refresh_token="test-refresh-token",
    )

    assert request.refresh_token == "test-refresh-token"


def test_refresh_token_request_rejects_empty_token():
    with pytest.raises(ValidationError):
        RefreshTokenRequest(
            refresh_token="",
        )
