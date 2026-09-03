from datetime import date
from uuid import UUID

from clearcut.projects.domain.models import Project
from clearcut.projects.ports.project_repository import ProjectRepositoryPort


class ProjectService:
    def __init__(self, repository: ProjectRepositoryPort) -> None:
        self.repository = repository

    async def create_project(
        self,
        org_id: UUID,
        actor_id: UUID,
        title: str,
        description: str | None = None,
        production_type: str | None = None,
        production_stage: str | None = None,
        jurisdiction: str | None = None,
        target_lock_date: date | None = None,
        review_brief: str | None = None,
    ) -> Project:
        project = Project.create(
            org_id=org_id,
            title=title,
            description=description,
            production_type=production_type,
            production_stage=production_stage,
            jurisdiction=jurisdiction,
            target_lock_date=target_lock_date,
            review_brief=review_brief,
        )
        return await self.repository.create_project(project)

    async def get_project(
        self,
        org_id: UUID,
        project_id: UUID,
    ) -> Project | None:
        return await self.repository.get_project(org_id=org_id, project_id=project_id)

    async def list_projects(self, org_id: UUID) -> list[Project]:
        return await self.repository.list_projects(org_id=org_id)
