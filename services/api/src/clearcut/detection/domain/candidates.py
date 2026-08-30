from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

import uuid6


class ClearanceCategory(StrEnum):
    REAL_PERSONS_LIVING = "real_persons_living"
    REAL_PERSONS_DECEASED = "real_persons_deceased"
    CORPORATE_ENTITIES = "corporate_entities"
    PRODUCTS_AND_TRADEMARKS = "products_and_trademarks"
    COPYRIGHTED_WORKS = "copyrighted_works"
    MUSIC_AND_LYRICS = "music_and_lyrics"
    LOCATIONS_AND_LANDMARKS = "locations_and_landmarks"
    VEHICLES_AND_INSIGNIA = "vehicles_and_insignia"
    SENSITIVE_HISTORICAL_EVENTS = "sensitive_historical_events"
    CONTACT_INFORMATION = "contact_information"


UncertaintyLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class CandidateItem:
    item_id: UUID
    category: ClearanceCategory
    element_id: UUID
    span_start: int
    span_end: int
    text: str
    rationale: str
    uncertainty: UncertaintyLevel

    @classmethod
    def create(
        cls,
        category: ClearanceCategory,
        element_id: UUID,
        span_start: int,
        span_end: int,
        text: str,
        rationale: str,
        uncertainty: UncertaintyLevel = "low",
    ) -> "CandidateItem":
        return cls(
            item_id=uuid6.uuid7(),
            category=category,
            element_id=element_id,
            span_start=span_start,
            span_end=span_end,
            text=text.strip(),
            rationale=rationale.strip(),
            uncertainty=uncertainty,
        )


@dataclass
class ClearanceItem:
    item_id: UUID
    org_id: UUID
    project_id: UUID
    script_id: UUID
    version_id: UUID
    element_id: UUID
    category: ClearanceCategory
    text: str
    status: str  # "unresolved" | "resolved"
    created_at: datetime

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        script_id: UUID,
        version_id: UUID,
        element_id: UUID,
        category: ClearanceCategory,
        text: str,
    ) -> "ClearanceItem":
        return cls(
            item_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            version_id=version_id,
            element_id=element_id,
            category=category,
            text=text.strip(),
            status="unresolved",
            created_at=datetime.now(UTC),
        )
