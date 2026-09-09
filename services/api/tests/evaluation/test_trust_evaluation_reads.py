"""HTTP-level coverage for the project-scoped Trust evaluation read path.

The persisted judge rows are seeded directly so the tests can assert what the
read path derives, including the case where the stored ``headline_score`` column
disagrees with the verdicts beneath it.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.evaluation.domain.rubric import (
    DimensionStatus,
    JudgeDimension,
)
from clearcut.main import app
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.ports.job_repository import EnqueueJob
from httpx import ASGITransport, AsyncClient

_BASE = "/api/v1/organizations"
_HASH = "a" * 64


def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def _bootstrap(client: AsyncClient, suffix: str) -> tuple[UUID, UUID, UUID]:
    """Register an owner and return ``(org_id, project_id, actor_id)``."""
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Trust Reader {suffix}",
            "email": f"trust-{suffix}-{uuid4().hex[:8]}@example.com",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text
    context = await client.get("/api/v1/session-context")
    actor_id = UUID(context.json()["data"]["userId"])

    organization = await client.post(
        "/api/v1/organizations",
        json={"name": f"Trust Studio {suffix}", "slug": f"trust-{uuid4().hex[:8]}"},
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])

    project = await client.post(
        f"{_BASE}/{org_id}/projects",
        json={"title": f"Trust Project {suffix}"},
    )
    assert project.status_code == 201, project.text
    return org_id, UUID(project.json()["data"]["projectId"]), actor_id


async def _create_run(org_id: UUID, project_id: UUID, actor_id: UUID) -> UUID:
    enqueued = await SqlJobRepository().enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            job_type="detection",
            idempotency_key=f"trust-read:{uuid4()}",
            payload={"schemaVersion": 1},
            audit_action="detection.started",
            target_type="project",
            target_id=project_id,
        )
    )
    return enqueued.job.job_id


def _all_ten(
    scored: dict[JudgeDimension, float],
    *,
    failed: frozenset[JudgeDimension] = frozenset(),
    incomplete: frozenset[JudgeDimension] = frozenset(),
) -> list[tuple[JudgeDimension, DimensionStatus, float | None]]:
    """Build one verdict per rubric dimension, honouring the score constraint."""
    verdicts: list[tuple[JudgeDimension, DimensionStatus, float | None]] = []
    for dimension in JudgeDimension:
        if dimension in scored:
            verdicts.append((dimension, DimensionStatus.SCORED, scored[dimension]))
        elif dimension in failed:
            verdicts.append((dimension, DimensionStatus.FAILED, 0.0))
        elif dimension in incomplete:
            verdicts.append((dimension, DimensionStatus.INCOMPLETE, None))
        else:
            verdicts.append((dimension, DimensionStatus.NOT_APPLICABLE, None))
    return verdicts


async def _seed_evaluation(
    *,
    org_id: UUID,
    project_id: UUID,
    run_id: UUID,
    verdicts: list[tuple[JudgeDimension, DimensionStatus, float | None]],
    stored_headline_score: float | None,
    stored_scored_count: int,
    stage: str = "detection",
    blockers_count: int = 0,
    critique: str = "Bounded critique of the seeded run.",
    gates: tuple[tuple[str, bool, str, str], ...] = (),
) -> UUID:
    evaluation_id = uuid6.uuid7()
    created_at = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                """
                INSERT INTO agent_evaluations (
                    id, org_id, project_id, run_id, stage,
                    headline_score, scored_dimensions_count, blockers_count,
                    created_at, critique, rubric_version, prompt_version,
                    policy_version, requested_model, returned_model,
                    input_sha256, response_id, input_tokens, output_tokens,
                    total_tokens, latency_ms, repair_count, attempt_group_id
                ) VALUES (
                    :id, :org_id, :project_id, :run_id, :stage,
                    :headline_score, :scored_dimensions_count, :blockers_count,
                    :created_at, :critique, 'rubric-2.4', 'cc-research-17',
                    'policy-3.2', 'gemini-3.1-pro-preview', 'gemini-3.1-pro-preview',
                    :input_sha256, 'resp-1', 900, 300,
                    1200, 4200, 0, :attempt_group_id
                )
                """
            ),
            {
                "id": str(evaluation_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "run_id": str(run_id),
                "stage": stage,
                "headline_score": stored_headline_score,
                "scored_dimensions_count": stored_scored_count,
                "blockers_count": blockers_count,
                "created_at": created_at,
                "critique": critique,
                "input_sha256": _HASH,
                "attempt_group_id": str(uuid6.uuid7()),
            },
        )
        await session.execute(
            sa.text(
                """
                INSERT INTO judge_verdicts (
                    id, evaluation_id, dimension, status, score,
                    rationale, created_at, org_id, project_id
                ) VALUES (
                    :id, :evaluation_id, :dimension, :status, :score,
                    :rationale, :created_at, :org_id, :project_id
                )
                """
            ),
            [
                {
                    "id": str(uuid6.uuid7()),
                    "evaluation_id": str(evaluation_id),
                    "dimension": dimension.value,
                    "status": status.value,
                    "score": score,
                    "rationale": f"Seeded rationale for {dimension.value}.",
                    # Distinct timestamps keep the returned dimension order stable.
                    "created_at": created_at + timedelta(milliseconds=ordinal),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                }
                for ordinal, (dimension, status, score) in enumerate(verdicts)
            ],
        )
        if gates:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO deterministic_gate_results (
                        id, org_id, project_id, run_id, candidate_id,
                        gate_name, passed, severity, details, created_at
                    ) VALUES (
                        :id, :org_id, :project_id, :run_id, NULL,
                        :gate_name, :passed, :severity, :details, :created_at
                    )
                    """
                ),
                [
                    {
                        "id": str(uuid6.uuid7()),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "run_id": str(run_id),
                        "gate_name": gate_name,
                        "passed": passed,
                        "severity": severity,
                        "details": details,
                        "created_at": created_at + timedelta(milliseconds=ordinal),
                    }
                    for ordinal, (gate_name, passed, severity, details) in enumerate(
                        gates
                    )
                ],
            )
    return evaluation_id


