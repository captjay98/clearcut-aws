"""Application service for the organization's protected configuration bindings.

A protected configuration is the accountable binding between an organization and
the exact policy and prompt versions its detection, research, and rescan passes
run under. All three refuse to run unless the organization holds exactly one
active binding, which makes this surface the governing precondition for every
evidence-producing pass.

Reading is an ordinary organization-scoped query: any active member of the
authenticated organization may list the bindings, and the delivery boundary has
already proven that membership.

Drafting, validating, and activating are **governed mutations**, and all three are
Owner-only through the protected ``governance:manage`` capability. Protected
configuration is human-only: nothing here drafts, validates, activates, or repairs
a binding without an accountable human trigger, and no code path invents a binding
for an organization that has none.

Each governed command:

1. Loads the exact organization-scoped aggregate — the governance ledger for a
   draft, the target binding for a validation or activation — with typed
   not-found parity when it is not visible.
2. Derives capability from the server-provided role only, never from the client.
3. Runs the command's domain rule: a draft's candidate is validated at
   construction; a validation is refused on a binding that is already governing or
   already history; an activation is refused on a binding no human has validated.
4. Classifies the command through the shared governed-command kernel: an
   idempotent replay of a prior receipt returns the original result, a reused key
   carrying different intent is a typed conflict, and a lost lifecycle
   compare-and-swap is a typed conflict.
5. For a fresh command, performs the lifecycle write and appends the authoritative
   audit event — in the caller's single transaction, so a binding can never
   change without its attestation, and neither can exist without the other.

The transactional choreography is the shared
:func:`~clearcut.commanding.template.execute_governed_command`; this module supplies
only the configuration specifics (capability, lifecycle rules, the deterministic
validation, the writes, and the audit and projection shapes) as injected hooks.

Lifecycle as version
--------------------
``protected_configurations`` has no version column, and it does not need one: the
lifecycle *is* the aggregate's monotonic version. ``draft`` -> ``validated`` ->
``active`` -> ``superseded`` advances by exactly one per governed transition and
never runs backwards, so guarding each write on its expected source stage is a
real version-guarded compare-and-swap. The contract exposes no
``expectedVersion`` on these operations, so the expected version is derived
server-side from the stage the command actually loaded; concurrency is caught by
the compare-and-swap and, for activation, by the one-active-binding uniqueness
constraint.

Derived idempotency for validation and activation
-------------------------------------------------
The contract gives only ``draftProtectedConfiguration`` an ``Idempotency-Key``
header, because only drafting creates a new resource. Validation and activation
target an existing binding, so their keys are derived server-side from that
binding's identity — and, for validation, from the organization's active binding,
which is the one external input its verdict depends on. A repeated validation of
an unchanged binding in an unchanged context therefore replays its recorded
verdict instead of appending a second attestation, while a genuinely different
governing context is a fresh command.

No legal conclusion
-------------------
A binding records which policy and prompt an organization's evidence gathering ran
under. Activating one is not clearance, and validation establishes only that the
binding is complete, accountable, and not a no-op — never that its content is
legally sufficient.

Only typed results or typed governed-command errors cross this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import CommandForbiddenError, CommandValidationError
from clearcut.commanding.template import (
    GovernedCommandContext,
    execute_governed_command,
)
from clearcut.evaluation.domain.configuration import (
    ACTIVATABLE_LIFECYCLES,
    VALIDATABLE_LIFECYCLES,
    ActiveBindingState,
    ConfigurationCandidate,
    ConfigurationLifecycle,
    ConfigurationValidation,
    NoActiveBinding,
    ProtectedConfiguration,
    active_binding_token,
    candidate_intent_digest,
    evaluate_configuration,
    transition_intent_digest,
)
from clearcut.evaluation.ports.configuration_repository import (
    ConfigurationAuditEvent,
    OrganizationGovernanceScope,
    ProtectedConfigurationRepositoryPort,
)
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

# The governed operation names that scope receipts for these commands.
DRAFT_OPERATION = "governance.configuration.draft"
VALIDATE_OPERATION = "governance.configuration.validate"
ACTIVATE_OPERATION = "governance.configuration.activate"

# The authoritative audit actions. Each is also the receipt key its operation
# replays from, so the ledger and the idempotency guard cannot drift apart.
DRAFT_AUDIT_ACTION = "governance.configuration.drafted"
VALIDATE_AUDIT_ACTION = "governance.configuration.validated"
ACTIVATE_AUDIT_ACTION = "governance.configuration.activated"

AUDIT_TARGET_TYPE = "protected_configuration"

# Capability, derived from the server-provided role only. Protected configuration
# is a protected rule: the policy and prompt an organization's evidence gathering
# runs under is Owner-only, which is exactly what ``governance:manage`` grants and
# what no other role holds.
GOVERNANCE_CAPABILITY = "governance:manage"


@dataclass(frozen=True)
class DraftConfigurationCommand:
    """A validated request to draft one new protected configuration binding.

    ``org_id`` and ``actor_role`` are server-derived: the delivery boundary takes
    them from the authenticated request scope, never from the path or the body.
    """

    org_id: UUID
    actor_id: UUID
    actor_role: str
    candidate: ConfigurationCandidate
    idempotency_key: str


@dataclass(frozen=True)
class ValidateConfigurationCommand:
    """A validated request to run the deterministic validation on one binding."""

    org_id: UUID
    actor_id: UUID
    actor_role: str
    config_id: UUID


@dataclass(frozen=True)
class ActivateConfigurationCommand:
    """A validated request to make one validated binding the governing binding."""

    org_id: UUID
    actor_id: UUID
    actor_role: str
    config_id: UUID


@dataclass(frozen=True)
class ConfigurationValidationResult:
    """The outcome of a governed validation, as the contract reports it."""

    config_id: UUID
    validation: ConfigurationValidation

    @property
    def valid(self) -> bool:
        return self.validation.valid

    @property
    def issues(self) -> tuple[str, ...]:
        return self.validation.issues


@dataclass(frozen=True)
class ConfigurationActivationResult:
    """The identity and resulting lifecycle of a governed activation."""

    config_id: UUID
    lifecycle: ConfigurationLifecycle


class ProtectedConfigurationService:
    """Coordinates protected configuration reads and the three governed commands."""

    def __init__(self, repository: ProtectedConfigurationRepositoryPort) -> None:
        self._repository = repository

    async def list_configurations(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> tuple[ProtectedConfiguration, ...]:
        """Return the organization's bindings, newest first.

        Any active member may read. The organization is required to exist so an
        unknown tenant is a neutral typed not-found rather than an empty list that
        would read as "this organization has no governing policy".
        """
        await self._repository.require_organization_scope(session, org_id=org_id)
        return await self._repository.list_for_organization(session, org_id=org_id)

    async def draft(
        self,
        session: AsyncSession,
        command: DraftConfigurationCommand,
    ) -> ProtectedConfiguration:
        """Draft one new binding inside the caller's transaction.

        The draft is inert: it binds nothing and governs nothing until a human
        validates and activates it, so the organization's current active binding
        is untouched by this command.
        """
        intent_hash = candidate_intent_digest(
            org_id=command.org_id,
            operation=DRAFT_OPERATION,
            candidate=command.candidate,
        )
        envelope = _envelope(
            org_id=command.org_id,
            actor_id=command.actor_id,
            operation=DRAFT_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=intent_hash,
            # The governance ledger is append-only, so a draft has no prior stage
            # to be stale against.
            expected_version=OrganizationGovernanceScope(org_id=command.org_id).version,
        )

        # The draft row's identity and content are derived from the command context,
        # so the insert, the audit target, and the projection are built from one
        # function of one context rather than from shared mutable state.
        def build_draft(
            context: GovernedCommandContext[OrganizationGovernanceScope],
        ) -> ProtectedConfiguration:
            return ProtectedConfiguration(
                config_id=context.result_id,
                org_id=command.org_id,
                lifecycle=ConfigurationLifecycle.DRAFT,
                policy_version=command.candidate.policy_version,
                prompt_version=command.candidate.prompt_version,
                created_at=context.occurred_at,
                label=command.candidate.label,
                rationale=command.candidate.rationale,
                created_by=command.actor_id,
            )

        async def load_item(
            session: AsyncSession,
            _envelope: CommandEnvelope,
        ) -> OrganizationGovernanceScope:
            return await self._repository.require_organization_scope(
                session,
                org_id=command.org_id,
            )

        def check_capability() -> None:
            _require_governance(command.actor_role)

        def validate_domain(_scope: OrganizationGovernanceScope) -> None:
            # The candidate was validated at construction, where a blank or
            # over-long field became a typed error before any storage was touched.
            # Nothing about the organization's current state can invalidate a
            # draft: an inert candidate is always draftable, and whether it is fit
            # to govern is decided by the separate validation command.
            return None

        async def lookup_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
        ) -> PriorReceipt | None:
            return await self._repository.find_prior_receipt(
                session,
                envelope,
                action=DRAFT_AUDIT_ACTION,
            )

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[OrganizationGovernanceScope],
        ) -> None:
            await self._repository.insert_draft(session, configuration=build_draft(context))

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            _context: GovernedCommandContext[OrganizationGovernanceScope],
        ) -> PriorReceipt | None:
            # The accountable receipt for this organization-level command is the
            # authoritative audit row appended below in the same transaction. This
            # step is the concurrent-duplicate reconciliation the template expects:
            # if another writer already committed this exact key, return its
            # receipt so the loser replays instead of drafting twice.
            return await self._repository.find_prior_receipt(
                session,
                envelope,
                action=DRAFT_AUDIT_ACTION,
            )

        def build_audit(
            context: GovernedCommandContext[OrganizationGovernanceScope],
        ) -> ConfigurationAuditEvent:
            return ConfigurationAuditEvent(
                action=DRAFT_AUDIT_ACTION,
                target_type=AUDIT_TARGET_TYPE,
                target_id=context.result_id,
                payload=AuditPayload(
                    {
                        "orgId": str(command.org_id),
                        "configurationId": str(context.result_id),
                        "lifecycle": ConfigurationLifecycle.DRAFT.value,
                        "policyVersion": command.candidate.policy_version,
                        "promptVersion": command.candidate.prompt_version,
                        "label": command.candidate.label,
                        "rationale": command.candidate.rationale,
                        "detail": (
                            "drafted a candidate policy and prompt binding; "
                            "it governs nothing until it is validated and activated"
                        ),
                    }
                ),
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
                result_id=context.result_id,
            )

        async def append_audit(session, envelope, audit, correlation_id, occurred_at) -> None:
            await self._repository.append_audit_event(
                session,
                envelope,
                audit,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> ProtectedConfiguration:
            # The prior command's draft is already durable; the replay reports it
            # exactly as stored rather than re-deriving it from the request.
            return await self._repository.load_scoped(
                session,
                org_id=command.org_id,
                config_id=prior.item_id,
            )

        def project_result(
            context: GovernedCommandContext[OrganizationGovernanceScope],
        ) -> ProtectedConfiguration:
            return build_draft(context)

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda scope: scope.version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )

    async def validate(
        self,
        session: AsyncSession,
        command: ValidateConfigurationCommand,
    ) -> ConfigurationValidationResult:
        """Run the deterministic validation on one binding and record the verdict.

        A clean verdict advances the binding to ``validated``, which is the only
        stage activation accepts. A verdict with issues records them and holds the
        binding at ``draft``, so an unfit binding cannot become the governing
        binding on the strength of a stage it did not earn.
        """
        active = await self._repository.load_active_binding(session, org_id=command.org_id)
        target = await self._repository.load_scoped(
            session,
            org_id=command.org_id,
            config_id=command.config_id,
        )
        intent_hash = transition_intent_digest(
            operation=VALIDATE_OPERATION,
            configuration=target,
            active=active,
        )
        envelope = _envelope(
            org_id=command.org_id,
            actor_id=command.actor_id,
            operation=VALIDATE_OPERATION,
            idempotency_key=_derived_key("validate", command.config_id, active),
            intent_hash=intent_hash,
            expected_version=target.version,
        )
        verdict = evaluate_configuration(target, active=active)

        async def load_item(
            session: AsyncSession,
            _envelope: CommandEnvelope,
        ) -> ProtectedConfiguration:
            return await self._repository.load_scoped(
                session,
                org_id=command.org_id,
                config_id=command.config_id,
            )

        def check_capability() -> None:
            _require_governance(command.actor_role)

        def validate_domain(configuration: ProtectedConfiguration) -> None:
            if configuration.lifecycle not in VALIDATABLE_LIFECYCLES:
                # An active binding is already governing and a superseded one is
                # history. Re-validating either would either re-litigate a live
                # binding or rewrite the record a report may already cite.
                raise CommandValidationError(
                    "Only a draft or validated binding can be validated."
                )

        async def lookup_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
        ) -> PriorReceipt | None:
            return await self._repository.find_prior_receipt(
                session,
                envelope,
                action=VALIDATE_AUDIT_ACTION,
            )

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ProtectedConfiguration],
        ) -> None:
            await self._repository.commit_validation(
                session,
                org_id=command.org_id,
                config_id=command.config_id,
                actor_id=command.actor_id,
                issues=verdict.issues,
                occurred_at=context.occurred_at,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            _context: GovernedCommandContext[ProtectedConfiguration],
        ) -> PriorReceipt | None:
            return await self._repository.find_prior_receipt(
                session,
                envelope,
                action=VALIDATE_AUDIT_ACTION,
            )

        def build_audit(
            context: GovernedCommandContext[ProtectedConfiguration],
        ) -> ConfigurationAuditEvent:
            return ConfigurationAuditEvent(
                action=VALIDATE_AUDIT_ACTION,
                target_type=AUDIT_TARGET_TYPE,
                target_id=command.config_id,
                payload=AuditPayload(
                    {
                        "orgId": str(command.org_id),
                        "configurationId": str(command.config_id),
                        "valid": verdict.valid,
                        "issues": list(verdict.issues),
                        "lifecycle": (
                            ConfigurationLifecycle.VALIDATED.value
                            if verdict.valid
                            else ConfigurationLifecycle.DRAFT.value
                        ),
                        "detail": _validation_detail(verdict),
                    }
                ),
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
                result_id=context.result_id,
            )

        async def append_audit(session, envelope, audit, correlation_id, occurred_at) -> None:
            await self._repository.append_audit_event(
                session,
                envelope,
                audit,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            _prior: PriorReceipt,
        ) -> ConfigurationValidationResult:
            # The validation is a pure function of the binding and the active
            # binding, both of which the derived key pins. Recomputing it from the
            # stored row reproduces the recorded verdict exactly.
            stored = await self._repository.load_scoped(
                session,
                org_id=command.org_id,
                config_id=command.config_id,
            )
            replayed = await self._repository.load_active_binding(
                session,
                org_id=command.org_id,
            )
            return ConfigurationValidationResult(
                config_id=command.config_id,
                validation=evaluate_configuration(stored, active=replayed),
            )

        def project_result(
            _context: GovernedCommandContext[ProtectedConfiguration],
        ) -> ConfigurationValidationResult:
            return ConfigurationValidationResult(
                config_id=command.config_id,
                validation=verdict,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda configuration: configuration.version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )

    async def activate(
        self,
        session: AsyncSession,
        command: ActivateConfigurationCommand,
    ) -> ConfigurationActivationResult:
        """Make one validated binding the organization's governing binding.

        The incumbent active binding is superseded in the same transaction, which
        the one-active-binding uniqueness constraint requires and which keeps the
        organization's history intact: the superseded row still says exactly what
        it bound, so a report that cites it remains readable.
        """
        target = await self._repository.load_scoped(
            session,
            org_id=command.org_id,
            config_id=command.config_id,
        )
        envelope = _envelope(
            org_id=command.org_id,
            actor_id=command.actor_id,
            operation=ACTIVATE_OPERATION,
            idempotency_key=f"activate:{command.config_id}",
            # An activation's intent is the binding it makes governing, not the
            # binding it replaces, so the incumbent is deliberately absent here.
            intent_hash=transition_intent_digest(
                operation=ACTIVATE_OPERATION,
                configuration=target,
                active=_NO_ACTIVE_CONTEXT,
            ),
            expected_version=target.version,
        )

        async def load_item(
            session: AsyncSession,
            _envelope: CommandEnvelope,
        ) -> ProtectedConfiguration:
            return await self._repository.load_scoped(
                session,
                org_id=command.org_id,
                config_id=command.config_id,
            )

        def check_capability() -> None:
            _require_governance(command.actor_role)

        def validate_domain(configuration: ProtectedConfiguration) -> None:
            if configuration.lifecycle not in ACTIVATABLE_LIFECYCLES:
                # A draft has no recorded verdict, so activating it would make a
                # binding govern that no human found fit. A superseded binding is
                # history and is never resurrected. An already-active binding is
                # admitted here so a replayed activation is recognised as one; a
                # non-replay activation of it loses the lifecycle
                # compare-and-swap and surfaces as a typed stale-version conflict.
                raise CommandValidationError(
                    "A binding must be validated before it can be activated."
                )

        async def lookup_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
        ) -> PriorReceipt | None:
            return await self._repository.find_prior_receipt(
                session,
                envelope,
                action=ACTIVATE_AUDIT_ACTION,
            )

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ProtectedConfiguration],
        ) -> None:
            await self._repository.commit_activation(
                session,
                org_id=command.org_id,
                config_id=command.config_id,
                actor_id=command.actor_id,
                occurred_at=context.occurred_at,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            _context: GovernedCommandContext[ProtectedConfiguration],
        ) -> PriorReceipt | None:
            return await self._repository.find_prior_receipt(
                session,
                envelope,
                action=ACTIVATE_AUDIT_ACTION,
            )

        def build_audit(
            context: GovernedCommandContext[ProtectedConfiguration],
        ) -> ConfigurationAuditEvent:
            return ConfigurationAuditEvent(
                action=ACTIVATE_AUDIT_ACTION,
                target_type=AUDIT_TARGET_TYPE,
                target_id=command.config_id,
                payload=AuditPayload(
                    {
                        "orgId": str(command.org_id),
                        "configurationId": str(command.config_id),
                        "lifecycle": ConfigurationLifecycle.ACTIVE.value,
                        "policyVersion": context.item.policy_version,
                        "promptVersion": context.item.prompt_version,
                        "detail": (
                            "activated this policy and prompt binding and superseded "
                            "the previous one; the organization's passes now run under it"
                        ),
                    }
                ),
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
                result_id=context.result_id,
            )

        async def append_audit(session, envelope, audit, correlation_id, occurred_at) -> None:
            await self._repository.append_audit_event(
                session,
                envelope,
                audit,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            _prior: PriorReceipt,
        ) -> ConfigurationActivationResult:
            stored = await self._repository.load_scoped(
                session,
                org_id=command.org_id,
                config_id=command.config_id,
            )
            return ConfigurationActivationResult(
                config_id=command.config_id,
                lifecycle=stored.lifecycle,
            )

        def project_result(
            _context: GovernedCommandContext[ProtectedConfiguration],
        ) -> ConfigurationActivationResult:
            return ConfigurationActivationResult(
                config_id=command.config_id,
                lifecycle=ConfigurationLifecycle.ACTIVE,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda configuration: configuration.version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )


# An activation's intent deliberately excludes the incumbent binding: what the
# command means is "make this binding govern", which does not change with whatever
# it happens to replace. The reserved no-context token stands in for that.
_NO_ACTIVE_CONTEXT: ActiveBindingState = NoActiveBinding()


def _require_governance(actor_role: str) -> None:
    """Refuse a governed configuration command to any role but Owner."""
    if not has_capability(actor_role, GOVERNANCE_CAPABILITY):
        raise CommandForbiddenError()


def _envelope(
    *,
    org_id: UUID,
    actor_id: UUID,
    operation: str,
    idempotency_key: str,
    intent_hash: str,
    expected_version: int,
) -> CommandEnvelope:
    """Build the typed kernel envelope for an organization-owned command.

    Constructed before any write, so a malformed key, digest, or version is a
    typed validation error while storage is still untouched. The kernel envelope
    carries a project field an organization-owned command has no value for; the
    organization stands in, and it is never written to any project column — the
    authoritative audit row this command appends has a null ``project_id``.
    """
    return CommandEnvelope(
        org_id=org_id,
        project_id=org_id,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
        intent_hash=intent_hash,
        expected_version=expected_version,
    )


def _derived_key(prefix: str, config_id: UUID, active: ActiveBindingState) -> str:
    """Derive the server-side idempotency key for a validation command.

    The contract gives validation no ``Idempotency-Key`` header because it targets
    an existing binding rather than creating one. The key is therefore derived
    from the binding's identity and the organization's active binding: a repeated
    validation in an unchanged context replays its recorded verdict, while a
    changed governing context is a fresh command rather than a replay of a verdict
    that no longer applies.
    """
    return f"{prefix}:{config_id}:{active_binding_token(active)}"


def _validation_detail(verdict: ConfigurationValidation) -> str:
    """Render the verdict the way every other audit detail reads."""
    if verdict.valid:
        return "validated the candidate binding; it is eligible for activation"
    return f"found {len(verdict.issues)} issue(s); the binding remains a draft"


__all__ = [
    "ACTIVATE_AUDIT_ACTION",
    "ACTIVATE_OPERATION",
    "AUDIT_TARGET_TYPE",
    "DRAFT_AUDIT_ACTION",
    "DRAFT_OPERATION",
    "GOVERNANCE_CAPABILITY",
    "VALIDATE_AUDIT_ACTION",
    "VALIDATE_OPERATION",
    "ActivateConfigurationCommand",
    "ConfigurationActivationResult",
    "ConfigurationValidationResult",
    "DraftConfigurationCommand",
    "ProtectedConfigurationService",
    "ValidateConfigurationCommand",
]
