"""Side-effect-free application configuration container."""

from dataclasses import dataclass, field

from clearcut.bootstrap.settings import ClearcutSettings


@dataclass(frozen=True)
class RedactedDeploymentSummary:
    profile: str
    database_configured: bool
    storage_adapter: str
    dispatch_adapter: str
    authentication_adapter: str
    secret_backend: str
    paid_providers_enabled: tuple[str, ...]


@dataclass(frozen=True)
class ApplicationContainer:
    settings: ClearcutSettings = field(repr=False)
    summary: RedactedDeploymentSummary


def build_application(settings: ClearcutSettings) -> ApplicationContainer:
    """Build immutable application metadata without importing the HTTP shell."""
    summary = RedactedDeploymentSummary(
        profile=settings.profile.value,
        database_configured=bool(settings.database.url.strip()),
        storage_adapter=settings.storage.adapter.value,
        dispatch_adapter=settings.dispatch.adapter.value,
        authentication_adapter=settings.authentication.adapter.value,
        secret_backend=settings.secrets.backend.value,
        paid_providers_enabled=tuple(sorted(settings.paid_providers_enabled)),
    )
    return ApplicationContainer(settings=settings, summary=summary)
