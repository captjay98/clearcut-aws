"""Persistent screenplay import application service."""

import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Literal
from uuid import UUID

import uuid6
from clearcut.scripts.adapters.fdx_parser import FdxParser
from clearcut.scripts.adapters.fountain_parser import FountainParser
from clearcut.scripts.adapters.paste_parser import PasteParser
from clearcut.scripts.adapters.pdf_parser import PdfParser
from clearcut.scripts.adapters.sql_import_repository import (
    AdjacentDiffRecord,
    ElementLineageRecord,
    ImportArtifactRecord,
    ImportRecordConflictError,
    ParseDiagnosticRecord,
    ParseRunRecord,
    ProjectScriptProjection,
    ScriptVersionRecord,
    SqlImportRepository,
    UploadCapabilityRecord,
)
from clearcut.scripts.domain.artifacts import (
    compute_sha256,
    validate_screenplay_magic_bytes,
)
from clearcut.scripts.domain.versions import ParseResult
from clearcut.scripts.ports.object_storage import ObjectStoragePort

MAX_SCRIPT_SIZE_BYTES = 25 * 1024 * 1024
PARSER_VERSION = "1.0.0"
logger = logging.getLogger(__name__)


class ImportScriptError(RuntimeError):
    """Base class for expected import lifecycle failures."""


class ImportNotFoundError(ImportScriptError):
    pass


class ImportConflictError(ImportScriptError):
    pass


class ImportValidationError(ImportScriptError):
    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


class ImportUnavailableError(ImportScriptError):
    pass


@dataclass(frozen=True)
class UploadCapabilityView:
    capability_id: UUID
    upload_url: str
    nonce: str
    expires_at: datetime


@dataclass(frozen=True)
class ImportArtifactView:
    artifact_id: UUID
    project_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class ParseWarningView:
    code: str
    line_number: int | None
    message: str


@dataclass(frozen=True)
class ParseRunView:
    run_id: UUID
    artifact_id: UUID
    status: str
    parser_name: str
    parser_version: str
    scene_count: int
    element_count: int
    warnings: tuple[ParseWarningView, ...]
    warnings_accepted: bool
    accepted_at: datetime | None
    created_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class ScriptVersionView:
    version_id: UUID
    script_id: UUID
    project_id: UUID
    version_number: int
    revision_label: str
    title: str
    source_artifact_id: UUID | None
    parse_run_id: UUID | None
    source_hash: str
    parser_version: str
    scene_count: int
    element_count: int
    created_at: datetime
    predecessor_version_id: UUID | None = None
    committed_by_user_id: UUID | None = None


@dataclass(frozen=True)
class ElementChangeView:
    before_element_id: UUID | None
    after_element_id: UUID | None
    before_ordinal: int | None
    after_ordinal: int | None
    before_text: str | None
    after_text: str | None
    element_type: str
    change_kind: str
    confidence: str

    @property
    def text(self) -> str | None:
        """Single representative element text: the after text when present else before."""
        return self.after_text if self.after_text is not None else self.before_text


@dataclass(frozen=True)
class AdjacentDiffView:
    diff_id: UUID
    project_id: UUID
    script_id: UUID
    before_version_id: UUID
    after_version_id: UUID
    before_version_number: int
    after_version_number: int
    algorithm_version: str
    changes: tuple[ElementChangeView, ...]
    impact_counts: dict[str, int]
    carried_forward_item_count: int
    created_at: datetime


