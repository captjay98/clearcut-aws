"""SQL authority for durable, scoped selective-rescan stage checkpoints.

Each stage checkpoint is a stage-level (no-target) row in
``selective_rescan_checkpoints``. Writes are idempotent on the migration-0035
``uq_selective_rescan_checkpoints_job_stage`` partial-unique key
(``script_version_id IS NULL AND item_id IS NULL``), so a replay of an
already-succeeded stage writes no duplicate row and never re-runs its work. All
scope is composite ``(org_id, project_id, job_id)`` and every read is filtered by
that scope; a missing scope simply returns no rows rather than leaking a foreign
tenant's checkpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import uuid6

from clearcut.database import session_scope
from clearcut.rescan.application.models import (
    ItemId,
    OrgId,
    ProjectId,
    RescanStage,
)

_STAGE_RANK = {stage: index for index, stage in enumerate(RescanStage)}


class SqlSelectiveRescanRepository:
    """Persists and reads per-stage checkpoints for a durable rescan job."""

    async def load_stage_history(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
    ) -> list[tuple[RescanStage, str]]:
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT stage, status FROM selective_rescan_checkpoints "
                            "WHERE org_id = :org_id AND project_id = :project_id "
                            "AND job_id = :job_id "
                            "AND script_version_id IS NULL AND item_id IS NULL"
                        ),
                        {
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "job_id": str(job_id),
                        },
                    )
                )
                .mappings()
                .all()
            )
        history = [(RescanStage(str(row["stage"])), str(row["status"])) for row in rows]
        history.sort(key=lambda entry: _STAGE_RANK[entry[0]])
        return history

    async def completed_stages(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
    ) -> frozenset[RescanStage]:
        history = await self.load_stage_history(org_id=org_id, project_id=project_id, job_id=job_id)
        return frozenset(stage for stage, status in history if status == "succeeded")

    async def record_stage_success(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
        stage: RescanStage,
        attempt_number: int,
        result: dict[str, Any],
    ) -> None:
        await self._insert_terminal_checkpoint(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            stage=stage,
            attempt_number=attempt_number,
            status="succeeded",
            result=result,
            safe_error=None,
        )

    async def record_stage_failure(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
        stage: RescanStage,
        attempt_number: int,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> None:
        await self._insert_terminal_checkpoint(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            stage=stage,
            attempt_number=attempt_number,
            status="failed",
            result=None,
            safe_error={
                "code": error_code,
                "message": error_message,
                "retryable": retryable,
            },
        )

    async def _insert_terminal_checkpoint(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
        stage: RescanStage,
        attempt_number: int,
        status: str,
        result: dict[str, Any] | None,
        safe_error: dict[str, Any] | None,
    ) -> None:
        if attempt_number <= 0:
            raise ValueError("Checkpoint attempt number must be positive.")
        now = datetime.now(UTC)
        # Stage-level (no-target) checkpoint: script_version_id and item_id stay
        # NULL so the partial-unique job/stage key guarantees exactly one row per
        # stage across retries. ``ON CONFLICT DO NOTHING`` makes a replay a no-op.
        statement = sa.text(
            """
            INSERT INTO selective_rescan_checkpoints (
                id, org_id, project_id, job_id, stage,
                script_version_id, item_id, status, result, safe_error,
                attempt_number, created_at, completed_at
            ) VALUES (
                :id, :org_id, :project_id, :job_id, :stage,
                NULL, NULL, :status, :result, :safe_error,
                :attempt_number, :created_at, :completed_at
            )
            ON CONFLICT DO NOTHING
            """
        ).bindparams(
            sa.bindparam("result", type_=sa.JSON(none_as_null=True)),
            sa.bindparam("safe_error", type_=sa.JSON(none_as_null=True)),
        )
        async with session_scope() as session:
            await session.execute(
                statement,
                {
                    "id": str(uuid6.uuid7()),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "job_id": str(job_id),
                    "stage": stage.value,
                    "status": status,
                    "result": result,
                    "safe_error": safe_error,
                    "attempt_number": attempt_number,
                    "created_at": now,
                    "completed_at": now,
                },
            )


__all__ = ["SqlSelectiveRescanRepository"]
