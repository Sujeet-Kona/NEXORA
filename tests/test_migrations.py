import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture()
def migration_config():
    config = Config("alembic.ini")

    if not TEST_DATABASE_URL:
        pytest.fail("TEST_DATABASE_URL must point to the dedicated migration test database")

    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    return config


@pytest.fixture()
def migration_engine():
    if not TEST_DATABASE_URL:
        pytest.fail("TEST_DATABASE_URL must point to the dedicated migration test database")

    engine = create_engine(TEST_DATABASE_URL)

    yield engine

    engine.dispose()


def reset_migration_database(migration_engine):
    with migration_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS users")
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


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