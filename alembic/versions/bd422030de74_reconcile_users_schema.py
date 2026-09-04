"""reconcile users schema

Revision ID: bd422030de74
Revises: d2467edaf213
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


revision: str = "bd422030de74"
down_revision: Union[str, Sequence[str], None] = "d2467edaf213"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    indexes = {
        index["name"]
        for index in inspector.get_indexes("users")
    }

    if "ix_users_id" in indexes:
        op.drop_index("ix_users_id", table_name="users")

    if "ix_users_email" in indexes:
        op.drop_index("ix_users_email", table_name="users")

    unique_constraints = inspector.get_unique_constraints("users")

    has_email_unique_constraint = any(
        constraint.get("column_names") == ["email"]
        for constraint in unique_constraints
    )

    if not has_email_unique_constraint:
        op.create_unique_constraint(
            "uq_users_email",
            "users",
            ["email"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    unique_constraints = inspector.get_unique_constraints("users")

    has_named_email_constraint = any(
        constraint.get("name") == "uq_users_email"
        for constraint in unique_constraints
    )

    if has_named_email_constraint:
        op.drop_constraint(
            "uq_users_email",
            "users",
            type_="unique",
        )

    indexes = {
        index["name"]
        for index in inspector.get_indexes("users")
    }

    if "ix_users_email" not in indexes:
        op.create_index(
            "ix_users_email",
            "users",
            ["email"],
            unique=True,
        )

    if "ix_users_id" not in indexes:
        op.create_index(
            "ix_users_id",
            "users",
            ["id"],
            unique=False,
        )