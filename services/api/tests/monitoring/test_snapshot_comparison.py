import uuid6
from clearcut.monitoring.application.compare_snapshots import compare_snapshots
from clearcut.monitoring.domain.materiality import ChangeMateriality
from clearcut.research.domain.snapshots import SourceSnapshot


def test_compare_identical_snapshots_returns_non_material():
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()

    s1 = SourceSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=uuid6.uuid7(),
        url="https://uspto.gov/trademarks/coca-cola",
        title="USPTO Record",
        publisher="uspto.gov",
        excerpt="Status: Live/Registered.",
        origin="extract",
    )
    s2 = SourceSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=uuid6.uuid7(),
        url="https://uspto.gov/trademarks/coca-cola",
        title="USPTO Record",
        publisher="uspto.gov",
        excerpt="Status: Live/Registered.",
        origin="extract",
    )

    delta = compare_snapshots(s1, s2)
    assert delta.materiality == ChangeMateriality.NON_MATERIAL

def test_compare_altered_snapshots_returns_material():
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()

    s1 = SourceSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=uuid6.uuid7(),
        url="https://uspto.gov/trademarks/coca-cola",
        title="USPTO Record",
        publisher="uspto.gov",
        excerpt="Status: Live/Registered.",
        origin="extract",
    )
    s2 = SourceSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=uuid6.uuid7(),
        url="https://uspto.gov/trademarks/coca-cola",
        title="USPTO Record",
        publisher="uspto.gov",
        excerpt="Status: Cancelled/Dead.",
        origin="extract",
    )

    delta = compare_snapshots(s1, s2)
    assert delta.materiality == ChangeMateriality.MATERIAL
