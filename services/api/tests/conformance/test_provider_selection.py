"""Provider-selection wiring tests.

Verify the hard rule: live app uses real providers; missing config is a typed
503; the hermetic/test runtimes are NEVER selected by the production providers.
These do not make network calls.
"""
import pytest
from fastapi import HTTPException

from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.research.runtime_provider import get_research_runtime


# --- research (Parallel) ---

def test_research_runtime_503_when_key_missing(monkeypatch):
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        get_research_runtime()
    assert exc.value.status_code == 503
    assert "PARALLEL_API_KEY" in exc.value.detail


def test_research_runtime_constructs_parallel_when_configured(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "test-key-value")
    runtime = get_research_runtime()
    # Real Parallel adapters are wired (no network call at construction).
    assert type(runtime.search).__name__ == "ParallelSearchAdapter"
    assert type(runtime.extract).__name__ == "ParallelExtractAdapter"


def test_research_runtime_never_returns_hermetic(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "test-key-value")
    runtime = get_research_runtime()
    assert "Hermetic" not in type(runtime.search).__name__
    assert "Hermetic" not in type(runtime.extract).__name__


# --- detection (Vertex/Gemini) ---

def test_detection_runtime_503_when_project_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("CLEARCUT_GCP_PROJECT", raising=False)
    monkeypatch.setenv("CLEARCUT_DETECTION_RUNTIME", "vertex")
    with pytest.raises(HTTPException) as exc:
        get_detection_runtime()
    assert exc.value.status_code == 503
    assert "GOOGLE_CLOUD_PROJECT" in exc.value.detail


def test_detection_runtime_503_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("CLEARCUT_DETECTION_RUNTIME", "definitely-not-a-provider")
    with pytest.raises(HTTPException) as exc:
        get_detection_runtime()
    assert exc.value.status_code == 503


def test_detection_runtime_constructs_vertex_when_project_configured(monkeypatch):
    monkeypatch.setenv("CLEARCUT_DETECTION_RUNTIME", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "clearcut-workspace")
    monkeypatch.setenv("CLEARCUT_VERTEX_LOCATION", "global")
    # Construction initializes a genai Client in Vertex mode but performs no
    # generate_content call, so no network round-trip occurs here.
    runtime = get_detection_runtime()
    assert type(runtime).__name__ == "VertexDetectionRuntime"
    assert runtime.project == "clearcut-workspace"
    assert runtime.location == "global"
    assert "Hermetic" not in type(runtime).__name__
