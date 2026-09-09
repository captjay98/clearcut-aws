"""Typed persistence port for the governed protected-configuration surface.

A protected configuration is *organization-owned* governance: the authenticated
``org_id`` is the whole tenant key, there is no project path scope, and nothing
here is global. This port is the single boundary the protected-configuration
application service uses to prove the organization exists, read its bindings,
transition one binding's lifecycle under a compare-and-swap, resolve a prior
governed-command receipt, and append the authoritative audit event.

Every value crossing the boundary is a typed dataclass, a typed enum, or a typed
error from the governed-command kernel. A binding that is not visible in the
authenticated organization scope surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError`, never a raw ``None``;
a lost lifecycle compare-and-swap surfaces as a typed
:class:`~clearcut.commanding.errors.StaleVersionConflictError`; the absence of an
active binding is the explicit
:class:`~clearcut.evaluation.domain.configuration.NoActiveBinding` value. No
method returns a bare boolean or a raw row.

Implementations run every statement inside the caller's unit of work, so the
lifecycle write and the authoritative audit event that attests to it commit or
roll back atomically.

Two deliberate absences
-----------------------
* **No content update.** A persisted binding's policy version, prompt version,
  label, and rationale are never rewritten. Changing what an organization runs
  under means drafting a new binding and activating it, which leaves the previous
  binding intact as superseded history. A report that cites a binding must still
  be able to read exactly what that binding said.
* **No delete.** Bindings are the provenance for every evidence pass an
  organization has run. They are superseded, never removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from clearcut.commanding.domain import CommandEnvelope, PriorReceipt
from clearcut.commanding.template import GovernedAudit
from clearcut.evaluation.domain.configuration import (
    ActiveBindingState,
    ProtectedConfiguration,
)
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class OrganizationGovernanceScope:
    """Proof that an organization exists and its governance ledger is readable.

    Drafting a binding creates a new aggregate, so there is no prior row to load.
    This is what the drafting command loads instead: it establishes tenant
    existence before any write, so a draft against an absent organization is a
    neutral typed not-found rather than a foreign-key failure surfacing from
    storage.

    ``version`` is the governance ledger's version. The ledger is append-only — a
    new draft invalidates nothing that already exists — so it is constant, and
    drafting carries no optimistic-concurrency guard. Concurrency on the binding
    that actually governs is enforced at activation, by the lifecycle
    compare-and-swap and the one-active-binding uniqueness constraint.
    """

    org_id: UUID
    version: int = 1


@dataclass(frozen=True)
class ConfigurationAuditEvent(GovernedAudit):
    """One authoritative, organization-scoped audit event to append.

    Extends the kernel's :class:`~clearcut.commanding.template.GovernedAudit` so
    the governed-command template's audit seam stays exactly typed, and adds the
    command-identity fields this operation's receipt is replayed from.

    The inherited ``payload`` carries the governance detail through the typed
    :class:`~clearcut.commanding.domain.AuditPayload` seam, so
    ``payload_redacted`` can never receive string-interpolated caller input.
    """

    expected_version: int
    resulting_version: int
    result_id: UUID


class ProtectedConfigurationRepositoryPort(Protocol):
    """Session-bound persistence operations for protected configuration bindings."""

    async def require_organization_scope(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> OrganizationGovernanceScope:
        """Load proof that the organization exists.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        organization is absent, with the same neutral shape a foreign
        organization produces.
        """
        ...

    async def list_for_organization(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> tuple[ProtectedConfiguration, ...]:
        """Return every binding in the organization's scope, newest first."""
        ...

    async def load_scoped(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        config_id: UUID,
    ) -> ProtectedConfiguration:
        """Load one binding within the exact organization scope.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        binding is absent or belongs to another organization, presenting the same
        neutral shape either way so a caller cannot probe another tenant.
        """
        ...

    async def load_active_binding(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> ActiveBindingState:
        """Return the organization's active binding, or explicit typed absence.

        Absence is :class:`~clearcut.evaluation.domain.configuration.NoActiveBinding`,
        so a caller cannot mistake an ungoverned organization for one whose
        binding was simply not checked.
        """
        ...

    async def insert_draft(
        self,
        session: AsyncSession,
        *,
        configuration: ProtectedConfiguration,
    ) -> None:
        """Insert a new draft binding in the caller's transaction.

        A draft is inert: it binds nothing until a human validates and activates
        it, so it records no activator and no validator. Raises
        :class:`~clearcut.commanding.errors.StaleVersionConflictError` when a
        concurrent writer already committed this exact draft identity, following
        the governed-command template's documented re-read contract so the losing
        race replays the original result instead of surfacing an integrity error.
        """
        ...

    async def seed_default_binding(
        self,
        session: AsyncSession,
        *,
        configuration: ProtectedConfiguration,
    ) -> None:
        """Insert the default active binding an organization is created with.

        This is not a governed transition and it supersedes nothing, because at
        the moment it runs the organization has no binding to supersede. It exists
        because detection, research, and rescan all refuse to run without exactly
        one active binding, so an organization created without one could never
        complete a first pass.

        It must be called inside the same transaction that creates the
        organization and its owner membership, so an organization can never be
        committed without the binding that governs it. The configuration must be
        active and must name who activated it and when; anything else is a typed
        :class:`~clearcut.commanding.errors.CommandValidationError`. Nothing else
        in the system may create an active binding this way: every later change is
        a governed, Owner-triggered draft/validate/activate sequence.
        """
        ...

    async def commit_validation(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        config_id: UUID,
        actor_id: UUID,
        issues: tuple[str, ...],
        occurred_at: datetime,
    ) -> None:
        """Record a validation outcome against the binding.

        A clean validation advances the binding to ``validated`` and records who
        validated it and when. A validation that found issues persists those
        issues and holds the binding at ``draft``, so an unfit binding can never
        reach activation on the strength of a verdict it did not earn.

        The write is a lifecycle-guarded compare-and-swap. On a miss it raises
        :class:`~clearcut.commanding.errors.StaleVersionConflictError` when the
        binding is still in scope (its lifecycle advanced concurrently) and
        :class:`~clearcut.commanding.errors.CommandNotFoundError` when it is
        absent or foreign.
        """
        ...

    async def commit_activation(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        config_id: UUID,
        actor_id: UUID,
        occurred_at: datetime,
    ) -> None:
        """Supersede the current active binding and activate the target.

        Both statements run in the caller's single transaction, in that order,
        because the organization may hold at most one active binding: superseding
        the incumbent first is what keeps the activation from colliding with that
        uniqueness constraint. The activation is a lifecycle-guarded
        compare-and-swap from ``validated`` and records the accountable actor and
        instant, satisfying the accountability constraint an active row carries.

        On a compare-and-swap miss it raises
        :class:`~clearcut.commanding.errors.StaleVersionConflictError` when the
        binding is still in scope and
        :class:`~clearcut.commanding.errors.CommandNotFoundError` when it is
        absent or foreign.
        """
        ...

    async def find_prior_receipt(
        self,
        session: AsyncSession,
        envelope: CommandEnvelope,
        *,
        action: str,
    ) -> PriorReceipt | None:
        """Return the prior receipt for this exact organization command, or ``None``.

        Scope is the organization-level accountability key
        ``(org_id, actor_id, action, operation, idempotency_key)``. ``None`` is a
        documented optional meaning "no prior command", matching the kernel's own
        lookup contract.
        """
        ...

    async def append_audit_event(
        self,
        session: AsyncSession,
        envelope: CommandEnvelope,
        event: ConfigurationAuditEvent,
        *,
        correlation_id: UUID,
        occurred_at: datetime,
    ) -> None:
        """Append the authoritative organization-scoped audit event.

        The row is organization-owned: its ``project_id`` is null, because a
        binding governs the whole organization and belongs to no project. It runs
        inside the caller's transaction, so it commits with the lifecycle write or
        not at all.
        """
        ...


__all__ = [
    "ConfigurationAuditEvent",
    "OrganizationGovernanceScope",
    "ProtectedConfigurationRepositoryPort",
]
