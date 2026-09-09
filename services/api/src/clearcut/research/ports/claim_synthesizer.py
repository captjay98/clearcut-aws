"""Typed boundary for bounded per-snapshot evidence claim synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from clearcut.research.domain.claims import EvidenceStance


@dataclass(frozen=True)
class ClaimSynthesisRequest:
    item_id: UUID
    snapshot_id: UUID
    category: str
    item_text: str
    url: str
    publisher: str
    excerpt: str
    correlation_id: UUID
    research_run_id: UUID


@dataclass(frozen=True)
class SynthesisTokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class SynthesisSafeError:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class SynthesisAttemptMetadata:
    status: str
    requested_model: str
    returned_model: str | None
    response_id: str | None
    usage: SynthesisTokenUsage
    latency_ms: int
    error: SynthesisSafeError | None


@dataclass(frozen=True)
class ClaimSynthesisSuccess:
    claim_text: str
    stance: EvidenceStance
    metadata: SynthesisAttemptMetadata


@dataclass(frozen=True)
class ClaimSynthesisFailure:
    error: SynthesisSafeError
    attempt: SynthesisAttemptMetadata


ClaimSynthesisResult = ClaimSynthesisSuccess | ClaimSynthesisFailure


class ClaimSynthesizerPort(Protocol):
    @property
    def requested_model(self) -> str: ...

    async def synthesize_claim(
        self,
        request: ClaimSynthesisRequest,
    ) -> ClaimSynthesisResult: ...
