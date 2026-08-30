import uuid6
from clearcut.research.application.evaluate_evidence import assess_clearance_evidence
from clearcut.research.domain.claims import EvidenceClaim, EvidenceStance, SourceAuthorityTier
from clearcut.research.domain.confidence import ClearanceConfidenceLevel


def test_detect_conflicting_claims_and_assess_confidence():
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()

    # Supporting claim from primary source
    claim1 = EvidenceClaim.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=uuid6.uuid7(),
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Trademark is active",
        provenance_excerpt="Status: Active"
    )

    # Disagreeing claim from news source
    claim2 = EvidenceClaim.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=uuid6.uuid7(),
        stance=EvidenceStance.DISAGREES,
        authority_tier=SourceAuthorityTier.REPUTABLE_NEWS,
        claim_text="Trademark was cancelled in recent litigation",
        provenance_excerpt="Status: Contested"
    )

    conflicts, confidence = assess_clearance_evidence(item_id, [claim1, claim2])
    assert len(conflicts) == 1
    assert confidence.has_conflicts is True
    assert confidence.level in {ClearanceConfidenceLevel.MODERATE, ClearanceConfidenceLevel.LOW}
