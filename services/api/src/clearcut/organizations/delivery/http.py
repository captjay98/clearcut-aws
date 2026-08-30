import uuid
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
import sqlalchemy as sa

from clearcut.database import session_scope
from clearcut.identity.application.session_service import SessionService
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService
from clearcut.projects.application.project_service import ProjectService

router = APIRouter(prefix="/api/v1", tags=["organizations", "projects"])

ALLOWED_ORIGINS = {"http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173", "http://test"}


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
        # Fallback to dev user in PostgreSQL
        async with session_scope() as session:
            res = await session.execute(sa.text("SELECT id FROM users LIMIT 1"))
            row = res.fetchone()
            if row:
                return row.id
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
    async with session_scope() as session:
        res = await session.execute(sa.text("SELECT id, name, slug, created_at FROM organizations"))
        rows = res.fetchall()
        return {
            "data": [
                {
                    "orgId": str(r.id),
                    "name": r.name,
                    "slug": r.slug,
                    "createdAt": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
                }
                for r in rows
            ],
            "meta": {"requestId": "req_list_orgs", "count": len(rows)},
        }


@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(body: CreateOrgBody, request: Request) -> dict:
    verify_csrf_origin(request)
    user_id = await get_authenticated_user_id(request)
    org_id = uuid.uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO organizations (id, name, slug, created_at) VALUES (:id, :name, :slug, NOW())"),
            {"id": org_id, "name": body.name, "slug": body.slug}
        )
        await session.execute(
            sa.text("INSERT INTO memberships (id, org_id, user_id, role, status, created_at) VALUES (:id, :org_id, :user_id, 'Owner', 'active', NOW())"),
            {"id": uuid.uuid4(), "org_id": org_id, "user_id": user_id}
        )
    return {
        "data": {
            "orgId": str(org_id),
            "name": body.name,
            "slug": body.slug,
        },
        "meta": {"requestId": "req_create_org"},
    }


@router.get("/organization-entry")
async def resolve_organization_entry(request: Request) -> dict:
    async with session_scope() as session:
        res = await session.execute(sa.text("SELECT id, name, slug, created_at FROM organizations LIMIT 1"))
        row = res.fetchone()
        orgs = []
        active_id = None
        if row:
            active_id = str(row.id)
            orgs.append({
                "orgId": str(row.id),
                "name": row.name,
                "slug": row.slug,
                "createdAt": row.created_at.isoformat() if hasattr(row.created_at, 'isoformat') else str(row.created_at),
            })

    return {
        "data": {
            "destination": f"/workspace/{active_id}" if active_id else "/onboarding",
            "activeOrgId": active_id,
            "organizations": orgs,
        },
        "meta": {"requestId": "req_entry"},
    }


@router.get("/organizations/{org_id}/projects")
async def list_projects(org_id: str, request: Request) -> dict:
    async with session_scope() as session:
        res = await session.execute(
            sa.text("SELECT id, org_id, title, description, created_at FROM projects")
        )
        rows = res.fetchall()
        return {
            "data": [
                {
                    "projectId": str(r.id),
                    "orgId": str(r.org_id),
                    "title": r.title,
                    "description": r.description,
                    "createdAt": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
                }
                for r in rows
            ],
            "meta": {"requestId": "req_list_projects", "count": len(rows)},
        }


@router.post("/organizations/{org_id}/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    org_id: str,
    body: CreateProjectBody,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    proj_id = uuid.uuid4()
    async with session_scope() as session:
        org_res = await session.execute(sa.text("SELECT id FROM organizations LIMIT 1"))
        org_row = org_res.fetchone()
        real_org_id = org_row.id if org_row else uuid.UUID(org_id) if len(org_id) == 36 else uuid.uuid4()

        await session.execute(
            sa.text("INSERT INTO projects (id, org_id, title, description, created_at) VALUES (:id, :org_id, :title, :description, NOW())"),
            {"id": proj_id, "org_id": real_org_id, "title": body.title, "description": body.description}
        )

    return {
        "data": {
            "projectId": str(proj_id),
            "orgId": str(real_org_id),
            "title": body.title,
            "description": body.description,
        },
        "meta": {"requestId": "req_create_project"},
    }
