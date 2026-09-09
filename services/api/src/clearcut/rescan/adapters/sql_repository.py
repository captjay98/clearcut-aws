"""SQL authority for durable, scoped selective-rescan stage checkpoints.

Each stage checkpoint is a stage-level (no-target) row in
``selective_rescan_checkpoints``. Writes are idempotent on the migration-0035
``uq_selective_rescan_checkpoints_job_stage`` partial-unique key
(``script_version_id IS NULL AND item_id IS NULL``), so a replay of an
already-succeeded stage writes no duplicate row and never re-runs its work. All
scope is composite ``(org_id, project_id, job_id)`` and every read is filtered by
that scope; a missing scope simply returns no rows rather than leaking a foreign
tenant's checkpoints.

A succeeded checkpoint's ``result`` also carries the stage's replayable OUTPUT
(carried item mappings, carried-evidence edge count, affected/added item ids) in
the existing JSON column, because a resumed run needs those outputs as the next
stage's inputs. The identities involved — successor item ids and freshly detected
added-item ids — are generated while the stage runs and cannot be recomputed by a
later attempt without repeating the write or the child provider work, so they are
read back rather than re-derived.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import uuid6

from clearcut.database import session_scope
from clearcut.rescan.application.models import (
    ADDED_ITEM_IDS_KEY,
    AFFECTED_ITEM_IDS_KEY,
    CARRIED_EVIDENCE_EDGE_COUNT_KEY,
    CARRIED_MAPPINGS_KEY,
    CarriedItemMapping,
    ItemId,
    OrgId,
    ProjectId,
    RescanSafeError,
    RescanStage,
    RestoredRescanProgress,
    decode_carried_mappings,
    decode_edge_count,
    decode_item_ids,
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
        rows = await self._load_stage_rows(org_id=org_id, project_id=project_id, job_id=job_id)
        return [(stage, status) for stage, status, _result in rows]

    async def completed_stages(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
    ) -> frozenset[RescanStage]:
        history = await self.load_stage_history(org_id=org_id, project_id=project_id, job_id=job_id)
        return frozenset(stage for stage, status in history if status == "succeeded")

    async def load_restored_progress(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
    ) -> RestoredRescanProgress:
        rows = await self._load_stage_rows(org_id=org_id, project_id=project_id, job_id=job_id)
        completed: set[RescanStage] = set()
        unrecoverable: set[RescanStage] = set()
        carried_mappings: tuple[CarriedItemMapping, ...] = ()
        carried_evidence_edge_count = 0
        affected_item_ids: tuple[ItemId, ...] = ()
        added_item_ids: tuple[ItemId, ...] = ()
        for stage, status, result in rows:
            if status != "succeeded":
                continue
            completed.add(stage)
            # Only the three stages with a downstream output need restoring; the
            # remaining stages consume nothing from a predecessor.
            try:
                if stage is RescanStage.MATERIALIZING_LINEAGE:
                    carried_mappings = decode_carried_mappings(result.get(CARRIED_MAPPINGS_KEY))
                elif stage is RescanStage.CARRYING_EVIDENCE:
                    carried_evidence_edge_count = decode_edge_count(
                        result.get(CARRIED_EVIDENCE_EDGE_COUNT_KEY)
                    )
                elif stage is RescanStage.DETECTING_AFFECTED_PASSAGES:
                    affected_item_ids = decode_item_ids(
                        result.get(AFFECTED_ITEM_IDS_KEY), detail="affected item ids"
                    )
                    added_item_ids = decode_item_ids(
                        result.get(ADDED_ITEM_IDS_KEY), detail="added item ids"
                    )
            except RescanSafeError:
                # A stage recorded as succeeded whose output cannot be restored is
                # never presented as empty: reporting it lets the caller fail the
                # job closed instead of running later stages against nothing.
                unrecoverable.add(stage)
        return RestoredRescanProgress(
            completed_stages=frozenset(completed),
            unrecoverable_stages=frozenset(unrecoverable),
            carried_mappings=carried_mappings,
            carried_evidence_edge_count=carried_evidence_edge_count,
            affected_item_ids=affected_item_ids,
            added_item_ids=added_item_ids,
        )

    async def _load_stage_rows(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
    ) -> list[tuple[RescanStage, str, dict[str, Any]]]:
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT stage, status, result FROM selective_rescan_checkpoints "
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
        history = [
            (
                RescanStage(str(row["stage"])),
                str(row["status"]),
                self._json_object(row["result"]),
            )
            for row in rows
        ]
        history.sort(key=lambda entry: _STAGE_RANK[entry[0]])
        return history

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        # The stage result is read through raw SQL, so the driver may hand back
        # either decoded JSON (PostgreSQL) or the stored text (SQLite).
        if value is None:
            return {}
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}

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
