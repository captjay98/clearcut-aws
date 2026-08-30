from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    DISAGREES = "disagrees"
    CONTEXT = "context"


class SourceAuthorityTier(StrEnum):
    PRIMARY_OFFICIAL = "primary_official"
    REPUTABLE_NEWS = "reputable_news"
    SECONDARY_INFORMAL = "secondary_informal"


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    snapshot_id: UUID
    stance: EvidenceStance
    authority_tier: SourceAuthorityTier
    claim_text: str
    provenance_excerpt: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        snapshot_id: UUID,
        stance: EvidenceStance,
        authority_tier: SourceAuthorityTier,
        claim_text: str,
        provenance_excerpt: str,
        claim_id: UUID | None = None,
    ) -> "EvidenceClaim":
        return cls(
            claim_id=claim_id or uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            snapshot_id=snapshot_id,
            stance=stance,
            authority_tier=authority_tier,
            claim_text=claim_text.strip(),
            provenance_excerpt=provenance_excerpt.strip(),
            created_at=datetime.now(UTC),
        )
