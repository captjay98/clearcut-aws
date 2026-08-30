import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import uuid6

ProviderFailureKind = Literal[
    "retryable",
    "rate_limited",
    "authentication",
    "configuration",
    "invalid_response",
    "permanent",
    "ambiguous",
]


@dataclass(frozen=True)
class ProviderFailure:
    kind: ProviderFailureKind
    message: str


@dataclass(frozen=True)
class SearchResultItem:
    url: str
    title: str
    publisher: str
    snippet: str
    published_date: str | None = None


@dataclass(frozen=True)
class SearchResponse:
    search_id: str
    session_id: str
    results: list[SearchResultItem]
    duration_ms: int = 0


ProviderResult = SearchResponse | ProviderFailure


@dataclass(frozen=True)
class SourceSnapshot:
    snapshot_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    run_id: UUID
    url: str
    title: str
    publisher: str
    excerpt: str
    origin: str  # "search" | "extract"
    sha256_hash: str
    retrieved_at: datetime = datetime.now(UTC)
    published_date: str | None = None

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        run_id: UUID,
        url: str,
        title: str,
        publisher: str,
        excerpt: str,
        origin: str = "search",
        published_date: str | None = None,
        snapshot_id: UUID | None = None,
    ) -> "SourceSnapshot":
        content_for_hash = f"{url}|{title}|{excerpt}".encode()
        sha256_hash = hashlib.sha256(content_for_hash).hexdigest()
        return cls(
            snapshot_id=snapshot_id or uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            run_id=run_id,
            url=url,
            title=title,
            publisher=publisher,
            excerpt=excerpt,
            origin=origin,
            sha256_hash=sha256_hash,
            retrieved_at=datetime.now(UTC),
            published_date=published_date,
        )
