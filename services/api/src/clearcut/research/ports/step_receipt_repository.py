"""Typed boundary for research step receipt persistence and replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


def compute_canonical_hash(payload: Any) -> str:
    """Compute deterministic SHA-256 hash of a payload dictionary or scalar."""
    if payload is None:
        serialized = "null"
    elif isinstance(payload, (str, int, float, bool)):
        serialized = json.dumps(payload)
    else:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StepReceiptRecord:
    id: UUID
    org_id: UUID
    project_id: UUID
    run_id: UUID
    item_id: UUID
    job_id: UUID | None
    attempt_number: int
    step_index: int
    tool_name: str
    tool_input_hash: str
    tool_output_hash: str
    input_payload: dict[str, Any] | None
    output_payload: dict[str, Any] | None
    status: str
    duration_ms: int
    created_at: datetime


class StepReceiptRepositoryPort(Protocol):
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
        """Persist an immutable step receipt record."""
        ...

    async def get_receipt(
        self,
        *,
        receipt_id: UUID,
    ) -> StepReceiptRecord | None:
        """Fetch a specific step receipt by its ID."""
        ...

    async def find_replay_receipt(
        self,
        *,
        run_id: UUID,
        attempt_number: int,
        tool_name: str,
        tool_input_hash: str,
    ) -> StepReceiptRecord | None:
        """Find an existing receipt matching the tool and input hash for replay."""
        ...

    async def list_receipts_for_run(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        attempt_number: int | None = None,
    ) -> list[StepReceiptRecord]:
        """List receipts for a given research run in ascending step order."""
        ...

    async def count_steps_by_tool(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        attempt_number: int | None = None,
    ) -> dict[str, int]:
        """Return a mapping of tool_name to execution count for the run."""
        ...

    async def get_next_step_index(
        self,
        *,
        run_id: UUID,
        attempt_number: int = 1,
    ) -> int:
        """Return the next available step index (max step_index + 1, or 0 if none)."""
        ...
