"""add document version

Revision ID: a020b6f4b1d6
Revises: 3a3c3a0c6ca7
Create Date: 2026-09-22 22:34:00.801558

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a020b6f4b1d6'
down_revision: Union[str, Sequence[str], None] = '3a3c3a0c6ca7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'documents',
        sa.Column('version', sa.Integer(), nullable=True),
    )

    op.execute("UPDATE documents SET version = 1 WHERE version IS NULL")

    op.alter_column(
        'documents',
        'version',
        existing_type=sa.Integer(),
        nullable=False,
        server_default="1",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'version')
