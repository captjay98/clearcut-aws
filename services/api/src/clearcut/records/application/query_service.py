from uuid import UUID

from clearcut.audit.domain.events import AuthoritativeAuditEvent


class RecordsQueryService:
    def __init__(self) -> None:
        self.events: list[AuthoritativeAuditEvent] = []

    def seed_events(self, events: list[AuthoritativeAuditEvent]) -> None:
        self.events.extend(events)

    def query_records_for_org(
        self,
        org_id: UUID,
        project_id: UUID | None = None,
    ) -> list[AuthoritativeAuditEvent]:
        results = [e for e in self.events if e.org_id == org_id]
        if project_id:
            results = [e for e in results if e.project_id == project_id]
        return sorted(results, key=lambda e: e.occurred_at, reverse=True)
