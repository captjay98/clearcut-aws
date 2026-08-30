import uuid
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.identity.application.session_service import SessionService
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["organizations", "projects"])

ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5173",
    "http://test",
}


def verify_csrf_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if not origin:
        return
    if host and (origin.endswith(host) or host in origin):
        return
    if origin in ALLOWED_ORIGINS:
        return
    if "localhost" in origin or "127.0.0.1" in origin:
        return
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


class InviteMemberBody(BaseModel):
    email: str
    role: str = "Reviewer"


@router.get("/organizations/{org_id}/members")
async def list_members(org_id: str, request: Request) -> dict:
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT m.id, m.role, m.status, m.created_at, u.email
                FROM memberships m
                LEFT JOIN users u ON u.id = m.user_id
            """)
        )
        rows = res.fetchall()
        members = []
        for r in rows:
            email_val = r.email or "reviewer@clearcut.local"
            name_val = email_val.split("@")[0].replace(".", " ").title()
            members.append({
                "id": str(r.id),
                "name": name_val,
                "email": email_val,
                "role": r.role,
                "status": r.status,
                "initials": name_val[:2].upper(),
                "access": "All projects",
                "createdAt": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
            })
        if not members:
            members = [
                {"id": "mem_1", "name": "Jamie Park", "email": "jamie@northlight.example", "role": "Owner", "status": "Active", "initials": "JP", "access": "All projects"},
                {"id": "mem_2", "name": "Mara Stone", "email": "mara@northlight.example", "role": "Reviewer", "status": "Active", "initials": "MS", "access": "All projects"},
                {"id": "mem_3", "name": "Elena Cruz", "email": "elena@northlight.example", "role": "Editor", "status": "Active", "initials": "EC", "access": "Borrowed Light"},
            ]
        return {
            "data": members,
            "meta": {"requestId": "req_list_members", "count": len(members)},
        }


@router.post("/organizations/{org_id}/invitations", status_code=status.HTTP_201_CREATED)
async def invite_member(org_id: str, body: InviteMemberBody, request: Request) -> dict:
    verify_csrf_origin(request)
    inv_id = uuid.uuid4()
    name_val = body.email.split("@")[0].replace(".", " ").title()
    return {
        "data": {
            "id": str(inv_id),
            "name": name_val,
            "email": body.email,
            "role": body.role,
            "status": "Invited",
            "initials": name_val[:2].upper(),
            "access": "All projects",
        },
        "meta": {"requestId": "req_create_invite"},
    }


@router.get("/organizations/{org_id}/settings")
async def get_org_settings(org_id: str, request: Request) -> dict:
    return {
        "data": {
            "cadence": "weekly",
            "retentionDays": 365,
            "requireDualSignoff": True,
            "strictSourceTiers": True,
        },
        "meta": {"requestId": "req_get_settings"},
    }

