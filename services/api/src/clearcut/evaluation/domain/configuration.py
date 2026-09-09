"""Domain model for an organization's protected configuration binding.

A protected configuration is the accountable binding between an organization and
the exact policy and prompt versions its detection, research, and rescan passes
run under. Detection, research, and selective rescan all refuse to run unless
exactly one binding per organization is ``active``, so this aggregate is the
governing precondition for every evidence-producing pass.

The binding is human-only and Owner-governed: nothing in this module activates,
edits, or repairs a binding on its own. It is a pure, storage-agnostic model of

* the closed lifecycle vocabulary (``draft`` -> ``validated`` -> ``active`` ->
  ``superseded``) and the monotonic aggregate version each stage represents,
* the fail-closed candidate value object a human drafts,
* the deterministic validation the Owner runs before activation, and
* the deterministic intent digest and correlation identity that make a governed
  draft replay-safe.

Every value crossing this module's boundary is a typed dataclass, a typed enum,
or a typed :class:`~clearcut.commanding.errors.CommandValidationError`. Absence
of an active binding is the explicit :class:`NoActiveBinding` value, never
``None``; validation returns :class:`ConfigurationValidation`, never a bare
boolean.

Nothing here asserts a legal conclusion. A binding records which policy and
prompt an organization's evidence gathering ran under; it is not clearance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from clearcut.commanding.errors import CommandValidationError

# Column widths the storage schema enforces. Validating against them here keeps
# an over-long candidate a typed domain error rather than a database failure.
POLICY_VERSION_MAX_LENGTH = 50
PROMPT_VERSION_MAX_LENGTH = 50
LABEL_MAX_LENGTH = 200

# The binding seeded when an organization is created, so a fresh organization can
# run its first detection pass under an accountable, named policy and prompt.
# The values match the versions the detection and research readers already
# expect, so the seeded binding governs a real pass rather than a placeholder.
DEFAULT_POLICY_VERSION = "policy-v1"
DEFAULT_PROMPT_VERSION = "prompt-v1"
DEFAULT_CONFIGURATION_LABEL = "Default protected configuration binding"
DEFAULT_CONFIGURATION_RATIONALE = (
    "Seeded when the organization was created so detection, research, and rescan "
    "have exactly one accountable active policy and prompt binding from the first "
    "pass. Replace it by drafting, validating, and activating a new binding."
)


class ConfigurationLifecycle(StrEnum):
    """The closed lifecycle vocabulary the database check constraint enforces."""

    DRAFT = "draft"
    VALIDATED = "validated"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


# The aggregate's optimistic-concurrency version is its lifecycle stage: each
# governed transition advances it by exactly one, and the transitions are
# one-way. This makes the lifecycle compare-and-swap in storage a real
# version-guarded write without adding a column the schema does not have.
_LIFECYCLE_VERSIONS: dict[ConfigurationLifecycle, int] = {
    ConfigurationLifecycle.DRAFT: 1,
    ConfigurationLifecycle.VALIDATED: 2,
    ConfigurationLifecycle.ACTIVE: 3,
    ConfigurationLifecycle.SUPERSEDED: 4,
}

# Stages from which a human may still run validation. An active binding is
# already governing and a superseded one is history; neither is re-validated.
VALIDATABLE_LIFECYCLES: frozenset[ConfigurationLifecycle] = frozenset(
    {ConfigurationLifecycle.DRAFT, ConfigurationLifecycle.VALIDATED}
)

# Stages an activation command accepts. ``ACTIVE`` is included so a replayed
# activation of the already-active binding is an idempotent replay rather than a
# rejected command; a draft must be validated first, and a superseded binding is
# never resurrected.
ACTIVATABLE_LIFECYCLES: frozenset[ConfigurationLifecycle] = frozenset(
    {ConfigurationLifecycle.VALIDATED, ConfigurationLifecycle.ACTIVE}
)


def lifecycle_version(lifecycle: ConfigurationLifecycle) -> int:
    """Return the monotonic aggregate version for a lifecycle stage."""
    return _LIFECYCLE_VERSIONS[lifecycle]


def parse_lifecycle(value: str) -> ConfigurationLifecycle:
    """Parse a stored lifecycle value, failing closed on an unknown stage.

    A row whose lifecycle is outside the closed vocabulary cannot be reasoned
    about, so it is a typed validation error rather than a silently coerced
    default.
    """
    try:
        return ConfigurationLifecycle(value)
    except ValueError as error:
        raise CommandValidationError(
            "The stored configuration lifecycle is outside the supported vocabulary."
        ) from error


@dataclass(frozen=True)
class ConfigurationCandidate:
    """A human-authored candidate binding, validated at construction.

    Construction is fail-closed: a blank or over-long field is a typed
    :class:`~clearcut.commanding.errors.CommandValidationError` before the value
    object exists, so no downstream caller has to re-check it. Error messages
    never echo the offending value back.
    """

    policy_version: str
    prompt_version: str
    rationale: str
    label: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.policy_version, "policy version")
        _require_text(self.prompt_version, "prompt version")
        _require_text(self.rationale, "rationale")
        if len(self.policy_version) > POLICY_VERSION_MAX_LENGTH:
            raise CommandValidationError("The policy version is too long.")
        if len(self.prompt_version) > PROMPT_VERSION_MAX_LENGTH:
            raise CommandValidationError("The prompt version is too long.")
        if self.label is not None:
            _require_text(self.label, "label")
            if len(self.label) > LABEL_MAX_LENGTH:
                raise CommandValidationError("The label is too long.")


@dataclass(frozen=True)
class ProtectedConfiguration:
    """A persisted protected configuration binding in one organization's scope.

    This is the full projection the governance surface reads: the lifecycle
    stage, the bound policy and prompt versions, the human rationale, the
    recorded validation issues, and the accountability trail for each governed
    transition.
    """

    config_id: UUID
    org_id: UUID
    lifecycle: ConfigurationLifecycle
    policy_version: str
    prompt_version: str
    created_at: datetime
    label: str | None = None
    rationale: str | None = None
    validation_issues: tuple[str, ...] = ()
    activated_by: UUID | None = None
    activated_at: datetime | None = None
    validated_by: UUID | None = None
    validated_at: datetime | None = None
    superseded_at: datetime | None = None
    superseded_by: UUID | None = None
    created_by: UUID | None = None

    @property
    def version(self) -> int:
        """The aggregate's monotonic version, derived from its lifecycle stage."""
        return lifecycle_version(self.lifecycle)

    @property
    def binding(self) -> ConfigurationBinding:
        """The policy-and-prompt pair this row binds."""
        return ConfigurationBinding(
            policy_version=self.policy_version,
            prompt_version=self.prompt_version,
        )


