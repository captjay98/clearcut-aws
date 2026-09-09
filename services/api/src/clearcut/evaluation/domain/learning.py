"""Bounded learning-candidate domain: what a candidate may change, and when.

The learning loop is deliberately small. A candidate may propose a change to
query phrasing, retrieval/category examples, a prompt refinement, or an
organization-scoped preference -- and nothing else. It touches no permissions,
no sign-off policy, no categories, no authority tiers, no evidence schema, no
deterministic blocking rules, no retention/privacy settings, and no
legal-boundary language. Those eight scopes are :data:`PROTECTED_SCOPES` and are
changed by an accountable human through the protected-configuration surface,
never by this pipeline.

Two invariants are enforced here rather than at the delivery or storage edge, so
they hold for every caller:

* **Bounded scope.** The candidate's own ``scope`` must be a
  :class:`LearningScope`, and any ``proposed_changes['target_scope']`` must also
  be a bounded :class:`LearningScope`. A protected target is a typed
  :class:`ProtectedScopeViolationError`; an unrecognized target is a typed
  :class:`UnboundedLearningScopeError`, because a scope that cannot be proven
  bounded is not treated as bounded.
* **Stage machine with gates.** ``candidate -> shadow -> canary -> promoted``,
  and ``canary | promoted -> rolled_back``. Any other move is a typed
  :class:`LearningStageTransitionError` -- never a silent no-op. Promotion
  additionally requires a fully passing regression suite (with at least one
  case) and a canary pass rate at or above
  :data:`CANARY_PASS_RATE_THRESHOLD`. Rollback is always available from
  ``canary`` or ``promoted``, because withdrawing a change must never be gated
  on the evidence that justified it.

Every failure crosses the boundary as a typed error from the governed-command
vocabulary (:mod:`clearcut.commanding.errors`), so one delivery mapping serves
this module and every other governed surface. No booleans encode decisions.

The module is storage-agnostic and side-effect free; each state change returns a
new immutable :class:`LearningCandidate`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import uuid6
from clearcut.commanding.errors import CommandForbiddenError, CommandValidationError

# The eight human-only scopes. A learning candidate may never target one of
# these, regardless of how strong its evaluation evidence looks.
PROTECTED_SCOPES: frozenset[str] = frozenset(
    {
        "permissions",
        "sign_off",
        "categories",
        "authority_tiers",
        "evidence_schema",
        "blockers",
        "retention",
        "legal_boundary",
    }
)

# The promotion gate on canary quality. Promotion is refused below this rate.
CANARY_PASS_RATE_THRESHOLD = 0.95

# The key inside ``proposed_changes`` that names what the candidate would change.
TARGET_SCOPE_KEY = "target_scope"


class LearningScope(StrEnum):
    """The complete set of things a learning candidate is allowed to change."""

    QUERY_PHRASING = "query_phrasing"
    RETRIEVAL_EXAMPLES = "retrieval_examples"
    PROMPT_REFINEMENT = "prompt_refinement"
    ORG_PREFERENCES = "org_preferences"


class LearningStage(StrEnum):
    """The auditable lifecycle stage of a learning candidate."""

    CANDIDATE = "candidate"
    SHADOW = "shadow"
    CANARY = "canary"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


# The only legal moves. Promotion is reachable exclusively through shadow and
# canary, so nothing is promoted before it has been observed; rollback is
# reachable from canary and promoted, and a rolled-back candidate is terminal.
_ALLOWED_TRANSITIONS: Mapping[LearningStage, frozenset[LearningStage]] = {
    LearningStage.CANDIDATE: frozenset({LearningStage.SHADOW}),
    LearningStage.SHADOW: frozenset({LearningStage.CANARY}),
    LearningStage.CANARY: frozenset({LearningStage.PROMOTED, LearningStage.ROLLED_BACK}),
    LearningStage.PROMOTED: frozenset({LearningStage.ROLLED_BACK}),
    LearningStage.ROLLED_BACK: frozenset(),
}

# Rollback is permitted from exactly these stages, and is never gated on
# evaluation evidence.
ROLLBACK_SOURCE_STAGES: frozenset[LearningStage] = frozenset(
    {LearningStage.CANARY, LearningStage.PROMOTED}
)


class ProtectedScopeViolationError(CommandForbiddenError):
    """The candidate would change a human-only protected scope."""

    code = "learning_protected_scope_violation"
    _default_message = (
        "A learning candidate may not change protected configuration; "
        "that change requires an accountable human decision."
    )


class UnboundedLearningScopeError(CommandForbiddenError):
    """The candidate's scope is not one of the four bounded learning scopes."""

    code = "learning_scope_unbounded"
    _default_message = (
        "A learning candidate may only change query phrasing, retrieval or "
        "category examples, prompt refinements, or organization preferences."
    )


