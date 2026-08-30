import hashlib
import json
from typing import Any
from uuid import UUID

from clearcut.decisions.domain.models import AuditEvent
from clearcut.export.domain.snapshots import ReportSnapshot, ReportSnapshotStatus
from clearcut.organizations.domain.capabilities import Role, has_capability
from clearcut.scripts.domain.versions import ScriptVersion


class GenerateReportSnapshotService:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, ReportSnapshot] = {}
        self.audits: list[AuditEvent] = []

    async def generate_snapshot(
        self,
        org_id: UUID,
        project_id: UUID,
        script_version: ScriptVersion,
        actor_id: UUID,
        actor_role: Role,
        items: list[Any],
    ) -> tuple[ReportSnapshot, AuditEvent]:
        if not has_capability(actor_role, "report:generate"):
            raise PermissionError(
                f"Role '{actor_role.value}' does not have capability 'report:generate'."
            )

        binding_manifest = {
            "version_ordinal": script_version.ordinal,
            "script_version_id": str(script_version.version_id),
            "item_count": len(items),
            "generated_by": str(actor_id),
        }

        manifest_str = json.dumps(binding_manifest, sort_keys=True)
        content_hash = f"sha256:{hashlib.sha256(manifest_str.encode()).hexdigest()}"

        snapshot = ReportSnapshot.create(
            org_id=org_id,
            project_id=project_id,
            script_version_id=script_version.version_id,
            status=ReportSnapshotStatus.GENERATED,
            content_hash=content_hash,
            binding_manifest=binding_manifest,
        )
        self.snapshots[snapshot.snapshot_id] = snapshot

        audit = AuditEvent.create(
            org_id=org_id,
            project_id=project_id,
            action="report_snapshot_generated",
            actor_id=actor_id,
            target_id=snapshot.snapshot_id,
            target_type="report_snapshot",
            details={
                "script_version_id": str(script_version.version_id),
                "content_hash": content_hash,
            },
        )
        self.audits.append(audit)

        return snapshot, audit
