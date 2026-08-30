import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import uuid6


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_screenplay_magic_bytes(data: bytes, content_type: str, filename: str) -> bool:
    lower_fn = filename.lower()

    if lower_fn.endswith(".pdf") or "pdf" in content_type:
        return data.startswith(b"%PDF-")

    if lower_fn.endswith(".fdx") or "xml" in content_type:
        # Check for XML preamble and FinalDraft root
        stripped = data.lstrip()
        return (
            stripped.startswith(b"<?xml")
            or b"<FinalDraft" in data[:1024]
            or b"<finaldraft" in data[:1024]
        )

    if lower_fn.endswith(".fountain") or lower_fn.endswith(".txt") or "text" in content_type:
        # Ensure it's valid UTF-8 text without null bytes
        if b"\x00" in data[:512]:
            return False
        try:
            data.decode("utf-8")
            return True
        except UnicodeDecodeError:
            try:
                data.decode("latin-1")
                return True
            except Exception:
                return False

    return False


@dataclass
class UploadCapability:
    capability_id: UUID
    org_id: UUID
    project_id: UUID
    actor_id: UUID
    filename: str
    content_type: str
    nonce: str
    expires_at: datetime
    used_at: datetime | None = None

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        filename: str,
        content_type: str,
        nonce: str,
        ttl_minutes: int = 30,
    ) -> "UploadCapability":
        now = datetime.now(UTC)
        return cls(
            capability_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            filename=filename.strip(),
            content_type=content_type.strip(),
            nonce=nonce,
            expires_at=now + timedelta(minutes=ttl_minutes),
            used_at=None,
        )

    def is_valid(self) -> bool:
        now = datetime.now(UTC)
        return self.used_at is None and self.expires_at > now


@dataclass
class ImportArtifact:
    artifact_id: UUID
    org_id: UUID
    project_id: UUID
    uploaded_by_user_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    storage_path: str
    status: str  # "staged" | "finalized" | "failed"
    created_at: datetime
    finalized_at: datetime | None = None

    @classmethod
    def create_finalized(
        cls,
        org_id: UUID,
        project_id: UUID,
        uploaded_by_user_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        sha256_hash: str,
        storage_path: str,
    ) -> "ImportArtifact":
        now = datetime.now(UTC)
        return cls(
            artifact_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            uploaded_by_user_id=uploaded_by_user_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256_hash=sha256_hash,
            storage_path=storage_path,
            status="finalized",
            created_at=now,
            finalized_at=now,
        )
