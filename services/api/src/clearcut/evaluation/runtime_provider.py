"""Production-only construction of the configured Vertex Gemini judge."""
from __future__ import annotations

import os

from clearcut.ai.model_roles import (
    GeminiRole,
    ModelRoleConfigurationError,
    resolve_model_role,
)
from clearcut.evaluation.ports.judge import JudgePort
from fastapi import HTTPException, status


def get_judge_runtime() -> JudgePort:
    """Return the live judge; hermetic adapters are test-injected only."""
    provider = os.getenv("CLEARCUT_JUDGE_RUNTIME", "vertex").strip().lower()
    if provider != "vertex":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unknown judge runtime '{provider}'. No live judge is available.",
        )

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("CLEARCUT_GCP_PROJECT")
    if not project:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Judge runtime is not configured. Set GOOGLE_CLOUD_PROJECT with "
                "Application Default Credentials to enable the Vertex Gemini judge."
            ),
        )
    location = os.getenv("CLEARCUT_VERTEX_LOCATION", "global")
    try:
        from clearcut.evaluation.adapters.vertex_judge import VertexJudgeAdapter

        return VertexJudgeAdapter(
            project=project,
            location=location,
            role_configuration=resolve_model_role(GeminiRole.JUDGE),
        )
    except ModelRoleConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ImportError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Vertex judge dependencies are not installed (google-genai). "
                "Install service dependencies to enable the live judge."
            ),
        ) from error