@pytest.mark.asyncio
async def test_headline_score_is_derived_and_overrides_a_wrong_stored_value() -> None:
    """The headline is the mean of the verdicts, not the stored column."""
    async with _client() as client:
        org_id, project_id, actor_id = await _bootstrap(client, "derive")
        run_id = await _create_run(org_id, project_id, actor_id)
        # 88 + 89 + 88 + 89 = 354 over four dimensions = 88.5, which rounds
        # half-up to 89 the way the canonical mock's Math.round does.
        evaluation_id = await _seed_evaluation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            verdicts=_all_ten(
                {
                    JudgeDimension.DETECTION_RECALL: 88.0,
                    JudgeDimension.APPROPRIATE_UNCERTAINTY: 89.0,
                    JudgeDimension.LEGAL_BOUNDARY: 88.0,
                    JudgeDimension.TOOL_EFFICIENCY: 89.0,
                }
            ),
            # Deliberately wrong stored values that the read must not echo.
            stored_headline_score=12.0,
            stored_scored_count=99,
            gates=(
                ("SpanBoundaryGate", True, "info", "Span boundaries valid"),
                ("LegalCertaintyGate", True, "info", "Legal boundaries respected"),
            ),
        )

        detail = await client.get(
            f"{_BASE}/{org_id}/projects/{project_id}/evaluations/{evaluation_id}"
        )
        assert detail.status_code == 200, detail.text
        data = detail.json()["data"]

    assert data["headlineScore"] == 89
    assert data["headlineScore"] != 12
    assert data["scoredDimensionsCount"] == 4
    assert data["evaluationId"] == str(evaluation_id)
    assert data["orgId"] == str(org_id)
    assert data["projectId"] == str(project_id)
    assert data["runId"] == str(run_id)
    assert data["stage"] == "detection"
    assert data["blockersCount"] == 0
    assert data["critique"] == "Bounded critique of the seeded run."
    assert len(data["dimensions"]) == len(JudgeDimension)

    # The headline is reproducible from exactly the rows printed beneath it.
    contributing = [
        dimension["score"]
        for dimension in data["dimensions"]
        if dimension["score"] is not None
    ]
    assert len(contributing) == data["scoredDimensionsCount"]
    assert data["headlineScore"] == round(sum(contributing) / len(contributing) + 1e-9)

    assert data["gates"] == [
        {
            "gateName": "LegalCertaintyGate",
            "passed": True,
            "severity": "info",
            "details": "Legal boundaries respected",
        },
        {
            "gateName": "SpanBoundaryGate",
            "passed": True,
            "severity": "info",
            "details": "Span boundaries valid",
        },
    ]
    assert data["provenance"] == {
        "rubricVersion": "rubric-2.4",
        "promptVersion": "cc-research-17",
        "policyVersion": "policy-3.2",
        "requestedModel": "gemini-3.1-pro-preview",
        "returnedModel": "gemini-3.1-pro-preview",
        "inputSha256": _HASH,
        "latencyMs": 4200,
        "totalTokens": 1200,
        "repairCount": 0,
    }


