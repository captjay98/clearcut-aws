import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6
from clearcut.detection.domain.candidates import CandidateItem


class GateSeverity(StrEnum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class GateResult:
    gate_id: UUID
    candidate_id: UUID
    gate_name: str
    passed: bool
    severity: GateSeverity
    details: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        candidate_id: UUID,
        gate_name: str,
        passed: bool,
        severity: GateSeverity,
        details: str,
    ) -> "GateResult":
        return cls(
            gate_id=uuid6.uuid7(),
            candidate_id=candidate_id,
            gate_name=gate_name,
            passed=passed,
            severity=severity,
            details=details,
            created_at=datetime.now(UTC),
        )


class SpanBoundaryGate:
    def evaluate(self, candidate: CandidateItem, element_text: str) -> GateResult:
        if candidate.span_start < 0 or candidate.span_end > len(element_text):
            return GateResult.create(
                candidate_id=candidate.item_id,
                gate_name="SpanBoundaryGate",
                passed=False,
                severity=GateSeverity.BLOCKER,
                details=(
                    f"Span ({candidate.span_start}, {candidate.span_end}) is "
                    f"out of bounds for text len {len(element_text)}"
                ),
            )
        if candidate.span_start >= candidate.span_end:
            return GateResult.create(
                candidate_id=candidate.item_id,
                gate_name="SpanBoundaryGate",
                passed=False,
                severity=GateSeverity.BLOCKER,
                details="Span start must be strictly less than span end",
            )
        return GateResult.create(
            candidate_id=candidate.item_id,
            gate_name="SpanBoundaryGate",
            passed=True,
            severity=GateSeverity.INFO,
            details="Span boundaries valid",
        )


LEGAL_CERTAINTY_PATTERNS = re.compile(
    r"\b(100%|guaranteed?|completely|definitely)\s+(?:\w+\s+)?"
    r"(cleared|safe|free of liability|legal)\b|"
    r"\b(as your lawyer|legal advice|no lawsuit possible|legally cleared)\b",
    re.IGNORECASE,
)


class LegalCertaintyGate:
    def evaluate(self, candidate: CandidateItem) -> GateResult:
        if LEGAL_CERTAINTY_PATTERNS.search(candidate.rationale):
            return GateResult.create(
                candidate_id=candidate.item_id,
                gate_name="LegalCertaintyGate",
                passed=False,
                severity=GateSeverity.BLOCKER,
                details="Model rationale makes impermissible absolute legal clearance claims",
            )
        return GateResult.create(
            candidate_id=candidate.item_id,
            gate_name="LegalCertaintyGate",
            passed=True,
            severity=GateSeverity.INFO,
            details="Legal boundaries respected",
        )


INJECTION_PATTERNS = re.compile(
    r"\b(ignore\s+(previous|all)\s+instructions|system\s+prompt|developer\s+mode)\b",
    re.IGNORECASE,
)


class PromptInjectionGate:
    def evaluate(self, candidate: CandidateItem) -> GateResult:
        has_injection = (
            INJECTION_PATTERNS.search(candidate.rationale) is not None
            or INJECTION_PATTERNS.search(candidate.text) is not None
        )
        if has_injection:
            return GateResult.create(
                candidate_id=candidate.item_id,
                gate_name="PromptInjectionGate",
                passed=False,
                severity=GateSeverity.BLOCKER,
                details="Prompt injection tokens detected in candidate output",
            )
        return GateResult.create(
            candidate_id=candidate.item_id,
            gate_name="PromptInjectionGate",
            passed=True,
            severity=GateSeverity.INFO,
            details="No injection tokens found",
        )


def run_deterministic_gates(
    candidates: list[CandidateItem],
    element_texts: dict[UUID, str],
) -> list[GateResult]:
    span_gate = SpanBoundaryGate()
    legal_gate = LegalCertaintyGate()
    injection_gate = PromptInjectionGate()

    results: list[GateResult] = []
    for c in candidates:
        text = element_texts.get(c.element_id, "")
        results.append(span_gate.evaluate(c, text))
        results.append(legal_gate.evaluate(c))
        results.append(injection_gate.evaluate(c))

    return results