class LearningStageTransitionError(CommandValidationError):
    """The requested stage move is not part of the learning lifecycle."""

    code = "learning_stage_transition_invalid"
    _default_message = "The learning candidate is not in a stage that allows this change."


class RegressionGateNotMetError(CommandValidationError):
    """The candidate has not cleared its regression or canary gate."""

    code = "learning_regression_gate_not_met"
    _default_message = "The learning candidate has not cleared its evaluation gates."


def parse_learning_scope(value: object) -> LearningScope:
    """Return the bounded :class:`LearningScope` for ``value``, or raise.

    A protected scope raises :class:`ProtectedScopeViolationError` so the caller
    can report the specific boundary that was hit; anything else unrecognized
    raises :class:`UnboundedLearningScopeError`. Fail-closed: an unknown scope is
    never assumed to be safe.
    """
    if isinstance(value, LearningScope):
        return value
    if isinstance(value, str):
        if value in PROTECTED_SCOPES:
            raise ProtectedScopeViolationError(
                f"Protected scope '{value}' is human-only and cannot be changed by learning."
            )
        try:
            return LearningScope(value)
        except ValueError:
            raise UnboundedLearningScopeError() from None
    raise UnboundedLearningScopeError()


def parse_learning_stage(value: object) -> LearningStage:
    """Return the :class:`LearningStage` for ``value``, or raise a typed error."""
    if isinstance(value, LearningStage):
        return value
    if isinstance(value, str):
        try:
            return LearningStage(value)
        except ValueError:
            raise LearningStageTransitionError(
                "The learning candidate has an unrecognized lifecycle stage."
            ) from None
    raise LearningStageTransitionError(
        "The learning candidate has an unrecognized lifecycle stage."
    )


