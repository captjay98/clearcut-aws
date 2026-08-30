import uuid6
from clearcut.research.application.admit_claims import ClaimAdmissionService
from clearcut.research.domain.claims import EvidenceClaim, EvidenceStance, SourceAuthorityTier
from clearcut.research.domain.snapshots import SourceSnapshot


def test_claim_admission_requires_matching_snapshot_scope():
    service = ClaimAdmissionService()

    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    run_id = uuid6.uuid7()

    snapshot = SourceSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=run_id,
        url="https://uspto.gov/tm1",
        title="USPTO",
        publisher="USPTO",
        excerpt="Status Active",
    )
    service.register_snapshot(snapshot)

    # Valid claim with registered snapshot
    valid_claim = EvidenceClaim.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=snapshot.snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Active trademark",
        provenance_excerpt="Status Active"
    )
    assert service.admit_claim(valid_claim) is True

    # Reject claim citing non-existent / cross-project snapshot
    other_snapshot_id = uuid6.uuid7()
    invalid_claim = EvidenceClaim.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=other_snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Active trademark",
        provenance_excerpt="Status Active"
    )
    assert service.admit_claim(invalid_claim) is False
