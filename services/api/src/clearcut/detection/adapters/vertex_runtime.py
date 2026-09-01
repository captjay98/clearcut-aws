"""Vertex AI (Gemini) detection runtime adapter.

Uses the google-genai SDK in Vertex mode (project + location=global, ADC auth).
Implements ModelRuntimePort: turns script elements into typed CandidateItems for
the ten fixed clearance categories, using structured JSON output.

This adapter performs live network calls to Vertex AI. It is constructed only
when configured (see detection.runtime_provider); it is never a fallback for the
hermetic test runtime.
"""
import json
import logging
import os

from clearcut.detection.domain.candidates import CandidateItem, ClearanceCategory
from clearcut.detection.ports.model_runtime import ModelRuntimePort
from clearcut.scripts.domain.elements import ScriptElement

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {c.value for c in ClearanceCategory}

_SYSTEM_INSTRUCTION = (
    "You are a screenplay pre-clearance detector. Identify entities that may "
    "require rights clearance. Only use these exact category values: "
    + ", ".join(sorted(_VALID_CATEGORIES))
    + ". Return findings strictly as JSON matching the provided schema. Do not "
    "invent entities that are not present in the supplied text."
)

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "candidates": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "category": {"type": "STRING", "enum": sorted(_VALID_CATEGORIES)},
                    "text": {"type": "STRING"},
                    "span_start": {"type": "INTEGER"},
                    "span_end": {"type": "INTEGER"},
                    "rationale": {"type": "STRING"},
                    "uncertainty": {"type": "STRING", "enum": ["low", "medium", "high"]},
                },
                "required": ["category", "text", "span_start", "span_end", "rationale", "uncertainty"],
            },
        }
    },
    "required": ["candidates"],
}


class VertexDetectionRuntime(ModelRuntimePort):
    def __init__(
        self,
        project: str,
        location: str = "global",
        model: str | None = None,
    ) -> None:
        self.project = project
        self.location = location
        self.model = model or os.getenv("CLEARCUT_GEMINI_MODEL", "gemini-3.1-pro-preview")
        # Imported lazily so the module (and tests that override the runtime) do
        # not require google-genai to be installed unless a live run occurs.
        from google import genai

        self._client = genai.Client(vertexai=True, project=project, location=location)

    def detect_candidates(self, elements: list[ScriptElement]) -> list[CandidateItem]:
        from google.genai import types

        candidates: list[CandidateItem] = []

        for element in elements:
            text = element.text or ""
            if not text.strip():
                continue

            response = self._client.models.generate_content(
                model=self.model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                ),
            )

            raw = getattr(response, "text", None)
            if not raw:
                continue

            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Vertex detection returned non-JSON output; skipping element.")
                continue

            for c in parsed.get("candidates", []):
                category_value = c.get("category")
                if category_value not in _VALID_CATEGORIES:
                    # Never accept a category outside the fixed protected set.
                    continue
                candidates.append(
                    CandidateItem.create(
                        category=ClearanceCategory(category_value),
                        element_id=element.element_id,
                        span_start=int(c.get("span_start", 0)),
                        span_end=int(c.get("span_end", 0)),
                        text=c.get("text", ""),
                        rationale=c.get("rationale", ""),
                        uncertainty=c.get("uncertainty", "medium"),
                    )
                )

        return candidates
