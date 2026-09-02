"""Persistent local object storage for development and single-node testing."""
import asyncio
import os
import tempfile
from pathlib import Path, PurePosixPath

from clearcut.scripts.ports.object_storage import ObjectStoragePort


class FilesystemObjectStorage(ObjectStoragePort):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _object_path(self, object_key: str) -> Path:
        relative = PurePosixPath(object_key)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("Object key must be a safe relative path")
        resolved = self.root.joinpath(*relative.parts).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Object key escapes the configured storage root")
        return resolved

    async def put_object(self, path: str, data: bytes, content_type: str) -> None:
        del content_type
        target = self._object_path(path)

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, temporary_name = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(file_descriptor, "wb") as temporary_file:
                    temporary_file.write(data)
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())
                os.replace(temporary_name, target)
            except Exception:
                Path(temporary_name).unlink(missing_ok=True)
                raise

        await asyncio.to_thread(_write)

    async def get_object(self, path: str) -> bytes | None:
        target = self._object_path(path)

        def _read() -> bytes | None:
            try:
                return target.read_bytes()
            except FileNotFoundError:
                return None

        return await asyncio.to_thread(_read)

    async def delete_object(self, path: str) -> None:
        target = self._object_path(path)
        await asyncio.to_thread(target.unlink, missing_ok=True)

    async def object_exists(self, path: str) -> bool:
        target = self._object_path(path)
        return await asyncio.to_thread(target.is_file)
