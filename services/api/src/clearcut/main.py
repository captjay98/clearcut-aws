"""FastAPI application shell entry point."""
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="ClearCut API",
    version="0.1.0",
    description="Screenplay pre-clearance research desk and evidence workspace API"
)

@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "0.1.0"
        }
    )
