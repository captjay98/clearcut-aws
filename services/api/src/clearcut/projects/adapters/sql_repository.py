from datetime import date, datetime
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.projects.domain.models import Project
from clearcut.projects.ports.project_repository import ProjectRepositoryPort
from sqlalchemy.ext.asyncio import AsyncSession


class SqlProjectRepository(ProjectRepositoryPort):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def create_project(self, project: Project) -> Project:
        await self.db.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, description, production_type, "
                "production_stage, jurisdiction, target_lock_date, review_brief, created_at) "
                "VALUES (:id, :org_id, :title, :description, :production_type, "
                ":production_stage, :jurisdiction, :target_lock_date, :review_brief, :created_at)"
            ),
            {
                "id": str(project.project_id),
                "org_id": str(project.org_id),
                "title": project.title,
                "description": project.description,
                "production_type": project.production_type,
                "production_stage": project.production_stage,
                "jurisdiction": project.jurisdiction,
                "target_lock_date": project.target_lock_date,
                "review_brief": project.review_brief,
                "created_at": project.created_at,
            },
        )
        await self.db.flush()
        return project

    async def get_project(self, org_id: UUID, project_id: UUID) -> Project | None:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, title, description, production_type, production_stage, "
                "jurisdiction, target_lock_date, review_brief, created_at "
                "FROM projects WHERE org_id = :org_id AND id = :id"
            ),
            {"org_id": str(org_id), "id": str(project_id)},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Project(
            project_id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            title=row["title"],
            description=row["description"],
            created_at=row["created_at"]
            if isinstance(row["created_at"], datetime)
            else datetime.fromisoformat(str(row["created_at"])),
            production_type=row["production_type"],
            production_stage=row["production_stage"],
            jurisdiction=row["jurisdiction"],
            target_lock_date=(
                row["target_lock_date"]
                if isinstance(row["target_lock_date"], date)
                else date.fromisoformat(str(row["target_lock_date"]))
                if row["target_lock_date"] is not None
                else None
            ),
            review_brief=row["review_brief"],
        )

    async def list_projects(self, org_id: UUID) -> list[Project]:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, title, description, production_type, production_stage, "
                "jurisdiction, target_lock_date, review_brief, created_at "
                "FROM projects WHERE org_id = :org_id ORDER BY created_at DESC"
            ),
            {"org_id": str(org_id)},
        )
        return [
            Project(
                project_id=UUID(str(row["id"])),
                org_id=UUID(str(row["org_id"])),
                title=row["title"],
                description=row["description"],
                created_at=row["created_at"]
                if isinstance(row["created_at"], datetime)
                else datetime.fromisoformat(str(row["created_at"])),
                production_type=row["production_type"],
                production_stage=row["production_stage"],
                jurisdiction=row["jurisdiction"],
                target_lock_date=(
                    row["target_lock_date"]
                    if isinstance(row["target_lock_date"], date)
                    else date.fromisoformat(str(row["target_lock_date"]))
                    if row["target_lock_date"] is not None
                    else None
                ),
                review_brief=row["review_brief"],
            )
            for row in res.mappings().all()
        ]


class DatabaseProjectRepository(ProjectRepositoryPort):
    async def create_project(self, project: Project) -> Project:
        async with session_scope() as db:
            repo = SqlProjectRepository(db)
            return await repo.create_project(project)

    async def get_project(self, org_id: UUID, project_id: UUID) -> Project | None:
        async with session_scope() as db:
            repo = SqlProjectRepository(db)
            return await repo.get_project(org_id, project_id)

    async def list_projects(self, org_id: UUID) -> list[Project]:
        async with session_scope() as db:
            repo = SqlProjectRepository(db)
            return await repo.list_projects(org_id)
