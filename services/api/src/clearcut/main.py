"""FastAPI application shell entry point."""
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from clearcut.identity.adapters.in_memory import InMemoryIdentityRepository
from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider
from clearcut.identity.application.session_service import SessionService
from clearcut.identity.delivery.http import router as identity_router

app = FastAPI(
    title="ClearCut API",
    version="0.1.0",
    description="Screenplay pre-clearance research desk and evidence workspace API",
)

# Initialize in-memory default state for development/testing
identity_repo = InMemoryIdentityRepository()
identity_provider = Argon2idIdentityProvider()
session_service = SessionService(repository=identity_repo, identity_provider=identity_provider)

app.state.identity_repo = identity_repo
app.state.identity_provider = identity_provider
app.state.session_service = session_service

app.include_router(identity_router)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "0.1.0",
        }
    )
