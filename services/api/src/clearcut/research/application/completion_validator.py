"""Deterministic post-agent completion validator for research runs.

Enforces five mandatory invariants following agentic workflow completion:
1. Mandatory Search: Evidence claims cannot be admitted without at least one
   successful search_evidence tool step.
2. Authentic Citations: Citations must link exclusively to authentic SourceSnapshot
   records belonging to the scoped (org_id, project_id, run_id).
3. Zero-Evidence Invariant: Zero-evidence items remain strictly 'unresolved'
   (cleared=False, needs_human_review=True).
4. Anti-Self-Certification: Strips and overrides any LLM attempts to claim legal clearance.
5. Error Visibility: Failures or refusals result in explicit error outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.research.ports.step_receipt_repository import StepReceiptRecord


class CompletionValidationError(Exception):
    """Base exception for deterministic completion validation failures."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MissingMandatorySearchError(CompletionValidationError):
    """Raised when claims or completion are attempted without executing search_evidence."""

    def __init__(self, message: str = "Mandatory search_evidence tool was not executed.") -> None:
        super().__init__("missing_mandatory_search", message)


class UnauthenticatedCitationError(CompletionValidationError):
    """Raised when a cited snapshot ID does not exist in the scoped run."""

    def __init__(
        self, message: str = "Citation does not link to authentic source snapshot in this run."
    ) -> None:
        super().__init__("unauthenticated_citation", message)


class IllegalSelfCertificationError(CompletionValidationError):
    """Raised when agent attempts unauthorized self-clearance."""

    def __init__(
        self, message: str = "Autonomous clearance is forbidden; items require human review."
    ) -> None:
        super().__init__("illegal_self_certification", message)


@dataclass(frozen=True)
class ValidationOutcome:
    valid: bool
    review_status: str
    reason: str
    needs_human_review: bool
    cleared: bool
    error: str | None = None
    sanitized_summary: dict[str, Any] | None = None


