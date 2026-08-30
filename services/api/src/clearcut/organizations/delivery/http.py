from uuid import UUID

from clearcut.identity.application.session_service import SessionService
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService
from clearcut.projects.application.project_service import ProjectService
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["organizations", "projects"])

ALLOWED_ORIGINS = {"http://localhost:3000", "http://localhost:5173", "http://test"}


def verify_csrf_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin state mutation rejected",
        )


class CreateOrgBody(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=100)


class CreateProjectBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


async def get_authenticated_user_id(request: Request) -> UUID:
    token = request.cookies.get("__Host-clearcut_session")
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    session_service: SessionService = request.app.state.session_service
    context = await session_service.get_session_context(token)
    if not context or not context.authenticated or not context.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return context.user_id


@router.get("/organizations")
async def list_organizations(request: Request) -> dict:
    user_id = await get_authenticated_user_id(request)
    org_service: OrganizationBootstrapService = request.app.state.org_service
    orgs = await org_service.list_organizations_for_user(user_id)

    return {
        "data": [
            {
                "orgId": str(o.org_id),
                "name": o.name,
                "slug": o.slug,
                "createdAt": o.created_at.isoformat(),
            }
            for o in orgs
        ],
        "meta": {"requestId": "req_list_orgs"},
    }


@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(body: CreateOrgBody, request: Request) -> dict:
    verify_csrf_origin(request)
    user_id = await get_authenticated_user_id(request)
    org_service: OrganizationBootstrapService = request.app.state.org_service

    try:
        org, _ = await org_service.bootstrap_organization(
            user_id=user_id,
            name=body.name,
            slug=body.slug,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None

    return {
        "data": {
            "orgId": str(org.org_id),
            "name": org.name,
            "slug": org.slug,
            "createdAt": org.created_at.isoformat(),
        },
        "meta": {"requestId": "req_create_org"},
    }


@router.get("/organization-entry")
async def resolve_organization_entry(request: Request) -> dict:
    user_id = await get_authenticated_user_id(request)
    org_service: OrganizationBootstrapService = request.app.state.org_service
    entry = await org_service.resolve_entry(user_id)

    return {
        "data": {
            "destination": entry.destination,
            "activeOrgId": str(entry.active_org_id) if entry.active_org_id else None,
            "organizations": [
                {
                    "orgId": str(o.org_id),
                    "name": o.name,
                    "slug": o.slug,
                    "createdAt": o.created_at.isoformat(),
                }
                for o in entry.organizations
            ],
        },
        "meta": {"requestId": "req_entry"},
    }


@router.get("/organizations/{org_id}/projects")
async def list_projects(org_id: UUID, request: Request) -> dict:
    await get_authenticated_user_id(request)
    project_service: ProjectService = request.app.state.project_service
    projects = await project_service.list_projects(org_id)

    return {
        "data": [
            {
                "projectId": str(p.project_id),
                "orgId": str(p.org_id),
                "title": p.title,
                "description": p.description,
                "createdAt": p.created_at.isoformat(),
            }
            for p in projects
        ],
        "meta": {"requestId": "req_list_projects"},
    }


@router.post("/organizations/{org_id}/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    org_id: UUID,
    body: CreateProjectBody,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    user_id = await get_authenticated_user_id(request)
    project_service: ProjectService = request.app.state.project_service

    project = await project_service.create_project(
        org_id=org_id,
        actor_id=user_id,
        title=body.title,
        description=body.description,
    )

    return {
        "data": {
            "projectId": str(project.project_id),
            "orgId": str(project.org_id),
            "title": project.title,
            "description": project.description,
            "createdAt": project.created_at.isoformat(),
        },
        "meta": {"requestId": "req_create_project"},
    }
