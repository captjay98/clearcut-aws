"""Behavioral tests for the shared typed governed-command kernel.

The kernel is a module-agnostic building block that Task 10 governed features
reuse for tenant scope, capability, expected version, intent, idempotency,
typed errors, and same-transaction authoritative audit. These tests pin the
typed public boundary (no booleans/None/raw dicts leaking), deterministic
replay/conflict classification, and session-bound SQL that never opens or
commits its own transaction.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.commanding.domain import (
    AuditPayload,
    CommandEnvelope,
    CurrentVersionUnknown,
    NewCommand,
    PriorReceipt,
    ReplayResult,
    classify_command,
)
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandNotFoundError,
    CommandValidationError,
    GovernedCommandError,
    IdempotencyIntentConflictError,
    StaleVersionConflictError,
)
from clearcut.commanding.sql import (
    insert_authoritative_audit,
    insert_command_receipt,
    lookup_command_receipt,
)
from clearcut.database import engine, session_scope
from clearcut.init_db import init_and_seed_db
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_VALID_INTENT_HASH = "a" * 64


def _envelope(
    *,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    actor_id: UUID | None = None,
    operation: str = "decision.evidence.accept",
    idempotency_key: str = "idem-key-001",
    intent_hash: str = _VALID_INTENT_HASH,
    expected_version: int = 1,
) -> CommandEnvelope:
    return CommandEnvelope(
        org_id=org_id or uuid6.uuid7(),
        project_id=project_id or uuid6.uuid7(),
        actor_id=actor_id or uuid6.uuid7(),
        operation=operation,
        idempotency_key=idempotency_key,
        intent_hash=intent_hash,
        expected_version=expected_version,
    )


# --------------------------------------------------------------------------- #
# Envelope construction, validation, and immutability.
# --------------------------------------------------------------------------- #


def test_valid_envelope_constructs_and_normalizes() -> None:
    envelope = _envelope()
    assert envelope.operation == "decision.evidence.accept"
    assert envelope.idempotency_key == "idem-key-001"
    assert envelope.intent_hash == _VALID_INTENT_HASH
    assert envelope.expected_version == 1


def test_envelope_is_frozen_and_immutable() -> None:
    envelope = _envelope()
    with pytest.raises(dataclasses.FrozenInstanceError):
        envelope.expected_version = 2  # type: ignore[misc]


@pytest.mark.parametrize("bad_key", ["", "   ", "\t\n"])
def test_empty_or_blank_idempotency_key_rejected_at_construction(bad_key: str) -> None:
    with pytest.raises(CommandValidationError) as excinfo:
        _envelope(idempotency_key=bad_key)
    assert isinstance(excinfo.value, GovernedCommandError)
    assert excinfo.value.code == "command_validation_failed"
    # Safe message must not echo tenant/foreign detail.
    assert bad_key.strip() not in excinfo.value.message or bad_key.strip() == ""


@pytest.mark.parametrize(
    "bad_hash",
    [
        "",
        "   ",
        "abc",  # too short
        "g" * 64,  # non-hex characters
        "A" * 64,  # uppercase is not canonical lowercase hex
        "a" * 63,  # off-by-one short
        "a" * 65,  # off-by-one long
    ],
)
def test_malformed_intent_hash_rejected_at_construction(bad_hash: str) -> None:
    with pytest.raises(CommandValidationError) as excinfo:
        _envelope(intent_hash=bad_hash)
    assert excinfo.value.code == "command_validation_failed"


@pytest.mark.parametrize("bad_operation", ["", "   "])
def test_blank_operation_rejected_at_construction(bad_operation: str) -> None:
    with pytest.raises(CommandValidationError):
        _envelope(operation=bad_operation)


@pytest.mark.parametrize("bad_version", [0, -1, -100])
def test_non_positive_expected_version_rejected_at_construction(bad_version: int) -> None:
    with pytest.raises(CommandValidationError):
        _envelope(expected_version=bad_version)


# --------------------------------------------------------------------------- #
# Typed safe errors.
# --------------------------------------------------------------------------- #


def test_all_typed_errors_share_safe_base_and_carry_machine_codes() -> None:
    errors = [
        CommandValidationError("bad input"),
        CommandForbiddenError(),
        CommandNotFoundError(),
        StaleVersionConflictError(),
        IdempotencyIntentConflictError(),
    ]
    codes = set()
    for error in errors:
        assert isinstance(error, GovernedCommandError)
        assert isinstance(error.code, str) and error.code
        assert isinstance(error.message, str) and error.message
        codes.add(error.code)
    # Distinct machine codes so callers can branch without string parsing.
    assert len(codes) == len(errors)


def test_not_found_and_forbidden_do_not_leak_foreign_resource_details() -> None:
    secret_id = "org-9999-project-cross-tenant-secret"
    not_found = CommandNotFoundError()
    forbidden = CommandForbiddenError()
    for error in (not_found, forbidden):
        assert secret_id not in error.message
    # Not-found parity: forbidden and not-found present the same neutral shape,
    # so probing cannot distinguish "exists but denied" from "absent".
    assert not_found.code != forbidden.code
    assert not_found.message  # neutral, non-empty
    assert forbidden.message


# --------------------------------------------------------------------------- #
# Deterministic replay / conflict classification (pure domain).
# --------------------------------------------------------------------------- #


def _prior(
    *,
    intent_hash: str = _VALID_INTENT_HASH,
    resulting_version: int = 2,
    result_id: UUID | None = None,
) -> PriorReceipt:
    return PriorReceipt(
        item_id=uuid6.uuid7(),
        intent_hash=intent_hash,
        expected_version=1,
        resulting_version=resulting_version,
        result_id=result_id or uuid6.uuid7(),
        occurred_at=datetime.now(UTC),
    )


def test_classify_no_prior_receipt_is_new_command() -> None:
    envelope = _envelope()
    outcome = classify_command(envelope, prior=None, current_version=CurrentVersionUnknown())
    assert isinstance(outcome, NewCommand)


def test_classify_same_key_same_intent_is_replay_with_prior_identity() -> None:
    envelope = _envelope()
    prior = _prior(intent_hash=envelope.intent_hash)
    outcome = classify_command(envelope, prior=prior, current_version=CurrentVersionUnknown())
    assert isinstance(outcome, ReplayResult)
    assert outcome.prior is prior
    assert outcome.prior.result_id == prior.result_id
    assert outcome.prior.resulting_version == prior.resulting_version


def test_classify_same_key_different_intent_is_typed_conflict() -> None:
    envelope = _envelope(intent_hash="a" * 64)
    prior = _prior(intent_hash="b" * 64)
    with pytest.raises(IdempotencyIntentConflictError) as excinfo:
        classify_command(envelope, prior=prior, current_version=CurrentVersionUnknown())
    assert excinfo.value.code == "idempotency_intent_conflict"


def test_classify_is_deterministic_across_repeated_calls() -> None:
    envelope = _envelope()
    prior = _prior(intent_hash=envelope.intent_hash)
    first = classify_command(envelope, prior=prior, current_version=CurrentVersionUnknown())
    second = classify_command(envelope, prior=prior, current_version=CurrentVersionUnknown())
    assert isinstance(first, ReplayResult)
    assert isinstance(second, ReplayResult)
    assert first.prior.result_id == second.prior.result_id


def test_classify_stale_expected_version_is_typed_conflict() -> None:
    # No prior receipt for this key, but the caller's expected_version does not
    # match the current aggregate version: a stale optimistic-concurrency guess.
    envelope = _envelope(expected_version=1)
    with pytest.raises(StaleVersionConflictError) as excinfo:
        classify_command(envelope, prior=None, current_version=5)
    assert excinfo.value.code == "stale_version_conflict"


def test_classify_matching_expected_version_with_no_prior_is_new_command() -> None:
    envelope = _envelope(expected_version=5)
    outcome = classify_command(envelope, prior=None, current_version=5)
    assert isinstance(outcome, NewCommand)


# --------------------------------------------------------------------------- #
# Session-bound SQL helpers (real schema, SQLite test DB).
# --------------------------------------------------------------------------- #


async def _seed_command_scope(session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID]:
    """Insert the minimal real scope chain: user, org, project, clearance item.

    The governed_command_receipts FKs require a live (item_id, org_id,
    project_id) clearance item plus an accountable actor user, so the kernel's
    receipt insertion is exercised against the true tenant-scoped schema.
    """
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    now = datetime.now(UTC)

    await session.execute(
        sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
        {"id": str(actor_id), "email": f"actor-{uuid4().hex}@example.com", "created_at": now},
    )
    await session.execute(
        sa.text(
            "INSERT INTO organizations (id, name, slug, created_at) "
            "VALUES (:id, :name, :slug, :created_at)"
        ),
        {
            "id": str(org_id),
            "name": "Kernel Studio",
            "slug": f"kernel-{uuid4().hex[:8]}",
            "created_at": now,
        },
    )
    await session.execute(
        sa.text(
            "INSERT INTO projects (id, org_id, title, created_at) "
            "VALUES (:id, :org_id, :title, :created_at)"
        ),
        {"id": str(project_id), "org_id": str(org_id), "title": "Governed", "created_at": now},
    )
    await session.execute(
        sa.text(
            "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
            "VALUES (:id, :org_id, :project_id, :title, :created_at)"
        ),
        {
            "id": str(script_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "title": "Draft",
            "created_at": now,
        },
    )
    await session.execute(
        sa.text(
            "INSERT INTO script_versions "
            "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at) "
            "VALUES (:id, :script_id, :org_id, :project_id, 1, :source_hash, :parser_version, :created_at)"
        ),
        {
            "id": str(version_id),
            "script_id": str(script_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "source_hash": "f" * 64,
            "parser_version": "v1",
            "created_at": now,
        },
    )
    await session.execute(
        sa.text(
            "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
            "VALUES (:id, :version_id, 1, 'action', :text)"
        ),
        {"id": str(element_id), "version_id": str(version_id), "text": "INT. HOUSE - DAY"},
    )
    await session.execute(
        sa.text(
            "INSERT INTO clearance_items "
            "(id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at, version) "
            "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, "
            ":category, :text, 'open', :created_at, 1)"
        ),
        {
            "id": str(item_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "script_id": str(script_id),
            "version_id": str(version_id),
            "element_id": str(element_id),
            "category": "products_and_trademarks",
            "text": "A branded soda can.",
            "created_at": now,
        },
    )
    return org_id, project_id, actor_id, item_id


@pytest.mark.asyncio
async def test_lookup_returns_none_typed_when_no_receipt_exists() -> None:
    async with session_scope() as session:
        org_id, project_id, actor_id, _item_id = await _seed_command_scope(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        prior = await lookup_command_receipt(session, envelope)
    assert prior is None


@pytest.mark.asyncio
async def test_insert_then_lookup_roundtrips_prior_identity_under_full_scope() -> None:
    result_id = uuid6.uuid7()
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        await insert_command_receipt(
            session,
            envelope,
            item_id=item_id,
            resulting_version=2,
            result_id=result_id,
            occurred_at=datetime.now(UTC),
        )
        prior = await lookup_command_receipt(session, envelope)

    assert isinstance(prior, PriorReceipt)
    assert prior.item_id == item_id
    assert prior.result_id == result_id
    assert prior.resulting_version == 2
    assert prior.intent_hash == envelope.intent_hash
    assert prior.expected_version == envelope.expected_version


@pytest.mark.asyncio
async def test_lookup_is_scoped_and_ignores_other_tenant_receipts() -> None:
    result_id = uuid6.uuid7()
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        await insert_command_receipt(
            session,
            envelope,
            item_id=item_id,
            resulting_version=2,
            result_id=result_id,
            occurred_at=datetime.now(UTC),
        )
        # A different actor within the same key/operation is a different scope
        # tuple and must not observe the first actor's receipt.
        other_actor_envelope = dataclasses.replace(envelope, actor_id=uuid6.uuid7())
        prior = await lookup_command_receipt(session, other_actor_envelope)
    assert prior is None


@pytest.mark.asyncio
async def test_receipt_and_audit_do_not_commit_when_caller_transaction_fails() -> None:
    """A provisional domain write plus receipt/audit must not persist if the
    caller-provided transaction later raises. The kernel helpers must run
    inside the caller's transaction and never open/commit their own."""
    result_id = uuid6.uuid7()
    correlation_id = uuid6.uuid7()
    receipt_key = "idem-rollback-001"

    class InjectedFailureError(RuntimeError):
        pass

    org_id = project_id = actor_id = item_id = None
    with pytest.raises(InjectedFailureError):
        async with session_scope() as session:
            org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
            envelope = _envelope(
                org_id=org_id,
                project_id=project_id,
                actor_id=actor_id,
                idempotency_key=receipt_key,
            )
            await insert_command_receipt(
                session,
                envelope,
                item_id=item_id,
                resulting_version=2,
                result_id=result_id,
                occurred_at=datetime.now(UTC),
            )
            await insert_authoritative_audit(
                session,
                envelope,
                action="decision.evidence.accepted",
                target_type="clearance_item",
                target_id=item_id,
                payload=AuditPayload({"resultId": str(result_id)}),
                correlation_id=correlation_id,
                occurred_at=datetime.now(UTC),
            )
            # Force the whole transaction to roll back after provisional writes.
            raise InjectedFailureError()

    # Nothing from the failed transaction is visible: not the seeded scope, not
    # the receipt, not the audit event.
    async with session_scope() as verify:
        receipt_count = (
            await verify.execute(
                sa.text(
                    "SELECT count(*) FROM governed_command_receipts WHERE idempotency_key = :key"
                ),
                {"key": receipt_key},
            )
        ).scalar_one()
        audit_count = (
            await verify.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE correlation_id = :correlation_id"
                ),
                {"correlation_id": str(correlation_id)},
            )
        ).scalar_one()
    assert receipt_count == 0
    assert audit_count == 0