def assert_transition_allowed(current: LearningStage, target: LearningStage) -> None:
    """Raise :class:`LearningStageTransitionError` unless the move is legal.

    An attempt to re-enter the current stage is rejected too: a repeated
    promotion or rollback is a real conflict the caller must see, not a silent
    no-op that would leave a second audit event claiming a change that did not
    happen.
    """
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise LearningStageTransitionError(
            f"A learning candidate cannot move from '{current.value}' to '{target.value}'."
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class LearningCandidate:
    """One bounded, auditable proposal and the stage it currently occupies.

    ``created_at`` uses a ``default_factory`` so each instance is stamped when it
    is built. (A plain ``= datetime.now(UTC)`` default would be evaluated once,
    at class-definition time, and hand every candidate the process start time.)

    ``version`` is the optimistic-concurrency version that guards every stage
    change. ``is_promoted`` is derived from ``stage`` rather than stored, so the
    legacy boolean column can never disagree with the stage machine.
    """

    candidate_id: UUID
    org_id: UUID
    scope: LearningScope
    proposed_changes: Mapping[str, Any]
    canary_pass_rate: float
    stage: LearningStage = LearningStage.CANDIDATE
    title: str | None = None
    summary: str | None = None
    regression_cases_passed: int = 0
    regression_cases_total: int = 0
    canary_started_at: datetime | None = None
    promoted_at: datetime | None = None
    promoted_by: UUID | None = None
    rolled_back_at: datetime | None = None
    rolled_back_by: UUID | None = None
    rollback_reason: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        # Coerce the two enum-backed fields through the fail-closed parsers so a
        # candidate can never hold a raw, unvalidated scope or stage string.
        object.__setattr__(self, "scope", parse_learning_scope(self.scope))
        object.__setattr__(self, "stage", parse_learning_stage(self.stage))
        if not isinstance(self.proposed_changes, Mapping):
            raise CommandValidationError("The proposed changes must be a mapping.")
        if self.regression_cases_passed < 0:
            raise CommandValidationError("The regression pass count cannot be negative.")
        if self.regression_cases_total < self.regression_cases_passed:
            raise CommandValidationError(
                "The regression total cannot be smaller than the passing count."
            )
        if not 0.0 <= float(self.canary_pass_rate) <= 1.0:
            raise CommandValidationError("The canary pass rate must be between 0 and 1.")
        if self.version < 1:
            raise CommandValidationError("The candidate version must be a positive integer.")

    @property
    def is_promoted(self) -> bool:
        """The legacy boolean, derived from the stage machine."""
        return self.stage is LearningStage.PROMOTED

    @classmethod
    def create(
        cls,
        org_id: UUID,
        scope: LearningScope,
        proposed_changes: Mapping[str, Any],
        canary_pass_rate: float,
        *,
        title: str | None = None,
        summary: str | None = None,
        regression_cases_passed: int = 0,
        regression_cases_total: int = 0,
    ) -> LearningCandidate:
        """Build a fresh candidate at the ``candidate`` stage."""
        return cls(
            candidate_id=uuid6.uuid7(),
            org_id=org_id,
            scope=scope,
            proposed_changes=proposed_changes,
            canary_pass_rate=canary_pass_rate,
            stage=LearningStage.CANDIDATE,
            title=title,
            summary=summary,
            regression_cases_passed=regression_cases_passed,
            regression_cases_total=regression_cases_total,
            created_at=_utc_now(),
        )

    def assert_bounded(self) -> None:
        """Raise unless this candidate changes only a bounded learning scope.

        ``scope`` is already validated at construction; this re-checks it and,
        when the proposal names a ``target_scope`` of its own, validates that too.
        A proposal that names no target changes exactly its declared ``scope``,
        which is already bounded; a proposal that names one must not use it to
        reach past that boundary.
        """
        parse_learning_scope(self.scope)
        target = self.proposed_changes.get(TARGET_SCOPE_KEY)
        if target is not None:
            parse_learning_scope(target)

    def assert_regression_gate(self) -> None:
        """Raise unless the regression suite fully passed and canary cleared.

        A candidate with zero regression cases has produced no evidence that it
        is safe, so it is refused for the same reason a partially failing suite
        is: promotion requires positive evidence, never the absence of a
        failure.
        """
        if self.regression_cases_total < 1:
            raise RegressionGateNotMetError(
                "Promotion requires at least one recorded regression case."
            )
        if self.regression_cases_passed < self.regression_cases_total:
            raise RegressionGateNotMetError(
                f"Promotion requires every regression case to pass "
                f"({self.regression_cases_passed} of {self.regression_cases_total} passed)."
            )
        if self.canary_pass_rate < CANARY_PASS_RATE_THRESHOLD:
            raise RegressionGateNotMetError(
                f"Promotion requires a canary pass rate of at least {CANARY_PASS_RATE_THRESHOLD}."
            )

    def promoted(
        self,
        *,
        actor_id: UUID,
        occurred_at: datetime,
        resulting_version: int,
    ) -> LearningCandidate:
        """Return this candidate promoted, or raise a typed refusal.

        Order is deliberate: the protected-scope boundary is checked before the
        evaluation gates, so a candidate that must never be promoted is refused
        as forbidden rather than merely under-evidenced.
        """
        self.assert_bounded()
        self.assert_regression_gate()
        assert_transition_allowed(self.stage, LearningStage.PROMOTED)
        _require_aware(occurred_at)
        return replace(
            self,
            stage=LearningStage.PROMOTED,
            promoted_at=occurred_at,
            promoted_by=actor_id,
            version=resulting_version,
        )

    def rolled_back(
        self,
        *,
        actor_id: UUID,
        occurred_at: datetime,
        resulting_version: int,
        reason: str | None = None,
    ) -> LearningCandidate:
        """Return this candidate rolled back, or raise a typed refusal.

        Rollback is intentionally ungated: withdrawing a change is always
        allowed from ``canary`` or ``promoted``, and it records who did it.
        """
        assert_transition_allowed(self.stage, LearningStage.ROLLED_BACK)
        _require_aware(occurred_at)
        cleaned = reason.strip() if isinstance(reason, str) else None
        return replace(
            self,
            stage=LearningStage.ROLLED_BACK,
            rolled_back_at=occurred_at,
            rolled_back_by=actor_id,
            rollback_reason=cleaned or None,
            version=resulting_version,
        )

    def advanced_to(
        self,
        stage: LearningStage,
        *,
        occurred_at: datetime,
        resulting_version: int,
    ) -> LearningCandidate:
        """Return this candidate moved to an observation stage.

        Used for the ``shadow`` and ``canary`` steps, which carry no accountable
        actor of their own; ``promoted`` and ``rolled_back`` must go through
        :meth:`promoted` and :meth:`rolled_back` so their gates and
        accountability columns are never bypassed.
        """
        if stage in {LearningStage.PROMOTED, LearningStage.ROLLED_BACK}:
            raise LearningStageTransitionError(
                "Promotion and rollback require an accountable human actor."
            )
        self.assert_bounded()
        assert_transition_allowed(self.stage, stage)
        _require_aware(occurred_at)
        return replace(
            self,
            stage=stage,
            canary_started_at=(
                occurred_at if stage is LearningStage.CANARY else self.canary_started_at
            ),
            version=resulting_version,
        )


def _require_aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CommandValidationError("The stage-change timestamp must be timezone-aware.")
    return value


__all__ = [
    "CANARY_PASS_RATE_THRESHOLD",
    "PROTECTED_SCOPES",
    "ROLLBACK_SOURCE_STAGES",
    "TARGET_SCOPE_KEY",
    "LearningCandidate",
    "LearningScope",
    "LearningStage",
    "LearningStageTransitionError",
    "ProtectedScopeViolationError",
    "RegressionGateNotMetError",
    "UnboundedLearningScopeError",
    "assert_transition_allowed",
    "parse_learning_scope",
    "parse_learning_stage",
]
