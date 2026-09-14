"""Production selection of the detection model runtime.

Rule: the live app must use a real, configured runtime. It must NEVER silently
fall back to the hermetic (test-double) runtime, which returns canned matches.
Missing configuration is a typed failure, surfaced as HTTP 503.

The hermetic runtime is only injected explicitly by tests via
`app.dependency_overrides`, never selected here.
"""
import os

from clearcut.ai.model_roles import (
    GeminiRole,
    ModelRoleConfigurationError,
    resolve_model_role,
)
from clearcut.detection.ports.model_runtime import ModelRuntimePort


class ProviderConfigurationError(RuntimeError):
    """Base error for misconfigured or unavailable provider adapters."""


class ProviderUnavailableError(ProviderConfigurationError):
    """Raised when an external provider capability is requested but not configured."""

    status_code: int = 503

    @property
    def detail(self) -> str:
        return str(self)


class DetectionRuntimeNotConfiguredError(ProviderUnavailableError):
    """Raised when no production detection runtime is configured."""


RuntimeNotConfiguredError = DetectionRuntimeNotConfiguredError


def get_detection_runtime() -> ModelRuntimePort:
    """Return the configured production detection runtime.

    Selection is driven by CLEARCUT_DETECTION_RUNTIME (or CLEARCUT_MODEL_BACKEND, default: 'vertex').
    Hermetic is intentionally NOT selectable here — it is test-only.
    """
    provider = os.getenv("CLEARCUT_DETECTION_RUNTIME")
    if not provider:
        backend = os.getenv("CLEARCUT_MODEL_BACKEND", "").strip().lower()
        provider = "bedrock" if backend == "bedrock" else "vertex"
    else:
        provider = provider.strip().lower()

    if provider == "vertex":
        # Vertex uses project + ADC (google.auth), not an API key. Location is
        # 'global' per deployment. Model is configurable.
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("CLEARCUT_GCP_PROJECT")
        if not project:
            raise DetectionRuntimeNotConfiguredError(
                "Live detection is not enabled on this deployment, so no findings "
                "can be produced and none have been invented. An administrator "
                "enables it by setting GOOGLE_CLOUD_PROJECT with Application "
                "Default Credentials for Vertex Gemini. The hermetic runtime is "
                "test-only and is never used to serve real detection results."
            )
        location = os.getenv("CLEARCUT_VERTEX_LOCATION", "global")
        try:
            from clearcut.detection.adapters.vertex_runtime import VertexDetectionRuntime

            return VertexDetectionRuntime(
                project=project,
                location=location,
                role_configuration=resolve_model_role(GeminiRole.DETECTION),
            )
        except ModelRoleConfigurationError as error:
            raise DetectionRuntimeNotConfiguredError(str(error)) from error
        except ImportError as error:
            raise DetectionRuntimeNotConfiguredError(
                "Vertex detection dependencies are not installed (google-genai). "
                "Install service deps to enable live detection."
            ) from error

    if provider == "bedrock":
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        try:
            from clearcut.ai.model_roles import BedrockRole, resolve_bedrock_role
            from clearcut.detection.adapters.bedrock_runtime import BedrockDetectionAdapter

            role_config = resolve_bedrock_role(BedrockRole.DETECTION)
            return BedrockDetectionAdapter(
                model=role_config.model,
                region=region,
                role_configuration=role_config,
            )
        except ModelRoleConfigurationError as error:
            raise DetectionRuntimeNotConfiguredError(str(error)) from error

    raise DetectionRuntimeNotConfiguredError(
        f"Unknown detection runtime '{provider}'. No live runtime available."
    )

