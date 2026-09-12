from pathlib import Path

import pytest

from backend.services.storage import LocalStorage


def test_local_storage_saves_file(tmp_path):
    storage = LocalStorage(
        str(tmp_path / "storage")
    )

    storage_key = storage.save(
        organization_id=10,
        document_id=20,
        filename="policy.pdf",
        content=b"hello nexora",
    )

    assert "organizations/10/documents/20/" in (
        storage_key.replace("\\", "/")
    )

    assert storage.read(storage_key) == b"hello nexora"


def test_local_storage_strips_filename_path(
    tmp_path,
):
    storage = LocalStorage(
        str(tmp_path / "storage")
    )

    storage_key = storage.save(
        organization_id=1,
        document_id=2,
        filename="..\\..\\secret.pdf",
        content=b"safe",
    )

    assert Path(storage_key).name.endswith(
        "_secret.pdf"
    )

    assert storage.read(storage_key) == b"safe"


def test_local_storage_delete(tmp_path):
    storage = LocalStorage(
        str(tmp_path / "storage")
    )

    storage_key = storage.save(
        organization_id=1,
        document_id=2,
        filename="delete.pdf",
        content=b"delete me",
    )

    storage.delete(storage_key)

    with pytest.raises(FileNotFoundError):
        storage.read(storage_key)
