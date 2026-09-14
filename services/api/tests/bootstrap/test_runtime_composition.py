"""Tests for decoupled RuntimeComposition and build_runtime_composition."""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from unittest.mock import MagicMock

import pytest
from clearcut.bootstrap.runtime import (
    RuntimeComposition,
    build_runtime_composition,
    web_lifespan,
    worker_lifespan,
)
from clearcut.bootstrap.settings import (
    ClearcutSettings,
    DatabaseSettings,
    FilesystemStorageSettings,
)
from clearcut.database import DATABASE_URL, AsyncSessionLocal, engine
from clearcut.detection.runtime_provider import (
    DetectionRuntimeNotConfiguredError,
)
from clearcut.evaluation.runtime_provider import JudgeRuntimeNotConfiguredError
from clearcut.research.runtime_provider import ResearchRuntimeNotConfiguredError
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def test_runtime_composition_dataclass_fields_and_immutability() -> None:
    """RuntimeComposition must be a frozen dataclass containing runtime dependencies."""
    assert dataclasses.is_dataclass(RuntimeComposition)

    field_names = {f.name for f in dataclasses.fields(RuntimeComposition)}
    expected_fields = {
        "settings",
        "engine",
        "session_factory",
        "job_repository",
        "storage_adapter",
        "secret_resolver",
        "provider_gate",
        "detection_runtime",
        "research_planner",
        "claim_synthesizer",
        "judge_runtime",
        "candidate_repository",
        "evaluation_repository",
        "evaluation_service",
        "run_detection_job",
        "research_repository",
        "research_runtime",
        "run_research_job",
        "rescan_repository",
        "rescan_item_lineage",
        "rescan_evidence_lineage",
        "rescan_child_work",
        "active_policy_gate",
        "run_rescan_job",
        "start_selective_rescan_service",
        "job_runner",
        "dispatch_outbox",
        "job_dispatcher",
        "reconcile_jobs_service",
        "identity_repo",
        "identity_provider",
        "session_service",
        "org_repo",
        "org_service",
        "project_repo",
        "project_service",
        "import_repository",
        "import_script_service",
    }
    assert expected_fields.issubset(field_names)

    settings = ClearcutSettings(
        profile="local",
        database=DatabaseSettings(url=DATABASE_URL),
        storage=FilesystemStorageSettings(path="/tmp/test_storage"),
    )
    composition = build_runtime_composition(
        settings=settings,
        engine=engine,
        session_factory=AsyncSessionLocal,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        composition.settings = settings  # type: ignore[misc]


def test_build_runtime_composition_creates_graph(tmp_path) -> None:
    """build_runtime_composition builds complete domain graph with engine and coordinators."""
    settings = ClearcutSettings(
        profile="local",
        database=DatabaseSettings(url=DATABASE_URL),
        storage=FilesystemStorageSettings(path=str(tmp_path / "storage")),
    )

    composition = build_runtime_composition(
        settings=settings,
        engine=engine,
        session_factory=AsyncSessionLocal,
    )
    assert isinstance(composition, RuntimeComposition)
    assert isinstance(composition.engine, AsyncEngine)
    assert isinstance(composition.session_factory, async_sessionmaker)
    assert composition.active_policy_gate is not None
    assert composition.rescan_item_lineage is not None
    assert composition.rescan_child_work is not None
    assert composition.detection_runtime is not None
    assert composition.judge_runtime is not None
    assert composition.research_runtime is not None
    assert composition.job_dispatcher is not None


def test_build_runtime_composition_injected_engine(tmp_path) -> None:
    """Injected engine and session_factory are preserved in RuntimeComposition."""
    mock_engine = MagicMock(spec=AsyncEngine)
    mock_session_factory = MagicMock(spec=async_sessionmaker)

    settings = ClearcutSettings(
        profile="local",
        database=DatabaseSettings(url=f"sqlite+aiosqlite:///{tmp_path / 'comp.db'}"),
        storage=FilesystemStorageSettings(path=str(tmp_path / "storage")),
    )

    composition = build_runtime_composition(
        settings=settings,
        engine=mock_engine,
        session_factory=mock_session_factory,
    )

    assert composition.engine is mock_engine
    assert composition.session_factory is mock_session_factory


def test_runtime_composition_isolation_from_web() -> None:
    """clearcut.bootstrap.runtime must NOT import clearcut.main."""
    code = (
        "import sys\n"
        "from clearcut.bootstrap.runtime import RuntimeComposition, build_runtime_composition\n"
        "assert 'clearcut.main' not in sys.modules, 'clearcut.main was imported!'\n"
        "print('OK')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Subprocess failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert res.stdout.strip() == "OK"


@pytest.mark.asyncio
async def test_web_lifespan_lifecycle() -> None:
    """web_lifespan runs startup and cleanup without raising errors."""
    mock_app = FastAPI()
    mock_app.state.job_dispatcher = None

    async with web_lifespan(mock_app):
        pass


@pytest.mark.asyncio
async def test_worker_lifespan_lifecycle() -> None:
    """worker_lifespan runs startup and cleanup without raising errors."""
    mock_composition = MagicMock(spec=RuntimeComposition)
    mock_composition.job_dispatcher = None
    mock_composition.local_job_recovery_interval_seconds = 30.0

    async with worker_lifespan(mock_composition):
        pass


@pytest.mark.asyncio
async def test_provider_unavailable_exception_handling(tmp_path) -> None:
    """ProviderUnavailableError returns HTTP 503 with capability_unavailable."""
    from clearcut.main import create_app

    settings = ClearcutSettings(
        profile="local",
        database=DatabaseSettings(url=DATABASE_URL),
        storage=FilesystemStorageSettings(path=str(tmp_path / "storage")),
    )
    app = create_app(settings)

    @app.get("/test-unavail")
    async def route_unavail() -> None:
        raise DetectionRuntimeNotConfiguredError("Detection provider is offline")

    @app.get("/test-judge-unavail")
    async def route_judge_unavail() -> None:
        raise JudgeRuntimeNotConfiguredError("Judge provider is offline")

    @app.get("/test-research-unavail")
    async def route_research_unavail() -> None:
        raise ResearchRuntimeNotConfiguredError("Research provider is offline")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/test-unavail")
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "capability_unavailable"
        assert "offline" in data["error"]["message"]

        resp2 = await client.get("/test-judge-unavail")
        assert resp2.status_code == 503
        assert resp2.json()["error"]["code"] == "capability_unavailable"

        resp3 = await client.get("/test-research-unavail")
        assert resp3.status_code == 503
        assert resp3.json()["error"]["code"] == "capability_unavailable"
