from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import uuid6
from clearcut.scripts.domain.elements import ScriptElement


class ImmutableVersionError(Exception):
    pass


@dataclass(frozen=True)
class ParseWarning:
    warning_code: str
    message: str
    line_number: int | None = None


@dataclass(frozen=True)
class ParseResult:
    title: str
    elements: list[ScriptElement]
    warnings: list[ParseWarning]
    parser_name: str


@dataclass(frozen=True)
class Script:
    script_id: UUID
    org_id: UUID
    project_id: UUID
    title: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        title: str,
    ) -> "Script":
        return cls(
            script_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            title=title.strip(),
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class ScriptVersion:
    version_id: UUID
    script_id: UUID
    org_id: UUID
    project_id: UUID
    ordinal: int
    source_hash: str
    parser_version: str
    created_at: datetime
    elements: tuple[ScriptElement, ...] = field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        version_id: UUID | None = None,
        script_id: UUID | None = None,
        org_id: UUID | None = None,
        project_id: UUID | None = None,
        ordinal: int = 1,
        source_hash: str = "",
        parser_version: str = "1.0.0",
        elements: list[ScriptElement] | None = None,
    ) -> "ScriptVersion":
        return cls(
            version_id=version_id or uuid6.uuid7(),
            script_id=script_id or uuid6.uuid7(),
            org_id=org_id or uuid6.uuid7(),
            project_id=project_id or uuid6.uuid7(),
            ordinal=ordinal,
            source_hash=source_hash,
            parser_version=parser_version,
            created_at=datetime.now(UTC),
            elements=tuple(elements or []),
        )
