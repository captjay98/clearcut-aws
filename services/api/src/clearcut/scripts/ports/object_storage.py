from abc import ABC, abstractmethod


class ObjectStoragePort(ABC):
    @abstractmethod
    async def put_object(self, path: str, data: bytes, content_type: str) -> None:
        pass

    @abstractmethod
    async def get_object(self, path: str) -> bytes | None:
        pass

    @abstractmethod
    async def delete_object(self, path: str) -> None:
        pass

    @abstractmethod
    async def object_exists(self, path: str) -> bool:
        pass
