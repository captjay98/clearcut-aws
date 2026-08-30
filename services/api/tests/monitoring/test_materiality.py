import uuid6
from clearcut.monitoring.domain.materiality import ChangeMateriality, SourceDelta


def test_source_delta_creation():
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    s1_id = uuid6.uuid7()
    s2_id = uuid6.uuid7()

    delta = SourceDelta.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        prior_snapshot_id=s1_id,
        new_snapshot_id=s2_id,
        materiality=ChangeMateriality.MATERIAL,
        rationale="Status changed from Live to Cancelled",
    )

    assert delta.materiality == ChangeMateriality.MATERIAL
    assert delta.prior_snapshot_id == s1_id
    assert delta.new_snapshot_id == s2_id
