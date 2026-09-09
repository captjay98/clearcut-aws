"""Session-bound SQL adapter for the learning-candidate port.

Every statement runs on the caller-provided
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and never opens, commits, or rolls
back a transaction of its own, so a stage change and its authoritative audit
event share one unit of work. All reads and writes are constrained by the
authenticated ``org_id``; a candidate is never loaded or mutated outside its
organization, and an absent or foreign candidate surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError` with the same neutral
shape.

Two details are deliberate:

* The stage write is a version-guarded compare-and-swap. A zero-row result means
  the row moved between load and update, and is classified as a stale-version
  conflict when the candidate is still in scope, or neutral not-found when it is
  not.
* The legacy ``is_promoted`` boolean is always written from the new stage, so the
  column migration 0036 kept for compatibility can never contradict the stage
  machine.

The authoritative audit insert here writes ``project_id`` as SQL ``NULL``,
because a learning candidate is organization-owned and belongs to no project.
The kernel helper :func:`clearcut.commanding.sql.insert_authoritative_audit`
derives that column from a project-scoped
:class:`~clearcut.commanding.domain.CommandEnvelope` and cannot express an
org-level event, so this adapter issues the same insert against the same ledger
table with a null project rather than persisting a project id that does not
exist. The typed :class:`~clearcut.commanding.domain.AuditPayload` seam is still
the only way a payload reaches ``payload_redacted``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.commanding.domain import AuditPayload
from clearcut.commanding.errors import (
    CommandNotFoundError,
    CommandValidationError,
    StaleVersionConflictError,
)
from clearcut.evaluation.domain.learning import LearningCandidate
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

_CANDIDATE_COLUMNS = """
    id, org_id, scope, proposed_changes, canary_pass_rate, stage, title, summary,
    regression_cases_passed, regression_cases_total, canary_started_at,
    promoted_at, promoted_by, rolled_back_at, rolled_back_by, rollback_reason,
    version, created_at
