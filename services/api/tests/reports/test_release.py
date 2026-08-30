import pytest
import uuid6
from clearcut.export.application.release_report import ReleaseReportService
from clearcut.export.domain.snapshots import ReportSnapshot, ReportSnapshotStatus
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_release_snapshot_commits_release_and_audit():
    service = ReleaseReportService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    snapshot = ReportSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        script_version_id=uuid6.uuid7(),
        status=ReportSnapshotStatus.GENERATED,
        content_hash="sha256:abcd1234",
        binding_manifest={},
    )

    release, audit = await service.release_snapshot(
        org_id=org_id,
        project_id=project_id,
        snapshot=snapshot,
        actor_id=actor_id,
        actor_role=Role.REVIEWER,
        attestation="I attest that this clearance report is accurate as of current review.",
    )

    assert release.snapshot_id == snapshot.snapshot_id
    assert release.released_by == actor_id
    assert audit.action == "report_snapshot_released"
