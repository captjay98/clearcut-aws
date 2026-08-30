"""FastAPI application shell entry point."""
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from clearcut.decisions.delivery.http import router as decisions_router
from clearcut.evaluation.delivery.http import router as evaluation_router
from clearcut.export.delivery.http import router as export_router
from clearcut.identity.adapters.in_memory import InMemoryIdentityRepository
from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider
from clearcut.identity.application.session_service import SessionService
from clearcut.identity.delivery.http import router as identity_router
from clearcut.items.delivery.http import router as items_router
from clearcut.monitoring.delivery.http import router as monitoring_router
from clearcut.organizations.adapters.in_memory import InMemoryOrganizationRepository
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService
from clearcut.organizations.delivery.http import router as organization_router
from clearcut.projects.adapters.in_memory import InMemoryProjectRepository
from clearcut.projects.application.project_service import ProjectService
from clearcut.records.delivery.http import router as records_router
from clearcut.scripts.adapters.in_memory_storage import InMemoryObjectStorage
from clearcut.scripts.application.upload_service import UploadService
from clearcut.scripts.delivery.http import router as scripts_router

app = FastAPI(
    title="ClearCut API",
    version="0.1.0",
    description="Screenplay pre-clearance research desk and evidence workspace API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize in-memory default state for development/testing
identity_repo = InMemoryIdentityRepository()
identity_provider = Argon2idIdentityProvider()
session_service = SessionService(
    repository=identity_repo,
    identity_provider=identity_provider,
)

org_repo = InMemoryOrganizationRepository()
org_service = OrganizationBootstrapService(repository=org_repo)

project_repo = InMemoryProjectRepository()
project_service = ProjectService(repository=project_repo)

storage = InMemoryObjectStorage()
upload_service = UploadService(storage=storage)

app.state.identity_repo = identity_repo
app.state.identity_provider = identity_provider
app.state.session_service = session_service
app.state.org_repo = org_repo
app.state.org_service = org_service
app.state.project_repo = project_repo
app.state.project_service = project_service
app.state.storage = storage
app.state.upload_service = upload_service

app.include_router(identity_router)
app.include_router(organization_router)
app.include_router(scripts_router)
app.include_router(items_router)
app.include_router(decisions_router)
app.include_router(monitoring_router)
app.include_router(records_router)
app.include_router(evaluation_router)
app.include_router(export_router)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "0.1.0",
        }
    )


# Optional Unified SPA Serving (for single-container self-hosted & Cloud Run deployment)
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

web_dist_env = os.getenv("WEB_DIST_PATH")
if web_dist_env and Path(web_dist_env).is_dir():
    assets_dir = Path(web_dist_env) / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        target = Path(web_dist_env) / full_path
        if target.is_file():
            return FileResponse(target)
        index_path = Path(web_dist_env) / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        return JSONResponse({"detail": "SPA index.html not found"}, status_code=404)
