"""Application service for the monitoring change-signal review loop.

A monitoring recheck can detect that a cited source changed and persist that
change as a pending :class:`SourceDelta` (a review target). This service closes
the loop: an accountable human reviews the pending signal and records a
governed :class:`MonitoringReviewDecision` — keep-with-follow-up, reopen, or
refer. The decision and its authoritative audit event commit in the caller's
single transaction, so a review is either fully durable or not recorded at all;
there is no in-memory dict that vanishes with the process.

Only typed results or typed governed-command errors cross the boundary. The
actor's capability is derived from the server-provided role (never the client),
and a signal that is absent, foreign, or already reviewed surfaces as a neutral
:class:`~clearcut.commanding.errors.CommandNotFoundError` so a caller can neither
double-review nor probe another tenant's signals.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import uuid6
from clearcut.commanding.domain import AuditPayload, CommandEnvelope
from clearcut.commanding.errors import CommandForbiddenError
from clearcut.commanding.sql import insert_authoritative_audit
from clearcut.monitoring.domain.materiality import (
    MonitoringReviewAction,
    MonitoringReviewDecision,
)
from clearcut.monitoring.ports.review_repository import MonitoringReviewRepositoryPort
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

# The governed operation name and audit action for a monitoring review decision.
_OPERATION = "monitoring.review.decide"
_REVIEW_CAPABILITY = "item:decide"
_AUDIT_ACTION = "monitoring_review_decided"
_AUDIT_TARGET_TYPE = "monitoring_source_delta"


class MonitoringReviewService:
    """Coordinates one governed monitoring review within a single transaction."""

    def __init__(self, repository: MonitoringReviewRepositoryPort) -> None:
        self._repository = repository

    async def review_monitoring_delta(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        delta_id: UUID,
        actor_id: UUID,
        actor_role: str,
        action: MonitoringReviewAction,
        rationale: str,
    ) -> MonitoringReviewDecision:
        """Record a governed review decision for a pending change signal.

        Capability is derived from ``actor_role`` (server-provided); an actor
        without ``item:decide`` is a typed
        :class:`~clearcut.commanding.errors.CommandForbiddenError`. The pending
        delta is flipped to reviewed and the authoritative audit event is
        appended in the same transaction; a delta that is absent, foreign, or
        already reviewed is a neutral
        :class:`~clearcut.commanding.errors.CommandNotFoundError` raised by the
        repository.
        """
        if not has_capability(actor_role, _REVIEW_CAPABILITY):
            raise CommandForbiddenError()

        decision = MonitoringReviewDecision.create(
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            delta_id=delta_id,
            actor_id=actor_id,
            action=action,
            rationale=rationale,
        )

        occurred_at = datetime.now(UTC)

        # Flip the pending delta to reviewed first; a delta that is absent,
        # foreign, or already reviewed raises CommandNotFoundError before any
        # audit event is written, so a review is never audited without a durable
        # decision behind it.
        await self._repository.record_review_decision(
            session,
            delta_id=delta_id,
            org_id=org_id,
            project_id=project_id,
            decision=decision,
            reviewed_at=occurred_at,
        )

        # The envelope carries tenant scope and the accountable actor. The review
        # is a monitoring triage action, not an item version advance, so the
        # optimistic-concurrency inputs are neutral placeholders that satisfy the
        # kernel's validation without asserting an aggregate version.
        envelope = CommandEnvelope(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            operation=_OPERATION,
            idempotency_key=f"monitoring-review:{delta_id}",
            intent_hash=f"{decision.review_id.hex}{decision.delta_id.hex}",
            expected_version=1,
        )

        # Append the authoritative audit event in the same transaction. Any
        # failure here rolls back the review flip together with it. The payload
        # records the operational triage only; it never asserts a legal
        # conclusion about the item.
        await insert_authoritative_audit(
            session,
            envelope,
            action=_AUDIT_ACTION,
            target_type=_AUDIT_TARGET_TYPE,
            target_id=decision.review_id,
            payload=AuditPayload(
                {
                    "deltaId": str(delta_id),
                    "itemId": str(item_id),
                    "action": action.value,
                    "rationale": rationale,
                }
            ),
            correlation_id=uuid6.uuid7(),
            occurred_at=occurred_at,
        )

        return decision


__all__ = ["MonitoringReviewService"]
