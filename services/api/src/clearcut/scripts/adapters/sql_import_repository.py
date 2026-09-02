"""SQL persistence for the screenplay import and immutable-version lifecycle."""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict, cast
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from sqlalchemy import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class ImportRecordNotFoundError(LookupError):
    pass


class ImportRecordConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class UploadCapabilityRecord:
    capability_id: UUID
    org_id: UUID
    project_id: UUID
    actor_id: UUID
    filename: str
    content_type: str
    nonce_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class ImportArtifactRecord:
    artifact_id: UUID
    org_id: UUID
    project_id: UUID
    uploaded_by_user_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    storage_path: str
    status: str
    created_at: datetime
    finalized_at: datetime | None


@dataclass(frozen=True)
class ParseDiagnosticRecord:
    code: str
    line_number: int | None
    message: str
    requires_acceptance: bool = True


@dataclass(frozen=True)
class ParseRunRecord:
    run_id: UUID
    org_id: UUID
    project_id: UUID
    artifact_id: UUID
    requested_by_user_id: UUID
    status: str
    parser_name: str
    parser_version: str
    title: str
    scene_count: int
    element_count: int
    result_json: str
    diagnostics_hash: str
    diagnostics: tuple[ParseDiagnosticRecord, ...]
    created_at: datetime
    completed_at: datetime
    accepted_at: datetime | None


@dataclass(frozen=True)
class ScriptVersionRecord:
    version_id: UUID
    script_id: UUID
    org_id: UUID
    project_id: UUID
    import_artifact_id: UUID | None
    parse_run_id: UUID | None
    ordinal: int
    title: str
    source_hash: str
    parser_version: str
    scene_count: int
    element_count: int
    created_at: datetime


@dataclass(frozen=True)
class ScriptLineProjection:
    element_type: str
    text: str
    flag: str | None


@dataclass(frozen=True)
class SceneProjection:
    number: int
    slug: str
    page: int | None
    lines: tuple[ScriptLineProjection, ...]


@dataclass(frozen=True)
class ProjectScriptProjection:
    title: str
    version_label: str
    version_id: UUID
    scenes: tuple[SceneProjection, ...]


class _SceneAccumulator(TypedDict):
    slug: str
    page: int | None
    lines: list[ScriptLineProjection]


def _as_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _require_datetime(value: datetime | str | None) -> datetime:
    parsed = _as_datetime(value)
    if parsed is None:
        raise ValueError("Expected a non-null datetime value")
    return parsed


def _capability_from_row(row: sa.RowMapping) -> UploadCapabilityRecord:
    return UploadCapabilityRecord(
        capability_id=UUID(str(row["id"])),
        org_id=UUID(str(row["org_id"])),
        project_id=UUID(str(row["project_id"])),
        actor_id=UUID(str(row["actor_id"])),
        filename=str(row["filename"]),
        content_type=str(row["content_type"]),
        nonce_hash=str(row["nonce_hash"]),
        expires_at=_require_datetime(row["expires_at"]),
        used_at=_as_datetime(row["used_at"]),
        created_at=_require_datetime(row["created_at"]),
    )


def _artifact_from_row(row: sa.RowMapping) -> ImportArtifactRecord:
    return ImportArtifactRecord(
        artifact_id=UUID(str(row["id"])),
        org_id=UUID(str(row["org_id"])),
        project_id=UUID(str(row["project_id"])),
        uploaded_by_user_id=UUID(str(row["uploaded_by_user_id"])),
        filename=str(row["filename"]),
        content_type=str(row["content_type"]),
        size_bytes=int(row["size_bytes"]),
        sha256_hash=str(row["sha256_hash"]),
        storage_path=str(row["storage_path"]),
        status=str(row["status"]),
        created_at=_require_datetime(row["created_at"]),
        finalized_at=_as_datetime(row["finalized_at"]),
    )


