"""Production selection of the research (search/extract) runtime.

Rule: live research must use the real Parallel Search/Extract provider. It must
NEVER silently fall back to the hermetic (test-double) adapters, which return
canned snapshots. Missing configuration is a typed failure (HTTP 503 at web boundary).

Hermetic adapters are only injected explicitly by tests via
`app.dependency_overrides`, never selected here. This guarantees no fabricated
evidence can reach a live user.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from clearcut.bootstrap.secrets import SecretResolutionError
from clearcut.detection.runtime_provider import ProviderUnavailableError
from pydantic import SecretStr

if TYPE_CHECKING:
    from clearcut.bootstrap.secrets import SecretResolver


class ResearchRuntimeNotConfiguredError(ProviderUnavailableError):
    """Raised when no production research runtime is configured."""


class ResearchRuntime:
    """Bundle of the search + extract ports used by a research run."""

    def __init__(self, search, extract) -> None:
        self.search = search
        self.extract = extract


def resolve_research_runtime(
    secret_resolver: SecretResolver | None = None,
    *,
    secret_name: str = "PARALLEL_API_KEY",
) -> ResearchRuntime:
    """Return the configured production research runtime (Parallel only)."""
    api_key: SecretStr | None = None
    if secret_resolver is not None:
        try:
            api_key = secret_resolver.resolve(secret_name)
        except SecretResolutionError as error:
            raise ResearchRuntimeNotConfiguredError(
                f"Failed to resolve Parallel API key from secret resolver: {error}"
            ) from error
    else:
        raw_key = os.getenv("PARALLEL_API_KEY")
        if raw_key and raw_key.strip():
            api_key = SecretStr(raw_key.strip())

    if not api_key or not api_key.get_secret_value().strip():
        raise ResearchRuntimeNotConfiguredError(
            "Research runtime is not configured. Set PARALLEL_API_KEY to enable "
            "live Parallel Search/Extract. Hermetic adapters are test-only and are "
            "never used to serve real evidence; zero evidence stays unresolved."
        )

    # Live Parallel adapters (search + extract), both reading PARALLEL_API_KEY.
    from clearcut.research.adapters.parallel_extract import ParallelExtractAdapter
    from clearcut.research.adapters.parallel_search import ParallelSearchAdapter

    return ResearchRuntime(
        search=ParallelSearchAdapter(api_key=api_key.get_secret_value()),
        extract=ParallelExtractAdapter(api_key=api_key.get_secret_value()),
    )


def get_research_runtime() -> ResearchRuntime:
    """FastAPI dependency for live research runtime verification."""
    return resolve_research_runtime()


def get_research_planner():
    """Return the configured production Flash-Lite or Bedrock research planner."""
    provider = os.getenv("CLEARCUT_RESEARCH_PLANNER_RUNTIME")
    if not provider:
        backend = os.getenv("CLEARCUT_MODEL_BACKEND", "").strip().lower()
        provider = "bedrock" if backend == "bedrock" else "vertex"
    else:
        provider = provider.strip().lower()

    if provider == "bedrock":
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        from clearcut.ai.model_roles import (
            BedrockRole,
            ModelRoleConfigurationError,
            resolve_bedrock_role,
        )
        from clearcut.research.adapters.bedrock_planner import BedrockResearchPlanner

        try:
            role_config = resolve_bedrock_role(BedrockRole.RESEARCH_PLANNING)
            return BedrockResearchPlanner(
                model=role_config.model,
                region=region,
                role_configuration=role_config,
            )
        except ModelRoleConfigurationError as error:
            raise ResearchRuntimeNotConfiguredError(str(error)) from error

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("CLEARCUT_GCP_PROJECT")
    if not project:
        raise ResearchRuntimeNotConfiguredError(
            "Research planning is not configured. Set GOOGLE_CLOUD_PROJECT "
            "with Application Default Credentials to enable Vertex planning."
        )
    from clearcut.ai.model_roles import GeminiRole, resolve_model_role
    from clearcut.research.adapters.vertex_planner import VertexResearchPlanner

    return VertexResearchPlanner(
        project=project,
        location=os.getenv("CLEARCUT_VERTEX_LOCATION", "global"),
        role_configuration=resolve_model_role(GeminiRole.RESEARCH_PLANNING),
    )


def get_claim_synthesizer():
    """Return the configured production evidence claim synthesizer."""
    provider = os.getenv("CLEARCUT_SYNTHESIS_RUNTIME") or os.getenv("CLEARCUT_RESEARCH_PLANNER_RUNTIME")
    if not provider:
        backend = os.getenv("CLEARCUT_MODEL_BACKEND", "").strip().lower()
        provider = "bedrock" if backend == "bedrock" else "vertex"
    else:
        provider = provider.strip().lower()

    if provider == "bedrock":
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        from clearcut.ai.model_roles import (
            BedrockRole,
            ModelRoleConfigurationError,
            resolve_bedrock_role,
        )
        from clearcut.research.adapters.bedrock_claim_synthesizer import (
            BedrockClaimSynthesizer,
        )

        try:
            role_config = resolve_bedrock_role(BedrockRole.CLAIM_SYNTHESIS)
            return BedrockClaimSynthesizer(
                model=role_config.model,
                region=region,
                role_configuration=role_config,
            )
        except ModelRoleConfigurationError as error:
            raise ResearchRuntimeNotConfiguredError(str(error)) from error

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("CLEARCUT_GCP_PROJECT")
    if not project:
        raise ResearchRuntimeNotConfiguredError(
            "Claim synthesis is not configured. Set GOOGLE_CLOUD_PROJECT "
            "with Application Default Credentials to enable Vertex synthesis."
        )
    from clearcut.ai.model_roles import GeminiRole, resolve_model_role
    from clearcut.research.adapters.vertex_claim_synthesizer import (
        VertexClaimSynthesizer,
    )

    return VertexClaimSynthesizer(
        project=project,
        location=os.getenv("CLEARCUT_VERTEX_LOCATION", "global"),
        role_configuration=resolve_model_role(GeminiRole.RESEARCH_PLANNING),
    )

