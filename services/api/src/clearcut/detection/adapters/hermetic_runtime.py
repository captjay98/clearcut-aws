import re

from clearcut.detection.domain.candidates import CandidateItem, ClearanceCategory
from clearcut.detection.ports.model_runtime import ModelRuntimePort
from clearcut.scripts.domain.elements import ScriptElement

# Canonical test heuristics for fast hermetic candidate detection
CATEGORY_PATTERNS: list[tuple[ClearanceCategory, re.Pattern[str], str]] = [
    (
        ClearanceCategory.PRODUCTS_AND_TRADEMARKS,
        re.compile(r"\b(Coca-Cola|Pepsi|iPhone|Nike|MacBook|Ferrari|Rolex)\b", re.IGNORECASE),
        "Trademarked commercial brand/product",
    ),
    (
        ClearanceCategory.CORPORATE_ENTITIES,
        re.compile(r"\b(Google|Apple|Sony|Paramount|Disney|Amazon|Microsoft)\b", re.IGNORECASE),
        "Corporate business entity or studio",
    ),
    (
        ClearanceCategory.REAL_PERSONS_LIVING,
        re.compile(r"\b(Tom Cruise|Elon Musk|Taylor Swift|Steven Spielberg)\b", re.IGNORECASE),
        "Living public figure",
    ),
    (
        ClearanceCategory.REAL_PERSONS_DECEASED,
        re.compile(r"\b(Marilyn Monroe|Elvis Presley|Steve Jobs|Abraham Lincoln)\b", re.IGNORECASE),
        "Deceased historic person / right of publicity",
    ),
    (
        ClearanceCategory.MUSIC_AND_LYRICS,
        re.compile(r"\b(Bohemian Rhapsody|Stairway to Heaven|Thriller|Imagine)\b", re.IGNORECASE),
        "Copyrighted song or musical composition",
    ),
    (
        ClearanceCategory.LOCATIONS_AND_LANDMARKS,
        re.compile(
            r"\b(Chrysler Building|Empire State|Golden Gate Bridge|Louvre|Taj Mahal)\b",
            re.IGNORECASE,
        ),
        "Prominent landmark or private architectural property",
    ),
    (
        ClearanceCategory.CONTACT_INFORMATION,
        re.compile(
            r"(\+?1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}|[\w.-]+@[\w.-]+\.\w+)",
            re.IGNORECASE,
        ),
        "Identifiable phone number, email address, or contact detail",
    ),
]


class HermeticDetectionRuntime(ModelRuntimePort):
    def detect_candidates(self, elements: list[ScriptElement]) -> list[CandidateItem]:
        candidates: list[CandidateItem] = []

        for element in elements:
            text = element.text
            for category, pattern, rationale in CATEGORY_PATTERNS:
                for match in pattern.finditer(text):
                    candidates.append(
                        CandidateItem.create(
                            category=category,
                            element_id=element.element_id,
                            span_start=match.start(),
                            span_end=match.end(),
                            text=match.group(),
                            rationale=rationale,
                            uncertainty="low",
                        )
                    )

        return candidates