class DeterministicCompletionValidator:
    """Enforces post-agent verification rules against DB state and step receipts."""

    async def validate(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        item_id: UUID,
        step_receipts: list[StepReceiptRecord],
        claims: list[Any] | None = None,
        raw_summary: dict[str, Any] | None = None,
        raise_exc: bool = True,
    ) -> ValidationOutcome:
        claims = claims or []
        summary = dict(raw_summary) if raw_summary else {}

        # 1. Check for agent refusal or failure in summary
        if summary.get("refused") is True or summary.get("error"):
            return ValidationOutcome(
                valid=False,
                review_status="unresolved",
                reason="agent_refusal_or_error",
                needs_human_review=True,
                cleared=False,
                error=str(summary.get("error") or "Agent refused or failed to research item"),
                sanitized_summary=summary,
            )

        # 2. Rule 1: Mandatory Search Enforcement
        search_receipts = [
            r for r in step_receipts if r.tool_name == "search_evidence" and r.status == "succeeded"
        ]

        if len(search_receipts) == 0:
            if raise_exc:
                raise MissingMandatorySearchError(
                    "Agent executed no successful search_evidence calls."
                )
            return ValidationOutcome(
                valid=False,
                review_status="unresolved",
                reason="missing_mandatory_search",
                needs_human_review=True,
                cleared=False,
                error="missing_mandatory_search",
                sanitized_summary=summary,
            )

        # 3. Rule 2: Authentic SourceSnapshot Citations
        cited_snapshot_ids: set[UUID] = set()
        for claim in claims:
            if hasattr(claim, "snapshot_id") and claim.snapshot_id is not None:
                s_id = claim.snapshot_id
            elif (
                isinstance(claim, dict)
                and "snapshot_id" in claim
                and claim["snapshot_id"] is not None
            ):
                s_id = claim["snapshot_id"]
            else:
                if raise_exc:
                    raise CompletionValidationError(
                        "invalid_claim",
                        f"Claim must have a valid snapshot_id: {claim!r}",
                    )
                return ValidationOutcome(
                    valid=False,
                    review_status="unresolved",
                    reason="invalid_claim",
                    needs_human_review=True,
                    cleared=False,
                    error=f"Claim must have a valid snapshot_id: {claim!r}",
                    sanitized_summary=summary,
                )
            if isinstance(s_id, UUID):
                cited_snapshot_ids.add(s_id)
            else:
                try:
                    cited_snapshot_ids.add(UUID(str(s_id)))
                except Exception as exc:
                    if raise_exc:
                        raise CompletionValidationError(
                            "invalid_claim",
                            f"Claim has unparseable snapshot_id: {s_id!r}",
                        ) from exc
                    return ValidationOutcome(
                        valid=False,
                        review_status="unresolved",
                        reason="invalid_claim",
                        needs_human_review=True,
                        cleared=False,
                        error=f"Claim has unparseable snapshot_id: {s_id!r}",
                        sanitized_summary=summary,
                    )

        # Also inspect summary if snapshots are cited there
        if "cited_snapshot_ids" in summary:
            for s_id in summary["cited_snapshot_ids"]:
                if isinstance(s_id, UUID):
                    cited_snapshot_ids.add(s_id)
                else:
                    try:
                        cited_snapshot_ids.add(UUID(str(s_id)))
                    except Exception as exc:
                        if raise_exc:
                            raise CompletionValidationError(
                                "invalid_claim",
                                f"Summary cited_snapshot_id unparseable: {s_id!r}",
                            ) from exc
                        return ValidationOutcome(
                            valid=False,
                            review_status="unresolved",
                            reason="invalid_claim",
                            needs_human_review=True,
                            cleared=False,
                            error=f"Summary cited_snapshot_id unparseable: {s_id!r}",
                            sanitized_summary=summary,
                        )

        if cited_snapshot_ids:
            async with session_scope() as session:
                result = await session.execute(
                    sa.text(
                        """
                        SELECT id FROM source_snapshots
                        WHERE org_id = :org_id
                          AND project_id = :project_id
                          AND run_id = :run_id
                          AND item_id = :item_id
                        """
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "run_id": str(run_id),
                        "item_id": str(item_id),
                    },
                )
                valid_ids = {UUID(str(row[0])) for row in result.all()}

            unauthenticated = cited_snapshot_ids - valid_ids
            if unauthenticated:
                if raise_exc:
                    raise UnauthenticatedCitationError(
                        f"Agent cited unauthenticated snapshot IDs: {[str(u) for u in unauthenticated]}"
                    )
                return ValidationOutcome(
                    valid=False,
                    review_status="unresolved",
                    reason="unauthenticated_citation",
                    needs_human_review=True,
                    cleared=False,
                    error=f"Agent cited unauthenticated snapshot IDs: {[str(u) for u in unauthenticated]}",
                    sanitized_summary=summary,
                )

        # 4. Check snapshot count in DB
        async with session_scope() as session:
            count_result = await session.execute(
                sa.text(
                    """
                    SELECT count(*) FROM source_snapshots
                    WHERE org_id = :org_id
                      AND project_id = :project_id
                      AND run_id = :run_id
                    """
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                },
            )
            snapshot_count = int(count_result.scalar_one())

        # 5. Rule 3: Zero-evidence is unresolved
        if snapshot_count == 0 or len(claims) == 0:
            review_status = "unresolved"
            reason = "no_search_results" if snapshot_count == 0 else "insufficient_evidence"
            needs_human_review = True
            cleared = False
        else:
            review_status = "unresolved"
            reason = "human_review_required"
            needs_human_review = True
            cleared = False

        # 6. Rule 4: Anti-self-certification
        # Even if agent summary contains cleared=True or claims clearance, override it.
        summary["cleared"] = False
        summary["needs_human_review"] = True
        summary["review_status"] = review_status
        summary["reason"] = reason

        return ValidationOutcome(
            valid=True,
            review_status=review_status,
            reason=reason,
            needs_human_review=needs_human_review,
            cleared=cleared,
            sanitized_summary=summary,
        )