@dataclass(frozen=True)
class ConfigurationBinding:
    """The policy-and-prompt pair an organization's passes run under."""

    policy_version: str
    prompt_version: str


@dataclass(frozen=True)
class NoActiveBinding:
    """Explicit typed absence of an active binding for an organization.

    Returned instead of ``None`` so a caller cannot mistake "no governing policy"
    for "not checked". A caller that receives this value must treat the
    organization as ungoverned, never substitute a default.
    """


type ActiveBindingState = ConfigurationBinding | NoActiveBinding


@dataclass(frozen=True)
class ConfigurationValidation:
    """The deterministic result of validating a candidate binding.

    ``issues`` is the ordered, human-readable list of reasons the candidate is
    not fit to activate. ``valid`` is derived from it rather than stored, so the
    two can never disagree.
    """

    issues: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.issues


def evaluate_configuration(
    configuration: ProtectedConfiguration,
    *,
    active: ActiveBindingState,
) -> ConfigurationValidation:
    """Validate a candidate binding deterministically.

    The checks are pure functions of the candidate row and the organization's
    current active binding, so re-running validation on unchanged inputs always
    produces the identical issue list. No check consults a provider, and none
    produces a legal conclusion: they establish only that the candidate is a
    complete, accountable, non-redundant binding a human may activate.
    """
    issues: list[str] = []

    if not configuration.policy_version.strip():
        issues.append("The binding must name a policy version.")
    elif len(configuration.policy_version) > POLICY_VERSION_MAX_LENGTH:
        issues.append("The policy version is longer than the governed limit.")

    if not configuration.prompt_version.strip():
        issues.append("The binding must name a prompt version.")
    elif len(configuration.prompt_version) > PROMPT_VERSION_MAX_LENGTH:
        issues.append("The prompt version is longer than the governed limit.")

    if configuration.rationale is None or not configuration.rationale.strip():
        issues.append("The binding must record the rationale for the change.")

    if configuration.label is not None and len(configuration.label) > LABEL_MAX_LENGTH:
        issues.append("The label is longer than the governed limit.")

    if isinstance(active, ConfigurationBinding) and active == configuration.binding:
        issues.append(
            "The candidate binds the same policy and prompt versions as the active "
            "binding, so activating it would change nothing."
        )

    return ConfigurationValidation(issues=tuple(issues))


