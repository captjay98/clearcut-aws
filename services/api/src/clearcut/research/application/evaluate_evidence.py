from uuid import UUID

from clearcut.research.domain.claims import (
    EvidenceClaim,
    EvidenceStance,
    SourceAuthorityTier,
)
from clearcut.research.domain.confidence import (
    ClearanceConfidenceLevel,
    ConfidenceAssessment,
)
from clearcut.research.domain.conflicts import EvidenceConflict


def assess_clearance_evidence(
    item_id: UUID,
    claims: list[EvidenceClaim],
) -> tuple[list[EvidenceConflict], ConfidenceAssessment]:
    if not claims:
        return (
            [],
            ConfidenceAssessment(
                item_id=item_id,
                level=ClearanceConfidenceLevel.UNRESOLVED,
                has_conflicts=False,
                primary_sources_count=0,
                rationale="Zero research evidence gathered; item remains unresolved.",
            ),
        )

    supports = [c for c in claims if c.stance == EvidenceStance.SUPPORTS]
    disagrees = [c for c in claims if c.stance == EvidenceStance.DISAGREES]
    primary = [c for c in claims if c.authority_tier == SourceAuthorityTier.PRIMARY_OFFICIAL]

    conflicts: list[EvidenceConflict] = []
    if supports and disagrees:
        conflicts.append(
            EvidenceConflict.create(
                item_id=item_id,
                description=(
                    f"Disagreement detected between {len(supports)} supporting source(s) "
                    f"and {len(disagrees)} disagreeing source(s)."
                ),
            )
        )

    has_conflicts = len(conflicts) > 0
    if has_conflicts:
        level = (
            ClearanceConfidenceLevel.LOW
            if not primary
            else ClearanceConfidenceLevel.MODERATE
        )
        rationale = (
            f"Conflicting evidence found ({len(supports)} supports vs "
            f"{len(disagrees)} disagrees)."
        )
    elif primary and len(supports) >= 2:
        level = ClearanceConfidenceLevel.HIGH
        rationale = (
            f"Corroborated by {len(primary)} primary source(s) with no "
            "conflicting evidence."
        )
    elif supports:
        level = ClearanceConfidenceLevel.MODERATE
        rationale = "Supporting evidence found, but single source or secondary authority."
    else:
        level = ClearanceConfidenceLevel.LOW
        rationale = "Contextual or inconclusive evidence gathered."

    assessment = ConfidenceAssessment(
        item_id=item_id,
        level=level,
        has_conflicts=has_conflicts,
        primary_sources_count=len(primary),
        rationale=rationale,
    )

    return conflicts, assessment
