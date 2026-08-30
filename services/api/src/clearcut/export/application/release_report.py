from uuid import UUID

from clearcut.decisions.domain.models import AuditEvent
from clearcut.export.domain.releases import ReportRelease
from clearcut.export.domain.snapshots import ReportSnapshot
from clearcut.organizations.domain.capabilities import Role, has_capability


class ReleaseReportService:
    def __init__(self) -> None:
        self.releases: dict[UUID, ReportRelease] = {}
        self.audits: list[AuditEvent] = []

    async def release_snapshot(
        self,
        org_id: UUID,
        project_id: UUID,
        snapshot: ReportSnapshot,
        actor_id: UUID,
        actor_role: Role,
        attestation: str,
    ) -> tuple[ReportRelease, AuditEvent]:
        if not has_capability(actor_role, "report:release"):
            raise PermissionError(
                f"Role '{actor_role.value}' does not have capability 'report:release'."
            )

        release = ReportRelease.create(
            snapshot_id=snapshot.snapshot_id,
            org_id=org_id,
            project_id=project_id,
            released_by=actor_id,
            attestation=attestation,
        )
        self.releases[release.release_id] = release

        audit = AuditEvent.create(
            org_id=org_id,
            project_id=project_id,
            action="report_snapshot_released",
            actor_id=actor_id,
            target_id=release.release_id,
            target_type="report_release",
            details={
                "snapshot_id": str(snapshot.snapshot_id),
                "attestation": attestation,
            },
        )
        self.audits.append(audit)

        return release, audit
