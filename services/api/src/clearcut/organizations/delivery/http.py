import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID
import uuid6
import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, EmailStr

from clearcut.database import session_scope
from clearcut.identity.delivery.scope import get_request_scope

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


async def get_authenticated_user_id(request: Request) -> UUID:
    scope = await get_request_scope(request)
    return scope.user_id


class CreateOrgBody(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=100)


class CreateProjectBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class CreateInvitationBody(BaseModel):
    email: EmailStr
    role: str = "reviewer"
    projectGrants: list[str] = []


class ChangeRoleBody(BaseModel):
    role: str


class ChangeProjectGrantBody(BaseModel):
    projectIds: list[str]


@router.get("/organizations")
async def list_organizations(request: Request) -> dict:
    scope = await get_request_scope(request)
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT o.id, o.name, o.slug, o.created_at
                FROM organizations o
                JOIN memberships m ON m.org_id = o.id
                WHERE m.user_id = :user_id AND m.status = 'active'
                ORDER BY o.created_at ASC
            """),
            {"user_id": str(scope.user_id)},
        )
        rows = res.fetchall()
        return {
            "data": [
                {
                    "orgId": str(r.id),
                    "name": r.name,
                    "slug": r.slug,
                    "createdAt": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
                }
                for r in rows
            ],
            "meta": {"requestId": "req_list_orgs", "count": len(rows)},
        }


@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(body: CreateOrgBody, request: Request) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request)
    org_id = uuid6.uuid7()
    membership_id = uuid6.uuid7()
    now = datetime.now(UTC)

    async with session_scope() as session:
        # Check if slug exists
        existing = await session.execute(
            sa.text("SELECT id FROM organizations WHERE slug = :slug"),
            {"slug": body.slug},
        )
        if existing.mappings().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization slug already in use",
            )

        await session.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {"id": str(org_id), "name": body.name, "slug": body.slug, "created_at": now},
        )
        await session.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                "VALUES (:id, :org_id, :user_id, 'owner', 'active', :created_at)"
            ),
            {
                "id": str(membership_id),
                "org_id": str(org_id),
                "user_id": str(scope.user_id),
                "created_at": now,
            },
        )

    return {
        "data": {
            "orgId": str(org_id),
            "name": body.name,
            "slug": body.slug,
            "createdAt": now.isoformat(),
        },
        "meta": {"requestId": "req_create_org"},
    }


@router.get("/organization-entry")
async def resolve_organization_entry(request: Request) -> dict:
    scope = await get_request_scope(request)
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT o.id, o.name, o.slug, o.created_at
                FROM organizations o
                JOIN memberships m ON m.org_id = o.id
                WHERE m.user_id = :user_id AND m.status = 'active'
                ORDER BY o.created_at ASC
                LIMIT 1
            """),
            {"user_id": str(scope.user_id)},
        )
        row = res.mappings().first()
        if row:
            return {
                "data": {
                    "hasOrganizations": True,
                    "defaultOrgSlug": row["slug"],
                    "defaultOrgId": str(row["id"]),
                },
                "meta": {"requestId": "req_entry"},
            }
        return {
            "data": {
                "hasOrganizations": False,
                "defaultOrgSlug": None,
                "defaultOrgId": None,
            },
            "meta": {"requestId": "req_entry"},
        }


@router.get("/organizations/{org_id}/projects")
async def list_projects(org_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id)
    async with session_scope() as session:
        res = await session.execute(
            sa.text(
                "SELECT id, org_id, title, description, created_at "
                "FROM projects WHERE org_id = :org_id ORDER BY created_at DESC"
            ),
            {"org_id": str(scope.org_id)},
        )
        rows = res.fetchall()
        return {
            "data": [
                {
                    "projectId": str(r.id),
                    "orgId": str(r.org_id),
                    "title": r.title,
                    "description": r.description,
                    "createdAt": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
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
    scope = await get_request_scope(request, org_id=org_id)
    proj_id = uuid6.uuid7()
    now = datetime.now(UTC)

    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, description, created_at) "
                "VALUES (:id, :org_id, :title, :description, :created_at)"
            ),
            {
                "id": str(proj_id),
                "org_id": str(scope.org_id),
                "title": body.title,
                "description": body.description,
                "created_at": now,
            },
        )

    return {
        "data": {
            "projectId": str(proj_id),
            "orgId": str(scope.org_id),
            "title": body.title,
            "description": body.description,
            "createdAt": now.isoformat(),
        },
        "meta": {"requestId": "req_create_project"},
    }


