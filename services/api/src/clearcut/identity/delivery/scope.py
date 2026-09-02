from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.identity.delivery.http import get_session_token_from_request
from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class RequestScope:
    user_id: UUID
    email: str
    org_id: UUID | None = None
    role: str | None = None
    project_id: UUID | None = None


async def get_request_scope(
    request: Request,
    org_id: str | None = None,
    project_id: str | None = None,
) -> RequestScope:
    # 1. Extract the explicit Bearer token or the cookie allowed for this scheme.
    token = get_session_token_from_request(request)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # 2. Validate session against database or session service
    session_service = getattr(request.app.state, "session_service", None)
    context = None
    if session_service:
        try:
            context = await session_service.get_session_context(token)
        except Exception:
            context = None

    if not context or not context.authenticated or not context.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    user_id = context.user_id
    email = context.email or ""

    # 3. If org_id is requested, enforce membership
    parsed_org_id: UUID | None = None
    role: str | None = None
    if org_id:
        try:
            parsed_org_id = UUID(org_id)
        except ValueError:
            # Check if slug was passed instead of UUID
            async with session_scope() as session:
                res = await session.execute(
                    sa.text("SELECT id FROM organizations WHERE slug = :slug"),
                    {"slug": org_id},
                )
                row = res.mappings().first()
                if row:
                    parsed_org_id = UUID(str(row["id"]))
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Organization not found",
                    ) from None

        async with session_scope() as session:
            res = await session.execute(
                sa.text(
                    "SELECT role, status FROM memberships "
                    "WHERE org_id = :org_id AND user_id = :user_id AND status = 'active'"
                ),
                {"org_id": str(parsed_org_id), "user_id": str(user_id)},
            )
            membership_row = res.mappings().first()
            if not membership_row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to organization",
                )
            role = membership_row["role"]

    # 4. If project_id is requested, enforce project ownership within org
    parsed_project_id: UUID | None = None
    if project_id and parsed_org_id:
        try:
            parsed_project_id = UUID(project_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            ) from None

        async with session_scope() as session:
            res = await session.execute(
                sa.text(
                    "SELECT id FROM projects WHERE org_id = :org_id AND id = :project_id"
                ),
                {"org_id": str(parsed_org_id), "project_id": str(parsed_project_id)},
            )
            if not res.mappings().first():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found in organization",
                )

    return RequestScope(
        user_id=user_id,
        email=email,
        org_id=parsed_org_id,
        role=role,
        project_id=parsed_project_id,
    )
