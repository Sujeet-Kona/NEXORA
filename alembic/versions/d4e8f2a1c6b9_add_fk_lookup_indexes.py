"""add indexes for foreign-key lookup columns

Revision ID: d4e8f2a1c6b9
Revises: c3d9a1f0e5b7
Create Date: 2026-10-02 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e8f2a1c6b9'
down_revision: Union[str, Sequence[str], None] = 'c3d9a1f0e5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = (
    ('ix_documents_uploaded_by', 'documents', ['uploaded_by']),
    (
        'ix_audit_logs_actor_user_id',
        'audit_logs',
        ['actor_user_id'],
    ),
)


def upgrade() -> None:
    """Upgrade schema."""
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    """Downgrade schema."""
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
