from datetime import datetime, timedelta, timezone

import pytest

from backend.core.exceptions import InvalidCredentialsError
from backend.core.security import (
    create_refresh_token,
    hash_refresh_token,
)
from backend.db.models import RefreshToken, User
from backend.services.refresh_token_service import (
    refresh_access_token_service,
)


def test_refresh_access_token_service_rotates_valid_token(db):
    user = User(
        email="refresh-service@example.com",
        full_name="Refresh Service User",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    raw_token = create_refresh_token()

    stored_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    db.add(stored_token)
    db.commit()
    db.refresh(stored_token)

    new_access_token, new_refresh_token = (
        refresh_access_token_service(
            db=db,
            refresh_token=raw_token,
        )
    )

    assert new_access_token
    assert new_refresh_token
    assert new_refresh_token != raw_token

    db.refresh(stored_token)

    assert stored_token.revoked_at is not None


def test_refresh_access_token_service_rejects_unknown_token(db):
    with pytest.raises(InvalidCredentialsError) as exc_info:
        refresh_access_token_service(
            db=db,
            refresh_token="unknown-refresh-token",
        )

    assert str(exc_info.value) == "Invalid refresh token"


def test_refresh_access_token_service_rejects_revoked_token(db):
    user = User(
        email="refresh-revoked@example.com",
        full_name="Refresh Revoked User",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    raw_token = create_refresh_token()

    stored_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=datetime.now(timezone.utc),
    )

    db.add(stored_token)
    db.commit()

    with pytest.raises(InvalidCredentialsError):
        refresh_access_token_service(
            db=db,
            refresh_token=raw_token,
        )


def test_refresh_access_token_service_rejects_expired_token(db):
    user = User(
        email="refresh-expired@example.com",
        full_name="Refresh Expired User",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    raw_token = create_refresh_token()

    stored_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    db.add(stored_token)
    db.commit()

    with pytest.raises(InvalidCredentialsError):
        refresh_access_token_service(
            db=db,
            refresh_token=raw_token,
        )


def test_refresh_access_token_service_rejects_missing_user(
    monkeypatch,
    db,
):
    raw_token = create_refresh_token()

    stored_token = RefreshToken(
        user_id=999999,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    def fake_get_refresh_token_by_hash(
        db,
        token_hash,
    ):
        return stored_token

    monkeypatch.setattr(
        "backend.services.refresh_token_service.get_refresh_token_by_hash",
        fake_get_refresh_token_by_hash,
    )

    with pytest.raises(InvalidCredentialsError) as exc_info:
        refresh_access_token_service(
            db=db,
            refresh_token=raw_token,
        )

    assert str(exc_info.value) == "Invalid refresh token"

def test_logout_user_service_revokes_refresh_token(db):
    user = User(
        email="logout-service@example.com",
        full_name="Logout Service User",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    raw_token = create_refresh_token()

    stored_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    db.add(stored_token)
    db.commit()
    db.refresh(stored_token)

    from backend.services.refresh_token_service import logout_user_service

    logout_user_service(
        db=db,
        refresh_token=raw_token,
    )

    db.refresh(stored_token)

    assert stored_token.revoked_at is not None


def test_logout_user_service_rejects_unknown_token(db):
    from backend.services.refresh_token_service import logout_user_service

    with pytest.raises(InvalidCredentialsError):
        logout_user_service(
            db=db,
            refresh_token="unknown-logout-token",
        )


def test_logout_user_service_rejects_already_revoked_token(db):
    user = User(
        email="logout-revoked@example.com",
        full_name="Logout Revoked User",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    raw_token = create_refresh_token()

    stored_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=datetime.now(timezone.utc),
    )

    db.add(stored_token)
    db.commit()

    from backend.services.refresh_token_service import logout_user_service

    with pytest.raises(InvalidCredentialsError):
        logout_user_service(
            db=db,
            refresh_token=raw_token,
        )
