"""ObjectStoragePort conformance using injected clients only."""

import io
import traceback
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from clearcut.bootstrap import storage as storage_module
from clearcut.bootstrap.settings import GCSStorageSettings, S3StorageSettings
from clearcut.scripts.ports.object_storage import ObjectStoragePort
from google.api_core.exceptions import NotFound


class MissingObject(NotFound):
    def __init__(self):
        super().__init__("Object not found")


class FakeClient:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.failure = None
        self.body = None

    def check(self, operation, kwargs):
        self.calls.append((operation, kwargs))
        if self.failure:
            raise self.failure

    def bucket(self, name):
        return SimpleNamespace(blob=lambda key: FakeBlob(self, name, key))

    def put_object(self, **kwargs):
        self.check("put", kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        self.check("get", kwargs)
        if kwargs["Key"] not in self.objects:
            raise MissingObject()
        self.body = io.BytesIO(self.objects[kwargs["Key"]])
        return {"Body": self.body}

    def head_object(self, **kwargs):
        self.check("head", kwargs)
        if kwargs["Key"] not in self.objects:
            raise MissingObject()
        return {}

    def delete_object(self, **kwargs):
        self.check("delete", kwargs)
        self.objects.pop(kwargs["Key"], None)


class FakeBlob:
    def __init__(self, client, bucket, key):
        self.client, self.bucket, self.key = client, bucket, key

    def upload_from_string(self, data, **kwargs):
        self.client.check("put", kwargs)
        self.client.objects[self.key] = data

    def download_as_bytes(self, **kwargs):
        self.client.check("get", kwargs)
        if self.key not in self.client.objects:
            raise MissingObject()
        return self.client.objects[self.key]

    def exists(self, **kwargs):
        self.client.check("head", kwargs)
        return self.key in self.client.objects

    def delete(self, **kwargs):
        self.client.check("delete", kwargs)
        if self.key not in self.client.objects:
            raise MissingObject()
        del self.client.objects[self.key]


@pytest.fixture(params=["gcs", "s3"])
def remote(request):
    client = FakeClient()
    settings = (
        GCSStorageSettings(bucket="scripts", project_id="project")
        if request.param == "gcs"
        else S3StorageSettings(bucket="scripts")
    )
    return storage_module.build_object_storage(settings, client=client), client


@pytest.mark.asyncio
async def test_binary_round_trip_and_idempotent_deletion(remote):
    storage, client = remote
    assert isinstance(storage, ObjectStoragePort)
    key = "org/project/version/original.fdx"
    assert await storage.get_object(key) is None
    assert await storage.object_exists(key) is False
    await storage.put_object(key, b"\x00\xffscreenplay", "application/octet-stream")
    assert await storage.get_object(key) == b"\x00\xffscreenplay"
    assert await storage.object_exists(key) is True
    await storage.delete_object(key)
    await storage.delete_object(key)
    assert await storage.get_object(key) is None
    if client.body is not None:
        assert client.body.closed
    put_kwargs = next(kwargs for operation, kwargs in client.calls if operation == "put")
    assert (
        put_kwargs.get("content_type", put_kwargs.get("ContentType")) == "application/octet-stream"
    )


@pytest.mark.parametrize(
    "key", ["", "/absolute", "../escape", "org/../escape", "a\\b", "a//b", "a/./b", "a\x00b"]
)
@pytest.mark.asyncio
async def test_invalid_keys_never_reach_client(remote, key):
    storage, client = remote
    with pytest.raises(ValueError):
        await storage.put_object(key, b"x", "text/plain")
    assert client.calls == []


@pytest.mark.parametrize("method", ["put_object", "get_object", "delete_object", "object_exists"])
@pytest.mark.asyncio
async def test_provider_failure_is_typed_redacted_and_not_missing(remote, method):
    storage, client = remote
    client.failure = RuntimeError("credential-secret-and-object-body")
    args = (
        ("org/project/file", b"x", "text/plain")
        if method == "put_object"
        else ("org/project/file",)
    )
    with pytest.raises(storage_module.ObjectStorageError) as caught:
        await getattr(storage, method)(*args)
    assert "credential-secret" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.asyncio
async def test_gcs_calls_have_bounded_timeout_without_implicit_retries():
    client = FakeClient()
    storage = storage_module.build_object_storage(
        GCSStorageSettings(bucket="b", project_id="p"), client=client
    )
    await storage.put_object("org/project/key", b"x", "text/plain")
    await storage.get_object("org/project/key")
    await storage.object_exists("org/project/key")
    await storage.delete_object("org/project/key")
    assert all(kwargs["timeout"] == 30 and kwargs["retry"] is None for _, kwargs in client.calls)


@pytest.mark.asyncio
async def test_s3_no_such_bucket_raises_bucket_not_found():
    client = FakeClient()
    error_response = {
        "Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist"}
    }
    client.failure = ClientError(error_response, "GetObject")
    storage = storage_module.build_object_storage(
        S3StorageSettings(bucket="non-existent-bucket"), client=client
    )
    with pytest.raises(
        storage_module.BucketNotFoundError, match="does not exist"
    ):
        await storage.get_object("org/project/file.txt")


@pytest.mark.asyncio
async def test_s3_access_denied_raises_storage_access_denied():
    client = FakeClient()
    error_response = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
    client.failure = ClientError(error_response, "PutObject")
    storage = storage_module.build_object_storage(
        S3StorageSettings(bucket="forbidden-bucket"), client=client
    )
    with pytest.raises(
        storage_module.StorageAccessDeniedError, match="Access denied to storage bucket"
    ):
        await storage.put_object("org/project/file.txt", b"data", "text/plain")


@pytest.mark.asyncio
async def test_s3_no_such_key_returns_none_and_false():
    client = FakeClient()
    error_response = {
        "Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist"}
    }
    client.failure = ClientError(error_response, "GetObject")
    storage = storage_module.build_object_storage(
        S3StorageSettings(bucket="valid-bucket"), client=client
    )
    assert await storage.get_object("org/project/missing.txt") is None

    client.failure = ClientError(error_response, "HeadObject")
    assert await storage.object_exists("org/project/missing.txt") is False


@pytest.mark.asyncio
async def test_s3_status_404_returns_none_and_false():
    client = FakeClient()
    error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
    client.failure = ClientError(error_response, "GetObject")
    storage = storage_module.build_object_storage(
        S3StorageSettings(bucket="valid-bucket"), client=client
    )
    assert await storage.get_object("org/project/missing.txt") is None

    client.failure = ClientError(error_response, "HeadObject")
    assert await storage.object_exists("org/project/missing.txt") is False


@pytest.mark.asyncio
async def test_s3_credential_redaction_in_exception():
    client = FakeClient()
    error_response = {
        "Error": {
            "Code": "InternalError",
            "Message": "Fatal AWS_SECRET_ACCESS_KEY=supersecretkeyfailure",
        }
    }
    client.failure = ClientError(error_response, "PutObject")
    storage = storage_module.build_object_storage(
        S3StorageSettings(bucket="my-bucket"), client=client
    )
    with pytest.raises(storage_module.ObjectStorageError) as caught:
        await storage.put_object("org/project/file.txt", b"x", "text/plain")
    assert "supersecretkeyfailure" not in "".join(traceback.format_exception(caught.value))

