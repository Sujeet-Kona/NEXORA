"""add staged document processing generations

Revision ID: 9ab1c2d3e4f5
Revises: 4c5d6e7f8091
Create Date: 2026-11-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9ab1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "4c5d6e7f8091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_processing_generations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="staging",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_processing_generations_document_id",
        "document_processing_generations",
        ["document_id"],
    )
    op.create_index(
        "ix_document_processing_generations_organization_id",
        "document_processing_generations",
        ["organization_id"],
    )
    op.create_index(
        "ix_document_processing_generations_attempt_id",
        "document_processing_generations",
        ["attempt_id"],
    )

    op.create_table(
        "document_generation_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["document_processing_generations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generation_id",
            "chunk_index",
            name="uq_document_generation_chunk_index",
        ),
    )
    op.create_index(
        "ix_document_generation_chunks_generation_id",
        "document_generation_chunks",
        ["generation_id"],
    )
    op.create_index(
        "ix_document_generation_chunks_document_id",
        "document_generation_chunks",
        ["document_id"],
    )
    op.create_index(
        "ix_document_generation_chunks_organization_id",
        "document_generation_chunks",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_generation_chunks_organization_id",
        table_name="document_generation_chunks",
    )
    op.drop_index(
        "ix_document_generation_chunks_document_id",
        table_name="document_generation_chunks",
    )
    op.drop_index(
        "ix_document_generation_chunks_generation_id",
        table_name="document_generation_chunks",
    )
    op.drop_table("document_generation_chunks")

    op.drop_index(
        "ix_document_processing_generations_attempt_id",
        table_name="document_processing_generations",
    )
    op.drop_index(
        "ix_document_processing_generations_organization_id",
        table_name="document_processing_generations",
    )
    op.drop_index(
        "ix_document_processing_generations_document_id",
        table_name="document_processing_generations",
    )
    op.drop_table("document_processing_generations")
