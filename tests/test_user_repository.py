import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.models import Base
from backend.repositories.user_repository import (
    create_user,
    get_all_users,
    get_user_by_email,
    get_user_by_id,
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


def test_get_all_users_returns_users(db):
    create_user(
        db=db,
        email="alice@example.com",
        full_name="Alice Smith",
    )
    create_user(
        db=db,
        email="bob@example.com",
        full_name="Bob Jones",
    )

    users = get_all_users(db)

    assert len(users) == 2
    assert users[0].email == "alice@example.com"
    assert users[1].email == "bob@example.com"


def test_get_user_by_id_returns_user(db):
    created_user = create_user(
        db=db,
        email="alice@example.com",
        full_name="Alice Smith",
    )

    user = get_user_by_id(
        db=db,
        user_id=created_user.id,
    )

    assert user is not None
    assert user.id == created_user.id
    assert user.email == "alice@example.com"


def test_get_user_by_id_returns_none_when_missing(db):
    user = get_user_by_id(
        db=db,
        user_id=9999,
    )

    assert user is None


def test_get_user_by_email_returns_user(db):
    create_user(
        db=db,
        email="alice@example.com",
        full_name="Alice Smith",
    )

    user = get_user_by_email(
        db=db,
        email="alice@example.com",
    )

    assert user is not None
    assert user.email == "alice@example.com"


def test_get_user_by_email_returns_none_when_missing(db):
    user = get_user_by_email(
        db=db,
        email="missing@example.com",
    )

    assert user is None


def test_create_user_persists_user(db):
    user = create_user(
        db=db,
        email="alice@example.com",
        full_name="Alice Smith",
    )

    assert user.id is not None
    assert user.email == "alice@example.com"
    assert user.full_name == "Alice Smith"

    persisted = get_user_by_id(
        db=db,
        user_id=user.id,
    )

    assert persisted is not None
    assert persisted.email == "alice@example.com"
