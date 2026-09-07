from backend.core.security import (
    create_refresh_token,
    hash_refresh_token,
)


def test_create_refresh_token_returns_random_values():
    first_token = create_refresh_token()
    second_token = create_refresh_token()

    assert first_token
    assert second_token
    assert first_token != second_token


def test_hash_refresh_token_is_deterministic():
    token = "test-refresh-token"

    first_hash = hash_refresh_token(token)
    second_hash = hash_refresh_token(token)

    assert first_hash == second_hash


def test_hash_refresh_token_returns_sha256_hex():
    token = "test-refresh-token"

    token_hash = hash_refresh_token(token)

    assert len(token_hash) == 64
    assert all(
        character in "0123456789abcdef"
        for character in token_hash
    )
