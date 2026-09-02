from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ExtractRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=3)
    objective: str = Field(..., min_length=10, max_length=600)
    session_id: str
    correlation_id: UUID
    research_run_id: UUID
    research_query_id: UUID
    search_attempt_id: UUID
    full_content: bool = False

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, urls: list[str]) -> list[str]:
        for url in urls:
            if not url.startswith("https://"):
                raise ValueError("Only secure HTTPS URLs are permitted for extraction")
        return urls


@dataclass(frozen=True)
class ExtractedPage:
    url: str
    title: str
    content: str
    published_date: str | None = None


@dataclass(frozen=True)
class ExtractedPageError:
    url: str
    error_kind: str
    message: str


@dataclass(frozen=True)
class ExtractBatchResponse:
    extract_id: str
    session_id: str
    results: tuple[ExtractedPage, ...]
    errors: tuple[ExtractedPageError, ...]
    warnings: tuple[str, ...]
