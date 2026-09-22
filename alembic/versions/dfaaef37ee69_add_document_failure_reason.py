"""add document failure reason

Revision ID: dfaaef37ee69
Revises: dd31530686cf
Create Date: 2026-09-23 00:57:59.267086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dfaaef37ee69'
down_revision: Union[str, Sequence[str], None] = 'dd31530686cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'documents',
        sa.Column(
            'failure_reason',
            sa.String(length=500),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'failure_reason')
