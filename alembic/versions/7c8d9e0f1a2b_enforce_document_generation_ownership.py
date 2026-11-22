"""enforce document generation ownership consistency

Revision ID: 7c8d9e0f1a2b
Revises: 1ab2c3d4e5f6
Create Date: 2026-11-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c8d9e0f1a2b"
down_revision: Union[str, Sequence[str], None] = "1ab2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    invalid_generations = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM document_processing_generations AS g
            LEFT JOIN documents AS d
              ON d.id = g.document_id
             AND d.organization_id = g.organization_id
            WHERE d.id IS NULL
            """
        )
    ).scalar_one()
    if invalid_generations:
        raise RuntimeError(
            "Cannot add generation ownership constraints: "
            f"{invalid_generations} generation rows have inconsistent document/organization ownership"
        )

    invalid_chunks = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM document_generation_chunks AS c
            LEFT JOIN document_processing_generations AS g
              ON g.id = c.generation_id
             AND g.document_id = c.document_id
             AND g.organization_id = c.organization_id
            WHERE g.id IS NULL
            """
        )
    ).scalar_one()
    if invalid_chunks:
        raise RuntimeError(
            "Cannot add generation chunk ownership constraints: "
            f"{invalid_chunks} chunk rows have inconsistent generation/document/organization ownership"
        )

    op.create_unique_constraint(
        "uq_document_id_organization",
        "documents",
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_document_generation_ownership",
        "document_processing_generations",
        ["id", "document_id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_generation_document_organization",
        "document_processing_generations",
        "documents",
        ["document_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_generation_chunk_generation_ownership",
        "document_generation_chunks",
        "document_processing_generations",
        ["generation_id", "document_id", "organization_id"],
        ["id", "document_id", "organization_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_generation_chunk_generation_ownership",
        "document_generation_chunks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_generation_document_organization",
        "document_processing_generations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_document_generation_ownership",
        "document_processing_generations",
        type_="unique",
    )
    op.drop_constraint(
        "uq_document_id_organization",
        "documents",
        type_="unique",
    )