@pytest.mark.asyncio
async def test_unscored_dimensions_serialize_null_and_stay_out_of_the_mean() -> None:
    """``incomplete`` and ``not_applicable`` are null; ``failed`` is a real zero."""
    async with _client() as client:
        org_id, project_id, actor_id = await _bootstrap(client, "nulls")
        run_id = await _create_run(org_id, project_id, actor_id)
        evaluation_id = await _seed_evaluation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            verdicts=_all_ten(
                {JudgeDimension.DETECTION_RECALL: 100.0},
                failed={JudgeDimension.LEGAL_BOUNDARY},
                incomplete={JudgeDimension.TOOL_EFFICIENCY},
            ),
            stored_headline_score=100.0,
            stored_scored_count=1,
            blockers_count=1,
        )

        detail = await client.get(
            f"{_BASE}/{org_id}/projects/{project_id}/evaluations/{evaluation_id}"
        )
        assert detail.status_code == 200, detail.text
        dimensions = {
            dimension["dimension"]: dimension
            for dimension in detail.json()["data"]["dimensions"]
        }
        data = detail.json()["data"]

    incomplete = dimensions[JudgeDimension.TOOL_EFFICIENCY.value]
    assert incomplete["status"] == "incomplete"
    assert incomplete["score"] is None
    assert incomplete["score"] != 0

    not_applicable = dimensions[JudgeDimension.CLAIM_GROUNDING.value]
    assert not_applicable["status"] == "not_applicable"
    assert not_applicable["score"] is None
    assert not_applicable["score"] != 0

    failed = dimensions[JudgeDimension.LEGAL_BOUNDARY.value]
    assert failed["status"] == "failed"
    assert failed["score"] == 0

    # A judged 100 and a judged 0 average to 50. The seven unscored dimensions
    # neither drag the mean down nor pad the divisor.
    assert data["scoredDimensionsCount"] == 2
    assert data["headlineScore"] == 50
    assert data["blockersCount"] == 1


