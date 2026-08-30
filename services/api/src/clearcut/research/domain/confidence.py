from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class ClearanceConfidenceLevel(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ConfidenceAssessment:
    item_id: UUID
    level: ClearanceConfidenceLevel
    has_conflicts: bool
    primary_sources_count: int
    rationale: str
    assessed_at: datetime = datetime.now(UTC)
