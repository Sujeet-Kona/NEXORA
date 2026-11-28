"""add active index generation pointer to documents

Revision ID: 1ab2c3d4e5f6
Revises: 9ab1c2d3e4f5
Create Date: 2026-11-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1ab2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9ab1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("active_generation_id", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "active_generation_id")
