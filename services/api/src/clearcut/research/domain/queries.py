from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SearchMode(StrEnum):
    FAST = "fast"
    ACCURATE = "accurate"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    mode: SearchMode = SearchMode.FAST
    max_results: int = Field(default=5, ge=1, le=10)


class ResearchPlan(BaseModel):
    objective: str = Field(..., min_length=20, max_length=600)
    search_queries: list[str] = Field(..., min_length=2, max_length=3)

    @field_validator("search_queries")
    @classmethod
    def validate_queries(cls, queries: list[str]) -> list[str]:
        for q in queries:
            if not q.strip() or len(q.split()) > 10:
                raise ValueError("Each search query must be 1 to 10 words")
        return [q.strip() for q in queries]
