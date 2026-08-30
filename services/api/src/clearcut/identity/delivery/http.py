
from clearcut.identity.application.session_service import SessionService
from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/v1", tags=["session"])

ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
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


class CreateSessionBody(BaseModel):
    email: EmailStr
    password: str


class RegisterUserBody(BaseModel):
    name: str
    email: EmailStr
    password: str


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def register_user(
    body: RegisterUserBody,
    request: Request,
    response: Response,
) -> dict:
    verify_csrf_origin(request)
    session_service: SessionService = request.app.state.session_service
    identity_repo = request.app.state.identity_repo
    identity_provider = request.app.state.identity_provider

    existing = await identity_repo.get_user_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )

    pw_hash = identity_provider.hash_password(body.password)
    user = await identity_repo.create_user_with_password(
        email=body.email,
        password_hash=pw_hash,
    )

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session, token = await session_service.create_session(
        email=body.email,
        password=body.password,
        ip_address=ip,
        user_agent=ua,
    )

    response.set_cookie(
        key="__Host-clearcut_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )

    return {
        "data": {
            "authenticated": True,
            "userId": str(user.user_id),
            "email": body.email,
            "name": body.name,
        },
        "meta": {"requestId": "req_register"},
    }


def get_session_token_from_request(
    cookie_token: str | None = Cookie(None, alias="__Host-clearcut_session"),
    authorization: str | None = Header(None),
) -> str | None:
    if cookie_token:
        return cookie_token
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]
    return None


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionBody,
    request: Request,
    response: Response,
) -> dict:
    verify_csrf_origin(request)
    session_service: SessionService = request.app.state.session_service

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        session, token = await session_service.create_session(
            email=body.email, password=body.password, ip_address=ip, user_agent=ua
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None

    # Set secure __Host- cookie
    response.set_cookie(
        key="__Host-clearcut_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in production HTTPS
        path="/",
    )

    return {
        "data": {
            "authenticated": True,
            "userId": str(session.user_id),
            "email": body.email,
        },
        "meta": {"requestId": "req_bootstrap"},
    }


@router.get("/session-context")
async def get_session_context(
    request: Request,
    token: str | None = Cookie(None, alias="__Host-clearcut_session"),
) -> dict:
    session_service: SessionService = request.app.state.session_service
    context = await session_service.get_session_context(token or "")

    if not context or not context.authenticated:
        return {
            "data": {"authenticated": False},
            "meta": {"requestId": "req_context"},
        }

    return {
        "data": {
            "authenticated": True,
            "userId": str(context.user_id),
            "email": context.email,
            "activeOrgId": str(context.active_org_id) if context.active_org_id else None,
            "role": context.role,
        },
        "meta": {"requestId": "req_context"},
    }


@router.delete("/sessions/current", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_session(
    request: Request,
    response: Response,
    token: str | None = Cookie(None, alias="__Host-clearcut_session"),
) -> None:
    verify_csrf_origin(request)
    session_service: SessionService = request.app.state.session_service
    if token:
        await session_service.revoke_current_session(token)
    response.delete_cookie(key="__Host-clearcut_session", path="/")
