import secrets
from uuid import UUID

from clearcut.scripts.domain.artifacts import (
    ImportArtifact,
    UploadCapability,
    compute_sha256,
    validate_screenplay_magic_bytes,
)
from clearcut.scripts.ports.object_storage import ObjectStoragePort

MAX_SCRIPT_SIZE_BYTES = 25 * 1024 * 1024  # 25MB limit


class UploadService:
    def __init__(self, storage: ObjectStoragePort) -> None:
        self.storage = storage
        self.capabilities: dict[UUID, UploadCapability] = {}
        self.artifacts: dict[UUID, ImportArtifact] = {}

    async def create_upload_capability(
        self,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        filename: str,
        content_type: str,
    ) -> tuple[UploadCapability, str]:
        nonce = secrets.token_hex(16)
        capability = UploadCapability.create(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            filename=filename,
            content_type=content_type,
            nonce=nonce,
        )
        self.capabilities[capability.capability_id] = capability

        upload_url = (
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/finalize?capability_id={capability.capability_id}"
        )
        return capability, upload_url

    async def finalize_upload(
        self,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        capability_id: UUID,
        data: bytes,
    ) -> ImportArtifact:
        capability = self.capabilities.get(capability_id)
        if not capability or not capability.is_valid():
            raise ValueError("Upload capability already used or invalid")

        if capability.org_id != org_id or capability.project_id != project_id:
            raise ValueError("Upload capability mismatch")

        if len(data) > MAX_SCRIPT_SIZE_BYTES:
            raise ValueError(f"File size exceeds {MAX_SCRIPT_SIZE_BYTES} bytes limit")

        if not validate_screenplay_magic_bytes(data, capability.content_type, capability.filename):
            raise ValueError("Invalid file format or spoofed magic bytes")

        sha256 = compute_sha256(data)
        storage_path = (
            f"orgs/{org_id}/projects/{project_id}/artifacts/"
            f"{capability_id}/{capability.filename}"
        )

        await self.storage.put_object(storage_path, data, capability.content_type)

        artifact = ImportArtifact.create_finalized(
            org_id=org_id,
            project_id=project_id,
            uploaded_by_user_id=actor_id,
            filename=capability.filename,
            content_type=capability.content_type,
            size_bytes=len(data),
            sha256_hash=sha256,
            storage_path=storage_path,
        )
        self.artifacts[artifact.artifact_id] = artifact
        capability.used_at = artifact.finalized_at

        return artifact
