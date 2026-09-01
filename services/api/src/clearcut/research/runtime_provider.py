"""Production selection of the research (search/extract) runtime.

Rule: live research must use the real Parallel Search/Extract provider. It must
NEVER silently fall back to the hermetic (test-double) adapters, which return
canned snapshots. Missing configuration is a typed failure (HTTP 503).

Hermetic adapters are only injected explicitly by tests via
`app.dependency_overrides`, never selected here. This guarantees no fabricated
evidence can reach a live user.
"""
import os

from fastapi import HTTPException, status


class ResearchRuntime:
    """Bundle of the search + extract ports used by a research run."""

    def __init__(self, search, extract) -> None:
        self.search = search
        self.extract = extract


def get_research_runtime() -> ResearchRuntime:
    """Return the configured production research runtime (Parallel only)."""
    api_key = os.getenv("PARALLEL_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Research runtime is not configured. Set PARALLEL_API_KEY to enable "
                "live Parallel Search/Extract. Hermetic adapters are test-only and are "
                "never used to serve real evidence; zero evidence stays unresolved."
            ),
        )
    # Live Parallel adapters are constructed here once the client is wired.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Live Parallel research runtime not yet available in this deployment. "
            "Research endpoint is wired and scoped; the provider client is pending."
        ),
    )