"""

_LIST_CANDIDATES = sa.text(
    f"""
    SELECT {_CANDIDATE_COLUMNS}
    FROM learning_candidates
    WHERE org_id = :org_id
    ORDER BY created_at DESC, id DESC
    """
)

_LOAD_CANDIDATE = sa.text(
    f"""
    SELECT {_CANDIDATE_COLUMNS}
    FROM learning_candidates
    WHERE id = :candidate_id AND org_id = :org_id
    """
)

_CANDIDATE_EXISTS_IN_SCOPE = sa.text(
    "SELECT 1 FROM learning_candidates WHERE id = :candidate_id AND org_id = :org_id"
)

_ADVANCE_STAGE = sa.text(
    """
    UPDATE learning_candidates
    SET stage = :stage,
        is_promoted = :is_promoted,
        canary_started_at = :canary_started_at,
        promoted_at = :promoted_at,
        promoted_by = :promoted_by,
        rolled_back_at = :rolled_back_at,
        rolled_back_by = :rolled_back_by,
        rollback_reason = :rollback_reason,
        version = :resulting_version
    WHERE id = :candidate_id AND org_id = :org_id AND version = :expected_version
    """
)

# The same authoritative ledger every governed surface writes, with a null
# project for an organization-level event.
_AUDIT_INSERT = sa.text(
    """
    INSERT INTO authoritative_audit_events (
        id, org_id, project_id, actor_id, action, target_type,
        target_id, payload_redacted, occurred_at, correlation_id
    ) VALUES (
        :id, :org_id, NULL, :actor_id, :action, :target_type,
        :target_id, :payload, :occurred_at, :correlation_id
    )
    """
).bindparams(sa.bindparam("payload", type_=sa.JSON()))


class SqlLearningRepository:
    """SQL implementation of :class:`LearningRepositoryPort`."""

    async def list_candidates(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> tuple[LearningCandidate, ...]:
        rows = (await session.execute(_LIST_CANDIDATES, {"org_id": str(org_id)})).mappings().all()
        return tuple(_row_to_candidate(row) for row in rows)

    async def load_candidate(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        candidate_id: UUID,
    ) -> LearningCandidate:
        row = (
            (
                await session.execute(
                    _LOAD_CANDIDATE,
                    {"candidate_id": str(candidate_id), "org_id": str(org_id)},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise CommandNotFoundError()
        return _row_to_candidate(row)

    async def commit_stage_change(
        self,
        session: AsyncSession,
        *,
        candidate: LearningCandidate,
        expected_version: int,
    ) -> None:
        result = await session.execute(
            _ADVANCE_STAGE,
            {
                "stage": candidate.stage.value,
                "is_promoted": candidate.is_promoted,
                "canary_started_at": candidate.canary_started_at,
                "promoted_at": candidate.promoted_at,
                "promoted_by": _optional_text(candidate.promoted_by),
                "rolled_back_at": candidate.rolled_back_at,
                "rolled_back_by": _optional_text(candidate.rolled_back_by),
                "rollback_reason": candidate.rollback_reason,
                "resulting_version": candidate.version,
                "candidate_id": str(candidate.candidate_id),
                "org_id": str(candidate.org_id),
                "expected_version": expected_version,
            },
        )
        # The version-guarded compare-and-swap must match exactly one row. Zero
        # rows means the candidate moved between load and update; the caller's
        # transaction must not commit a stage change against a version that
        # changed under it.
        if cast(CursorResult[Any], result).rowcount != 1:
            await self.classify_cas_miss(
                session,
                org_id=candidate.org_id,
                candidate_id=candidate.candidate_id,
            )

    async def classify_cas_miss(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        candidate_id: UUID,
    ) -> None:
        exists = (
            await session.execute(
                _CANDIDATE_EXISTS_IN_SCOPE,
                {"candidate_id": str(candidate_id), "org_id": str(org_id)},
            )
        ).first()
        if exists is not None:
            raise StaleVersionConflictError()
        raise CommandNotFoundError()

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
        if not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None:
            raise CommandValidationError("The occurred_at timestamp must be timezone-aware.")
        await session.execute(
            _AUDIT_INSERT,
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "actor_id": str(actor_id),
                "action": action,
                "target_type": target_type,
                "target_id": str(target_id),
                "payload": dict(payload.as_redacted()),
                "occurred_at": occurred_at,
                "correlation_id": str(correlation_id),
            },
        )


def _row_to_candidate(row: Any) -> LearningCandidate:
    """Build the typed candidate from a stored row.

    Scope and stage are parsed through the domain's fail-closed parsers, so a
    stored value outside the bounded vocabulary raises a typed error instead of
    being presented as if it were bounded.
    """
    return LearningCandidate(
        candidate_id=_as_uuid(row["id"]),
        org_id=_as_uuid(row["org_id"]),
        scope=row["scope"],
        proposed_changes=_as_mapping(row["proposed_changes"]),
        canary_pass_rate=float(row["canary_pass_rate"]),
        stage=row["stage"],
        title=_optional_str(row["title"]),
        summary=_optional_str(row["summary"]),
        regression_cases_passed=int(row["regression_cases_passed"]),
        regression_cases_total=int(row["regression_cases_total"]),
        canary_started_at=_optional_datetime(row["canary_started_at"]),
        promoted_at=_optional_datetime(row["promoted_at"]),
        promoted_by=_optional_uuid(row["promoted_by"]),
        rolled_back_at=_optional_datetime(row["rolled_back_at"]),
        rolled_back_by=_optional_uuid(row["rolled_back_by"]),
        rollback_reason=_optional_str(row["rollback_reason"]),
        version=int(row["version"]),
        created_at=_as_datetime(row["created_at"]),
    )


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return decoded
    raise CommandValidationError("The stored proposed changes are not a mapping.")


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _optional_uuid(value: Any) -> UUID | None:
    return None if value is None else _as_uuid(value)


def _optional_text(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else _as_datetime(value)


__all__ = ["SqlLearningRepository"]
