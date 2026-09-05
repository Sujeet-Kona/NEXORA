import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.exceptions import (
    InvalidUserIdError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from backend.db.models import Base
from backend.services.user_service import (
    create_user_service,
    get_user_service,
    get_users_service,
)


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


def test_get_users_service_returns_users(db):
    create_user_service(
        db=db,
        email="alice@example.com",
        full_name="Alice Smith",
    )

    create_user_service(
        db=db,
        email="bob@example.com",
        full_name="Bob Jones",
    )

    users = get_users_service(db)

    assert len(users) == 2
    assert users[0].email == "alice@example.com"
    assert users[1].email == "bob@example.com"


def test_get_user_service_returns_user(db):
    created_user = create_user_service(
        db=db,
        email="alice@example.com",
        full_name="Alice Smith",
    )

    user = get_user_service(
        db=db,
        user_id=created_user.id,
    )

    assert user.id == created_user.id
    assert user.email == "alice@example.com"


@pytest.mark.parametrize("user_id", [0, -1])
def test_get_user_service_rejects_non_positive_id(db, user_id):
    with pytest.raises(InvalidUserIdError) as exc_info:
        get_user_service(
            db=db,
            user_id=user_id,
        )

    assert str(exc_info.value) == (
        "User ID must be a positive integer"
    )


def test_get_user_service_raises_when_user_missing(db):
    with pytest.raises(UserNotFoundError) as exc_info:
        get_user_service(
            db=db,
            user_id=9999,
        )

    assert str(exc_info.value) == "User not found"


def test_create_user_service_rejects_duplicate_email(db):
    create_user_service(
        db=db,
        email="duplicate@example.com",
        full_name="First User",
    )

    with pytest.raises(UserAlreadyExistsError) as exc_info:
        create_user_service(
            db=db,
            email="duplicate@example.com",
            full_name="Second User",
        )

    assert str(exc_info.value) == "Email already registered"
