"""Typed persistence port for organization-scoped settings reads and writes.

Organization settings are *organization-owned* configuration: the authenticated
``org_id`` is the whole tenant key, there is no project path scope, and nothing
here is global. The port is the single boundary the settings application service
uses to load the current settings, advance them under an optimistic-concurrency
compare-and-swap, resolve a prior governed-command receipt, and append the
authoritative audit event.

Every value that crosses the boundary is a typed dataclass, a typed enum, or a
typed error from the governed-command kernel. An organization that is not
visible in the authenticated scope surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError`; a lost
compare-and-swap surfaces as a typed
:class:`~clearcut.commanding.errors.StaleVersionConflictError`. No booleans,
raw rows, or raw dicts encode outcomes.

Implementations run every statement inside the caller's unit of work, so the
settings write, the accountable command receipt, and the authoritative audit
event commit or roll back atomically.

Two deliberate absences
-----------------------
* **No slug write.** ``slug`` is the organization's URL identity. It is read and
  returned, never accepted as input, because changing it would silently break
  every link already handed out.
* **No evidence-retention duration.** Evidence is kept until its project is
  deleted. A retention-duration field would only let a surface print a promise
  the product does not make, so no column, field, or method exists for one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from clearcut.commanding.domain import CommandEnvelope, PriorReceipt
from clearcut.commanding.template import GovernedAudit
from sqlalchemy.ext.asyncio import AsyncSession


class MonitoringCadence(StrEnum):
    """The canonical stored monitoring-cadence vocabulary.

    These four tokens are exactly the values the database check constraint
    admits. They are what is stored and what the contract transports; they are
    never what a human reads. :func:`cadence_label` is the single exit for that.
    """

    OFF = "off"
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"


# The one display vocabulary for a stored cadence token. It lives beside the
# enum so a stored value and its rendering cannot drift apart, and so an audit
# entry can speak the same words a surface does rather than leaking the token.
CADENCE_LABELS: Mapping[MonitoringCadence, str] = {
    MonitoringCadence.OFF: "Off",
    MonitoringCadence.MANUAL: "Manual only",
    MonitoringCadence.DAILY: "Daily",
    MonitoringCadence.WEEKLY: "Weekly",
}


def cadence_label(value: MonitoringCadence) -> str:
    """Return the human-readable label for a stored cadence token."""
    return CADENCE_LABELS[value]


@dataclass(frozen=True)
class OrganizationSettings:
    """The organization-owned settings record, as stored.

    ``version`` is the optimistic-concurrency version that guards every write.
    ``slug`` is present because the contract returns it, not because it can be
    written.
    """

    org_id: UUID
    name: str
    slug: str
    jurisdiction: str | None
    default_monitoring_cadence: MonitoringCadence
    version: int


@dataclass(frozen=True)
class OrganizationAuditEvent(GovernedAudit):
    """One authoritative, organization-scoped audit event to append.

    Extends the kernel's :class:`~clearcut.commanding.template.GovernedAudit` so
    the governed-command template's audit seam stays exactly typed, and adds the
    command-identity fields this operation's receipt is replayed from.

    The inherited ``payload`` carries the domain detail (which fields changed and
    their humanized before/after values) through the typed
    :class:`~clearcut.commanding.domain.AuditPayload` seam, so
    ``payload_redacted`` can never receive string-interpolated caller input.
    """

    expected_version: int
    resulting_version: int
    result_id: UUID


class OrganizationSettingsRepositoryPort(Protocol):
    """Session-bound persistence operations for organization settings."""

    async def load_settings(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> OrganizationSettings:
        """Load the settings for the exact authenticated organization.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        organization is not visible, so an absent and a foreign organization
        present the same neutral shape.
        """
        ...

    async def update_settings(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        name: str,
        jurisdiction: str | None,
        default_monitoring_cadence: MonitoringCadence,
        expected_version: int,
        resulting_version: int,
    ) -> None:
        """Advance the settings under a version-guarded compare-and-swap.

        The update matches on ``(id, version)``, so a row that moved between load
        and write affects zero rows. That miss is classified by scoped existence:
        a still-present organization raises
        :class:`~clearcut.commanding.errors.StaleVersionConflictError` and an
        absent one raises
        :class:`~clearcut.commanding.errors.CommandNotFoundError`. ``slug`` is
        never in the SET list.
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
        ``(org_id, actor_id, action, idempotency_key)``. ``None`` is a documented
        optional meaning "no prior command", matching the kernel's own lookup
        contract.
        """
        ...

    async def append_audit_event(
        self,
        session: AsyncSession,
        envelope: CommandEnvelope,
        event: OrganizationAuditEvent,
        *,
        correlation_id: UUID,
        occurred_at: datetime,
    ) -> None:
        """Append the authoritative organization-scoped audit event.

        The row is organization-owned: its ``project_id`` is null, because this
        governed change belongs to no project. It runs inside the caller's
        transaction, so it commits with the settings write or not at all.
        """
        ...


__all__ = [
    "CADENCE_LABELS",
    "MonitoringCadence",
    "OrganizationAuditEvent",
    "OrganizationSettings",
    "OrganizationSettingsRepositoryPort",
    "cadence_label",
]
