"""Typed boundary for one bounded screenplay-element detection invocation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from clearcut.detection.domain.candidates import CandidateItem
from clearcut.scripts.domain.elements import ScriptElement


@dataclass(frozen=True)
class DetectionTokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class DetectionSafeError:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class DetectionAttemptMetadata:
    status: str
    requested_model: str
    returned_model: str | None
    response_id: str | None
    usage: DetectionTokenUsage
    latency_ms: int
    error: DetectionSafeError | None


@dataclass(frozen=True)
class DetectionSuccess:
    candidates: tuple[CandidateItem, ...]
    metadata: DetectionAttemptMetadata


@dataclass(frozen=True)
class DetectionFailure:
    error: DetectionSafeError
    attempt: DetectionAttemptMetadata


DetectionResult = DetectionSuccess | DetectionFailure


class ModelRuntimePort(Protocol):
    @property
    def requested_model(self) -> str: ...

    async def detect_element(self, element: ScriptElement) -> DetectionResult: ...