class ImportScriptService:
    def __init__(
        self,
        repository: SqlImportRepository,
        storage: ObjectStoragePort,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._fountain_parser = FountainParser()
        self._fdx_parser = FdxParser()
        self._paste_parser = PasteParser()
        self._pdf_parser = PdfParser()

    async def create_upload_capability(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        filename: str,
        content_type: str,
    ) -> UploadCapabilityView:
        clean_filename = self._validate_filename(filename)
        clean_content_type = content_type.strip().lower()
        if not clean_content_type:
            raise ImportValidationError("Content type is required.")

        now = datetime.now(UTC)
        capability_id = uuid6.uuid7()
        nonce = secrets.token_hex(32)
        record = UploadCapabilityRecord(
            capability_id=capability_id,
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            filename=clean_filename,
            content_type=clean_content_type,
            nonce_hash=self._hash_nonce(nonce),
            expires_at=now + timedelta(minutes=30),
            used_at=None,
            created_at=now,
        )
        await self._repository.create_upload_capability(record)
        return UploadCapabilityView(
            capability_id=capability_id,
            upload_url=(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"import-artifacts/{capability_id}:finalize"
            ),
            nonce=nonce,
            expires_at=record.expires_at,
        )

    async def finalize_upload(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        capability_id: UUID,
        nonce: str,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> ImportArtifactView:
        capability = await self._repository.get_upload_capability(org_id, project_id, capability_id)
        if capability is None or capability.actor_id != actor_id:
            raise ImportNotFoundError("Upload capability was not found.")
        if capability.used_at is not None:
            raise ImportConflictError("Upload capability was already consumed.")
        expires_at = capability.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise ImportConflictError("Upload capability has expired.")
        if not hmac.compare_digest(capability.nonce_hash, self._hash_nonce(nonce)):
            raise ImportNotFoundError("Upload capability was not found.")
        if filename != capability.filename:
            raise ImportValidationError("Uploaded filename does not match the capability.")
        if (content_type or "").lower() != capability.content_type:
            raise ImportValidationError("Uploaded content type does not match the capability.")
        self._validate_bytes(data, capability.content_type, capability.filename)

        now = datetime.now(UTC)
        storage_path = self._storage_path(
            org_id,
            project_id,
            capability_id,
            capability.filename,
            attempt_id=uuid6.uuid7(),
        )
        artifact = ImportArtifactRecord(
            artifact_id=capability_id,
            org_id=org_id,
            project_id=project_id,
            uploaded_by_user_id=actor_id,
            filename=capability.filename,
            content_type=capability.content_type,
            size_bytes=len(data),
            sha256_hash=compute_sha256(data),
            storage_path=storage_path,
            status="ready_to_parse",
            created_at=now,
            finalized_at=now,
        )
        await self._storage.put_object(storage_path, data, capability.content_type)
        try:
            persisted = await self._repository.finalize_upload_capability(capability, artifact, now)
        except ImportRecordConflictError as error:
            await self._delete_staged_object_best_effort(
                storage_path=storage_path,
                capability_id=capability_id,
            )
            raise ImportConflictError(str(error)) from error
        except Exception:
            await self._delete_staged_object_best_effort(
                storage_path=storage_path,
                capability_id=capability_id,
            )
            raise
        return self._artifact_view(persisted)

    async def _delete_staged_object_best_effort(
        self,
        *,
        storage_path: str,
        capability_id: UUID,
    ) -> None:
        try:
            await self._storage.delete_object(storage_path)
        except Exception:
            logger.warning(
                "Failed to delete staged import object after finalize error; "
                "manual cleanup is required. capability_id=%s storage_path=%s",
                capability_id,
                storage_path,
                exc_info=True,
            )

    async def create_paste_import(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        raw_text: str,
        source_format: Literal["fountain", "fdx", "raw"],
    ) -> ImportArtifactView:
        if not raw_text.strip():
            raise ImportValidationError("Pasted screenplay text is required.")
        data = raw_text.encode("utf-8")
        extension_by_format = {
            "fountain": "fountain",
            "fdx": "fdx",
            "raw": "txt",
        }
        content_type = "application/xml" if source_format == "fdx" else "text/plain"
        artifact_id = uuid6.uuid7()
        filename = f"paste-{artifact_id}.{extension_by_format[source_format]}"
        self._validate_bytes(data, content_type, filename)
        now = datetime.now(UTC)
        storage_path = self._storage_path(org_id, project_id, artifact_id, filename)
        artifact = ImportArtifactRecord(
            artifact_id=artifact_id,
            org_id=org_id,
            project_id=project_id,
            uploaded_by_user_id=actor_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            sha256_hash=compute_sha256(data),
            storage_path=storage_path,
            status="ready_to_parse",
            created_at=now,
            finalized_at=now,
        )
        await self._storage.put_object(storage_path, data, content_type)
        try:
            persisted = await self._repository.create_artifact(artifact)
        except Exception:
            await self._storage.delete_object(storage_path)
            raise
        return self._artifact_view(persisted)

    async def parse_artifact(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        artifact_id: UUID,
    ) -> ParseRunView:
        artifact = await self._repository.get_artifact(org_id, project_id, artifact_id)
        if artifact is None:
            raise ImportNotFoundError("Import artifact was not found.")
        existing = await self._repository.get_parse_run_by_artifact(org_id, project_id, artifact_id)
        if existing is not None:
            return self._parse_run_view(existing)

        data = await self._storage.get_object(artifact.storage_path)
        if data is None:
            raise ImportUnavailableError("Imported screenplay bytes are unavailable.")
        if len(data) != artifact.size_bytes or not hmac.compare_digest(
            compute_sha256(data), artifact.sha256_hash
        ):
            raise ImportUnavailableError("Imported screenplay bytes failed integrity verification.")
        try:
            parsed = self._parser_for(artifact).parse(data, artifact.filename)
        except ValueError as error:
            raise ImportValidationError(str(error)) from error

        scene_count = sum(element.element_type == "scene_heading" for element in parsed.elements)
        if not parsed.elements or scene_count == 0:
            raise ImportValidationError(
                "A screenplay must contain at least one valid scene heading."
            )

        now = datetime.now(UTC)
        diagnostics = tuple(
            ParseDiagnosticRecord(
                code=warning.warning_code,
                line_number=warning.line_number,
                message=warning.message,
            )
            for warning in parsed.warnings
        )
        record = ParseRunRecord(
            run_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            artifact_id=artifact_id,
            requested_by_user_id=actor_id,
            status="succeeded",
            parser_name=parsed.parser_name,
            parser_version=PARSER_VERSION,
            title=parsed.title.strip() or "Untitled Screenplay",
            scene_count=scene_count,
            element_count=len(parsed.elements),
            result_json=self._serialize_parse_result(parsed),
            diagnostics_hash=self._diagnostics_hash(diagnostics),
            diagnostics=diagnostics,
            created_at=now,
            completed_at=now,
            accepted_at=None,
        )
        try:
            persisted = await self._repository.create_parse_run(record)
        except ImportRecordConflictError:
            persisted = await self._repository.get_parse_run_by_artifact(
                org_id, project_id, artifact_id
            )
            if persisted is None:
                raise
        return self._parse_run_view(persisted)

    async def accept_warnings(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        run_id: UUID,
    ) -> ParseRunView:
        record = await self._repository.get_parse_run(org_id, project_id, run_id)
        if record is None:
            raise ImportNotFoundError("Parse run was not found.")
        if record.diagnostics and record.accepted_at is None:
            await self._repository.accept_warnings(record, actor_id, datetime.now(UTC))
            record = await self._repository.get_parse_run(org_id, project_id, run_id)
            if record is None:
                raise ImportNotFoundError("Parse run was not found.")
        return self._parse_run_view(record)

    async def commit_version_one(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        actor_id: UUID,
    ) -> ScriptVersionView:
        record = await self._repository.get_parse_run(org_id, project_id, run_id)
        if record is None:
            raise ImportNotFoundError("Parse run was not found.")
        if record.status != "succeeded":
            raise ImportConflictError("Only a successful parse run can be committed.")
        try:
            version = await self._repository.commit_version(org_id, project_id, run_id, actor_id)
        except ImportRecordConflictError as error:
            raise ImportConflictError(str(error)) from error
        return self._version_view(version)

    async def get_adjacent_diff(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
    ) -> AdjacentDiffView | None:
        record = await self._repository.get_adjacent_diff(org_id, project_id, after_version_id)
        return self._adjacent_diff_view(record) if record is not None else None

    async def get_current_script(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
    ) -> ProjectScriptProjection | None:
        return await self._repository.get_current_script(org_id, project_id)

    async def get_version(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        version_id: UUID,
    ) -> ScriptVersionView | None:
        record = await self._repository.get_version(org_id, project_id, version_id)
        return self._version_view(record) if record is not None else None

    async def list_versions(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
    ) -> tuple[ScriptVersionView, ...]:
        records = await self._repository.list_versions(org_id, project_id)
        return tuple(self._version_view(record) for record in records)

    @staticmethod
    def _hash_nonce(nonce: str) -> str:
        return hashlib.sha256(nonce.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_filename(filename: str) -> str:
        clean = filename.strip()
        if not clean or PurePath(clean).name != clean or clean in {".", ".."}:
            raise ImportValidationError("Filename must be a safe basename.")
        return clean

    @staticmethod
    def _validate_bytes(data: bytes, content_type: str, filename: str) -> None:
        if not data:
            raise ImportValidationError("Screenplay file is empty.")
        if len(data) > MAX_SCRIPT_SIZE_BYTES:
            raise ImportValidationError(
                f"File size exceeds {MAX_SCRIPT_SIZE_BYTES} bytes.", status_code=413
            )
        lower_filename = filename.lower()
        if lower_filename.endswith((".fountain", ".txt")) or content_type.startswith("text/"):
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ImportValidationError(
                    "Fountain and text screenplay imports must be valid UTF-8.",
                    status_code=415,
                ) from error
        if not validate_screenplay_magic_bytes(data, content_type, filename):
            raise ImportValidationError(
                "File content does not match the declared screenplay format.",
                status_code=415,
            )

    @staticmethod
    def _storage_path(
        org_id: UUID,
        project_id: UUID,
        artifact_id: UUID,
        filename: str,
        *,
        attempt_id: UUID | None = None,
    ) -> str:
        attempt_segment = f"/attempts/{attempt_id}" if attempt_id else ""
        return (
            f"orgs/{org_id}/projects/{project_id}/artifacts/{artifact_id}"
            f"{attempt_segment}/{filename}"
        )

    def _parser_for(self, artifact: ImportArtifactRecord):
        lower_filename = artifact.filename.lower()
        if lower_filename.endswith(".fdx"):
            return self._fdx_parser
        if lower_filename.endswith(".pdf"):
            return self._pdf_parser
        if lower_filename.startswith("paste-"):
            return self._paste_parser
        return self._fountain_parser

    @staticmethod
    def _serialize_parse_result(parsed: ParseResult) -> str:
        return json.dumps(
            {
                "title": parsed.title,
                "elements": [
                    {
                        "ordinal": element.ordinal,
                        "elementType": element.element_type.value,
                        "text": element.text,
                        "sceneNumber": element.scene_number,
                        "pageNumber": element.page_number,
                    }
                    for element in parsed.elements
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _diagnostics_hash(
        diagnostics: tuple[ParseDiagnosticRecord, ...],
    ) -> str:
        payload = [
            {
                "code": diagnostic.code,
                "line": diagnostic.line_number,
                "message": diagnostic.message,
                "requiresAcceptance": diagnostic.requires_acceptance,
            }
            for diagnostic in diagnostics
        ]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _artifact_view(record: ImportArtifactRecord) -> ImportArtifactView:
        return ImportArtifactView(
            artifact_id=record.artifact_id,
            project_id=record.project_id,
            filename=record.filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            sha256_hash=record.sha256_hash,
            status=record.status,
            created_at=record.created_at,
        )

    @staticmethod
    def _parse_run_view(record: ParseRunRecord) -> ParseRunView:
        return ParseRunView(
            run_id=record.run_id,
            artifact_id=record.artifact_id,
            status=record.status,
            parser_name=record.parser_name,
            parser_version=record.parser_version,
            scene_count=record.scene_count,
            element_count=record.element_count,
            warnings=tuple(
                ParseWarningView(
                    code=diagnostic.code,
                    line_number=diagnostic.line_number,
                    message=diagnostic.message,
                )
                for diagnostic in record.diagnostics
            ),
            warnings_accepted=not record.diagnostics or record.accepted_at is not None,
            accepted_at=record.accepted_at,
            created_at=record.created_at,
            completed_at=record.completed_at,
        )

    @staticmethod
    def _version_view(record: ScriptVersionRecord) -> ScriptVersionView:
        return ScriptVersionView(
            version_id=record.version_id,
            script_id=record.script_id,
            project_id=record.project_id,
            version_number=record.ordinal,
            revision_label=f"v{record.ordinal}",
            title=record.title,
            source_artifact_id=record.import_artifact_id,
            parse_run_id=record.parse_run_id,
            source_hash=record.source_hash,
            parser_version=record.parser_version,
            scene_count=record.scene_count,
            element_count=record.element_count,
            created_at=record.created_at,
            predecessor_version_id=record.predecessor_version_id,
            committed_by_user_id=record.committed_by_actor_id,
        )

    @staticmethod
    def _adjacent_diff_view(record: AdjacentDiffRecord) -> AdjacentDiffView:
        changes = tuple(
            ImportScriptService._element_change_view(change) for change in record.changes
        )
        impact_counts: dict[str, int] = {}
        for change in changes:
            impact_counts[change.change_kind] = impact_counts.get(change.change_kind, 0) + 1
        return AdjacentDiffView(
            diff_id=record.diff_id,
            project_id=record.project_id,
            script_id=record.script_id,
            before_version_id=record.before_version_id,
            after_version_id=record.after_version_id,
            before_version_number=record.before_ordinal,
            after_version_number=record.after_ordinal,
            algorithm_version=record.algorithm_version,
            changes=changes,
            impact_counts=impact_counts,
            carried_forward_item_count=ImportScriptService._carried_forward_item_count(changes),
            created_at=record.created_at,
        )

    # Element classifications eligible to carry a predecessor clearance item forward,
    # mirroring the scoped rescan revision plan (``SqlRevisionPlanAdapter``): an
    # unchanged or moved element carries forward only when its lineage confidence is
    # exact or contextual and both element ids are present. A similar (fuzzy) match is
    # treated as modified and re-detected instead, so it is not carried.
    _CARRYABLE_CHANGE_KINDS = frozenset({"unchanged", "moved"})
    _CARRYABLE_CONFIDENCES = frozenset({"exact", "contextual"})

    @staticmethod
    def _carried_forward_item_count(changes: tuple[ElementChangeView, ...]) -> int:
        return sum(
            1
            for change in changes
            if change.change_kind in ImportScriptService._CARRYABLE_CHANGE_KINDS
            and change.confidence in ImportScriptService._CARRYABLE_CONFIDENCES
            and change.before_element_id is not None
            and change.after_element_id is not None
        )

    @staticmethod
    def _element_change_view(record: ElementLineageRecord) -> ElementChangeView:
        return ElementChangeView(
            before_element_id=record.before_element_id,
            after_element_id=record.after_element_id,
            before_ordinal=record.before_ordinal,
            after_ordinal=record.after_ordinal,
            before_text=record.before_text,
            after_text=record.after_text,
            element_type=(
                record.after_element_type
                if record.after_element_type is not None
                else (record.before_element_type or "unknown")
            ),
            change_kind=record.change_kind,
            confidence=record.confidence,
        )
