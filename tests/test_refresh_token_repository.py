from datetime import datetime, timedelta, timezone

from backend.db.models import User
from backend.repositories.refresh_token_repository import (
    create_refresh_token,
    get_refresh_token_by_hash,
    revoke_refresh_token,
)


def test_create_refresh_token_persists_record(db):
    user = User(
        email="refresh-repo@example.com",
        full_name="Refresh Repo User",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    refresh_token = create_refresh_token(
        db=db,
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=expires_at,
    )

    assert refresh_token.id is not None
    assert refresh_token.user_id == user.id
    assert refresh_token.token_hash == "a" * 64
    assert refresh_token.expires_at == expires_at.replace(tzinfo=None)
    assert refresh_token.revoked_at is None


def test_get_refresh_token_by_hash_returns_record(db):
    user = User(
        email="refresh-find@example.com",
        full_name="Refresh Find User",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    refresh_token = create_refresh_token(
        db=db,
        user_id=user.id,
        token_hash="b" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    found = get_refresh_token_by_hash(
        db=db,
        token_hash=refresh_token.token_hash,
    )

    assert found is not None
    assert found.id == refresh_token.id


def test_get_refresh_token_by_hash_returns_none_when_missing(db):
    found = get_refresh_token_by_hash(
        db=db,
        token_hash="c" * 64,
    )

    assert found is None


def test_revoke_refresh_token_sets_revoked_at(db):
    user = User(
        email="refresh-revoke@example.com",
        full_name="Refresh Revoke User",
        password_hash="test-hash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    refresh_token = create_refresh_token(
        db=db,
        user_id=user.id,
        token_hash="d" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    revoked_at = datetime.now(timezone.utc)

    revoked = revoke_refresh_token(
        db=db,
        refresh_token=refresh_token,
        revoked_at=revoked_at,
    )

    assert revoked.revoked_at == revoked_at.replace(tzinfo=None)

    found = get_refresh_token_by_hash(
        db=db,
        token_hash=refresh_token.token_hash,
    )

    assert found is not None
    assert found.revoked_at == revoked_at.replace(tzinfo=None)

