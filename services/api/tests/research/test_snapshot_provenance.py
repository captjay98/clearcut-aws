import uuid6
from clearcut.research.domain.snapshots import SourceSnapshot


def test_source_snapshot_creation_and_hash():
    snapshot_id = uuid6.uuid7()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    run_id = uuid6.uuid7()

    snapshot = SourceSnapshot.create(
        snapshot_id=snapshot_id,
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=run_id,
        url="https://uspto.gov/trademarks/coca-cola",
        title="USPTO Trademark Database - Coca-Cola",
        publisher="USPTO",
        excerpt="Active trademark registered in 1893 for carbonated soft drinks.",
        origin="search",
        published_date="2024-01-01"
    )

    assert snapshot.url == "https://uspto.gov/trademarks/coca-cola"
    assert snapshot.origin == "search"
    assert len(snapshot.sha256_hash) == 64
