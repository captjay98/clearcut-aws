"""Shared exact-origin validation for browser state mutations."""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://localhost:29000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:29000",
    "http://test",
}


def verify_csrf_origin(request: Request) -> None:
    """Reject malformed or untrusted Origin headers before state mutation."""
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if not origin:
        return

    parsed_origin = urlsplit(origin)
    valid_origin = (
        parsed_origin.scheme in {"http", "https"}
        and bool(parsed_origin.netloc)
        and parsed_origin.username is None
        and parsed_origin.password is None
        and parsed_origin.path in {"", "/"}
        and not parsed_origin.query
        and not parsed_origin.fragment
    )
    if not valid_origin:
        _reject_cross_origin_mutation()

    if host and parsed_origin.netloc == host and parsed_origin.scheme == request.url.scheme:
        return
    if origin.rstrip("/") in ALLOWED_ORIGINS:
        return
    _reject_cross_origin_mutation()


def _reject_cross_origin_mutation() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cross-origin state mutation rejected",
    )
