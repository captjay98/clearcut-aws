from abc import ABC, abstractmethod
from uuid import UUID

from clearcut.projects.domain.models import Project


class ProjectRepositoryPort(ABC):
    @abstractmethod
    async def create_project(self, project: Project) -> Project:
        pass

    @abstractmethod
    async def get_project(self, org_id: UUID, project_id: UUID) -> Project | None:
        pass

    @abstractmethod
    async def list_projects(self, org_id: UUID) -> list[Project]:
        pass
