import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.exceptions import (
    InvalidUserIdError,
    UserNotFoundError,
)
from backend.db.models import Base, UserRole
from backend.repositories.user_repository import create_user
from backend.services.user_service import (
    get_user_service,
    get_users_service,
    update_user_role_service,
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


def create_test_user(db, email, full_name):
    return create_user(
        db=db,
        email=email,
        full_name=full_name,
        password_hash="test-hash",
    )


def test_get_users_service_returns_users(db):
    create_test_user(
        db,
        "alice@example.com",
        "Alice Smith",
    )

    create_test_user(
        db,
        "bob@example.com",
        "Bob Jones",
    )

    users = get_users_service(db)

    assert len(users) == 2
    assert users[0].email == "alice@example.com"
    assert users[1].email == "bob@example.com"


def test_get_user_service_returns_user(db):
    created_user = create_test_user(
        db,
        "alice@example.com",
        "Alice Smith",
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


def test_create_user_rejects_duplicate_email(db):
    create_test_user(
        db,
        "duplicate@example.com",
        "First User",
    )

    with pytest.raises(IntegrityError):
        create_test_user(
            db,
            "duplicate@example.com",
            "Second User",
        )


def test_update_user_role_service_updates_role(db):
    created_user = create_test_user(
        db,
        "promote@example.com",
        "Promote Me",
    )

    updated_user = update_user_role_service(
        db=db,
        user_id=created_user.id,
        role=UserRole.ADMIN,
    )

    assert updated_user.id == created_user.id
    assert updated_user.role == UserRole.ADMIN


@pytest.mark.parametrize("user_id", [0, -1])
def test_update_user_role_service_rejects_non_positive_id(
    db,
    user_id,
):
    with pytest.raises(InvalidUserIdError):
        update_user_role_service(
            db=db,
            user_id=user_id,
            role=UserRole.ADMIN,
        )


def test_update_user_role_service_raises_when_user_missing(db):
    with pytest.raises(UserNotFoundError):
        update_user_role_service(
            db=db,
            user_id=9999,
            role=UserRole.ADMIN,
        )
