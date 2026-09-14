"""Production-only construction of the configured Vertex Gemini judge."""
from __future__ import annotations

import os

from clearcut.ai.model_roles import (
    GeminiRole,
    ModelRoleConfigurationError,
    resolve_model_role,
)
from clearcut.detection.runtime_provider import ProviderUnavailableError
from clearcut.evaluation.ports.judge import JudgePort


class JudgeRuntimeNotConfiguredError(ProviderUnavailableError):
    """Raised when no production judge runtime is configured."""


def get_judge_runtime() -> JudgePort:
    """Return the live judge; hermetic adapters are test-injected only."""
    provider = os.getenv("CLEARCUT_JUDGE_RUNTIME")
    if not provider:
        backend = os.getenv("CLEARCUT_MODEL_BACKEND", "").strip().lower()
        provider = "bedrock" if backend == "bedrock" else "vertex"
    else:
        provider = provider.strip().lower()

    if provider == "bedrock":
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        from clearcut.ai.model_roles import (
            BedrockRole,
            resolve_bedrock_role,
        )
        from clearcut.evaluation.adapters.bedrock_judge import BedrockJudgeAdapter

        try:
            role_config = resolve_bedrock_role(BedrockRole.JUDGE)
            return BedrockJudgeAdapter(
                model=role_config.model,
                region=region,
                role_configuration=role_config,
            )
        except ModelRoleConfigurationError as error:
            raise JudgeRuntimeNotConfiguredError(str(error)) from error

    if provider != "vertex":
        raise JudgeRuntimeNotConfiguredError(
            f"Unknown judge runtime '{provider}'. No live judge is available."
        )

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("CLEARCUT_GCP_PROJECT")
    if not project:
        raise JudgeRuntimeNotConfiguredError(
            "Judge runtime is not configured. Set GOOGLE_CLOUD_PROJECT with "
            "Application Default Credentials to enable the Vertex Gemini judge."
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
        raise JudgeRuntimeNotConfiguredError(str(error)) from error
    except ImportError as error:
        raise JudgeRuntimeNotConfiguredError(
            "Vertex judge dependencies are not installed (google-genai). "
            "Install service dependencies to enable the live judge."
        ) from error

