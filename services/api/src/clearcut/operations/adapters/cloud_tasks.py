"""Cloud Tasks REST adapter with lazy ADC and no local fallback."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC
from typing import Any
from urllib.parse import urlsplit

import google.auth
import httpx
from clearcut.operations.ports.job_dispatcher import (
    AccessTokenPort,
    DispatchOutboxPort,
    DispatchReceipt,
    DispatchStatus,
    JobDispatchError,
    JobDispatchRequest,
    TaskClientPort,
    TokenVerifierPort,
)
from clearcut.operations.ports.job_repository import JobRecord
from fastapi import BackgroundTasks
from google.auth.transport.requests import Request

EXECUTION_PATH = "/api/internal/jobs:execute"
RECONCILIATION_PATH = "/api/internal/jobs:reconcile"


@dataclass(frozen=True)
class CloudTasksConfiguration:
    project_id: str
    location: str
    queue: str
    target_url: str
    audience: str
    service_account_email: str

    def __post_init__(self) -> None:
        target, audience = urlsplit(self.target_url), urlsplit(self.audience)
        if (
            target.scheme != "https"
            or not target.netloc
            or target.username
            or target.password
            or target.path != EXECUTION_PATH
            or target.query
            or target.fragment
            or audience.scheme != "https"
            or audience.netloc != target.netloc
            or audience.path not in {"", "/"}
            or audience.query
            or audience.fragment
            or audience.username
            or audience.password
        ):
            raise ValueError(
                "Cloud Tasks requires an HTTPS same-service execution URL and audience."
            )
        if any(
            not re.fullmatch(r"[A-Za-z0-9_-]+", value)
            for value in (
                self.project_id,
                self.location,
                self.queue,
            )
        ):
            raise ValueError(
                "Cloud Tasks project, location, and queue must be resource identifiers."
            )
        if not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com", self.service_account_email
        ):
            raise ValueError("Cloud Tasks requires a dedicated service account email.")

    @property
    def parent(self) -> str:
        return f"projects/{self.project_id}/locations/{self.location}/queues/{self.queue}"


def task_name(configuration: CloudTasksConfiguration, command: JobDispatchRequest) -> str:
    generation = ":".join(
        (
            str(command.org_id),
            str(command.project_id),
            str(command.job_id),
            command.available_at.astimezone(UTC).isoformat(),
            str(command.attempt_count),
        )
    )
    digest = hashlib.sha256(generation.encode()).hexdigest()
    return f"{configuration.parent}/tasks/cc-{digest}"


class GoogleAccessToken:
    async def authorization(self) -> str:
        return await asyncio.to_thread(self._authorization)

    @staticmethod
    def _authorization() -> str:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        if not credentials.token:
            raise JobDispatchError("Cloud Tasks credentials are unavailable.")
        return f"Bearer {credentials.token}"


class CloudTasksClient:
    def __init__(
        self,
        *,
        configuration: CloudTasksConfiguration,
        credentials: AccessTokenPort,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.configuration = configuration
        self._credentials = credentials
        self._client = client

    async def create_task(self, command: JobDispatchRequest) -> DispatchReceipt:
        name = task_name(self.configuration, command)
        body = json.dumps(
            {
                "orgId": str(command.org_id),
                "projectId": str(command.project_id),
                "jobId": str(command.job_id),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        payload = {
            "task": {
                "name": name,
                "scheduleTime": command.available_at.astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "dispatchDeadline": "1800s",
                "httpRequest": {
                    "httpMethod": "POST",
                    "url": self.configuration.target_url,
                    "headers": {"Content-Type": "application/json"},
                    "body": base64.b64encode(body).decode(),
                    "oidcToken": {
                        "serviceAccountEmail": self.configuration.service_account_email,
                        "audience": self.configuration.audience,
                    },
                },
            }
        }
        try:
            authorization = await self._credentials.authorization()
            if self._client is not None:
                response = await self._client.post(
                    f"https://cloudtasks.googleapis.com/v2/{self.configuration.parent}/tasks",
                    json=payload,
                    headers={"Authorization": authorization},
                    timeout=20,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"https://cloudtasks.googleapis.com/v2/{self.configuration.parent}/tasks",
                        json=payload,
                        headers={"Authorization": authorization},
                        timeout=20,
                    )
            if response.status_code == 409:
                return DispatchReceipt(DispatchStatus.ALREADY_EXISTS, name)
            response.raise_for_status()
            if response.json().get("name") != name:
                raise JobDispatchError("Cloud Tasks returned an unexpected task identity.")
            return DispatchReceipt(DispatchStatus.CONFIRMED, name)
        except Exception as error:
            raise JobDispatchError("Cloud Tasks delivery could not be confirmed.") from error


class OidcAuthError(RuntimeError):
    """Raised when OIDC authorization or token claims fail validation."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 403,
        code: str = "permission_denied",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class GoogleTokenVerifier:
    def verify_token(self, token: str, *, audience: str) -> dict[str, Any]:
        from google.auth.transport.requests import Request as AuthRequest
        from google.oauth2 import id_token

        return dict(id_token.verify_oauth2_token(token, AuthRequest(), audience=audience))


