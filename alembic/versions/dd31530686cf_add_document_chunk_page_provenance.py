"""add document chunk page provenance

Revision ID: dd31530686cf
Revises: 03fb24c8bfbe
Create Date: 2026-09-23 00:02:20.502339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd31530686cf'
down_revision: Union[str, Sequence[str], None] = '03fb24c8bfbe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'document_chunks',
        sa.Column('page_start', sa.Integer(), nullable=True),
    )

    op.add_column(
        'document_chunks',
        sa.Column('page_end', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('document_chunks', 'page_end')
    op.drop_column('document_chunks', 'page_start')
