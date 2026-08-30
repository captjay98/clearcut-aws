from uuid import UUID

from clearcut.scripts.domain.versions import ParseResult, Script, ScriptVersion
from clearcut.scripts.ports.object_storage import ObjectStoragePort
from clearcut.scripts.ports.parser import ScriptParserPort


class ParseService:
    def __init__(
        self,
        storage: ObjectStoragePort,
        parser: ScriptParserPort,
    ) -> None:
        self.storage = storage
        self.parser = parser
        self.scripts: dict[UUID, Script] = {}
        self.versions: dict[UUID, ScriptVersion] = {}

    def parse(self, data: bytes, filename: str) -> ParseResult:
        return self.parser.parse(data, filename)

    async def commit_version_one(
        self,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        title: str,
        parse_result: ParseResult,
        source_hash: str,
    ) -> tuple[Script, ScriptVersion]:
        script = Script.create(
            org_id=org_id,
            project_id=project_id,
            title=title or parse_result.title,
        )
        self.scripts[script.script_id] = script

        # Bind elements to version
        version = ScriptVersion.create(
            script_id=script.script_id,
            org_id=org_id,
            project_id=project_id,
            ordinal=1,
            source_hash=source_hash,
            parser_version="1.0.0",
            elements=parse_result.elements,
        )
        self.versions[version.version_id] = version

        return script, version
