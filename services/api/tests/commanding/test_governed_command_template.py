"""Focused unit tests for the reusable governed-command template.

These tests exercise the shared choreography in isolation with in-memory fakes,
independent of any database, so the template's safety invariants are proven once
here and reused by every governed feature (evidence decisions, dispositions, and
future referrals/comments):

* the fixed pre-classification order load -> capability -> domain-validation;
* the same-key replay short-circuit that projects the prior identity and never
  writes, mints ids, or audits;
* the reconcile-and-rollback-and-replay race branch, including the P3 intent-hash
  tie assertion and that no audit is appended on that path;
* the fresh-command happy path that writes, persists the receipt, audits, and
  projects the fresh identity;
* that an audit failure propagates so the caller's transaction rolls the whole
  command back.

Behavioral, database-backed coverage of the two decision services lives in the
``tests/decisions`` suites; this module pins the extracted template contract the
services now delegate to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandNotFoundError,
    CommandValidationError,
    IdempotencyIntentConflictError,
    StaleVersionConflictError,
)
from clearcut.commanding.template import (
    GovernedAudit,
    GovernedCommandContext,
    execute_governed_command,
)

_VALID_INTENT_HASH = "a" * 64


def _envelope(
    *, intent_hash: str = _VALID_INTENT_HASH, expected_version: int = 1
) -> CommandEnvelope:
    return CommandEnvelope(
        org_id=uuid4(),
        project_id=uuid4(),
        actor_id=uuid4(),
        operation="decision.evidence.record",
        idempotency_key="idem-key-000001",
        intent_hash=intent_hash,
        expected_version=expected_version,
    )


@dataclass
class _FakeItem:
    version: int = 1
    state: str = "in_review"


@dataclass
class _FakeResult:
    result_id: UUID
    resulting_version: int
    projected_state: str
    kind: str  # "replay" or "fresh"


@dataclass
class _FakeSession:
    """Records the ordered side effects the template drives on a session."""

    calls: list[str] = field(default_factory=list)
    rolled_back: bool = False

    async def rollback(self) -> None:
        self.rolled_back = True
        self.calls.append("rollback")


@dataclass
class _Recorder:
    """Captures the injected-hook invocation order and their arguments."""

    events: list[str] = field(default_factory=list)


def _hooks(
    *,
    session: _FakeSession,
    item: _FakeItem,
    recorder: _Recorder,
    prior: PriorReceipt | None = None,
    receipt_race: PriorReceipt | None = None,
    capability_error: Exception | None = None,
    domain_error: Exception | None = None,
    load_error: Exception | None = None,
    audit_error: Exception | None = None,
):
    async def load_item(_session, _envelope):
        recorder.events.append("load")
        if load_error is not None:
            raise load_error
        return item

    def check_capability() -> None:
        recorder.events.append("capability")
        if capability_error is not None:
            raise capability_error

    def validate_domain(_item) -> None:
        recorder.events.append("validate")
        if domain_error is not None:
            raise domain_error

    def current_version(loaded: _FakeItem) -> int:
        return loaded.version

    async def lookup_receipt(_session, _envelope):
        recorder.events.append("lookup")
        return prior

    async def commit_provisional(_session, _context) -> None:
        recorder.events.append("commit")
        session.calls.append("commit")

    async def persist_receipt(_session, _envelope, _context):
        recorder.events.append("persist")
        session.calls.append("persist")
        return receipt_race

    def build_audit(context: GovernedCommandContext[_FakeItem]) -> GovernedAudit:
        recorder.events.append("build_audit")
        return GovernedAudit(
            action="decision.evidence.recorded",
            target_type="clearance_item",
            target_id=context.envelope.project_id,
            payload=AuditPayload({"resultingVersion": context.resulting_version}),
        )

    async def append_audit(_session, _envelope, _audit, _correlation_id, _occurred_at) -> None:
        recorder.events.append("append_audit")
        session.calls.append("append_audit")
        if audit_error is not None:
            raise audit_error

    async def load_replay_result(
        _session, _envelope, receipt: PriorReceipt
    ) -> _FakeResult:
        recorder.events.append("load_replay")
        return _FakeResult(
            result_id=receipt.result_id,
            resulting_version=receipt.resulting_version,
            projected_state="persisted-authoritative-state",
            kind="replay",
        )

    def project_result(context: GovernedCommandContext[_FakeItem]) -> _FakeResult:
        recorder.events.append("project_result")
        return _FakeResult(
            result_id=context.result_id,
            resulting_version=context.resulting_version,
            projected_state="resolved",
            kind="fresh",
        )

    return {
        "load_item": load_item,
        "check_capability": check_capability,
        "validate_domain": validate_domain,
        "current_version": current_version,
        "lookup_receipt": lookup_receipt,
        "commit_provisional": commit_provisional,
        "persist_receipt": persist_receipt,
        "build_audit": build_audit,
        "append_audit": append_audit,
        "load_replay_result": load_replay_result,
        "project_result": project_result,
    }


@pytest.mark.asyncio
async def test_fresh_command_runs_full_choreography_in_order() -> None:
    session = _FakeSession()
    item = _FakeItem(version=1)
    recorder = _Recorder()
    envelope = _envelope(expected_version=1)

    result = await execute_governed_command(
        session,  # type: ignore[arg-type]
        envelope,
        **_hooks(session=session, item=item, recorder=recorder),
    )

    assert recorder.events == [
        "load",
        "capability",
        "validate",
        "lookup",
        "commit",
        "persist",
        "build_audit",
        "append_audit",
        "project_result",
    ]
    assert session.rolled_back is False
    assert result.kind == "fresh"
    assert result.resulting_version == 2
    assert result.projected_state == "resolved"


@pytest.mark.asyncio
async def test_capability_runs_after_load_and_before_any_write() -> None:
    session = _FakeSession()
    recorder = _Recorder()
    with pytest.raises(CommandForbiddenError):
        await execute_governed_command(
            session,  # type: ignore[arg-type]
            _envelope(),
            **_hooks(
                session=session,
                item=_FakeItem(),
                recorder=recorder,
                capability_error=CommandForbiddenError(),
            ),
        )
    # Loaded first, then denied; no classification, write, or audit.
    assert recorder.events == ["load", "capability"]
    assert session.calls == []


@pytest.mark.asyncio
async def test_not_found_load_short_circuits_before_capability() -> None:
    session = _FakeSession()
    recorder = _Recorder()
    with pytest.raises(CommandNotFoundError):
        await execute_governed_command(
            session,  # type: ignore[arg-type]
            _envelope(),
            **_hooks(
                session=session,
                item=_FakeItem(),
                recorder=recorder,
                load_error=CommandNotFoundError(),
            ),
        )
    assert recorder.events == ["load"]


@pytest.mark.asyncio
async def test_domain_validation_runs_after_capability_and_blocks_write() -> None:
    session = _FakeSession()
    recorder = _Recorder()
    with pytest.raises(CommandValidationError):
        await execute_governed_command(
            session,  # type: ignore[arg-type]
            _envelope(),
            **_hooks(
                session=session,
                item=_FakeItem(),
                recorder=recorder,
                domain_error=CommandValidationError("zero evidence"),
            ),
        )
    assert recorder.events == ["load", "capability", "validate"]
    assert session.calls == []


@pytest.mark.asyncio
async def test_same_key_replay_projects_prior_identity_without_writing() -> None:
    session = _FakeSession()
    item = _FakeItem(version=2, state="already-advanced")
    recorder = _Recorder()
    prior = PriorReceipt(
        item_id=uuid4(),
        intent_hash=_VALID_INTENT_HASH,
        expected_version=1,
        resulting_version=2,
        result_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )

    result = await execute_governed_command(
        session,  # type: ignore[arg-type]
        _envelope(expected_version=1),
        **_hooks(session=session, item=item, recorder=recorder, prior=prior),
    )

    # No provisional write, receipt insert, or audit on a replay.
    assert recorder.events == ["load", "capability", "validate", "lookup", "load_replay"]
    assert session.calls == []
    assert session.rolled_back is False
    assert result.kind == "replay"
    assert result.result_id == prior.result_id
    assert result.resulting_version == 2
    assert result.projected_state == "persisted-authoritative-state"


@pytest.mark.asyncio
async def test_receipt_race_rolls_back_and_replays_prior_identity() -> None:
    session = _FakeSession()
    item = _FakeItem(version=1)
    recorder = _Recorder()
    race = PriorReceipt(
        item_id=uuid4(),
        intent_hash=_VALID_INTENT_HASH,
        expected_version=1,
        resulting_version=2,
        result_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )

    result = await execute_governed_command(
        session,  # type: ignore[arg-type]
        _envelope(expected_version=1),
        **_hooks(session=session, item=item, recorder=recorder, receipt_race=race),
    )

    # The provisional write happened, then the losing race rolled it back and
    # replayed the winner's identity; crucially, no audit was appended.
    assert recorder.events == [
        "load",
        "capability",
        "validate",
        "lookup",
        "commit",
        "persist",
        "load_replay",
    ]
    assert session.rolled_back is True
    assert "append_audit" not in session.calls
    assert result.kind == "replay"
    assert result.result_id == race.result_id
    assert result.resulting_version == 2


@pytest.mark.asyncio
async def test_receipt_race_with_mismatched_intent_is_typed_conflict() -> None:
    """A duplicate-key race with a different intent rolls back and fails typed."""
    session = _FakeSession()
    recorder = _Recorder()
    mismatched = PriorReceipt(
        item_id=uuid4(),
        intent_hash="b" * 64,
        expected_version=1,
        resulting_version=2,
        result_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )

    with pytest.raises(IdempotencyIntentConflictError):
        await execute_governed_command(
            session,  # type: ignore[arg-type]
            _envelope(intent_hash=_VALID_INTENT_HASH, expected_version=1),
            **_hooks(session=session, item=_FakeItem(), recorder=recorder, receipt_race=mismatched),
        )

    assert session.rolled_back is True
    assert recorder.events == [
        "load",
        "capability",
        "validate",
        "lookup",
        "commit",
        "persist",
    ]
    assert "load_replay" not in recorder.events
    assert "append_audit" not in session.calls


@pytest.mark.asyncio
async def test_audit_failure_propagates_for_caller_rollback() -> None:
    session = _FakeSession()
    recorder = _Recorder()

    class _InjectedAuditError(RuntimeError):
        pass

    with pytest.raises(_InjectedAuditError):
        await execute_governed_command(
            session,  # type: ignore[arg-type]
            _envelope(),
            **_hooks(
                session=session,
                item=_FakeItem(),
                recorder=recorder,
                audit_error=_InjectedAuditError("boom"),
            ),
        )
    # The write and receipt were attempted and the audit raised; the template
    # does not swallow it, so the caller's transaction rolls the unit of work
    # back. It never reaches the fresh projection.
    assert recorder.events[-1] == "append_audit"
    assert "project_result" not in recorder.events



@pytest.mark.asyncio
async def test_cas_stale_with_matching_concurrent_receipt_reconciles_to_replay() -> None:
    session = _FakeSession()
    item = _FakeItem(version=1)
    recorder = _Recorder()
    race = PriorReceipt(
        item_id=uuid4(),
        intent_hash=_VALID_INTENT_HASH,
        expected_version=1,
        resulting_version=2,
        result_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )
    lookups = iter((None, race))
    hooks = _hooks(session=session, item=item, recorder=recorder)

    async def lookup_receipt(_session, _envelope):
        recorder.events.append("lookup")
        return next(lookups)

    async def lose_cas(_session, _context) -> None:
        recorder.events.append("commit")
        raise StaleVersionConflictError()

    hooks["lookup_receipt"] = lookup_receipt
    hooks["commit_provisional"] = lose_cas

    result = await execute_governed_command(
        session,  # type: ignore[arg-type]
        _envelope(expected_version=1),
        **hooks,
    )

    assert session.rolled_back is True
    assert recorder.events == [
        "load",
        "capability",
        "validate",
        "lookup",
        "commit",
        "lookup",
        "load_replay",
    ]
    assert result.result_id == race.result_id
    assert result.kind == "replay"


@pytest.mark.asyncio
async def test_cas_stale_without_concurrent_receipt_remains_stale() -> None:
    session = _FakeSession()
    recorder = _Recorder()
    hooks = _hooks(session=session, item=_FakeItem(), recorder=recorder)

    async def lose_cas(_session, _context) -> None:
        recorder.events.append("commit")
        raise StaleVersionConflictError()

    hooks["commit_provisional"] = lose_cas

    with pytest.raises(StaleVersionConflictError):
        await execute_governed_command(
            session,  # type: ignore[arg-type]
            _envelope(expected_version=1),
            **hooks,
        )

    assert session.rolled_back is True
    assert recorder.events == [
        "load",
        "capability",
        "validate",
        "lookup",
        "commit",
        "lookup",
    ]
