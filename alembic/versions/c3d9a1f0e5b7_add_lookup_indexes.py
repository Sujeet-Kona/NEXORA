"""add lookup indexes for tenant-scoped queries

Revision ID: c3d9a1f0e5b7
Revises: b7c1d9e2f4a6
Create Date: 2026-09-27 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d9a1f0e5b7'
down_revision: Union[str, Sequence[str], None] = 'b7c1d9e2f4a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = (
    ('ix_documents_organization_id', 'documents', ['organization_id']),
    (
        'ix_document_chunks_document_id',
        'document_chunks',
        ['document_id'],
    ),
    (
        'ix_document_chunks_organization_id',
        'document_chunks',
        ['organization_id'],
    ),
    ('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id']),
    (
        'ix_organization_memberships_user_id',
        'organization_memberships',
        ['user_id'],
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
