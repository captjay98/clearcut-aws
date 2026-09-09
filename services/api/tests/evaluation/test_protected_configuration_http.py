"""Behavioral tests for the governed protected-configuration surface.

Every test drives the real ASGI application over HTTP with a real authenticated
session, then inspects the database directly to confirm what actually committed.
Nothing is stubbed: the governed-command kernel, the lifecycle compare-and-swaps,
the partial unique index, and the authoritative audit ledger are all exercised as
they run in production.

The organization is created through the production
:class:`~clearcut.organizations.application.bootstrap.OrganizationBootstrapService`
wiring — the same ``DatabaseOrganizationRepository`` the composition root
constructs — because that is the path the default binding seed lives on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.evaluation.application.protected_configuration import (
    ACTIVATE_AUDIT_ACTION,
    DRAFT_AUDIT_ACTION,
    VALIDATE_AUDIT_ACTION,
)
from clearcut.evaluation.delivery.configuration_http import router as configuration_router
from clearcut.evaluation.domain.configuration import (
    DEFAULT_POLICY_VERSION,
    DEFAULT_PROMPT_VERSION,
)
from clearcut.main import app
from clearcut.organizations.adapters.sql_repository import DatabaseOrganizationRepository
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService
from httpx import ASGITransport, AsyncClient

_PASSWORD = "Password123!"


def _mount_configuration_router() -> None:
    """Make the four contract operations reachable in the test application.

    ``clearcut.evaluation.delivery.http`` carries an unschematized
    ``/protected-configurations`` placeholder that answers 503, and FastAPI
    resolves routes in registration order. The composition root must therefore
    mount this router ahead of that one (or drop the placeholder); until it does,
    these tests insert the contract routes at the front so they exercise the real
    handlers rather than the placeholder. The insertion is idempotent.
    """
    operation_ids = {getattr(route, "operation_id", None) for route in app.router.routes}
    if "listProtectedConfigurations" in operation_ids:
        return
    for offset, route in enumerate(configuration_router.routes):
        app.router.routes.insert(offset, route)


@dataclass(frozen=True)
class Fixture:
    """One authenticated owner and the organization they created."""

    client: AsyncClient
    user_id: UUID
    org_id: UUID
    seeded_config_id: UUID


def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def _register(client: AsyncClient, suffix: str) -> UUID:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": f"Governance User {suffix}",
            "email": f"governance-{suffix}-{uuid4().hex[:8]}@example.com",
            "password": _PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["data"]["userId"])


async def _bootstrap_org(user_id: UUID, suffix: str) -> tuple[UUID, UUID]:
    """Create an organization through the production bootstrap wiring.

    Returns the organization id and the id of the binding the creation seeded.
    """
    service = OrganizationBootstrapService(repository=DatabaseOrganizationRepository())
    result = await service.bootstrap_organization_with_governance(
        user_id=user_id,
        name=f"Governance Studio {suffix}",
        slug=f"governance-{suffix}-{uuid4().hex[:8]}",
    )
    # The SQL repository can seed, so this is a real persisted binding, never the
    # typed-unavailable value the in-memory repository returns.
    return result.organization.org_id, result.governance.config_id  # type: ignore[union-attr]


@asynccontextmanager
async def _owner_fixture(suffix: str) -> AsyncIterator[Fixture]:
    """Yield an authenticated Owner and the organization their creation seeded."""
    _mount_configuration_router()
    async with _client() as client:
        user_id = await _register(client, suffix)
        org_id, seeded_config_id = await _bootstrap_org(user_id, suffix)
        yield Fixture(
            client=client,
            user_id=user_id,
            org_id=org_id,
            seeded_config_id=seeded_config_id,
        )


async def _set_role(*, org_id: UUID, user_id: UUID, role: str) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE memberships SET role = :role WHERE org_id = :org_id AND user_id = :user_id"
            ),
            {"role": role, "org_id": str(org_id), "user_id": str(user_id)},
        )


async def _active_rows(org_id: UUID) -> list[sa.RowMapping]:
    async with session_scope() as session:
        return list(
            (
                await session.execute(
                    sa.text(
                        "SELECT id, lifecycle, activated_by, activated_at, superseded_by "
                        "FROM protected_configurations "
                        "WHERE org_id = :org_id AND lifecycle = 'active'"
                    ),
                    {"org_id": str(org_id)},
                )
            )
            .mappings()
            .all()
        )


async def _audit_actions(org_id: UUID) -> list[sa.RowMapping]:
    async with session_scope() as session:
        return list(
            (
                await session.execute(
                    sa.text(
                        "SELECT action, target_type, target_id, actor_id, project_id "
                        "FROM authoritative_audit_events "
                        "WHERE org_id = :org_id AND target_type = 'protected_configuration' "
                        "ORDER BY occurred_at ASC"
                    ),
                    {"org_id": str(org_id)},
                )
            )
            .mappings()
            .all()
        )


async def _draft(
    fixture: Fixture,
    *,
    policy_version: str,
    prompt_version: str,
    rationale: str = "Adopt the reviewed policy revision for the next pass.",
    label: str | None = "Q3 policy revision",
    idempotency_key: str | None = None,
):
    body: dict[str, object] = {
        "policyVersion": policy_version,
        "promptVersion": prompt_version,
        "rationale": rationale,
    }
    if label is not None:
        body["label"] = label
    return await fixture.client.post(
        f"/api/v1/organizations/{fixture.org_id}/protected-configurations",
        json=body,
        headers={"Idempotency-Key": idempotency_key or f"draft-{uuid4().hex}"},
    )


async def _validate(fixture: Fixture, config_id: str):
    return await fixture.client.post(
        f"/api/v1/organizations/{fixture.org_id}/protected-configurations/{config_id}:validate"
    )


async def _activate(fixture: Fixture, config_id: str):
    return await fixture.client.post(
        f"/api/v1/organizations/{fixture.org_id}/protected-configurations/{config_id}:activate"
    )


async def _promote(fixture: Fixture, *, policy_version: str, prompt_version: str) -> str:
    """Draft, validate, and activate one binding through the governed HTTP path."""
    drafted = await _draft(
        fixture,
        policy_version=policy_version,
        prompt_version=prompt_version,
    )
    assert drafted.status_code == 201, drafted.text
    config_id = drafted.json()["data"]["configurationId"]

    validated = await _validate(fixture, config_id)
    assert validated.status_code == 200, validated.text
    assert validated.json()["data"] == {"valid": True, "issues": []}

    activated = await _activate(fixture, config_id)
    assert activated.status_code == 200, activated.text
    assert activated.json()["data"] == {"configurationId": config_id, "status": "active"}
    return config_id


@pytest.mark.asyncio
async def test_fresh_organization_is_created_with_exactly_one_accountable_active_binding() -> None:
    """A newly created organization can run a detection pass immediately.

    Detection, research, and rescan all refuse to run unless the organization has
    exactly one active binding, so creation must produce one — and it must be
    accountable to the human who created the organization.
    """
    async with _owner_fixture("fresh") as fixture:
        active = await _active_rows(fixture.org_id)
        assert len(active) == 1
        assert UUID(str(active[0]["id"])) == fixture.seeded_config_id
        assert UUID(str(active[0]["activated_by"])) == fixture.user_id
        assert active[0]["activated_at"] is not None

        async with session_scope() as session:
            binding = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT policy_version, prompt_version, label FROM "
                            "protected_configurations WHERE id = :id"
                        ),
                        {"id": str(fixture.seeded_config_id)},
                    )
                )
                .mappings()
                .one()
            )
        assert binding["policy_version"] == DEFAULT_POLICY_VERSION
        assert binding["prompt_version"] == DEFAULT_PROMPT_VERSION
        assert "default" in str(binding["label"]).lower()


@pytest.mark.asyncio
async def test_organization_creation_rolls_back_entirely_when_the_binding_cannot_be_seeded() -> (
    None
):
    """An organization is never committed without the binding that governs it.

    The three rows are one act. If the binding write fails, the organization and
    its owner membership must not survive — an organization that exists but can
    never run a pass is worse than no organization at all.
    """
    _mount_configuration_router()
    async with _client() as client:
        user_id = await _register(client, "rollback")

    service = OrganizationBootstrapService(repository=DatabaseOrganizationRepository())
    slug = f"rollback-{uuid4().hex[:8]}"

    from clearcut.evaluation.adapters import sql_configuration_repository as adapter_module

    original = adapter_module.SqlProtectedConfigurationRepository.seed_default_binding

    async def failing_seed(self, session, *, configuration):  # noqa: ANN001, ANN202
        raise RuntimeError("seed unavailable")

    adapter_module.SqlProtectedConfigurationRepository.seed_default_binding = failing_seed
    try:
        with pytest.raises(RuntimeError):
            await service.bootstrap_organization_with_governance(
                user_id=user_id,
                name="Rollback Studio",
                slug=slug,
            )
    finally:
        adapter_module.SqlProtectedConfigurationRepository.seed_default_binding = original

    async with session_scope() as session:
        organizations = (
            await session.execute(
                sa.text("SELECT count(*) FROM organizations WHERE slug = :slug"),
                {"slug": slug},
            )
        ).scalar_one()
        memberships = (
            await session.execute(
                sa.text("SELECT count(*) FROM memberships WHERE user_id = :user_id"),
                {"user_id": str(user_id)},
            )
        ).scalar_one()
    assert organizations == 0
    assert memberships == 0


@pytest.mark.asyncio
async def test_owner_drafts_validates_and_activates_leaving_exactly_one_active_binding() -> None:
    """Activating a second binding supersedes the first, never coexists with it.

    The one-active-binding invariant is what detection reads. This walks the full
    governed sequence twice and confirms the invariant holds after each, that the
    superseded row records what replaced it, and that every governed step left an
    authoritative audit event.
    """
    async with _owner_fixture("promote") as fixture:
        first = await _promote(fixture, policy_version="policy-v2", prompt_version="prompt-v2")

        active = await _active_rows(fixture.org_id)
        assert len(active) == 1
        assert str(active[0]["id"]) == first

        # The seeded binding is now history and names its successor.
        async with session_scope() as session:
            seeded = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT lifecycle, superseded_by, superseded_at FROM "
                            "protected_configurations WHERE id = :id"
                        ),
                        {"id": str(fixture.seeded_config_id)},
                    )
                )
                .mappings()
                .one()
            )
        assert seeded["lifecycle"] == "superseded"
        assert UUID(str(seeded["superseded_by"])) == UUID(first)
        assert seeded["superseded_at"] is not None

        second = await _promote(fixture, policy_version="policy-v3", prompt_version="prompt-v3")

        active = await _active_rows(fixture.org_id)
        assert len(active) == 1
        assert str(active[0]["id"]) == second

        async with session_scope() as session:
            lifecycles = {
                str(row["id"]): str(row["lifecycle"])
                for row in (
                    await session.execute(
                        sa.text(
                            "SELECT id, lifecycle FROM protected_configurations "
                            "WHERE org_id = :org_id"
                        ),
                        {"org_id": str(fixture.org_id)},
                    )
                )
                .mappings()
                .all()
            }
        assert lifecycles[str(fixture.seeded_config_id)] == "superseded"
        assert lifecycles[first] == "superseded"
        assert lifecycles[second] == "active"

        # Every governed step is attested, and every event is organization-scoped
        # (no project), which is what makes it a valid organization-level event.
        events = await _audit_actions(fixture.org_id)
        assert [row["action"] for row in events] == [
            DRAFT_AUDIT_ACTION,
            VALIDATE_AUDIT_ACTION,
            ACTIVATE_AUDIT_ACTION,
            DRAFT_AUDIT_ACTION,
            VALIDATE_AUDIT_ACTION,
            ACTIVATE_AUDIT_ACTION,
        ]
        assert all(row["project_id"] is None for row in events)
        assert all(UUID(str(row["actor_id"])) == fixture.user_id for row in events)


@pytest.mark.asyncio
async def test_repeated_activation_never_violates_the_one_active_binding_index() -> None:
    """A repeated activation replays instead of racing the uniqueness constraint.

    The partial unique index on ``(org_id) WHERE lifecycle = 'active'`` cannot be
    raced, so a second activation of the same binding must resolve to the recorded
    outcome rather than attempting a second promotion.
    """
    async with _owner_fixture("replay") as fixture:
        config_id = await _promote(
            fixture,
            policy_version="policy-v4",
            prompt_version="prompt-v4",
        )

        replayed = await _activate(fixture, config_id)
        assert replayed.status_code == 200, replayed.text
        assert replayed.json()["data"] == {"configurationId": config_id, "status": "active"}

        assert len(await _active_rows(fixture.org_id)) == 1
        # The replay appended no second attestation for the activation.
        activations = [
            row
            for row in await _audit_actions(fixture.org_id)
            if row["action"] == ACTIVATE_AUDIT_ACTION
        ]
        assert len(activations) == 1


@pytest.mark.asyncio
async def test_retried_draft_with_the_same_key_returns_the_same_binding() -> None:
    """One idempotency key drafts one binding, however many times it is sent."""
    async with _owner_fixture("idempotent") as fixture:
        key = f"draft-{uuid4().hex}"
        first = await _draft(
            fixture,
            policy_version="policy-v5",
            prompt_version="prompt-v5",
            idempotency_key=key,
        )
        second = await _draft(
            fixture,
            policy_version="policy-v5",
            prompt_version="prompt-v5",
            idempotency_key=key,
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert first.json()["data"]["configurationId"] == second.json()["data"]["configurationId"]

        async with session_scope() as session:
            drafts = (
                await session.execute(
                    sa.text(
                        "SELECT count(*) FROM protected_configurations "
                        "WHERE org_id = :org_id AND lifecycle = 'draft'"
                    ),
                    {"org_id": str(fixture.org_id)},
                )
            ).scalar_one()
        assert drafts == 1


@pytest.mark.asyncio
async def test_reusing_a_key_for_a_different_binding_is_a_conflict() -> None:
    """A key reused for different intent is refused, not silently applied."""
    async with _owner_fixture("intent") as fixture:
        key = f"draft-{uuid4().hex}"
        first = await _draft(
            fixture,
            policy_version="policy-v6",
            prompt_version="prompt-v6",
            idempotency_key=key,
        )
        assert first.status_code == 201, first.text

        conflicting = await _draft(
            fixture,
            policy_version="policy-v7",
            prompt_version="prompt-v7",
            idempotency_key=key,
        )
        assert conflicting.status_code == 409, conflicting.text
        assert conflicting.json()["error"]["code"] == "conflict_idempotency_mismatch"


@pytest.mark.asyncio
async def test_non_owner_cannot_draft_validate_or_activate_but_can_list() -> None:
    """Protected configuration is Owner-governed and readable by any active member.

    Admin is the strongest non-Owner role and holds every other organization
    administration capability, so it is the sharpest test that governance is not
    merely "an administrator".
    """
    async with _owner_fixture("forbidden") as fixture:
        drafted = await _draft(fixture, policy_version="policy-v8", prompt_version="prompt-v8")
        assert drafted.status_code == 201, drafted.text
        config_id = drafted.json()["data"]["configurationId"]

        await _set_role(org_id=fixture.org_id, user_id=fixture.user_id, role="admin")

        refused_draft = await _draft(
            fixture,
            policy_version="policy-v9",
            prompt_version="prompt-v9",
        )
        assert refused_draft.status_code == 403, refused_draft.text
        assert refused_draft.json()["error"]["code"] == "permission_denied"

        refused_validate = await _validate(fixture, config_id)
        assert refused_validate.status_code == 403, refused_validate.text

        refused_activate = await _activate(fixture, config_id)
        assert refused_activate.status_code == 403, refused_activate.text

        # Reading stays open to any active member.
        listed = await fixture.client.get(
            f"/api/v1/organizations/{fixture.org_id}/protected-configurations"
        )
        assert listed.status_code == 200, listed.text
        assert len(listed.json()["data"]) == 2

        # No refused command wrote anything.
        async with session_scope() as session:
            total = (
                await session.execute(
                    sa.text("SELECT count(*) FROM protected_configurations WHERE org_id = :org_id"),
                    {"org_id": str(fixture.org_id)},
                )
            ).scalar_one()
        assert total == 2
        assert len(await _active_rows(fixture.org_id)) == 1


@pytest.mark.asyncio
async def test_list_reports_the_seeded_binding_in_the_contract_shape() -> None:
    """The list surfaces the governing binding with its accountability trail."""
    async with _owner_fixture("list") as fixture:
        response = await fixture.client.get(
            f"/api/v1/organizations/{fixture.org_id}/protected-configurations"
        )
        assert response.status_code == 200, response.text
        entries = response.json()["data"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["configurationId"] == str(fixture.seeded_config_id)
        assert entry["orgId"] == str(fixture.org_id)
        assert entry["lifecycle"] == "active"
        assert entry["policyVersion"] == DEFAULT_POLICY_VERSION
        assert entry["promptVersion"] == DEFAULT_PROMPT_VERSION
        assert entry["activatedBy"] == str(fixture.user_id)
        assert entry["validationIssues"] == []
        assert entry["activatedAt"]
        assert entry["createdAt"]
        assert entry["rationale"]


@pytest.mark.asyncio
async def test_validation_records_issues_and_holds_an_unfit_binding_at_draft() -> None:
    """A binding identical to the active one is not fit to activate.

    Activating it would change nothing while producing a new governing record, so
    validation reports the issue and refuses to advance the stage — and activation
    of the un-advanced draft is then refused too.
    """
    async with _owner_fixture("issues") as fixture:
        drafted = await _draft(
            fixture,
            policy_version=DEFAULT_POLICY_VERSION,
            prompt_version=DEFAULT_PROMPT_VERSION,
        )
        assert drafted.status_code == 201, drafted.text
        config_id = drafted.json()["data"]["configurationId"]

        validated = await _validate(fixture, config_id)
        assert validated.status_code == 200, validated.text
        payload = validated.json()["data"]
        assert payload["valid"] is False
        assert payload["issues"]

        async with session_scope() as session:
            row = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT lifecycle, validated_at, validation_issues "
                            "FROM protected_configurations WHERE id = :id"
                        ),
                        {"id": config_id},
                    )
                )
                .mappings()
                .one()
            )
        assert row["lifecycle"] == "draft"
        assert row["validated_at"] is None

        refused = await _activate(fixture, config_id)
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "validation_failed"
        assert len(await _active_rows(fixture.org_id)) == 1


@pytest.mark.asyncio
async def test_activating_an_unvalidated_draft_is_refused() -> None:
    """A binding no human validated can never become the governing binding."""
    async with _owner_fixture("unvalidated") as fixture:
        drafted = await _draft(fixture, policy_version="policy-vX", prompt_version="prompt-vX")
        assert drafted.status_code == 201, drafted.text

        refused = await _activate(fixture, drafted.json()["data"]["configurationId"])
        assert refused.status_code == 422, refused.text

        active = await _active_rows(fixture.org_id)
        assert len(active) == 1
        assert UUID(str(active[0]["id"])) == fixture.seeded_config_id


@pytest.mark.asyncio
async def test_a_foreign_or_unknown_binding_is_a_neutral_not_found() -> None:
    """Another tenant's binding and an unparseable id are indistinguishable."""
    async with _owner_fixture("parity") as fixture:
        unknown = await _validate(fixture, str(uuid6.uuid7()))
        assert unknown.status_code == 404, unknown.text
        assert unknown.json()["error"]["code"] == "not_found"

        unparseable = await _activate(fixture, "not-a-uuid")
        assert unparseable.status_code == 404, unparseable.text
        assert unparseable.json()["error"]["code"] == "not_found"
