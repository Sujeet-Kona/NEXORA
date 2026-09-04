import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture()
def migration_config():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    return config


@pytest.fixture()
def migration_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_engine(TEST_DATABASE_URL)

    yield engine

    engine.dispose()


def test_migration_upgrade_creates_users_table(
    migration_config,
    migration_engine,
):
    command.downgrade(migration_config, "base")
    command.upgrade(migration_config, "head")

    inspector = inspect(migration_engine)
    tables = inspector.get_table_names()

    assert "alembic_version" in tables
    assert "users" in tables

    columns = {
        column["name"]
        for column in inspector.get_columns("users")
    }

    assert columns == {
        "id",
        "email",
        "full_name",
        "created_at",
    }


def test_migration_downgrade_removes_users_table(
    migration_config,
    migration_engine,
):
    command.upgrade(migration_config, "head")

    assert "users" in inspect(migration_engine).get_table_names()

    command.downgrade(migration_config, "base")

    tables = inspect(migration_engine).get_table_names()

    assert "users" not in tables