class SqlImportRepository:
    async def create_upload_capability(
        self,
        record: UploadCapabilityRecord,
    ) -> UploadCapabilityRecord:
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO import_upload_capabilities "
                    "(id, org_id, project_id, actor_id, filename, content_type, nonce_hash, "
                    "expires_at, used_at, created_at) VALUES "
                    "(:id, :org_id, :project_id, :actor_id, :filename, :content_type, "
                    ":nonce_hash, :expires_at, NULL, :created_at)"
                ),
                {
                    "id": str(record.capability_id),
                    "org_id": str(record.org_id),
                    "project_id": str(record.project_id),
                    "actor_id": str(record.actor_id),
                    "filename": record.filename,
                    "content_type": record.content_type,
                    "nonce_hash": record.nonce_hash,
                    "expires_at": record.expires_at,
                    "created_at": record.created_at,
                },
            )
        return record

    async def get_upload_capability(
        self,
        org_id: UUID,
        project_id: UUID,
        capability_id: UUID,
    ) -> UploadCapabilityRecord | None:
        async with session_scope() as session:
            result = await session.execute(
                sa.text(
                    "SELECT * FROM import_upload_capabilities "
                    "WHERE id = :id AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "id": str(capability_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
            row = result.mappings().first()
        return _capability_from_row(row) if row else None

    async def finalize_upload_capability(
        self,
        capability: UploadCapabilityRecord,
        artifact: ImportArtifactRecord,
        used_at: datetime,
    ) -> ImportArtifactRecord:
        async with session_scope() as session:
            update = await session.execute(
                sa.text(
                    "UPDATE import_upload_capabilities SET used_at = :used_at "
                    "WHERE id = :id AND org_id = :org_id AND project_id = :project_id "
                    "AND actor_id = :actor_id AND used_at IS NULL AND expires_at > :used_at"
                ),
                {
                    "used_at": used_at,
                    "id": str(capability.capability_id),
                    "org_id": str(capability.org_id),
                    "project_id": str(capability.project_id),
                    "actor_id": str(capability.actor_id),
                },
            )
            if cast(CursorResult[Any], update).rowcount != 1:
                current = await session.execute(
                    sa.text(
                        "SELECT used_at, expires_at FROM import_upload_capabilities "
                        "WHERE id = :id AND org_id = :org_id AND project_id = :project_id "
                        "AND actor_id = :actor_id"
                    ),
                    {
                        "id": str(capability.capability_id),
                        "org_id": str(capability.org_id),
                        "project_id": str(capability.project_id),
                        "actor_id": str(capability.actor_id),
                    },
                )
                state = current.mappings().first()
                expires_at = _as_datetime(state["expires_at"]) if state else None
                if expires_at is not None:
                    if expires_at.tzinfo is None and used_at.tzinfo is not None:
                        expires_at = expires_at.replace(tzinfo=used_at.tzinfo)
                    if expires_at <= used_at:
                        raise ImportRecordConflictError("Upload capability has expired")
                raise ImportRecordConflictError("Upload capability was already consumed")
            await self._insert_artifact(session, artifact)
        return artifact

    async def create_artifact(
        self,
        artifact: ImportArtifactRecord,
    ) -> ImportArtifactRecord:
        async with session_scope() as session:
            await self._insert_artifact(session, artifact)
        return artifact

    async def _insert_artifact(
        self,
        session: AsyncSession,
        artifact: ImportArtifactRecord,
    ) -> None:
        await session.execute(
            sa.text(
                "INSERT INTO import_artifacts "
                "(id, org_id, project_id, uploaded_by_user_id, filename, content_type, "
                "size_bytes, sha256_hash, storage_path, status, created_at, finalized_at) "
                "VALUES (:id, :org_id, :project_id, :uploaded_by_user_id, :filename, "
                ":content_type, :size_bytes, :sha256_hash, :storage_path, :status, "
                ":created_at, :finalized_at)"
            ),
            {
                "id": str(artifact.artifact_id),
                "org_id": str(artifact.org_id),
                "project_id": str(artifact.project_id),
                "uploaded_by_user_id": str(artifact.uploaded_by_user_id),
                "filename": artifact.filename,
                "content_type": artifact.content_type,
                "size_bytes": artifact.size_bytes,
                "sha256_hash": artifact.sha256_hash,
                "storage_path": artifact.storage_path,
                "status": artifact.status,
                "created_at": artifact.created_at,
                "finalized_at": artifact.finalized_at,
            },
        )

    async def get_artifact(
        self,
        org_id: UUID,
        project_id: UUID,
        artifact_id: UUID,
    ) -> ImportArtifactRecord | None:
        async with session_scope() as session:
            result = await session.execute(
                sa.text(
                    "SELECT * FROM import_artifacts "
                    "WHERE id = :id AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "id": str(artifact_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
            row = result.mappings().first()
        return _artifact_from_row(row) if row else None

    async def get_parse_run_by_artifact(
        self,
        org_id: UUID,
        project_id: UUID,
        artifact_id: UUID,
    ) -> ParseRunRecord | None:
        async with session_scope() as session:
            result = await session.execute(
                sa.text(
                    "SELECT * FROM parse_runs WHERE org_id = :org_id "
                    "AND project_id = :project_id AND artifact_id = :artifact_id"
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "artifact_id": str(artifact_id),
                },
            )
            row = result.mappings().first()
            if row is None:
                return None
            return await self._parse_run_from_row(session, row)

    async def get_parse_run(
        self,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ) -> ParseRunRecord | None:
        async with session_scope() as session:
            result = await session.execute(
                sa.text(
                    "SELECT * FROM parse_runs WHERE id = :id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
            row = result.mappings().first()
            if row is None:
                return None
            return await self._parse_run_from_row(session, row)

    async def create_parse_run(
        self,
        record: ParseRunRecord,
    ) -> ParseRunRecord:
        async with session_scope() as session:
            insert = await session.execute(
                sa.text(
                    "INSERT INTO parse_runs "
                    "(id, org_id, project_id, artifact_id, requested_by_user_id, status, "
                    "parser_name, parser_version, title, scene_count, element_count, "
                    "result_json, diagnostics_hash, created_at, completed_at) VALUES "
                    "(:id, :org_id, :project_id, :artifact_id, :requested_by_user_id, "
                    ":status, :parser_name, :parser_version, :title, :scene_count, "
                    ":element_count, :result_json, :diagnostics_hash, :created_at, "
                    ":completed_at) ON CONFLICT (org_id, project_id, artifact_id) "
                    "DO NOTHING"
                ),
                {
                    "id": str(record.run_id),
                    "org_id": str(record.org_id),
                    "project_id": str(record.project_id),
                    "artifact_id": str(record.artifact_id),
                    "requested_by_user_id": str(record.requested_by_user_id),
                    "status": record.status,
                    "parser_name": record.parser_name,
                    "parser_version": record.parser_version,
                    "title": record.title,
                    "scene_count": record.scene_count,
                    "element_count": record.element_count,
                    "result_json": record.result_json,
                    "diagnostics_hash": record.diagnostics_hash,
                    "created_at": record.created_at,
                    "completed_at": record.completed_at,
                },
            )
            if cast(CursorResult[Any], insert).rowcount == 0:
                existing = await session.execute(
                    sa.text(
                        "SELECT * FROM parse_runs WHERE org_id = :org_id "
                        "AND project_id = :project_id AND artifact_id = :artifact_id"
                    ),
                    {
                        "org_id": str(record.org_id),
                        "project_id": str(record.project_id),
                        "artifact_id": str(record.artifact_id),
                    },
                )
                row = existing.mappings().one()
                return await self._parse_run_from_row(session, row)

            for diagnostic in record.diagnostics:
                await session.execute(
                    sa.text(
                        "INSERT INTO parse_diagnostics "
                        "(id, run_id, org_id, project_id, code, line_number, message, "
                        "requires_acceptance, created_at) VALUES "
                        "(:id, :run_id, :org_id, :project_id, :code, :line_number, "
                        ":message, :requires_acceptance, :created_at)"
                    ),
                    {
                        "id": str(uuid6.uuid7()),
                        "run_id": str(record.run_id),
                        "org_id": str(record.org_id),
                        "project_id": str(record.project_id),
                        "code": diagnostic.code,
                        "line_number": diagnostic.line_number,
                        "message": diagnostic.message,
                        "requires_acceptance": diagnostic.requires_acceptance,
                        "created_at": record.created_at,
                    },
                )
        return record

    async def accept_warnings(
        self,
        record: ParseRunRecord,
        actor_id: UUID,
        accepted_at: datetime,
    ) -> None:
        async with session_scope() as session:
            existing = await session.execute(
                sa.text(
                    "SELECT id FROM parse_warning_acceptances WHERE run_id = :run_id "
                    "AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "run_id": str(record.run_id),
                    "org_id": str(record.org_id),
                    "project_id": str(record.project_id),
                },
            )
            if existing.first() is not None:
                return
            await session.execute(
                sa.text(
                    "INSERT INTO parse_warning_acceptances "
                    "(id, run_id, org_id, project_id, accepted_by_user_id, "
                    "diagnostics_hash, accepted_at) VALUES "
                    "(:id, :run_id, :org_id, :project_id, :accepted_by_user_id, "
                    ":diagnostics_hash, :accepted_at) "
                    "ON CONFLICT (org_id, project_id, run_id) DO NOTHING"
                ),
                {
                    "id": str(uuid6.uuid7()),
                    "run_id": str(record.run_id),
                    "org_id": str(record.org_id),
                    "project_id": str(record.project_id),
                    "accepted_by_user_id": str(actor_id),
                    "diagnostics_hash": record.diagnostics_hash,
                    "accepted_at": accepted_at,
                },
            )

    async def commit_version_one(
        self,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ) -> ScriptVersionRecord:
        try:
            return await self._commit_version_one_once(org_id, project_id, run_id)
        except IntegrityError as error:
            async with session_scope() as session:
                existing = await self._get_version_by_run(
                    session, org_id, project_id, run_id
                )
                if existing is not None:
                    return existing
                current = await session.execute(
                    sa.text(
                        "SELECT v.id FROM script_versions v JOIN scripts s "
                        "ON s.id = v.script_id WHERE v.org_id = :org_id "
                        "AND v.project_id = :project_id "
                        "AND s.current_slot = 'current' LIMIT 1"
                    ),
                    {"org_id": str(org_id), "project_id": str(project_id)},
                )
                if current.first() is not None:
                    raise ImportRecordConflictError(
                        "Version one already exists for this project"
                    ) from error
            raise ImportRecordConflictError(
                "Version one could not be committed concurrently"
            ) from error

    async def _commit_version_one_once(
        self,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ) -> ScriptVersionRecord:
        async with session_scope() as session:
            existing = await self._get_version_by_run(session, org_id, project_id, run_id)
            if existing is not None:
                return existing

            run_result = await session.execute(
                sa.text(
                    "SELECT r.*, a.sha256_hash FROM parse_runs r "
                    "JOIN import_artifacts a ON a.id = r.artifact_id "
                    "AND a.org_id = r.org_id AND a.project_id = r.project_id "
                    "WHERE r.id = :run_id AND r.org_id = :org_id "
                    "AND r.project_id = :project_id"
                ),
                {
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
            run = run_result.mappings().first()
            if run is None:
                raise ImportRecordNotFoundError("Parse run was not found")

            warning_result = await session.execute(
                sa.text(
                    "SELECT count(*) FROM parse_diagnostics WHERE run_id = :run_id "
                    "AND requires_acceptance = :required"
                ),
                {"run_id": str(run_id), "required": True},
            )
            if int(warning_result.scalar_one()) > 0:
                acceptance = await session.execute(
                    sa.text(
                        "SELECT diagnostics_hash FROM parse_warning_acceptances "
                        "WHERE run_id = :run_id AND org_id = :org_id "
                        "AND project_id = :project_id"
                    ),
                    {
                        "run_id": str(run_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
                accepted_hash = acceptance.scalar_one_or_none()
                if accepted_hash != run["diagnostics_hash"]:
                    raise ImportRecordConflictError(
                        "Parse warnings must be accepted before committing version one"
                    )

            script_result = await session.execute(
                sa.text(
                    "SELECT id FROM scripts WHERE org_id = :org_id "
                    "AND project_id = :project_id AND current_slot = 'current'"
                ),
                {"org_id": str(org_id), "project_id": str(project_id)},
            )
            script_id = script_result.scalar_one_or_none()
            created_at = _require_datetime(run["completed_at"])
            if script_id is None:
                script_id = str(uuid6.uuid7())
                await session.execute(
                    sa.text(
                        "INSERT INTO scripts "
                        "(id, org_id, project_id, title, created_at, current_slot) "
                        "VALUES (:id, :org_id, :project_id, :title, :created_at, 'current')"
                    ),
                    {
                        "id": script_id,
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "title": run["title"],
                        "created_at": created_at,
                    },
                )
            else:
                prior_version = await session.execute(
                    sa.text(
                        "SELECT id FROM script_versions WHERE script_id = :script_id LIMIT 1"
                    ),
                    {"script_id": str(script_id)},
                )
                if prior_version.first() is not None:
                    raise ImportRecordConflictError(
                        "Version one already exists for this project"
                    )

            version_id = uuid6.uuid7()
            await session.execute(
                sa.text(
                    "INSERT INTO script_versions "
                    "(id, script_id, org_id, project_id, ordinal, source_hash, "
                    "parser_version, created_at, import_artifact_id, parse_run_id) "
                    "VALUES (:id, :script_id, :org_id, :project_id, 1, :source_hash, "
                    ":parser_version, :created_at, :artifact_id, :parse_run_id)"
                ),
                {
                    "id": str(version_id),
                    "script_id": str(script_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "source_hash": run["sha256_hash"],
                    "parser_version": run["parser_version"],
                    "created_at": created_at,
                    "artifact_id": str(run["artifact_id"]),
                    "parse_run_id": str(run_id),
                },
            )

            payload = json.loads(str(run["result_json"]))
            for element in payload["elements"]:
                await session.execute(
                    sa.text(
                        "INSERT INTO script_elements "
                        "(id, version_id, ordinal, element_type, text, scene_number, "
                        "page_number) VALUES (:id, :version_id, :ordinal, :element_type, "
                        ":text, :scene_number, :page_number)"
                    ),
                    {
                        "id": str(uuid6.uuid7()),
                        "version_id": str(version_id),
                        "ordinal": element["ordinal"],
                        "element_type": element["elementType"],
                        "text": element["text"],
                        "scene_number": element["sceneNumber"],
                        "page_number": element["pageNumber"],
                    },
                )

            return ScriptVersionRecord(
                version_id=version_id,
                script_id=UUID(str(script_id)),
                org_id=org_id,
                project_id=project_id,
                import_artifact_id=UUID(str(run["artifact_id"])),
                parse_run_id=run_id,
                ordinal=1,
                title=str(run["title"]),
                source_hash=str(run["sha256_hash"]),
                parser_version=str(run["parser_version"]),
                scene_count=int(run["scene_count"]),
                element_count=int(run["element_count"]),
                created_at=created_at,
            )

    async def get_version(
        self,
        org_id: UUID,
        project_id: UUID,
        version_id: UUID,
    ) -> ScriptVersionRecord | None:
        async with session_scope() as session:
            return await self._get_version(session, org_id, project_id, version_id)

    async def list_versions(
        self,
        org_id: UUID,
        project_id: UUID,
    ) -> tuple[ScriptVersionRecord, ...]:
        async with session_scope() as session:
            result = await session.execute(
                sa.text(
                    "SELECT v.id FROM script_versions v JOIN scripts s ON s.id = v.script_id "
                    "WHERE v.org_id = :org_id AND v.project_id = :project_id "
                    "AND s.current_slot = 'current' "
                    "ORDER BY v.ordinal DESC, v.created_at DESC"
                ),
                {"org_id": str(org_id), "project_id": str(project_id)},
            )
            records = []
            for version_id in result.scalars():
                record = await self._get_version(
                    session, org_id, project_id, UUID(str(version_id))
                )
                if record is not None:
                    records.append(record)
            return tuple(records)

    async def get_current_script(
        self,
        org_id: UUID,
        project_id: UUID,
    ) -> ProjectScriptProjection | None:
        async with session_scope() as session:
            version_result = await session.execute(
                sa.text(
                    "SELECT v.id, v.ordinal, s.title FROM script_versions v "
                    "JOIN scripts s ON s.id = v.script_id "
                    "WHERE v.org_id = :org_id AND v.project_id = :project_id "
                    "AND s.current_slot = 'current' "
                    "ORDER BY v.ordinal DESC, v.created_at DESC, v.id DESC LIMIT 1"
                ),
                {"org_id": str(org_id), "project_id": str(project_id)},
            )
            version = version_result.mappings().first()
            if version is None:
                return None

            element_result = await session.execute(
                sa.text(
                    "SELECT e.ordinal, e.element_type, e.text, e.scene_number, "
                    "e.page_number, (SELECT tag FROM element_spans span "
                    "WHERE span.element_id = e.id ORDER BY span.start_char LIMIT 1) AS flag "
                    "FROM script_elements e WHERE e.version_id = :version_id "
                    "ORDER BY e.ordinal"
                ),
                {"version_id": str(version["id"])},
            )
            scenes: dict[int, _SceneAccumulator] = {}
            for row in element_result.mappings():
                if row["scene_number"] is None or int(row["scene_number"]) <= 0:
                    continue
                scene_number = int(row["scene_number"])
                scene = scenes.setdefault(
                    scene_number,
                    {
                        "slug": f"SCENE {scene_number}",
                        "page": (
                            int(row["page_number"])
                            if row["page_number"] is not None
                            else None
                        ),
                        "lines": [],
                    },
                )
                if row["element_type"] == "scene_heading":
                    scene["slug"] = str(row["text"])
                    continue
                scene["lines"].append(
                    ScriptLineProjection(
                        element_type=str(row["element_type"]),
                        text=str(row["text"]),
                        flag=str(row["flag"]) if row["flag"] else None,
                    )
                )

            return ProjectScriptProjection(
                title=str(version["title"]),
                version_label=f"v{version['ordinal']}",
                version_id=UUID(str(version["id"])),
                scenes=tuple(
                    SceneProjection(
                        number=number,
                        slug=str(scene["slug"]),
                        page=scene["page"],
                        lines=tuple(scene["lines"]),
                    )
                    for number, scene in scenes.items()
                ),
            )

    async def _parse_run_from_row(
        self,
        session: AsyncSession,
        row: sa.RowMapping,
    ) -> ParseRunRecord:
        diagnostic_result = await session.execute(
            sa.text(
                "SELECT code, line_number, message, requires_acceptance "
                "FROM parse_diagnostics WHERE run_id = :run_id ORDER BY line_number, id"
            ),
            {"run_id": str(row["id"])},
        )
        diagnostics = tuple(
            ParseDiagnosticRecord(
                code=str(diagnostic["code"]),
                line_number=(
                    int(diagnostic["line_number"])
                    if diagnostic["line_number"] is not None
                    else None
                ),
                message=str(diagnostic["message"]),
                requires_acceptance=bool(diagnostic["requires_acceptance"]),
            )
            for diagnostic in diagnostic_result.mappings()
        )
        acceptance = await session.execute(
            sa.text(
                "SELECT accepted_at FROM parse_warning_acceptances WHERE run_id = :run_id "
                "AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "run_id": str(row["id"]),
                "org_id": str(row["org_id"]),
                "project_id": str(row["project_id"]),
            },
        )
        return ParseRunRecord(
            run_id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            project_id=UUID(str(row["project_id"])),
            artifact_id=UUID(str(row["artifact_id"])),
            requested_by_user_id=UUID(str(row["requested_by_user_id"])),
            status=str(row["status"]),
            parser_name=str(row["parser_name"]),
            parser_version=str(row["parser_version"]),
            title=str(row["title"]),
            scene_count=int(row["scene_count"]),
            element_count=int(row["element_count"]),
            result_json=str(row["result_json"]),
            diagnostics_hash=str(row["diagnostics_hash"]),
            diagnostics=diagnostics,
            created_at=_require_datetime(row["created_at"]),
            completed_at=_require_datetime(row["completed_at"]),
            accepted_at=_as_datetime(acceptance.scalar_one_or_none()),
        )

    async def _get_version_by_run(
        self,
        session: AsyncSession,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ) -> ScriptVersionRecord | None:
        result = await session.execute(
            sa.text(
                "SELECT id FROM script_versions WHERE parse_run_id = :run_id "
                "AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )
        version_id = result.scalar_one_or_none()
        if version_id is None:
            return None
        return await self._get_version(
            session, org_id, project_id, UUID(str(version_id))
        )

    async def _get_version(
        self,
        session: AsyncSession,
        org_id: UUID,
        project_id: UUID,
        version_id: UUID,
    ) -> ScriptVersionRecord | None:
        result = await session.execute(
            sa.text(
                "SELECT v.*, s.title, COALESCE(r.scene_count, "
                "(SELECT count(DISTINCT e.scene_number) FROM script_elements e "
                "WHERE e.version_id = v.id AND e.scene_number IS NOT NULL), 0) "
                "AS scene_count, COALESCE(r.element_count, "
                "(SELECT count(*) FROM script_elements e WHERE e.version_id = v.id), 0) "
                "AS element_count FROM script_versions v "
                "JOIN scripts s ON s.id = v.script_id "
                "LEFT JOIN parse_runs r ON r.id = v.parse_run_id "
                "AND r.org_id = v.org_id AND r.project_id = v.project_id "
                "WHERE v.id = :id AND v.org_id = :org_id AND v.project_id = :project_id"
            ),
            {
                "id": str(version_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        import_artifact_id = row["import_artifact_id"]
        parse_run_id = row["parse_run_id"]
        return ScriptVersionRecord(
            version_id=UUID(str(row["id"])),
            script_id=UUID(str(row["script_id"])),
            org_id=UUID(str(row["org_id"])),
            project_id=UUID(str(row["project_id"])),
            import_artifact_id=(
                UUID(str(import_artifact_id)) if import_artifact_id is not None else None
            ),
            parse_run_id=UUID(str(parse_run_id)) if parse_run_id is not None else None,
            ordinal=int(row["ordinal"]),
            title=str(row["title"]),
            source_hash=str(row["source_hash"]),
            parser_version=str(row["parser_version"]),
            scene_count=int(row["scene_count"]),
            element_count=int(row["element_count"]),
            created_at=_require_datetime(row["created_at"]),
        )