@pytest.mark.asyncio
async def test_foreign_unknown_and_malformed_identifiers_share_one_answer() -> None:
    """Cross-tenant, unknown, and unparseable identifiers are indistinguishable."""
    async with _client() as owner_client:
        owner_org, owner_project, owner_actor = await _bootstrap(owner_client, "owner")
        owner_run = await _create_run(owner_org, owner_project, owner_actor)
        foreign_evaluation_id = await _seed_evaluation(
            org_id=owner_org,
            project_id=owner_project,
            run_id=owner_run,
            verdicts=_all_ten({JudgeDimension.DETECTION_RECALL: 91.0}),
            stored_headline_score=91.0,
            stored_scored_count=1,
        )

    async with _client() as outsider_client:
        other_org, other_project, _actor = await _bootstrap(outsider_client, "other")
        prefix = f"{_BASE}/{other_org}/projects/{other_project}/evaluations"
        foreign = await outsider_client.get(f"{prefix}/{foreign_evaluation_id}")
        unknown = await outsider_client.get(f"{prefix}/{uuid6.uuid7()}")
        malformed = await outsider_client.get(f"{prefix}/not-a-uuid")

        # The other organization's project is also invisible by path.
        cross_scope = await outsider_client.get(
            f"{_BASE}/{other_org}/projects/{owner_project}/evaluations"
        )

    for response in (foreign, unknown, malformed):
        assert response.status_code == 404, response.text
        error = response.json()["error"]
        assert error["code"] == "not_found"
        assert error["message"] == "Evaluation not found"
        # Nothing about the requested identifier leaks back.
        assert str(foreign_evaluation_id) not in response.text
        assert "not-a-uuid" not in response.text

    assert foreign.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert malformed.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert cross_scope.status_code == 404, cross_scope.text


@pytest.mark.asyncio
async def test_job_id_filter_selects_one_run() -> None:
    async with _client() as client:
        org_id, project_id, actor_id = await _bootstrap(client, "filter")
        first_run = await _create_run(org_id, project_id, actor_id)
        second_run = await _create_run(org_id, project_id, actor_id)
        first_evaluation = await _seed_evaluation(
            org_id=org_id,
            project_id=project_id,
            run_id=first_run,
            verdicts=_all_ten({JudgeDimension.DETECTION_RECALL: 70.0}),
            stored_headline_score=70.0,
            stored_scored_count=1,
        )
        second_evaluation = await _seed_evaluation(
            org_id=org_id,
            project_id=project_id,
            run_id=second_run,
            verdicts=_all_ten({JudgeDimension.DETECTION_RECALL: 80.0}),
            stored_headline_score=80.0,
            stored_scored_count=1,
        )

        prefix = f"{_BASE}/{org_id}/projects/{project_id}/evaluations"
        everything = await client.get(prefix)
        filtered = await client.get(prefix, params={"jobId": str(second_run)})
        foreign_filter = await client.get(prefix, params={"jobId": str(uuid6.uuid7())})
        malformed_filter = await client.get(prefix, params={"jobId": "not-a-uuid"})

    assert everything.status_code == 200, everything.text
    assert {row["evaluationId"] for row in everything.json()["data"]} == {
        str(first_evaluation),
        str(second_evaluation),
    }

    assert filtered.status_code == 200, filtered.text
    assert [row["evaluationId"] for row in filtered.json()["data"]] == [
        str(second_evaluation)
    ]
    assert filtered.json()["data"][0]["runId"] == str(second_run)
    assert filtered.json()["data"][0]["headlineScore"] == 80

    # A run with no evaluation and an unparseable run identifier are both simply
    # empty rather than an error that would imply the capability is broken.
    assert foreign_filter.status_code == 200
    assert foreign_filter.json()["data"] == []
    assert malformed_filter.status_code == 200
    assert malformed_filter.json()["data"] == []


@pytest.mark.asyncio
async def test_project_without_persisted_evaluations_returns_an_empty_array() -> None:
    """Absence is an empty collection, never a 503 outage."""
    async with _client() as client:
        org_id, project_id, _actor = await _bootstrap(client, "empty")
        listed = await client.get(f"{_BASE}/{org_id}/projects/{project_id}/evaluations")

    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == []
    assert listed.json()["meta"]["requestId"]


@pytest.mark.asyncio
async def test_trust_reads_require_authentication() -> None:
    async with _client() as client:
        org_id, project_id, _actor = await _bootstrap(client, "authn")

    async with _client() as anonymous:
        listed = await anonymous.get(
            f"{_BASE}/{org_id}/projects/{project_id}/evaluations"
        )
        detail = await anonymous.get(
            f"{_BASE}/{org_id}/projects/{project_id}/evaluations/{uuid6.uuid7()}"
        )

    assert listed.status_code == 401, listed.text
    assert detail.status_code == 401, detail.text
