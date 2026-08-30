import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import uuid6

RoleType = Literal["owner", "admin", "editor", "reviewer"]
MembershipStatus = Literal["active", "deactivated"]


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


@dataclass(frozen=True)
class Organization:
    org_id: UUID
    name: str
    slug: str
    created_at: datetime

    @classmethod
    def create(cls, name: str, slug: str) -> "Organization":
        return cls(
            org_id=uuid6.uuid7(),
            name=name.strip(),
            slug=slugify(slug),
            created_at=datetime.now(UTC),
        )


@dataclass
class Membership:
    membership_id: UUID
    org_id: UUID
    user_id: UUID
    role: RoleType
    status: MembershipStatus
    created_at: datetime

    @classmethod
    def create_owner(cls, org_id: UUID, user_id: UUID) -> "Membership":
        return cls(
            membership_id=uuid6.uuid7(),
            org_id=org_id,
            user_id=user_id,
            role="owner",
            status="active",
            created_at=datetime.now(UTC),
        )
