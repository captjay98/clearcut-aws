import pytest
import uuid6
from clearcut.export.application.generate_snapshot import GenerateReportSnapshotService
from clearcut.organizations.domain.capabilities import Role
from clearcut.scripts.domain.versions import ScriptVersion


@pytest.mark.asyncio
async def test_snapshot_bindings_include_script_version_and_hash():
    service = GenerateReportSnapshotService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    v1 = ScriptVersion.create(
        org_id=org_id,
        project_id=project_id,
        ordinal=1,
        source_hash="sha256:abc12345",
    )

    snapshot, _ = await service.generate_snapshot(
        org_id=org_id,
        project_id=project_id,
        script_version=v1,
        actor_id=actor_id,
        actor_role=Role.OWNER,
        items=[],
    )

    assert snapshot.script_version_id == v1.version_id
    assert snapshot.binding_manifest["version_ordinal"] == 1
    assert snapshot.content_hash.startswith("sha256:")
