"""add user platform role

Revision ID: a03d0831b09b
Revises: 5e614c5e8484
Create Date: 2026-09-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a03d0831b09b"
down_revision: Union[str, Sequence[str], None] = "5e614c5e8484"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.execute(
        "UPDATE users SET role = 'member' WHERE role IS NULL"
    )

    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default="member",
    )


def downgrade() -> None:
    op.drop_column("users", "role")
