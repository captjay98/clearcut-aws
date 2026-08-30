
from clearcut.scripts.ports.object_storage import ObjectStoragePort


class InMemoryObjectStorage(ObjectStoragePort):
    def __init__(self) -> None:
        self._storage: dict[str, tuple[bytes, str]] = {}

    async def put_object(self, path: str, data: bytes, content_type: str) -> None:
        self._storage[path] = (data, content_type)

    async def get_object(self, path: str) -> bytes | None:
        entry = self._storage.get(path)
        if entry:
            return entry[0]
        return None

    async def delete_object(self, path: str) -> None:
        self._storage.pop(path, None)

    async def object_exists(self, path: str) -> bool:
        return path in self._storage
