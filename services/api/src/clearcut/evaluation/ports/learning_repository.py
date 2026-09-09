"""Typed persistence port for the bounded learning-candidate lifecycle.

The port is the only boundary the learning application service uses to read
organization-scoped candidates and to commit an accountable stage change. Every
value that crosses it is a typed domain object
(:class:`~clearcut.evaluation.domain.learning.LearningCandidate`) or a typed
governed-command error; no booleans, ``None`` sentinels, or raw rows encode
outcomes. A candidate that is not visible in the authenticated organization is a
:class:`~clearcut.commanding.errors.CommandNotFoundError`, so a caller in one
tenant cannot probe another tenant's candidates.

Learning candidates are organization-owned, not project-owned: every read and
write is constrained by the authenticated ``org_id`` alone, and the audit event a
stage change appends carries a null ``project_id``.

Implementations run every statement inside the caller's unit of work, so the
stage change and its authoritative audit event commit or roll back together.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from clearcut.commanding.domain import AuditPayload
from clearcut.evaluation.domain.learning import LearningCandidate
from sqlalchemy.ext.asyncio import AsyncSession


class LearningRepositoryPort(Protocol):
    """Session-bound persistence operations for learning candidates."""

    async def list_candidates(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> tuple[LearningCandidate, ...]:
        """Return the organization's candidates, newest first.

        Raises a typed error rather than returning a partially parsed row: a
        stored scope or stage outside the bounded vocabulary is a visible fault,
        never silently rendered as if it were bounded.
        """
        ...

    async def load_candidate(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        candidate_id: UUID,
    ) -> LearningCandidate:
        """Load one candidate within the authenticated organization scope.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        candidate is absent or belongs to another organization, with the same
        neutral shape in both cases.
        """
        ...

    async def commit_stage_change(
        self,
        session: AsyncSession,
        *,
        candidate: LearningCandidate,
        expected_version: int,
    ) -> None:
        """Persist the new stage with a version-guarded compare-and-swap.

        ``candidate`` is the already-validated next state, carrying its
        ``resulting_version``; ``expected_version`` is the version the caller
        loaded. The legacy ``is_promoted`` boolean is written from the stage so
        the two can never disagree. A zero-row compare-and-swap is classified by
        :meth:`classify_cas_miss`.
        """
        ...

    async def classify_cas_miss(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        candidate_id: UUID,
    ) -> None:
        """Classify a compare-and-swap miss; never returns normally.

        Raises :class:`~clearcut.commanding.errors.StaleVersionConflictError`
        when the candidate is still present in scope (its version advanced
        concurrently) and
        :class:`~clearcut.commanding.errors.CommandNotFoundError` when it is
        absent or foreign, so a concurrent change is a conflict while genuine
        not-found keeps neutral parity.
        """
        ...

    async def append_org_audit(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        actor_id: UUID,
        action: str,
        target_type: str,
        target_id: UUID,
        payload: AuditPayload,
        correlation_id: UUID,
        occurred_at: datetime,
    ) -> None:
        """Append the authoritative audit event for an organization-level change.

        Runs in the caller's transaction so the audit row and the stage change
        are one atomic fact. The payload crosses the boundary as the typed
        :class:`~clearcut.commanding.domain.AuditPayload` seam, never a raw dict.
        """
        ...


__all__ = ["LearningRepositoryPort"]
