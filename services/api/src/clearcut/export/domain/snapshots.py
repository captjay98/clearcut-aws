from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import uuid6


class ReportSnapshotStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    RELEASED = "released"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class ReportSnapshot:
    snapshot_id: UUID
    org_id: UUID
    project_id: UUID
    script_version_id: UUID
    status: ReportSnapshotStatus
    content_hash: str
    binding_manifest: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        script_version_id: UUID,
        status: ReportSnapshotStatus,
        content_hash: str,
        binding_manifest: dict[str, Any],
    ) -> "ReportSnapshot":
        return cls(
            snapshot_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            script_version_id=script_version_id,
            status=status,
            content_hash=content_hash,
            binding_manifest=binding_manifest,
            created_at=datetime.now(UTC),
        )
