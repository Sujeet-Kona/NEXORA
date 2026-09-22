import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.engine import make_url


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def require_test_database_url() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip(
            "TEST_DATABASE_URL is not set; skipping migration tests"
        )

    database_name = make_url(TEST_DATABASE_URL).database or ""

    if "test" not in database_name.lower():
        pytest.fail(
            "TEST_DATABASE_URL must point to a dedicated migration test database"
        )

    return TEST_DATABASE_URL


@pytest.fixture()
def migration_config():
    config = Config("alembic.ini")

    config.set_main_option(
        "sqlalchemy.url",
        require_test_database_url(),
    )

    return config


@pytest.fixture()
def migration_engine():
    engine = create_engine(
        require_test_database_url(),
    )

    yield engine

    engine.dispose()


def reset_migration_database(migration_engine):
    metadata = MetaData()

    metadata.reflect(bind=migration_engine)

    with migration_engine.begin() as connection:
        metadata.drop_all(bind=connection)


def test_migration_upgrade_creates_users_table(
    migration_config,
    migration_engine,
):
    reset_migration_database(migration_engine)
    command.upgrade(migration_config, "head")

    inspector = inspect(migration_engine)

    assert "users" in inspector.get_table_names()
    assert "alembic_version" in inspector.get_table_names()

    columns = {
        column["name"]
        for column in inspector.get_columns("users")
    }

    assert columns == {
        "id",
        "email",
        "full_name",
        "created_at",
        "password_hash",
        "role",
    }
    assert "documents" in inspector.get_table_names()

    document_columns = {
        column["name"]
        for column in inspector.get_columns("documents")
    }

    assert document_columns == {
        "id",
        "organization_id",
        "uploaded_by",
        "name",
        "storage_key",
        "file_size",
        "content_type",
        "status",
        "created_at",
        "updated_at",
    }

    document_foreign_keys = {
        (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("documents")
    }

    assert document_foreign_keys == {
        (
            ("organization_id",),
            "organizations",
            ("id",),
        ),
        (
            ("uploaded_by",),
            "users",
            ("id",),
        ),
    }

    primary_key = inspector.get_pk_constraint("users")
    assert primary_key["constrained_columns"] == ["id"]

    unique_constraints = inspector.get_unique_constraints("users")
    assert {
        column
        for constraint in unique_constraints
        for column in constraint["column_names"]
    } == {"email"}


def test_migration_downgrade_removes_users_table(
    migration_config,
    migration_engine,
):
    reset_migration_database(migration_engine)
    command.upgrade(migration_config, "head")

    assert "users" in inspect(migration_engine).get_table_names()

    command.downgrade(migration_config, "base")

    tables = inspect(migration_engine).get_table_names()

    assert "users" not in tables

    command.upgrade(migration_config, "head")

    assert "users" in inspect(migration_engine).get_table_names()
