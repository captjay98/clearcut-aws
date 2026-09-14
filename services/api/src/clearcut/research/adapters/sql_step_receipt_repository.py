"""SQL adapter for persisting and querying research step receipts."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.research.ports.step_receipt_repository import (
    StepReceiptRecord,
    StepReceiptRepositoryPort,
)
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class SqlStepReceiptRepository(StepReceiptRepositoryPort):
    def __init__(self, session_scope_factory: SessionFactory | None = None) -> None:
        self._session_scope = session_scope_factory or session_scope

    async def record_step(
        self,
        *,
        receipt_id: UUID | None = None,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        item_id: UUID,
        job_id: UUID | None = None,
        attempt_number: int = 1,
        step_index: int,
        tool_name: str,
        tool_input_hash: str,
        tool_output_hash: str,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        status: str = "succeeded",
        duration_ms: int = 0,
        created_at: datetime | None = None,
    ) -> StepReceiptRecord:
        now = created_at or datetime.now(UTC)
        record_id = receipt_id or uuid6.uuid7()

        stmt = sa.text(
            """
                INSERT INTO research_step_receipts (
                    id, org_id, project_id, run_id, item_id, job_id,
                    attempt_number, step_index, tool_name,
                    tool_input_hash, tool_output_hash,
                    input_payload, output_payload,
                    status, duration_ms, created_at
                ) VALUES (
                    :id, :org_id, :project_id, :run_id, :item_id, :job_id,
                    :attempt_number, :step_index, :tool_name,
                    :tool_input_hash, :tool_output_hash,
                    :input_payload, :output_payload,
                    :status, :duration_ms, :created_at
                )
                """
        ).bindparams(
            sa.bindparam("input_payload", type_=sa.JSON()),
            sa.bindparam("output_payload", type_=sa.JSON()),
        )

        params: dict[str, Any] = {
            "id": str(record_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "run_id": str(run_id),
            "item_id": str(item_id),
            "job_id": str(job_id) if job_id is not None else None,
            "attempt_number": attempt_number,
            "step_index": step_index,
            "tool_name": tool_name,
            "tool_input_hash": tool_input_hash,
            "tool_output_hash": tool_output_hash,
            "input_payload": input_payload,
            "output_payload": output_payload,
            "status": status,
            "duration_ms": duration_ms,
            "created_at": now,
        }

        async with self._session_scope() as session:
            await session.execute(stmt, params)

        return StepReceiptRecord(
            id=record_id,
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            job_id=job_id,
            attempt_number=attempt_number,
            step_index=step_index,
            tool_name=tool_name,
            tool_input_hash=tool_input_hash,
            tool_output_hash=tool_output_hash,
            input_payload=input_payload,
            output_payload=output_payload,
            status=status,
            duration_ms=duration_ms,
            created_at=now,
        )

    async def get_receipt(
        self,
        *,
        receipt_id: UUID,
    ) -> StepReceiptRecord | None:
        stmt = sa.text(
            """
            SELECT id, org_id, project_id, run_id, item_id, job_id,
                   attempt_number, step_index, tool_name,
                   tool_input_hash, tool_output_hash,
                   input_payload, output_payload,
                   status, duration_ms, created_at
            FROM research_step_receipts
            WHERE id = :receipt_id
            """
        )
        async with self._session_scope() as session:
            result = await session.execute(stmt, {"receipt_id": str(receipt_id)})
            row = result.mappings().first()
            if row is None:
                return None
            return self._row_to_record(row)

    async def find_replay_receipt(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        tool_name: str,
        tool_input_hash: str,
    ) -> StepReceiptRecord | None:
        stmt = sa.text(
            """
            SELECT id, org_id, project_id, run_id, item_id, job_id,
                   attempt_number, step_index, tool_name,
                   tool_input_hash, tool_output_hash,
                   input_payload, output_payload,
                   status, duration_ms, created_at
            FROM research_step_receipts
            WHERE run_id = :run_id
              AND attempt_number = :attempt_number
              AND tool_name = :tool_name
              AND tool_input_hash = :tool_input_hash
            ORDER BY step_index ASC
            LIMIT 1
            """
        )
        async with self._session_scope() as session:
            result = await session.execute(
                stmt,
                {
                    "run_id": str(run_id),
                    "attempt_number": attempt_number,
                    "tool_name": tool_name,
                    "tool_input_hash": tool_input_hash,
                },
            )
            row = result.mappings().first()
            if row is None:
                return None
            return self._row_to_record(row)

    async def list_receipts_for_run(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        attempt_number: int | None = None,
    ) -> list[StepReceiptRecord]:
        query = """
            SELECT id, org_id, project_id, run_id, item_id, job_id,
                   attempt_number, step_index, tool_name,
                   tool_input_hash, tool_output_hash,
                   input_payload, output_payload,
                   status, duration_ms, created_at
            FROM research_step_receipts
            WHERE org_id = :org_id
              AND project_id = :project_id
              AND run_id = :run_id
        """
        params: dict[str, Any] = {
            "org_id": str(org_id),
            "project_id": str(project_id),
            "run_id": str(run_id),
        }
        if attempt_number is not None:
            query += " AND attempt_number = :attempt_number"
            params["attempt_number"] = attempt_number

        query += " ORDER BY step_index ASC"

        async with self._session_scope() as session:
            result = await session.execute(sa.text(query), params)
            return [self._row_to_record(row) for row in result.mappings().all()]

    async def count_steps_by_tool(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        attempt_number: int | None = None,
    ) -> dict[str, int]:
        query = """
            SELECT tool_name, COUNT(*) as cnt
            FROM research_step_receipts
            WHERE org_id = :org_id
              AND project_id = :project_id
              AND run_id = :run_id
        """
        params: dict[str, Any] = {
            "org_id": str(org_id),
            "project_id": str(project_id),
            "run_id": str(run_id),
        }
        if attempt_number is not None:
            query += " AND attempt_number = :attempt_number"
            params["attempt_number"] = attempt_number

        query += " GROUP BY tool_name"

        async with self._session_scope() as session:
            result = await session.execute(sa.text(query), params)
            return {str(row["tool_name"]): int(row["cnt"]) for row in result.mappings().all()}

    async def get_next_step_index(
        self,
        *,
        run_id: UUID,
        attempt_number: int = 1,
    ) -> int:
        stmt = sa.text(
            """
            SELECT COALESCE(MAX(step_index), -1) + 1 AS next_index
            FROM research_step_receipts
            WHERE run_id = :run_id
              AND attempt_number = :attempt_number
            """
        )
        async with self._session_scope() as session:
            result = await session.execute(
                stmt,
                {"run_id": str(run_id), "attempt_number": attempt_number},
            )
            val = result.scalar_one()
            return int(val)

    @classmethod
    def _row_to_record(cls, row: RowMapping) -> StepReceiptRecord:
        input_payload = row["input_payload"]
        if isinstance(input_payload, str):
            input_payload = json.loads(input_payload)

        output_payload = row["output_payload"]
        if isinstance(output_payload, str):
            output_payload = json.loads(output_payload)

        raw_created = row["created_at"]
        if isinstance(raw_created, str):
            created_at = datetime.fromisoformat(raw_created)
        else:
            created_at = raw_created

        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        return StepReceiptRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            project_id=UUID(str(row["project_id"])),
            run_id=UUID(str(row["run_id"])),
            item_id=UUID(str(row["item_id"])),
            job_id=UUID(str(row["job_id"])) if row["job_id"] else None,
            attempt_number=int(row["attempt_number"]),
            step_index=int(row["step_index"]),
            tool_name=str(row["tool_name"]),
            tool_input_hash=str(row["tool_input_hash"]),
            tool_output_hash=str(row["tool_output_hash"]),
            input_payload=input_payload,
            output_payload=output_payload,
            status=str(row["status"]),
            duration_ms=int(row["duration_ms"]),
            created_at=created_at,
        )
