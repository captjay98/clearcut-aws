"""Shared truthful HTTP error responses for delivery boundaries."""
from collections.abc import Mapping

import uuid6
from fastapi import status
from fastapi.responses import JSONResponse


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return the canonical error envelope with a traceable request identifier."""
    request_id = str(uuid6.uuid7())
    response_headers = dict(headers or {})
    response_headers["x-request-id"] = request_id
    return JSONResponse(
        status_code=status_code,
        headers=response_headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "requestId": request_id,
                "retryable": retryable,
            }
        },
    )


def capability_unavailable(message: str) -> JSONResponse:
    """Return a stable error envelope without implying that work succeeded."""
    return error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="capability_unavailable",
        message=message,
    )
