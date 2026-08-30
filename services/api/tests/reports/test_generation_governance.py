import pytest
import uuid6
from clearcut.export.application.generate_snapshot import GenerateReportSnapshotService
from clearcut.export.domain.snapshots import ReportSnapshotStatus
from clearcut.organizations.domain.capabilities import Role
from clearcut.scripts.domain.versions import ScriptVersion


@pytest.mark.asyncio
async def test_reviewer_can_generate_report_snapshot():
    service = GenerateReportSnapshotService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    v1 = ScriptVersion.create(
        org_id=org_id,
        project_id=project_id,
        ordinal=1,
    )

    snapshot, audit = await service.generate_snapshot(
        org_id=org_id,
        project_id=project_id,
        script_version=v1,
        actor_id=actor_id,
        actor_role=Role.REVIEWER,
        items=[],
    )

    assert snapshot.status == ReportSnapshotStatus.GENERATED
    assert audit.action == "report_snapshot_generated"
    assert audit.actor_id == actor_id

@pytest.mark.asyncio
async def test_editor_cannot_generate_report_snapshot():
    service = GenerateReportSnapshotService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    v1 = ScriptVersion.create(
        org_id=org_id,
        project_id=project_id,
        ordinal=1,
    )

    with pytest.raises(PermissionError):
        await service.generate_snapshot(
            org_id=org_id,
            project_id=project_id,
            script_version=v1,
            actor_id=actor_id,
            actor_role=Role.EDITOR,
            items=[],
        )
