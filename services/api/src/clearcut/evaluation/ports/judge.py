"""Typed boundary for bounded, non-governing model judge invocations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from clearcut.detection.domain.candidates import CandidateItem
from clearcut.evaluation.domain.gates import GateResult
from clearcut.evaluation.domain.rubric import EvaluationStage, JudgeVerdict


@dataclass(frozen=True)
class JudgeBindings:
    rubric_version: str
    prompt_version: str
    policy_version: str
    input_sha256: str


@dataclass(frozen=True)
class ResearchEvidence:
    snapshot_id: UUID
    url: str
    publisher: str
    excerpt: str
    authority_tier: str
    stance: str
    claim_text: str


@dataclass(frozen=True)
class JudgeRequest:
    org_id: UUID
    project_id: UUID
    run_id: UUID
    stage: EvaluationStage | str
    candidates: tuple[CandidateItem, ...]
    gate_results: tuple[GateResult, ...]
    bindings: JudgeBindings
    research_evidence: tuple[ResearchEvidence, ...] = ()

    def __post_init__(self) -> None:
        try:
            stage = EvaluationStage(self.stage)
        except ValueError as error:
            raise ValueError(f"Unknown evaluation stage: {self.stage!r}") from error
        object.__setattr__(self, "stage", stage)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class JudgeSafeError:
    code: str
    message: str
    retryable: bool


def validate_judge_bindings(bindings: JudgeBindings) -> JudgeSafeError | None:
    if any(
        not value.strip()
        for value in (
            bindings.rubric_version,
            bindings.prompt_version,
            bindings.policy_version,
        )
    ):
        return JudgeSafeError(
            code="invalid_request",
            message="Judge invocation bindings are incomplete.",
            retryable=False,
        )
    if len(bindings.input_sha256) != 64 or any(
        character not in "0123456789abcdef"
        for character in bindings.input_sha256.lower()
    ):
        return JudgeSafeError(
            code="invalid_request",
            message="Judge input binding is invalid.",
            retryable=False,
        )
    return None


@dataclass(frozen=True)
class JudgeAttemptMetadata:
    ordinal: int
    status: str
    returned_model: str | None
    response_id: str | None
    usage: TokenUsage
    latency_ms: int
    error: JudgeSafeError | None


@dataclass(frozen=True)
class JudgeInvocationMetadata:
    requested_model: str
    returned_model: str | None
    response_id: str | None
    usage: TokenUsage
    latency_ms: int
    repair_count: int
    attempts: tuple[JudgeAttemptMetadata, ...]


@dataclass(frozen=True)
class JudgeSuccess:
    verdicts: tuple[JudgeVerdict, ...]
    critique: str
    metadata: JudgeInvocationMetadata


@dataclass(frozen=True)
class JudgeFailure:
    error: JudgeSafeError
    requested_model: str
    attempts: tuple[JudgeAttemptMetadata, ...]


JudgeResult = JudgeSuccess | JudgeFailure


class JudgePort(Protocol):
    @property
    def requested_model(self) -> str: ...

    async def evaluate(self, request: JudgeRequest) -> JudgeResult: ...
