"""Production selection of the detection model runtime.

Rule: the live app must use a real, configured runtime. It must NEVER silently
fall back to the hermetic (test-double) runtime, which returns canned matches.
Missing configuration is a typed failure, surfaced as HTTP 503.

The hermetic runtime is only injected explicitly by tests via
`app.dependency_overrides`, never selected here.
"""
import os

from fastapi import HTTPException, status

from clearcut.detection.ports.model_runtime import ModelRuntimePort


class RuntimeNotConfiguredError(RuntimeError):
    """Raised when no production detection runtime is configured."""


def get_detection_runtime() -> ModelRuntimePort:
    """Return the configured production detection runtime.

    Selection is driven by CLEARCUT_DETECTION_RUNTIME (default: 'vertex').
    Hermetic is intentionally NOT selectable here — it is test-only.
    """
    provider = os.getenv("CLEARCUT_DETECTION_RUNTIME", "vertex").lower()

    if provider == "vertex":
        # Vertex uses project + ADC (google.auth), not an API key. Location is
        # 'global' per deployment. Model is configurable.
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("CLEARCUT_GCP_PROJECT")
        if not project:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Detection runtime is not configured. Set GOOGLE_CLOUD_PROJECT "
                    "(with Application Default Credentials) to enable live Vertex "
                    "Gemini detection. The hermetic runtime is test-only and is never "
                    "used to serve real detection results."
                ),
            )
        location = os.getenv("CLEARCUT_VERTEX_LOCATION", "global")
        try:
            from clearcut.detection.adapters.vertex_runtime import VertexDetectionRuntime

            return VertexDetectionRuntime(project=project, location=location)
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Vertex detection dependencies are not installed (google-genai). "
                    "Install service deps to enable live detection."
                ),
            )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Unknown detection runtime '{provider}'. No live runtime available.",
    )