class UnverifiedTokenVerifier:
    def verify_token(self, token: str, *, audience: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise OidcAuthError(
                "Malformed token structure.",
                status_code=401,
                code="authentication_required",
            )
        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        except Exception as error:
            raise OidcAuthError(
                "Invalid token payload encoding.",
                status_code=401,
                code="authentication_required",
            ) from error
        return claims


def verify_google_oidc_claims(
    token: str,
    *,
    expected_audience: str,
    expected_caller: str,
    verifier: TokenVerifierPort | None = None,
) -> dict[str, Any]:
    active_verifier = verifier or GoogleTokenVerifier()
    try:
        claims = active_verifier.verify_token(token, audience=expected_audience)
    except OidcAuthError:
        raise
    except Exception as error:
        raise OidcAuthError(
            "Token verification failed.",
            status_code=401,
            code="authentication_required",
        ) from error

    issuer = claims.get("iss")
    if issuer not in {"https://accounts.google.com", "accounts.google.com"}:
        raise OidcAuthError("Invalid token issuer.", status_code=403, code="permission_denied")

    aud = claims.get("aud")
    if aud != expected_audience:
        raise OidcAuthError("Token audience mismatch.", status_code=403, code="permission_denied")

    email = claims.get("email")
    if email != expected_caller:
        raise OidcAuthError(
            "Unauthorized caller identity.", status_code=403, code="permission_denied"
        )

    if not claims.get("email_verified", False):
        raise OidcAuthError("Caller email not verified.", status_code=403, code="permission_denied")

    return claims


class CloudTasksJobDispatcher:
    mode = "cloud_tasks"
    durable = True

    def __init__(
        self,
        *,
        client: TaskClientPort,
        outbox: DispatchOutboxPort | None = None,
    ) -> None:
        self._client = client
        self._outbox = outbox

    def dispatch(self, background_tasks: BackgroundTasks, job: JobRecord) -> DispatchReceipt:
        command = JobDispatchRequest.from_job(job)
        background_tasks.add_task(self._dispatch_safely, command)
        return DispatchReceipt(status=DispatchStatus.SCHEDULED, task_name=None)

    async def _dispatch_safely(self, command: JobDispatchRequest) -> None:
        import logging

        logger = logging.getLogger(__name__)
        try:
            await self._client.create_task(command)
            if self._outbox is not None:
                await self._outbox.confirm_dispatch(command)
        except Exception:
            logger.exception(
                "Cloud Tasks delivery failed for job_id=%s org_id=%s project_id=%s; durable intent remains pending.",
                command.job_id,
                command.org_id,
                command.project_id,
            )
