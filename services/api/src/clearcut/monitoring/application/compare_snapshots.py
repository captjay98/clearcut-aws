from clearcut.monitoring.domain.materiality import ChangeMateriality, SourceDelta
from clearcut.research.domain.snapshots import SourceSnapshot


def compare_snapshots(
    prior_snapshot: SourceSnapshot,
    new_snapshot: SourceSnapshot,
) -> SourceDelta:
    if prior_snapshot.sha256_hash == new_snapshot.sha256_hash:
        return SourceDelta.create(
            org_id=prior_snapshot.org_id,
            project_id=prior_snapshot.project_id,
            item_id=prior_snapshot.item_id,
            prior_snapshot_id=prior_snapshot.snapshot_id,
            new_snapshot_id=new_snapshot.snapshot_id,
            materiality=ChangeMateriality.NON_MATERIAL,
            rationale="Identical content hash; non-material.",
        )

    # If excerpt or text changed significantly
    if prior_snapshot.excerpt != new_snapshot.excerpt:
        return SourceDelta.create(
            org_id=prior_snapshot.org_id,
            project_id=prior_snapshot.project_id,
            item_id=prior_snapshot.item_id,
            prior_snapshot_id=prior_snapshot.snapshot_id,
            new_snapshot_id=new_snapshot.snapshot_id,
            materiality=ChangeMateriality.MATERIAL,
            rationale=(
                f"Source content excerpt modified: '{prior_snapshot.excerpt}' "
                f"-> '{new_snapshot.excerpt}'"
            ),
        )

    return SourceDelta.create(
        org_id=prior_snapshot.org_id,
        project_id=prior_snapshot.project_id,
        item_id=prior_snapshot.item_id,
        prior_snapshot_id=prior_snapshot.snapshot_id,
        new_snapshot_id=new_snapshot.snapshot_id,
        materiality=ChangeMateriality.NON_MATERIAL,
        rationale="Minor metadata/whitespace change; non-material.",
    )
