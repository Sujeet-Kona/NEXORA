"""add document processing attempt ownership fields

Revision ID: 4c5d6e7f8091
Revises: d4e8f2a1c6b9
Create Date: 2026-11-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c5d6e7f8091"
down_revision: Union[str, Sequence[str], None] = "d4e8f2a1c6b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("processing_attempt_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("processing_lease_expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "processing_lease_expires_at")
    op.drop_column("documents", "processing_attempt_id")
