from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

import uuid6


class ElementType(StrEnum):
    SCENE_HEADING = "scene_heading"
    ACTION = "action"
    CHARACTER = "character"
    DIALOGUE = "dialogue"
    PARENTHETICAL = "parenthetical"
    TRANSITION = "transition"
    PROP = "prop"
    LOCATION = "location"


@dataclass(frozen=True)
class ElementSpan:
    span_id: UUID
    element_id: UUID
    start_char: int
    end_char: int
    text: str
    tag: str | None = None

    @classmethod
    def create(
        cls,
        element_id: UUID,
        start_char: int,
        end_char: int,
        text: str,
        tag: str | None = None,
    ) -> "ElementSpan":
        return cls(
            span_id=uuid6.uuid7(),
            element_id=element_id,
            start_char=start_char,
            end_char=end_char,
            text=text,
            tag=tag,
        )


@dataclass(frozen=True)
class ScriptElement:
    element_id: UUID
    version_id: UUID
    ordinal: int
    element_type: ElementType
    text: str
    scene_number: int | None = None
    page_number: int | None = None
    spans: tuple[ElementSpan, ...] = field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        element_id: UUID | None = None,
        version_id: UUID | None = None,
        ordinal: int = 1,
        element_type: ElementType = ElementType.ACTION,
        text: str = "",
        scene_number: int | None = None,
        page_number: int | None = None,
        spans: list[ElementSpan] | None = None,
    ) -> "ScriptElement":
        return cls(
            element_id=element_id or uuid6.uuid7(),
            version_id=version_id or uuid6.uuid7(),
            ordinal=ordinal,
            element_type=element_type,
            text=text,
            scene_number=scene_number,
            page_number=page_number,
            spans=tuple(spans or []),
        )
