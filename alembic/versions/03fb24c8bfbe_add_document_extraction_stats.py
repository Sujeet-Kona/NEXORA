"""add document extraction stats

Revision ID: 03fb24c8bfbe
Revises: a020b6f4b1d6
Create Date: 2026-09-22 23:39:47.544597

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03fb24c8bfbe'
down_revision: Union[str, Sequence[str], None] = 'a020b6f4b1d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'documents',
        sa.Column('page_count', sa.Integer(), nullable=True),
    )

    op.add_column(
        'documents',
        sa.Column('word_count', sa.Integer(), nullable=True),
    )

    op.add_column(
        'documents',
        sa.Column('character_count', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'character_count')
    op.drop_column('documents', 'word_count')
    op.drop_column('documents', 'page_count')
