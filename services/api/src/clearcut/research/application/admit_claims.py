from uuid import UUID

from clearcut.research.domain.claims import EvidenceClaim
from clearcut.research.domain.snapshots import SourceSnapshot


class ClaimAdmissionService:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, SourceSnapshot] = {}
        self.admitted_claims: dict[UUID, EvidenceClaim] = {}

    def register_snapshot(self, snapshot: SourceSnapshot) -> None:
        self.snapshots[snapshot.snapshot_id] = snapshot

    def admit_claim(self, claim: EvidenceClaim) -> bool:
        snapshot = self.snapshots.get(claim.snapshot_id)
        if not snapshot:
            return False

        # Verify tenant scope match
        if (
            snapshot.org_id != claim.org_id
            or snapshot.project_id != claim.project_id
            or snapshot.item_id != claim.item_id
        ):
            return False

        self.admitted_claims[claim.claim_id] = claim
        return True