@router.get("/organizations/{org_id}/projects/{project_id}")
async def get_project(org_id: str, project_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    async with session_scope() as session:
        res = await session.execute(
            sa.text("SELECT id, org_id, title, description, created_at FROM projects WHERE id = :id AND org_id = :org_id"),
            {"id": str(scope.project_id), "org_id": str(scope.org_id)},
        )
        row = res.mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return {
            "data": {
                "projectId": str(row["id"]),
                "orgId": str(row["org_id"]),
                "title": row["title"],
                "description": row["description"],
                "createdAt": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            },
            "meta": {"requestId": "req_get_project"},
        }


@router.get("/organizations/{org_id}/memberships")
async def list_memberships(org_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id)
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT m.id, m.org_id, m.user_id, m.role, m.status, m.created_at, u.email
                FROM memberships m
                JOIN users u ON u.id = m.user_id
                WHERE m.org_id = :org_id
                ORDER BY m.created_at ASC
            """),
            {"org_id": str(scope.org_id)},
        )
        rows = res.fetchall()
        return {
            "data": [
                {
                    "membershipId": str(r.id),
                    "orgId": str(r.org_id),
                    "userId": str(r.user_id),
                    "email": r.email,
                    "role": r.role.lower(),
                    "active": r.status == "active",
                    "createdAt": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
                }
                for r in rows
            ],
            "meta": {"requestId": "req_list_memberships", "count": len(rows)},
        }


@router.post("/organizations/{org_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    org_id: str,
    body: CreateInvitationBody,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    if scope.role not in ["owner", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied to invite members")

    invitation_id = uuid6.uuid7()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=7)

    async with session_scope() as session:
        await session.execute(
            sa.text("""
                INSERT INTO invitations (id, org_id, invited_by_user_id, email, role, token_hash, status, created_at, expires_at)
                VALUES (:id, :org_id, :invited_by_user_id, :email, :role, :token_hash, 'pending', :created_at, :expires_at)
            """),
            {
                "id": str(invitation_id),
                "org_id": str(scope.org_id),
                "invited_by_user_id": str(scope.user_id),
                "email": body.email,
                "role": body.role.lower(),
                "token_hash": token_hash,
                "created_at": now,
                "expires_at": expires_at,
            },
        )

    return {
        "data": {
            "invitationId": str(invitation_id),
            "orgId": str(scope.org_id),
            "email": body.email,
            "role": body.role.lower(),
            "status": "pending",
            "token": token,
            "createdAt": now.isoformat(),
        },
        "meta": {"requestId": "req_create_invitation"},
    }


@router.post("/organizations/{org_id}/memberships/{membership_id}:changeRole")
async def change_membership_role(
    org_id: str,
    membership_id: str,
    body: ChangeRoleBody,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    if scope.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners may change membership roles")

    async with session_scope() as session:
        # Protect last active owner
        target_res = await session.execute(
            sa.text("SELECT id, role, status, user_id FROM memberships WHERE id = :id AND org_id = :org_id"),
            {"id": membership_id, "org_id": str(scope.org_id)},
        )
        target = target_res.mappings().first()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

        if target["role"] == "owner" and body.role.lower() != "owner":
            owner_count_res = await session.execute(
                sa.text("SELECT count(*) FROM memberships WHERE org_id = :org_id AND role = 'owner' AND status = 'active'"),
                {"org_id": str(scope.org_id)},
            )
            owner_count = owner_count_res.scalar() or 0
            if owner_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote the last active owner of an organization",
                )

        await session.execute(
            sa.text("UPDATE memberships SET role = :role WHERE id = :id AND org_id = :org_id"),
            {"id": membership_id, "org_id": str(scope.org_id), "role": body.role.lower()},
        )

    return {
        "data": {
            "membershipId": membership_id,
            "orgId": str(scope.org_id),
            "userId": str(target["user_id"]),
            "role": body.role.lower(),
            "active": target["status"] == "active",
            "createdAt": datetime.now(UTC).isoformat(),
        },
        "meta": {"requestId": "req_change_role"},
    }


@router.post("/organizations/{org_id}/memberships/{membership_id}:deactivate")
async def deactivate_membership(
    org_id: str,
    membership_id: str,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    if scope.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners may deactivate memberships")

    async with session_scope() as session:
        target_res = await session.execute(
            sa.text("SELECT id, role, status, user_id FROM memberships WHERE id = :id AND org_id = :org_id"),
            {"id": membership_id, "org_id": str(scope.org_id)},
        )
        target = target_res.mappings().first()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

        if target["role"] == "owner":
            owner_count_res = await session.execute(
                sa.text("SELECT count(*) FROM memberships WHERE org_id = :org_id AND role = 'owner' AND status = 'active'"),
                {"org_id": str(scope.org_id)},
            )
            owner_count = owner_count_res.scalar() or 0
            if owner_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot deactivate the last active owner of an organization",
                )

        await session.execute(
            sa.text("UPDATE memberships SET status = 'inactive' WHERE id = :id AND org_id = :org_id"),
            {"id": membership_id, "org_id": str(scope.org_id)},
        )

    return {
        "data": {
            "membershipId": membership_id,
            "orgId": str(scope.org_id),
            "userId": str(target["user_id"]),
            "role": target["role"],
            "active": False,
            "createdAt": datetime.now(UTC).isoformat(),
        },
        "meta": {"requestId": "req_deactivate_membership"},
    }


@router.post("/invitations/{token}:accept")
async def accept_invitation(token: str, request: Request) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)

    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT id, org_id, email, role, status, expires_at
                FROM invitations
                WHERE token_hash = :token_hash AND status = 'pending'
            """),
            {"token_hash": token_hash},
        )
        inv = res.mappings().first()
        if not inv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired invitation")

        if inv["expires_at"] and (inv["expires_at"] if isinstance(inv["expires_at"], datetime) else datetime.fromisoformat(str(inv["expires_at"]))) < now:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired")

        membership_id = uuid6.uuid7()
        await session.execute(
            sa.text("""
                INSERT INTO memberships (id, org_id, user_id, role, status, created_at)
                VALUES (:id, :org_id, :user_id, :role, 'active', :created_at)
                ON CONFLICT (org_id, user_id) DO UPDATE SET status = 'active', role = EXCLUDED.role
            """),
            {
                "id": str(membership_id),
                "org_id": str(inv["org_id"]),
                "user_id": str(scope.user_id),
                "role": inv["role"],
                "created_at": now,
            },
        )
        await session.execute(
            sa.text("UPDATE invitations SET status = 'accepted', accepted_at = :accepted_at WHERE id = :id"),
            {"id": str(inv["id"]), "accepted_at": now},
        )

    return {
        "data": {
            "membershipId": str(membership_id),
            "orgId": str(inv["org_id"]),
            "userId": str(scope.user_id),
            "role": inv["role"],
            "active": True,
            "createdAt": now.isoformat(),
        },
        "meta": {"requestId": "req_accept_invitation"},
    }
