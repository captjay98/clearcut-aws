from clearcut.csrf import verify_csrf_origin
from clearcut.delivery_errors import error_response
from clearcut.identity.application.session_service import SessionService
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix="/api/v1", tags=["session"])

LOCAL_SESSION_COOKIE = "clearcut_session"
HOST_SESSION_COOKIE = "__Host-clearcut_session"


def _session_cookie_policy(request: Request) -> tuple[str, bool]:
    if request.url.scheme == "https":
        return HOST_SESSION_COOKIE, True
    return LOCAL_SESSION_COOKIE, False


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    cookie_name, secure = _session_cookie_policy(request)
    response.set_cookie(
        key=cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def _delete_session_cookies(response: Response) -> None:
    response.delete_cookie(
        key=LOCAL_SESSION_COOKIE,
        path="/",
        secure=False,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=HOST_SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def get_session_token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if authorization:
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.casefold() == "bearer" and token:
            return token
        return None

    cookie_name, _secure = _session_cookie_policy(request)
    return request.cookies.get(cookie_name)


class CreateSessionBody(BaseModel):
    email: EmailStr
    password: str


class RegisterUserBody(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    operation_id="registerUser",
    response_model=None,
)
async def register_user(
    body: RegisterUserBody,
    request: Request,
    response: Response,
) -> dict | JSONResponse:
    verify_csrf_origin(request)
    session_service: SessionService = request.app.state.session_service
    identity_repo = request.app.state.identity_repo
    identity_provider = request.app.state.identity_provider

    existing = await identity_repo.get_user_by_email(body.email)
    if existing:
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="conflict",
            message="An account with this email address already exists.",
        )

    password_hash = identity_provider.hash_password(body.password)
    user = await identity_repo.create_user_with_password(
        email=body.email,
        password_hash=password_hash,
    )

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    _, token = await session_service.create_session(
        email=body.email,
        password=body.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    _set_session_cookie(request, response, token)

    return {
        "data": {
            "authenticated": True,
            "userId": str(user.user_id),
            "email": body.email,
            "name": body.name,
        },
        "meta": {"requestId": "req_register"},
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED, operation_id="createSession")
async def create_session(
    body: CreateSessionBody,
    request: Request,
    response: Response,
) -> dict:
    verify_csrf_origin(request)
    session_service: SessionService = request.app.state.session_service

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        session, token = await session_service.create_session(
            email=body.email,
            password=body.password,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None

    _set_session_cookie(request, response, token)

    return {
        "data": {
            "authenticated": True,
            "userId": str(session.user_id),
            "email": body.email,
        },
        "meta": {"requestId": "req_bootstrap"},
    }


@router.get("/session-context", operation_id="getSessionContext")
async def get_session_context(request: Request) -> dict:
    session_service: SessionService = request.app.state.session_service
    token = get_session_token_from_request(request)
    context = await session_service.get_session_context(token or "")

    if not context or not context.authenticated:
        return {
            "data": {
                "authenticated": False,
                "userId": None,
                "email": None,
                "activeOrgId": None,
                "role": None,
            },
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


@router.delete(
    "/sessions/current",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteCurrentSession",
)
async def delete_current_session(request: Request, response: Response) -> None:
    verify_csrf_origin(request)
    session_service: SessionService = request.app.state.session_service
    token = get_session_token_from_request(request)
    if token:
        await session_service.revoke_current_session(token)
    _delete_session_cookies(response)
