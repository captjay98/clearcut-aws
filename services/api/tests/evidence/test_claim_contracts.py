import uuid6
from clearcut.research.domain.claims import (
    EvidenceClaim,
    EvidenceStance,
    SourceAuthorityTier,
)


def test_evidence_claim_creation():
    claim_id = uuid6.uuid7()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    snapshot_id = uuid6.uuid7()

    claim = EvidenceClaim.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Coca-Cola is a registered active trademark.",
        provenance_excerpt="USPTO status: Active, registered to The Coca-Cola Company.",
        claim_id=claim_id,
    )

    assert claim.stance == EvidenceStance.SUPPORTS
    assert claim.authority_tier == SourceAuthorityTier.PRIMARY_OFFICIAL
    assert claim.snapshot_id == snapshot_id
