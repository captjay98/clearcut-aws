import pytest
import uuid6
from clearcut.projects.adapters.in_memory import InMemoryProjectRepository
from clearcut.projects.application.project_service import ProjectService


@pytest.mark.asyncio
async def test_project_scope_enforces_org_id_tuple():
    repo = InMemoryProjectRepository()
    service = ProjectService(repository=repo)

    org_a = uuid6.uuid7()
    org_b = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    project = await service.create_project(
        org_id=org_a,
        actor_id=actor_id,
        title="Inception 2",
        description="Sci-fi sequel"
    )
    assert project.org_id == org_a

    # Accessible within Org A
    fetched = await service.get_project(org_id=org_a, project_id=project.project_id)
    assert fetched is not None
    assert fetched.title == "Inception 2"

    # Inaccessible from Org B (cross-tenant rejection)
    cross_fetched = await service.get_project(org_id=org_b, project_id=project.project_id)
    assert cross_fetched is None
