"""Fixed-query, tenant-scoped SQL projection for authoritative item detail."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from clearcut.commanding.errors import CommandForbiddenError, CommandNotFoundError
from clearcut.items.application.read_models import (
    CapabilityRead,
    ClearanceItemDetail,
    CommentRead,
    CommentRevisionRead,
    DecisionRecordRead,
    EvidenceClaimRead,
    EvidenceConflictRead,
    EvidenceState,
    ReferralRead,
    SourceSnapshotRead,
)
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

_PROJECT_ACCESS = sa.text(
    """
    SELECT 1
    FROM memberships m
    WHERE m.org_id = :org_id AND m.user_id = :actor_id AND m.status = 'active'
      AND (
        m.role IN ('owner', 'admin')
        OR EXISTS (
          SELECT 1 FROM project_grants pg
          WHERE pg.membership_id = m.id
            AND pg.org_id = m.org_id
            AND pg.project_id = :project_id
        )
      )
    """
)

_BASE_ITEM = sa.text(
    """
    SELECT i.id, i.project_id, i.version_id, i.version, i.category, i.text,
           i.status, i.workflow_status, i.research_status, i.disposition_status,
           i.assigned_to_user_id, e.text AS context_text,
           e.scene_number, e.page_number
    FROM clearance_items i
    LEFT JOIN script_elements e ON e.id = i.element_id
    WHERE i.id = :item_id AND i.org_id = :org_id AND i.project_id = :project_id
    """
)

_EVIDENCE = sa.text(
    """
    SELECT s.id AS snapshot_id, s.url, s.title, s.publisher, s.excerpt,
           s.origin, s.retrieved_at,
           c.id AS claim_id, c.claim_text, c.stance, c.authority_tier,
           c.provenance_excerpt, c.created_at AS claim_created_at
    FROM source_snapshots s
    LEFT JOIN evidence_claims c
      ON c.snapshot_id = s.id
     AND c.item_id = s.item_id
     AND c.org_id = s.org_id
     AND c.project_id = s.project_id
    WHERE s.item_id = :item_id AND s.org_id = :org_id AND s.project_id = :project_id
    ORDER BY s.retrieved_at, s.id, c.created_at, c.id
    """
)

_CONFLICTS = sa.text(
    """
    SELECT id, description, created_at
    FROM evidence_conflicts
    WHERE item_id = :item_id AND org_id = :org_id AND project_id = :project_id
    ORDER BY created_at, id
    """
)

_DECISIONS = sa.text(
    """
    SELECT id, actor_id, decision_kind, decision_value, rationale,
           expected_version, resulting_version, created_at
    FROM governed_decision_records
    WHERE item_id = :item_id AND org_id = :org_id AND project_id = :project_id
    ORDER BY created_at, id
    """
)

_REFERRALS = sa.text(
    """
    SELECT id, target_role, question, notes, status, submitted_by_actor_id,
           acknowledged_by_actor_id, submitted_at, acknowledged_at
    FROM governed_referrals
    WHERE item_id = :item_id AND org_id = :org_id AND project_id = :project_id
    ORDER BY submitted_at, id
    """
)

_COMMENTS = sa.text(
    """
    SELECT c.id AS comment_id, c.author_id AS comment_author_id,
           c.parent_comment_id, c.reply_depth, c.created_at AS comment_created_at,
           r.id AS revision_id, r.ordinal, r.author_id AS revision_author_id,
           r.body, r.created_at AS revision_created_at,
           m.recipient_user_id, m.created_at AS mention_created_at
    FROM governed_comments c
    JOIN governed_comment_revisions r
      ON r.comment_id = c.id
     AND r.org_id = c.org_id
     AND r.project_id = c.project_id
    LEFT JOIN governed_comment_mentions m
      ON m.revision_id = r.id
     AND m.comment_id = c.id
     AND m.org_id = c.org_id
     AND m.project_id = c.project_id
    WHERE c.item_id = :item_id AND c.org_id = :org_id AND c.project_id = :project_id
    ORDER BY c.created_at, c.id, r.ordinal, m.created_at, m.id
    """
)

_CAPABILITY_EXPLANATIONS = {
    "item:assign": "Assign or unassign an active member in this project.",
    "item:refer": "Refer unresolved evidence to an authorized specialist.",
    "item:decide": "Record a human evidence-review decision; this is not legal clearance.",
    "item:disposition": "Record a pre-clearance workflow disposition.",
    "rewrite:propose": "Propose a screenplay rewrite without changing protected policy.",
    "rewrite:approve": "Approve an attributable rewrite through maker-checker review.",
    "report:generate": "Generate a version-bound report snapshot for human review.",
    "report:release": "Release an immutable report after accountable attestation.",
}


class SqlItemReadRepository:
    """Load one detail with a constant number of exact-scope SQL statements."""

    async def load_detail(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        actor_id: UUID,
        actor_role: str,
    ) -> ClearanceItemDetail:
        parameters = {
            "org_id": str(org_id),
            "project_id": str(project_id),
            "item_id": str(item_id),
        }
        access = await session.execute(
            _PROJECT_ACCESS,
            {**parameters, "actor_id": str(actor_id)},
        )
        if access.first() is None:
            raise CommandForbiddenError()

        item = (await session.execute(_BASE_ITEM, parameters)).mappings().first()
        if item is None:
            raise CommandNotFoundError()

        evidence_rows = (await session.execute(_EVIDENCE, parameters)).mappings().all()
        conflict_rows = (await session.execute(_CONFLICTS, parameters)).mappings().all()
        decision_rows = (await session.execute(_DECISIONS, parameters)).mappings().all()
        referral_rows = (await session.execute(_REFERRALS, parameters)).mappings().all()
        comment_rows = (await session.execute(_COMMENTS, parameters)).mappings().all()

        snapshots: list[SourceSnapshotRead] = []
        claims: list[EvidenceClaimRead] = []
        seen_snapshots: set[str] = set()
        for row in evidence_rows:
            snapshot_id = str(row["snapshot_id"])
            if snapshot_id not in seen_snapshots:
                seen_snapshots.add(snapshot_id)
                snapshots.append(
                    SourceSnapshotRead(
                        snapshot_id=snapshot_id,
                        url=str(row["url"]),
                        title=str(row["title"]),
                        publisher=str(row["publisher"]),
                        excerpt=str(row["excerpt"]),
                        origin=str(row["origin"]),
                        retrieved_at=_aware(row["retrieved_at"]),
                    )
                )
            if row["claim_id"] is not None:
                claims.append(
                    EvidenceClaimRead(
                        claim_id=str(row["claim_id"]),
                        snapshot_id=snapshot_id,
                        claim_text=str(row["claim_text"]),
                        stance=str(row["stance"]),
                        authority_tier=str(row["authority_tier"]),
                        provenance_excerpt=str(row["provenance_excerpt"]),
                        created_at=_aware(row["claim_created_at"]),
                    )
                )

        revisions_by_comment: dict[str, dict[str, CommentRevisionRead]] = {}
        comments_by_id: dict[str, CommentRead] = {}
        for row in comment_rows:
            comment_id = str(row["comment_id"])
            if comment_id not in comments_by_id:
                revisions_by_comment[comment_id] = {}
                comments_by_id[comment_id] = CommentRead(
                    comment_id=comment_id,
                    author_id=str(row["comment_author_id"]),
                    parent_id=(
                        str(row["parent_comment_id"])
                        if row["parent_comment_id"] is not None
                        else None
                    ),
                    reply_depth=int(row["reply_depth"]),
                    created_at=_aware(row["comment_created_at"]),
                    revisions=[],
                )
            revision_id = str(row["revision_id"])
            revision = revisions_by_comment[comment_id].get(revision_id)
            if revision is None:
                revision = CommentRevisionRead(
                    revision_id=revision_id,
                    ordinal=int(row["ordinal"]),
                    author_id=str(row["revision_author_id"]),
                    body=str(row["body"]),
                    created_at=_aware(row["revision_created_at"]),
                    mention_recipient_ids=[],
                )
                revisions_by_comment[comment_id][revision_id] = revision
                comments_by_id[comment_id].revisions.append(revision)
            if row["recipient_user_id"] is not None:
                recipient = str(row["recipient_user_id"])
                if recipient not in revision.mention_recipient_ids:
                    revision.mention_recipient_ids.append(recipient)

        evidence_state = _evidence_state(str(item["research_status"]), len(claims))
        disposition = (
            str(item["disposition_status"])
            if item["disposition_status"] not in (None, "undisposed")
            else None
        )
        return ClearanceItemDetail(
            item_id=str(item["id"]),
            project_id=str(item["project_id"]),
            version_id=str(item["version_id"]),
            version=int(item["version"]),
            category=str(item["category"]),
            entity_name=str(item["text"]),
            context_text=(str(item["context_text"]) if item["context_text"] is not None else None),
            scene=(int(item["scene_number"]) if item["scene_number"] is not None else None),
            page=(int(item["page_number"]) if item["page_number"] is not None else None),
            status=str(item["status"]),
            workflow_status=str(item["workflow_status"]),
            research_status=str(item["research_status"]),
            disposition=disposition,
            assigned_to=(
                str(item["assigned_to_user_id"])
                if item["assigned_to_user_id"] is not None
                else None
            ),
            evidence_state=evidence_state,
            claims=claims,
            snapshots=snapshots,
            conflicts=[
                EvidenceConflictRead(
                    conflict_id=str(row["id"]),
                    description=str(row["description"]),
                    created_at=_aware(row["created_at"]),
                )
                for row in conflict_rows
            ],
            decisions=[
                DecisionRecordRead(
                    record_id=str(row["id"]),
                    kind=str(row["decision_kind"]),
                    value=str(row["decision_value"]),
                    rationale=str(row["rationale"]),
                    actor_id=str(row["actor_id"]),
                    expected_version=int(row["expected_version"]),
                    resulting_version=int(row["resulting_version"]),
                    created_at=_aware(row["created_at"]),
                )
                for row in decision_rows
            ],
            referrals=[
                ReferralRead(
                    referral_id=str(row["id"]),
                    target_role=str(row["target_role"]),
                    question=str(row["question"]),
                    notes=(str(row["notes"]) if row["notes"] is not None else None),
                    status=str(row["status"]),
                    submitted_by_actor_id=str(row["submitted_by_actor_id"]),
                    acknowledged_by_actor_id=(
                        str(row["acknowledged_by_actor_id"])
                        if row["acknowledged_by_actor_id"] is not None
                        else None
                    ),
                    submitted_at=_aware(row["submitted_at"]),
                    acknowledged_at=(
                        _aware(row["acknowledged_at"])
                        if row["acknowledged_at"] is not None
                        else None
                    ),
                )
                for row in referral_rows
            ],
            comments=list(comments_by_id.values()),
            capabilities=[
                CapabilityRead(
                    action=action,
                    allowed=has_capability(actor_role, action),
                    explanation=explanation,
                )
                for action, explanation in _CAPABILITY_EXPLANATIONS.items()
            ],
        )


def _evidence_state(research_status: str, claim_count: int) -> EvidenceState:
    if claim_count:
        return EvidenceState(
            status="cited",
            claim_count=claim_count,
            reason="Cited evidence is available for qualified human review.",
        )
    if research_status == "completed":
        return EvidenceState(
            status="no_results",
            claim_count=0,
            reason="Research completed without cited evidence; the item remains unresolved.",
        )
    if research_status == "failed":
        return EvidenceState(
            status="failed",
            claim_count=0,
            reason="Evidence research failed; the item remains unresolved.",
        )
    if research_status == "unavailable":
        return EvidenceState(
            status="unavailable",
            claim_count=0,
            reason="Evidence research is unavailable; the item remains unresolved.",
        )
    return EvidenceState(
        status="pending",
        claim_count=0,
        reason="Evidence research has not produced cited claims.",
    )


def _aware(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = ["SqlItemReadRepository"]
