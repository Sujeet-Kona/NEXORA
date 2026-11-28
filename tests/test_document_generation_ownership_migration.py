"""Unit tests for document-generation ownership migration preflight checks."""

import importlib.util
from pathlib import Path


_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "7c8d9e0f1a2b_enforce_document_generation_ownership.py"
)
_spec = importlib.util.spec_from_file_location("generation_ownership_migration", _MIGRATION_PATH)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


class _ScalarResult:
    def __init__(self, value):
        self.value = value



    def scalar_one(self):
        return self.value


class _FakeBind:
    def __init__(self, counts):
        self.counts = iter(counts)
        self.queries = []



    def execute(self, statement):
        self.queries.append(str(statement))
        return _ScalarResult(next(self.counts))



def test_migration_preflight_rejects_generation_owner_mismatch(monkeypatch):
    bind = _FakeBind([2])
    monkeypatch.setattr(_migration.op, "get_bind", lambda: bind)

    try:
        _migration.upgrade()
    except RuntimeError as exc:
        assert "2 generation rows" in str(exc)
    else:
        raise AssertionError("migration accepted inconsistent generation ownership")

    assert len(bind.queries) == 1
    assert "document_processing_generations" in bind.queries[0]
    assert "organization_id" in bind.queries[0]



def test_migration_preflight_rejects_chunk_owner_mismatch(monkeypatch):
    bind = _FakeBind([0, 3])
    monkeypatch.setattr(_migration.op, "get_bind", lambda: bind)

    try:
        _migration.upgrade()
    except RuntimeError as exc:
        assert "3 chunk rows" in str(exc)
    else:
        raise AssertionError("migration accepted inconsistent chunk ownership")

    assert len(bind.queries) == 2
    assert "document_generation_chunks" in bind.queries[1]
    assert "organization_id" in bind.queries[1]
