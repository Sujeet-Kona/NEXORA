import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from backend.db.models import DocumentGenerationChunk, DocumentProcessingGeneration
from tests.test_document_generation_repository import _document


def _enable_sqlite_foreign_keys(db):
    # SQLite disables FK enforcement by default; enable it on the active test
    # connection before creating rows so the assertions exercise the DB.
    db.execute(text("PRAGMA foreign_keys=ON"))


def test_generation_rejects_document_organization_mismatch(db):
    _enable_sqlite_foreign_keys(db)
    document = _document(db, "generation-owner-integrity-document@example.com")
    other_document = _document(db, "generation-owner-integrity-other@example.com")

    generation = DocumentProcessingGeneration(
        id="generation-owner-integrity-invalid",
        document_id=document.id,
        organization_id=other_document.organization_id,
        attempt_id="attempt-owner-integrity",
        status="staging",
    )
    db.add(generation)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_generation_chunk_rejects_cross_document_generation_reference(db):
    _enable_sqlite_foreign_keys(db)
    document = _document(db, "generation-chunk-owner-document@example.com")
    other_document = _document(db, "generation-chunk-owner-other@example.com")

    generation = DocumentProcessingGeneration(
        id="generation-chunk-owner-valid",
        document_id=document.id,
        organization_id=document.organization_id,
        attempt_id="attempt-chunk-owner",
        status="staging",
    )
    db.add(generation)
    db.flush()

    chunk = DocumentGenerationChunk(
        generation_id=generation.id,
        document_id=other_document.id,
        organization_id=other_document.organization_id,
        chunk_index=0,
        text="must not attach to another document",
    )
    db.add(chunk)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_generation_chunk_rejects_organization_mismatch(db):
    _enable_sqlite_foreign_keys(db)
    document = _document(db, "generation-chunk-org-owner-document@example.com")
    other_document = _document(db, "generation-chunk-org-owner-other@example.com")

    generation = DocumentProcessingGeneration(
        id="generation-chunk-org-owner-valid",
        document_id=document.id,
        organization_id=document.organization_id,
        attempt_id="attempt-chunk-org-owner",
        status="staging",
    )
    db.add(generation)
    db.flush()

    chunk = DocumentGenerationChunk(
        generation_id=generation.id,
        document_id=document.id,
        organization_id=other_document.organization_id,
        chunk_index=0,
        text="must not be assigned to another organization",
    )
    db.add(chunk)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
