import pytest
from pydantic import ValidationError

from backend.schemas.auth import AuthRegisterRequest


def test_register_request_accepts_valid_payload():
    request = AuthRegisterRequest(
        email="alice@example.com",
        full_name=" Alice Smith ",
        password="MySecret123!",
    )

    assert request.email == "alice@example.com"
    assert request.full_name == "Alice Smith"
    assert request.password == "MySecret123!"


def test_register_request_rejects_short_password():
    with pytest.raises(ValidationError):
        AuthRegisterRequest(
            email="alice@example.com",
            full_name="Alice Smith",
            password="short",
        )


def test_register_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        AuthRegisterRequest(
            email="not-an-email",
            full_name="Alice Smith",
            password="MySecret123!",
        )


def test_register_request_rejects_blank_full_name():
    with pytest.raises(ValidationError):
        AuthRegisterRequest(
            email="alice@example.com",
            full_name="   ",
            password="MySecret123!",
        )
