import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError

from backend.core.exceptions import UserAlreadyExistsError
from backend.core.security import verify_password
from backend.db.models import Base
from backend.services.auth_service import register_user_service


TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_register_user_creates_user_with_hashed_password(db):
    user = register_user_service(
        db=db,
        email="auth@example.com",
        full_name="Auth User",
        password="MySecret123!",
    )

    assert user.email == "auth@example.com"
    assert user.full_name == "Auth User"
    assert user.password_hash is not None
    assert user.password_hash != "MySecret123!"
    assert verify_password(
        "MySecret123!",
        user.password_hash,
    )


def test_register_user_rejects_existing_email(db):
    register_user_service(
        db=db,
        email="existing@example.com",
        full_name="Existing User",
        password="MySecret123!",
    )

    with pytest.raises(UserAlreadyExistsError) as exc_info:
        register_user_service(
            db=db,
            email="existing@example.com",
            full_name="Another User",
            password="MySecret123!",
        )

    assert str(exc_info.value) == "Email already registered"


def test_register_user_converts_integrity_error(
    monkeypatch,
    db,
):
    def broken_create_user(**kwargs):
        raise IntegrityError(
            "duplicate",
            {},
            Exception("duplicate"),
        )

    monkeypatch.setattr(
        "backend.services.auth_service.create_user",
        broken_create_user,
    )

    with pytest.raises(UserAlreadyExistsError) as exc_info:
        register_user_service(
            db=db,
            email="race@example.com",
            full_name="Race User",
            password="MySecret123!",
        )

    assert str(exc_info.value) == "Email already registered"
