from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import uuid6


@dataclass(frozen=True)
class ReportRelease:
    release_id: UUID
    snapshot_id: UUID
    org_id: UUID
    project_id: UUID
    released_by: UUID
    attestation: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        snapshot_id: UUID,
        org_id: UUID,
        project_id: UUID,
        released_by: UUID,
        attestation: str,
    ) -> "ReportRelease":
        return cls(
            release_id=uuid6.uuid7(),
            snapshot_id=snapshot_id,
            org_id=org_id,
            project_id=project_id,
            released_by=released_by,
            attestation=attestation.strip(),
            created_at=datetime.now(UTC),
        )
