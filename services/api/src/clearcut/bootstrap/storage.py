"""Construct the explicitly selected storage adapter with optional injected SDK clients."""

from typing import Any

import boto3
from botocore.config import Config
from clearcut.bootstrap.settings import (
    FilesystemStorageSettings,
    GCSStorageSettings,
    StorageSettings,
)
from clearcut.scripts.adapters.filesystem_storage import FilesystemObjectStorage
from clearcut.scripts.adapters.remote_storage import (
    BucketNotFoundError,
    GCSObjectStorage,
    ObjectNotFoundError,
    ObjectStorageError,
    S3ObjectStorage,
    StorageAccessDeniedError,
    StorageConfigurationError,
)
from clearcut.scripts.ports.object_storage import ObjectStoragePort
from google.cloud import storage

__all__ = [
    "BucketNotFoundError",
    "ObjectNotFoundError",
    "ObjectStorageError",
    "StorageAccessDeniedError",
    "StorageConfigurationError",
    "build_object_storage",
]


def build_object_storage(settings: StorageSettings, *, client: Any = None) -> ObjectStoragePort:
    try:
        if isinstance(settings, FilesystemStorageSettings):
            return FilesystemObjectStorage(settings.path)
        if isinstance(settings, GCSStorageSettings):
            return GCSObjectStorage(
                settings.bucket,
                client if client is not None else storage.Client(project=settings.project_id),
            )
        if client is None:
            client = boto3.client(
                "s3",
                endpoint_url=settings.endpoint_url,
                region_name=settings.region,
                aws_access_key_id=settings.access_key_id.get_secret_value()
                if settings.access_key_id
                else None,
                aws_secret_access_key=settings.secret_access_key.get_secret_value()
                if settings.secret_access_key
                else None,
                config=Config(
                    connect_timeout=5, read_timeout=30, retries={"total_max_attempts": 1}
                ),
            )
        return S3ObjectStorage(settings.bucket, client)
    except Exception:
        raise ObjectStorageError("Object storage initialization failed.") from None
