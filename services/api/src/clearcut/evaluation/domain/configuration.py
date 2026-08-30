from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class ConfigurationLifecycle(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class ProtectedConfiguration:
    config_id: UUID
    org_id: UUID
    lifecycle: ConfigurationLifecycle
    policy_version: str
    prompt_version: str
    activated_by: UUID | None = None
    rationale: str | None = None
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        policy_version: str,
        prompt_version: str,
        lifecycle: ConfigurationLifecycle = ConfigurationLifecycle.DRAFT,
    ) -> "ProtectedConfiguration":
        return cls(
            config_id=uuid6.uuid7(),
            org_id=org_id,
            lifecycle=lifecycle,
            policy_version=policy_version,
            prompt_version=prompt_version,
            created_at=datetime.now(UTC),
        )