def default_active_configuration(
    *,
    config_id: UUID,
    org_id: UUID,
    owner_user_id: UUID,
    created_at: datetime,
) -> ProtectedConfiguration:
    """Build the default active binding seeded when an organization is created.

    Detection, research, and rescan all refuse to run unless the organization has
    exactly one active binding, so an organization created without one can never
    complete a first pass. This is that binding: named, accountable to the owner
    who created the organization, and active from the same instant.

    ``activated_by`` and ``activated_at`` are both set because an active row is
    accountable — the database check constraint requires them — and because the
    human who created the organization is the accountable trigger for the binding
    their organization starts under. It is a real, replaceable binding, not a
    placeholder: an Owner supersedes it by drafting, validating, and activating a
    new one.
    """
    return ProtectedConfiguration(
        config_id=config_id,
        org_id=org_id,
        lifecycle=ConfigurationLifecycle.ACTIVE,
        policy_version=DEFAULT_POLICY_VERSION,
        prompt_version=DEFAULT_PROMPT_VERSION,
        created_at=created_at,
        label=DEFAULT_CONFIGURATION_LABEL,
        rationale=DEFAULT_CONFIGURATION_RATIONALE,
        validation_issues=(),
        activated_by=owner_user_id,
        activated_at=created_at,
        validated_by=owner_user_id,
        validated_at=created_at,
        created_by=owner_user_id,
    )


def candidate_intent_digest(
    *,
    org_id: UUID,
    operation: str,
    candidate: ConfigurationCandidate,
) -> str:
    """Return the 64-character intent digest for a drafting command.

    The digest covers the accountable scope, the operation, and every field of
    the candidate binding. Two drafts that request the identical binding produce
    the identical digest, so a retry replays; a reused idempotency key carrying a
    different binding produces a different digest, so it is a typed conflict.
    """
    return _digest(
        [
            operation,
            str(org_id),
            candidate.policy_version,
            candidate.prompt_version,
            candidate.rationale,
            candidate.label or "",
        ]
    )


def transition_intent_digest(
    *,
    operation: str,
    configuration: ProtectedConfiguration,
    active: ActiveBindingState,
) -> str:
    """Return the 64-character intent digest for a validate/activate command.

    A validation or activation carries no client-authored body: its intent is the
    identity and bound content of the target row, plus the organization's active
    binding, which is the one external input the deterministic validation
    consults. A persisted binding's content is immutable, so the digest is stable
    across retries — which is what makes a repeated validation or activation an
    idempotent replay rather than a second governed write — while a genuinely
    different governing context produces a different intent.
    """
    return _digest(
        [
            operation,
            str(configuration.org_id),
            str(configuration.config_id),
            configuration.policy_version,
            configuration.prompt_version,
            active_binding_token(active),
        ]
    )


def active_binding_token(active: ActiveBindingState) -> str:
    """Return a stable, unambiguous token for the organization's active binding.

    Used in a derived idempotency key so that a validation re-run against a
    genuinely different governing context is a fresh governed command rather than
    a replay of a verdict that no longer applies. Typed absence has its own
    reserved token, so "no active binding" can never collide with a binding whose
    versions happen to be empty strings.
    """
    if isinstance(active, NoActiveBinding):
        return "none"
    return _digest([active.policy_version, active.prompt_version])


def parse_validation_issues(raw: object) -> tuple[str, ...]:
    """Normalise a stored ``validation_issues`` value into a typed tuple.

    The column is JSON, which different dialects hand back as a decoded list or
    as an encoded string. Anything that is not a list of strings is treated as no
    recorded issues rather than being propagated as an untyped value: a
    malformed cache of a deterministic computation must never be mistaken for a
    validation verdict.
    """
    if raw is None:
        return ()
    decoded: object = raw
    if isinstance(raw, (str, bytes)):
        try:
            decoded = json.loads(raw)
        except (ValueError, TypeError):
            return ()
    if not isinstance(decoded, list):
        return ()
    return tuple(str(issue) for issue in decoded if isinstance(issue, str))


def _digest(parts: list[str]) -> str:
    """Return a lowercase 64-hex digest over unambiguously joined parts.

    Parts are length-prefixed before hashing so no combination of field values
    can collide with a different combination through delimiter injection.
    """
    payload = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CommandValidationError(f"The {field} must be a non-empty value.")


__all__ = [
    "ACTIVATABLE_LIFECYCLES",
    "DEFAULT_CONFIGURATION_LABEL",
    "DEFAULT_CONFIGURATION_RATIONALE",
    "DEFAULT_POLICY_VERSION",
    "DEFAULT_PROMPT_VERSION",
    "LABEL_MAX_LENGTH",
    "POLICY_VERSION_MAX_LENGTH",
    "PROMPT_VERSION_MAX_LENGTH",
    "VALIDATABLE_LIFECYCLES",
    "ActiveBindingState",
    "ConfigurationBinding",
    "ConfigurationCandidate",
    "ConfigurationLifecycle",
    "ConfigurationValidation",
    "NoActiveBinding",
    "ProtectedConfiguration",
    "active_binding_token",
    "candidate_intent_digest",
    "default_active_configuration",
    "evaluate_configuration",
    "lifecycle_version",
    "parse_lifecycle",
    "parse_validation_issues",
    "transition_intent_digest",
]