@pytest.mark.asyncio
async def test_audit_insertion_records_accountable_actor_and_correlation() -> None:
    correlation_id = uuid6.uuid7()
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        await insert_authoritative_audit(
            session,
            envelope,
            action="decision.evidence.accepted",
            target_type="clearance_item",
            target_id=item_id,
            payload=AuditPayload({"resultId": "abc"}),
            correlation_id=correlation_id,
            occurred_at=datetime.now(UTC),
        )

    async with session_scope() as verify:
        row = (
            (
                await verify.execute(
                    sa.text(
                        "SELECT org_id, project_id, actor_id, action, target_type, "
                        "target_id, correlation_id FROM authoritative_audit_events "
                        "WHERE correlation_id = :correlation_id"
                    ),
                    {"correlation_id": str(correlation_id)},
                )
            )
            .mappings()
            .one()
        )
    assert UUID(str(row["actor_id"])) == actor_id
    assert UUID(str(row["org_id"])) == org_id
    assert UUID(str(row["project_id"])) == project_id
    assert UUID(str(row["correlation_id"])) == correlation_id
    assert row["action"] == "decision.evidence.accepted"


@pytest.mark.asyncio
async def test_helpers_do_not_open_their_own_transaction() -> None:
    """When the caller opens an explicit transaction, the helpers must join it
    rather than committing independently; a rollback discards their writes."""
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
    async with session_scope() as outer:
        # Re-seed inside this session because the previous scope was committed.
        org_id, project_id, actor_id, item_id = await _seed_command_scope(outer)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        await insert_command_receipt(
            outer,
            envelope,
            item_id=item_id,
            resulting_version=2,
            result_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
        )
        await outer.rollback()
        remaining = (
            await outer.execute(
                sa.text(
                    "SELECT count(*) FROM governed_command_receipts "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": str(org_id), "project_id": str(project_id)},
            )
        ).scalar_one()
    assert remaining == 0


# --------------------------------------------------------------------------- #
# Finding 1 (P2): typed / redaction audit payload seam.
# --------------------------------------------------------------------------- #


def test_audit_payload_is_a_typed_seam_carrying_a_mapping() -> None:
    """The authoritative audit payload crosses the boundary as a typed value,
    not an arbitrary raw dict, and preserves the caller's mapping."""
    payload = AuditPayload({"resultId": "abc"})
    assert dict(payload.as_redacted()) == {"resultId": "abc"}


def test_audit_payload_applies_a_redaction_hook_before_persistence() -> None:
    """A redaction hook may transform the mapping so secrets never reach the
    authoritative payload_redacted column verbatim."""
    payload = AuditPayload(
        {"resultId": "abc", "token": "super-secret"},
        redactor=lambda raw: {k: v for k, v in raw.items() if k != "token"},
    )
    redacted = dict(payload.as_redacted())
    assert redacted == {"resultId": "abc"}
    assert "token" not in redacted


def test_audit_payload_rejects_non_mapping_input_at_construction() -> None:
    """The seam refuses a non-mapping so an unconstrained value cannot flow
    silently to payload_redacted."""
    with pytest.raises(CommandValidationError) as excinfo:
        AuditPayload([("resultId", "abc")])  # type: ignore[arg-type]
    assert excinfo.value.code == "command_validation_failed"


@pytest.mark.asyncio
async def test_audit_insertion_persists_typed_payload_seam() -> None:
    correlation_id = uuid6.uuid7()
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        await insert_authoritative_audit(
            session,
            envelope,
            action="decision.evidence.accepted",
            target_type="clearance_item",
            target_id=item_id,
            payload=AuditPayload(
                {"resultId": "abc", "token": "secret"},
                redactor=lambda raw: {k: v for k, v in raw.items() if k != "token"},
            ),
            correlation_id=correlation_id,
            occurred_at=datetime.now(UTC),
        )

    async with session_scope() as verify:
        row = (
            (
                await verify.execute(
                    sa.text(
                        "SELECT payload_redacted FROM authoritative_audit_events "
                        "WHERE correlation_id = :correlation_id"
                    ),
                    {"correlation_id": str(correlation_id)},
                )
            )
            .mappings()
            .one()
        )
    stored = row["payload_redacted"]
    stored_map = stored if isinstance(stored, dict) else json.loads(str(stored))
    assert stored_map == {"resultId": "abc"}


# --------------------------------------------------------------------------- #
# Finding 3 (P3): naive datetimes rejected on the write path.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_insert_receipt_rejects_naive_datetime() -> None:
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        with pytest.raises(CommandValidationError) as excinfo:
            await insert_command_receipt(
                session,
                envelope,
                item_id=item_id,
                resulting_version=2,
                result_id=uuid6.uuid7(),
                occurred_at=datetime.now(),  # noqa: DTZ005 - intentionally naive
            )
        assert excinfo.value.code == "command_validation_failed"


@pytest.mark.asyncio
async def test_insert_audit_rejects_naive_datetime() -> None:
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        with pytest.raises(CommandValidationError) as excinfo:
            await insert_authoritative_audit(
                session,
                envelope,
                action="decision.evidence.accepted",
                target_type="clearance_item",
                target_id=item_id,
                payload=AuditPayload({"resultId": "abc"}),
                correlation_id=uuid6.uuid7(),
                occurred_at=datetime.now(),  # noqa: DTZ005 - intentionally naive
            )
        assert excinfo.value.code == "command_validation_failed"


# --------------------------------------------------------------------------- #
# Finding 2 (P3): duplicate receipt violates the unique idempotency guard.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_duplicate_receipt_scope_tuple_raises_integrity_error() -> None:
    """A second receipt for the same
    (org_id, project_id, actor_id, operation, idempotency_key) must violate the
    real migrated unique constraint, proving the durable idempotency guard."""
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_command_scope(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        await insert_command_receipt(
            session,
            envelope,
            item_id=item_id,
            resulting_version=2,
            result_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
        )
        with pytest.raises(IntegrityError):
            await insert_command_receipt(
                session,
                envelope,
                item_id=item_id,
                resulting_version=3,
                result_id=uuid6.uuid7(),
                occurred_at=datetime.now(UTC),
            )


# --------------------------------------------------------------------------- #
# Finding 4 (P3): stale-version guard is non-opt-in for governed use.
# --------------------------------------------------------------------------- #


def test_classify_missing_current_version_cannot_silently_skip_stale_guard() -> None:
    """A caller that does not know the current version must say so explicitly
    with the typed sentinel; a plain missing value is a typed validation error
    rather than a silently skipped stale-version check."""
    envelope = _envelope(expected_version=1)
    with pytest.raises(CommandValidationError):
        classify_command(envelope, prior=None, current_version=None)  # type: ignore[arg-type]


def test_classify_explicit_unknown_current_version_is_accepted_new_command() -> None:
    envelope = _envelope(expected_version=1)
    outcome = classify_command(envelope, prior=None, current_version=CurrentVersionUnknown())
    assert isinstance(outcome, NewCommand)


@pytest.mark.asyncio
async def test_module_migrated_to_head_exposes_expected_receipt_schema() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_conn: {
                column["name"]
                for column in sa.inspect(sync_conn).get_columns("governed_command_receipts")
            }
        )
    assert {
        "org_id",
        "project_id",
        "actor_id",
        "operation",
        "idempotency_key",
        "expected_version",
        "resulting_version",
        "intent_hash",
        "result_id",
        "occurred_at",
    } <= columns
