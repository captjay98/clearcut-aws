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
    # Live Parallel adapters (search + extract), both reading PARALLEL_API_KEY.
    from clearcut.research.adapters.parallel_extract import ParallelExtractAdapter
    from clearcut.research.adapters.parallel_search import ParallelSearchAdapter

    return ResearchRuntime(
        search=ParallelSearchAdapter(api_key=api_key),
        extract=ParallelExtractAdapter(api_key=api_key),
    )



def get_research_planner():
    """Return the configured production Flash-Lite research planner."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("CLEARCUT_GCP_PROJECT")
    if not project:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Research planning is not configured. Set GOOGLE_CLOUD_PROJECT "
                "with Application Default Credentials to enable Vertex planning."
            ),
        )
    from clearcut.ai.model_roles import GeminiRole, resolve_model_role
    from clearcut.research.adapters.vertex_planner import VertexResearchPlanner

    return VertexResearchPlanner(
        project=project,
        location=os.getenv("CLEARCUT_VERTEX_LOCATION", "global"),
        role_configuration=resolve_model_role(GeminiRole.RESEARCH_PLANNING),
    )
