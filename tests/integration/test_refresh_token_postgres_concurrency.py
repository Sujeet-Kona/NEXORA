"""PostgreSQL concurrency regression for refresh-token rotation.

Runs when TEST_DATABASE_URL points to PostgreSQL (as in CI). SQLite cannot
exercise PostgreSQL row-update locking semantics.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.core.exceptions import InvalidCredentialsError
from backend.core.security import create_refresh_token, hash_refresh_token
from backend.db.models import RefreshToken, User
from backend.services import refresh_token_service


@pytest.mark.integration
def test_postgres_concurrent_refresh_token_rotation_consumes_token_once(
    monkeypatch,
):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("TEST_DATABASE_URL must point to PostgreSQL")

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    email = f"refresh-concurrency-{uuid4().hex}@example.com"
    raw_token = create_refresh_token()
    token_hash = hash_refresh_token(raw_token)

    try:
        with SessionLocal() as setup_db:
            user = User(
                email=email,
                full_name="Refresh Concurrency Test",
                password_hash="integration-test-hash",
            )
            setup_db.add(user)
            setup_db.commit()

            old_token = RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            setup_db.add(old_token)
            setup_db.commit()
            user_id = user.id

        barrier = Barrier(2)
        original_rotate = refresh_token_service.rotate_refresh_token

        def synchronized_rotate(**kwargs):
            # Both service calls have already read the old token and reached
            # rotation before either can execute the guarded UPDATE.
            barrier.wait(timeout=15)
            return original_rotate(**kwargs)

        monkeypatch.setattr(
            refresh_token_service,
            "rotate_refresh_token",
            synchronized_rotate,
        )

        def attempt_rotation():
            with SessionLocal() as session:
                try:
                    return refresh_token_service.refresh_access_token_service(
                        db=session,
                        refresh_token=raw_token,
                    )
                except InvalidCredentialsError:
                    return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: attempt_rotation(), range(2)))

        successful_rotations = [result for result in results if result is not None]
        assert len(successful_rotations) == 1

        with SessionLocal() as verify_db:
            tokens = (
                verify_db.query(RefreshToken)
                .filter(RefreshToken.user_id == user_id)
                .all()
            )
            assert len(tokens) == 2
            consumed = next(token for token in tokens if token.token_hash == token_hash)
            replacements = [token for token in tokens if token.token_hash != token_hash]
            assert consumed.revoked_at is not None
            assert len(replacements) == 1
            assert replacements[0].revoked_at is None
    finally:
        with SessionLocal() as cleanup_db:
            user = cleanup_db.query(User).filter(User.email == email).first()
            if user:
                cleanup_db.query(RefreshToken).filter(
                    RefreshToken.user_id == user.id
                ).delete(synchronize_session=False)
                cleanup_db.delete(user)
                cleanup_db.commit()
        engine.dispose()
