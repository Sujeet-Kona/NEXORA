from pathlib import Path
from uuid import uuid4


class LocalStorage:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)

    def save(
        self,
        organization_id: int,
        document_id: int,
        filename: str,
        content: bytes,
    ) -> str:
        document_directory = (
            self.base_path
            / "organizations"
            / str(organization_id)
            / "documents"
            / str(document_id)
        )

        document_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_filename = Path(filename.replace("\\", "/")).name
        storage_name = f"{uuid4().hex}_{safe_filename}"

        destination = document_directory / storage_name

        destination.write_bytes(content)

        return str(
            destination.relative_to(self.base_path)
        )

    def _resolve_within_base(self, storage_key: str) -> Path:
        base = self.base_path.resolve()
        target = (self.base_path / storage_key).resolve()

        if not target.is_relative_to(base):
            raise ValueError(
                "Resolved storage path escapes the storage root"
            )

        return target

    def read(self, storage_key: str) -> bytes:
        path = self._resolve_within_base(storage_key)

        if not path.is_file():
            raise FileNotFoundError(
                "Stored file not found"
            )

        return path.read_bytes()

    def delete(self, storage_key: str) -> None:
        path = self._resolve_within_base(storage_key)

        if path.is_file():
            path.unlink()
