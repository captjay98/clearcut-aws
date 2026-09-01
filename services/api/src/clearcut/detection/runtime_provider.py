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

    Selection is driven by CLEARCUT_DETECTION_RUNTIME (default: 'gemini').
    Hermetic is intentionally NOT selectable here.
    """
    provider = os.getenv("CLEARCUT_DETECTION_RUNTIME", "gemini").lower()

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Detection runtime is not configured. Set GEMINI_API_KEY to "
                    "enable live detection. The hermetic runtime is test-only and "
                    "is never used to serve real detection results."
                ),
            )
        # Live adapter is implemented separately; until it lands, a configured but
        # unbuilt runtime is an explicit, honest failure rather than a silent stub.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Live detection runtime not yet available in this deployment. "
                "Detection endpoint is wired and scoped; the provider adapter is pending."
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Unknown detection runtime '{provider}'. No live runtime available.",
    )
