"""Remote storage adapters; SDK details and errors stay inside this boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from botocore.exceptions import ClientError
from clearcut.scripts.ports.object_storage import ObjectStoragePort
from google.api_core.exceptions import NotFound

_T = TypeVar("_T")


class ObjectStorageError(RuntimeError):
    """Redacted storage failure, distinct from an absent object."""


def validate_object_key(key: str) -> str:
    if (
        not key
        or "\\" in key
        or "\x00" in key
        or any(part in {"", ".", ".."} for part in key.split("/"))
    ):
        raise ValueError("Object key must be a safe relative path")
    return key


class _RemoteStorage(ObjectStoragePort):
    @staticmethod
    async def _call(operation: Callable[[], _T], *, missing: _T) -> _T:
        def invoke() -> _T:
            try:
                return operation()
            except NotFound:
                return missing
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
                    return missing
            except Exception:
                pass
            raise ObjectStorageError("Object storage operation failed.") from None

        return await asyncio.to_thread(invoke)


class GCSObjectStorage(_RemoteStorage):
    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = client.bucket(bucket)

    def _blob(self, path: str) -> Any:
        return self._bucket.blob(validate_object_key(path))

    async def put_object(self, path: str, data: bytes, content_type: str) -> None:
        blob = self._blob(path)

        # Writes must never turn a missing bucket into a successful no-op.
        def upload() -> None:
            try:
                blob.upload_from_string(data, content_type=content_type, timeout=30, retry=None)
            except Exception:
                raise ObjectStorageError("Object storage operation failed.") from None

        await asyncio.to_thread(upload)

    async def get_object(self, path: str) -> bytes | None:
        blob = self._blob(path)
        return await self._call(
            lambda: blob.download_as_bytes(timeout=30, retry=None), missing=None
        )

    async def delete_object(self, path: str) -> None:
        blob = self._blob(path)
        await self._call(lambda: blob.delete(timeout=30, retry=None), missing=None)

    async def object_exists(self, path: str) -> bool:
        blob = self._blob(path)
        return await self._call(lambda: blob.exists(timeout=30, retry=None), missing=False)


class S3ObjectStorage(_RemoteStorage):
    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    async def put_object(self, path: str, data: bytes, content_type: str) -> None:
        key = validate_object_key(path)

        def upload() -> None:
            try:
                self._client.put_object(
                    Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
                )
            except Exception:
                raise ObjectStorageError("Object storage operation failed.") from None

        await asyncio.to_thread(upload)

    async def get_object(self, path: str) -> bytes | None:
        key = validate_object_key(path)

        def download() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"]
            try:
                data = body.read()
                if not isinstance(data, bytes):
                    raise ObjectStorageError("Object storage returned invalid data.")
                return data
            finally:
                body.close()

        return await self._call(download, missing=None)

    async def delete_object(self, path: str) -> None:
        key = validate_object_key(path)

        def delete() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=key)

        await self._call(delete, missing=None)

    async def object_exists(self, path: str) -> bool:
        key = validate_object_key(path)

        def exists() -> bool:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True

        return await self._call(exists, missing=False)
