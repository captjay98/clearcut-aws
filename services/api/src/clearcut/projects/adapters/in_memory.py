from uuid import UUID

from clearcut.projects.domain.models import Project
from clearcut.projects.ports.project_repository import ProjectRepositoryPort


class InMemoryProjectRepository(ProjectRepositoryPort):
    def __init__(self) -> None:
        self.projects: dict[tuple[UUID, UUID], Project] = {}

    async def create_project(self, project: Project) -> Project:
        self.projects[(project.org_id, project.project_id)] = project
        return project

    async def get_project(self, org_id: UUID, project_id: UUID) -> Project | None:
        return self.projects.get((org_id, project_id))

    async def list_projects(self, org_id: UUID) -> list[Project]:
        return [p for (o_id, _), p in self.projects.items() if o_id == org_id]
