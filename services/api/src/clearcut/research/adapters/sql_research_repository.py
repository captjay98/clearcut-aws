"""SQL authority for lease-fenced research execution and provenance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import database_wall_clock_sql, session_scope
from clearcut.evaluation.domain.gates import GateResult, GateSeverity
from clearcut.evaluation.ports.judge import ResearchEvidence
from clearcut.research.application.select_extract_targets import (
    canonicalize_https_url,
)
from clearcut.research.domain.extraction import ExtractBatchResponse
from clearcut.research.domain.queries import ResearchPlan
from clearcut.research.domain.snapshots import ProviderFailure, SearchResponse
from clearcut.research.ports.planner import (
    PlanningAttemptMetadata,
    PlanningSafeError,
    PlanningTokenUsage,
    ResearchPlanningFailure,
    ResearchPlanningSuccess,
)
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_MAX_EXTRACT_EXCERPT_CHARS = 4000
_SAFE_EXTRACT_ERROR_KINDS = frozenset(
    {"blocked", "not_found", "rate_limited", "timeout", "unavailable", "unknown"}
)


class ResearchPersistenceError(RuntimeError):
    pass


class ResearchAttemptState(StrEnum):
    READY = "ready"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class ResearchInput:
    item_id: UUID
    version_id: UUID
    category: str
    text: str


@dataclass(frozen=True)
class ResearchQueryRecord:
    query_id: UUID
    ordinal: int
    query: str


@dataclass(frozen=True)
class PreparedPlanning:
    run_id: UUID
    attempt_id: UUID
    state: ResearchAttemptState
    result: ResearchPlanningSuccess | None = None
    error: PlanningSafeError | None = None


@dataclass(frozen=True)
class PreparedProviderAttempt:
    attempt_id: UUID
    state: ResearchAttemptState


@dataclass(frozen=True)
class PersistedSearch:
    snapshot_count: int
    authorization_count: int


class SqlResearchRepository:
    async def load_input(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> ResearchInput:
        async with session_scope() as session:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT id, version_id, category, text FROM clearance_items "
                        "WHERE id = :item_id AND org_id = :org_id "
                        "AND project_id = :project_id"
                    ),
                    {
                        "item_id": str(item_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            ).mappings().first()
        if row is None:
            raise ResearchPersistenceError(
                "The clearance item was not found in the scoped project."
            )
        category = str(row["category"]).strip()
        text = str(row["text"]).strip()
        if not category or not text:
            raise ResearchPersistenceError(
                "The clearance item is incomplete for bounded research planning."
            )
        return ResearchInput(
            item_id=self._uuid(row["id"]),
            version_id=self._uuid(row["version_id"]),
            category=category,
            text=text,
        )

    async def prepare_planning(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        correlation_id: UUID,
        research_input: ResearchInput,
        requested_model: str,
        input_sha256: str,
    ) -> PreparedPlanning:
        run_id = uuid6.uuid7()
        attempt_id = uuid6.uuid7()
        now = datetime.now(UTC)
        try:
            async with session_scope() as session:
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    job_id=job_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
                await self._close_superseded_runs(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    job_id=job_id,
                    current_job_attempt_number=job_attempt_number,
                )
                existing_run = (
                    await session.execute(
                        sa.text(
                            "SELECT * FROM research_runs WHERE job_id = :job_id "
                            "AND job_attempt_number = :job_attempt_number "
                            "AND org_id = :org_id AND project_id = :project_id"
                        ),
                        {
                            "job_id": str(job_id),
                            "job_attempt_number": job_attempt_number,
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                        },
                    )
                ).mappings().first()
                if existing_run is not None:
                    return await self._replay_planning(
                        session,
                        existing_run,
                        research_input=research_input,
                        job_attempt_number=job_attempt_number,
                        requested_model=requested_model,
                        input_sha256=input_sha256,
                    )

                await session.execute(
                    sa.text(
                        """
                        INSERT INTO research_runs (
                            id, org_id, project_id, item_id, status, created_at,
                            job_id, version_id, job_attempt_number, lease_owner,
                            correlation_id, input_sha256
                        ) VALUES (
                            :id, :org_id, :project_id, :item_id, 'planning', :created_at,
                            :job_id, :version_id, :job_attempt_number, :lease_owner,
                            :correlation_id, :input_sha256
                        )
                        """
                    ),
                    {
                        "id": str(run_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "item_id": str(research_input.item_id),
                        "created_at": now,
                        "job_id": str(job_id),
                        "version_id": str(research_input.version_id),
                        "job_attempt_number": job_attempt_number,
                        "lease_owner": lease_owner,
                        "correlation_id": str(correlation_id),
                        "input_sha256": input_sha256,
                    },
                )
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO provider_attempts (
                            id, run_id, operation_kind, status, created_at,
                            org_id, project_id, item_id, job_attempt_number,
                            lease_owner, correlation_id, requested_model, input_sha256
                        ) VALUES (
                            :id, :run_id, 'planning', 'pending', :created_at,
                            :org_id, :project_id, :item_id, :job_attempt_number,
                            :lease_owner, :correlation_id, :requested_model, :input_sha256
                        )
                        """
                    ),
                    {
                        "id": str(attempt_id),
                        "run_id": str(run_id),
                        "created_at": now,
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "item_id": str(research_input.item_id),
                        "job_attempt_number": job_attempt_number,
                        "lease_owner": lease_owner,
                        "correlation_id": str(correlation_id),
                        "requested_model": requested_model,
                        "input_sha256": input_sha256,
                    },
                )
                await session.execute(
                    sa.text(
                        "UPDATE clearance_items SET research_status = 'running' "
                        "WHERE id = :item_id AND org_id = :org_id "
                        "AND project_id = :project_id"
                    ),
                    {
                        "item_id": str(research_input.item_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    job_id=job_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
        except IntegrityError as error:
            raise ResearchPersistenceError(
                "Research planning intent conflicts with scoped database state."
            ) from error
        return PreparedPlanning(
            run_id=run_id,
            attempt_id=attempt_id,
            state=ResearchAttemptState.READY,
        )

    async def persist_planning_success(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        attempt_id: UUID,
        result: ResearchPlanningSuccess,
    ) -> tuple[ResearchQueryRecord, ...]:
        self._validate_planning_success(result)
        now = datetime.now(UTC)
        queries = tuple(
            ResearchQueryRecord(uuid6.uuid7(), ordinal, query)
            for ordinal, query in enumerate(result.plan.search_queries, start=1)
        )
        metadata = result.metadata
        try:
            async with session_scope() as session:
                await self._require_pending_attempt(
                    session,
                    attempt_id=attempt_id,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    operation_kind="planning",
                )
                updated = (
                    await session.execute(
                        sa.text(
                            """
                            UPDATE provider_attempts SET status = 'succeeded',
                                returned_model = :returned_model,
                                response_id = :response_id,
                                receipt_id = :response_id,
                                input_tokens = :input_tokens,
                                output_tokens = :output_tokens,
                                total_tokens = :total_tokens,
                                duration_ms = :duration_ms,
                                warnings = :warnings,
                                completed_at = :completed_at
                            WHERE id = :attempt_id AND status = 'pending'
                            RETURNING id
                            """
                        ).bindparams(sa.bindparam("warnings", type_=sa.JSON())),
                        {
                            "attempt_id": str(attempt_id),
                            "returned_model": metadata.returned_model,
                            "response_id": metadata.response_id,
                            "input_tokens": metadata.usage.input_tokens,
                            "output_tokens": metadata.usage.output_tokens,
                            "total_tokens": metadata.usage.total_tokens,
                            "duration_ms": metadata.latency_ms,
                            "warnings": [],
                            "completed_at": now,
                        },
                    )
                ).first()
                if updated is None:
                    raise ResearchPersistenceError(
                        "The planning attempt was already finalized."
                    )
                await session.execute(
                    sa.text(
                        "UPDATE research_runs SET objective = :objective, "
                        "status = 'running' WHERE id = :run_id AND org_id = :org_id "
                        "AND project_id = :project_id AND status = 'planning'"
                    ),
                    {
                        "objective": result.plan.objective,
                        "run_id": str(run_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO research_queries (
                            id, run_id, query, ordinal, org_id, project_id,
                            item_id, version_id, created_at
                        ) SELECT :id, :run_id, :query, :ordinal, org_id, project_id,
                            item_id, version_id, :created_at
                        FROM research_runs WHERE id = :run_id AND org_id = :org_id
                            AND project_id = :project_id
                        """
                    ),
                    [
                        {
                            "id": str(query.query_id),
                            "run_id": str(run_id),
                            "query": query.query,
                            "ordinal": query.ordinal,
                            "created_at": now,
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                        }
                        for query in queries
                    ],
                )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    job_id=job_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
        except IntegrityError as error:
            raise ResearchPersistenceError(
                "Research plan provenance conflicts with scoped database state."
            ) from error
        return queries

    async def persist_planning_failure(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        attempt_id: UUID,
        result: ResearchPlanningFailure,
    ) -> None:
        await self._persist_failure(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            job_attempt_number=job_attempt_number,
            lease_owner=lease_owner,
            run_id=run_id,
            attempt_id=attempt_id,
            operation_kind="planning",
            code=result.error.code,
            message=result.error.message,
            retryable=result.error.retryable,
            duration_ms=result.attempt.latency_ms,
            returned_model=result.attempt.returned_model,
            response_id=result.attempt.response_id,
            usage=result.attempt.usage,
        )

    async def load_queries(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ) -> tuple[ResearchQueryRecord, ...]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT id, ordinal, query FROM research_queries "
                        "WHERE run_id = :run_id AND org_id = :org_id "
                        "AND project_id = :project_id ORDER BY ordinal"
                    ),
                    {
                        "run_id": str(run_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            ).mappings().all()
        return tuple(
            ResearchQueryRecord(
                query_id=self._uuid(row["id"]),
                ordinal=int(row["ordinal"]),
                query=str(row["query"]),
            )
            for row in rows
        )

    async def prepare_search(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        correlation_id: UUID,
        run_id: UUID,
        item_id: UUID,
        query: ResearchQueryRecord,
    ) -> PreparedProviderAttempt:
        return await self._prepare_provider_attempt(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            job_attempt_number=job_attempt_number,
            lease_owner=lease_owner,
            correlation_id=correlation_id,
            run_id=run_id,
            item_id=item_id,
            query_id=query.query_id,
            operation_kind="search",
            input_sha256=self._hash(
                {"queryId": str(query.query_id), "query": query.query}
            ),
        )

    async def persist_search_success(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        item_id: UUID,
        query_id: UUID,
        attempt_id: UUID,
        result: SearchResponse,
    ) -> PersistedSearch:
        if not result.search_id.strip() or not result.session_id.strip():
            raise ResearchPersistenceError(
                "Successful Search metadata omitted authentic provider identity."
            )
        now = datetime.now(UTC)
        normalized: list[tuple[UUID, str, Any]] = []
        seen: set[str] = set()
        for item in result.results:
            canonical_url = canonicalize_https_url(item.url)
            if (
                canonical_url is None
                or canonical_url in seen
                or not item.title.strip()
                or not item.publisher.strip()
                or not item.snippet.strip()
            ):
                continue
            seen.add(canonical_url)
            normalized.append((uuid6.uuid7(), canonical_url, item))
        try:
            async with session_scope() as session:
                await self._require_pending_attempt(
                    session,
                    attempt_id=attempt_id,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    operation_kind="search",
                    query_id=query_id,
                )
                for ordinal, (authorization_id, canonical_url, item) in enumerate(
                    normalized,
                    start=1,
                ):
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO search_result_authorizations (
                                id, org_id, project_id, item_id, run_id, query_id,
                                search_attempt_id, search_operation_kind, ordinal,
                                url, canonical_url, title, publisher, excerpt,
                                published_date, created_at
                            ) VALUES (
                                :id, :org_id, :project_id, :item_id, :run_id,
                                :query_id, :attempt_id, 'search', :ordinal, :url,
                                :canonical_url, :title, :publisher, :excerpt,
                                :published_date, :created_at
                            )
                            """
                        ),
                        {
                            "id": str(authorization_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "item_id": str(item_id),
                            "run_id": str(run_id),
                            "query_id": str(query_id),
                            "attempt_id": str(attempt_id),
                            "ordinal": ordinal,
                            "url": item.url,
                            "canonical_url": canonical_url,
                            "title": item.title,
                            "publisher": item.publisher,
                            "excerpt": item.snippet,
                            "published_date": item.published_date,
                            "created_at": now,
                        },
                    )
                    await self._insert_snapshot(
                        session,
                        snapshot_id=uuid6.uuid7(),
                        org_id=org_id,
                        project_id=project_id,
                        item_id=item_id,
                        run_id=run_id,
                        query_id=query_id,
                        provider_attempt_id=attempt_id,
                        authorization_id=authorization_id,
                        authorizing_search_attempt_id=attempt_id,
                        url=canonical_url,
                        title=item.title,
                        publisher=item.publisher,
                        excerpt=item.snippet,
                        origin="search",
                        published_date=item.published_date,
                        retrieved_at=now,
                    )
                updated = (
                    await session.execute(
                        sa.text(
                            """
                            UPDATE provider_attempts SET status = 'succeeded',
                                receipt_id = :search_id,
                                provider_session_id = :session_id,
                                duration_ms = :duration_ms,
                                warnings = :warnings,
                                completed_at = :completed_at
                            WHERE id = :attempt_id AND status = 'pending'
                            RETURNING id
                            """
                        ).bindparams(sa.bindparam("warnings", type_=sa.JSON())),
                        {
                            "attempt_id": str(attempt_id),
                            "search_id": result.search_id,
                            "session_id": result.session_id,
                            "duration_ms": result.duration_ms,
                            "warnings": [],
                            "completed_at": now,
                        },
                    )
                ).first()
                if updated is None:
                    raise ResearchPersistenceError(
                        "The Search attempt was already finalized."
                    )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    job_id=job_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
        except IntegrityError as error:
            raise ResearchPersistenceError(
                "Search provenance conflicts with scoped database state."
            ) from error
        return PersistedSearch(
            snapshot_count=len(normalized),
            authorization_count=len(normalized),
        )

    async def prepare_extract(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        correlation_id: UUID,
        run_id: UUID,
        item_id: UUID,
        query_id: UUID,
        search_attempt_id: UUID,
        urls: list[str],
    ) -> PreparedProviderAttempt:
        if not 1 <= len(urls) <= 3:
            raise ResearchPersistenceError("Extract requires one to three authorized URLs.")
        canonical_urls = [canonicalize_https_url(url) for url in urls]
        if any(url is None for url in canonical_urls) or len(set(canonical_urls)) != len(
            canonical_urls
        ):
            raise ResearchPersistenceError("Extract targets must be distinct HTTPS URLs.")
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT authorization.id, authorization.canonical_url "
                        "FROM search_result_authorizations authorization "
                        "JOIN provider_attempts search_attempt "
                        "ON search_attempt.id = authorization.search_attempt_id "
                        "AND search_attempt.run_id = authorization.run_id "
                        "AND search_attempt.org_id = authorization.org_id "
                        "AND search_attempt.project_id = authorization.project_id "
                        "AND search_attempt.item_id = authorization.item_id "
                        "AND search_attempt.query_id = authorization.query_id "
                        "AND search_attempt.operation_kind = 'search' "
                        "AND search_attempt.status = 'succeeded' "
                        "WHERE authorization.org_id = :org_id "
                        "AND authorization.project_id = :project_id "
                        "AND authorization.item_id = :item_id "
                        "AND authorization.run_id = :run_id "
                        "AND authorization.query_id = :query_id "
                        "AND authorization.search_attempt_id = :attempt_id "
                        "AND authorization.search_operation_kind = 'search'"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "item_id": str(item_id),
                        "run_id": str(run_id),
                        "query_id": str(query_id),
                        "attempt_id": str(search_attempt_id),
                    },
                )
            ).mappings().all()
        authorizations = {str(row["canonical_url"]): row for row in rows}
        selected_urls = [str(url) for url in canonical_urls]
        if not set(selected_urls).issubset(authorizations):
            raise ResearchPersistenceError(
                "Extract target is outside the authorizing Search attempt."
            )
        return await self._prepare_provider_attempt(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            job_attempt_number=job_attempt_number,
            lease_owner=lease_owner,
            correlation_id=correlation_id,
            run_id=run_id,
            item_id=item_id,
            query_id=query_id,
            operation_kind="extract",
            authorizing_search_attempt_id=search_attempt_id,
            extract_targets=[
                (self._uuid(authorizations[url]["id"]), url)
                for url in selected_urls
            ],
            input_sha256=self._hash(
                {
                    "searchAttemptId": str(search_attempt_id),
                    "urls": selected_urls,
                }
            ),
        )

    async def persist_extract_success(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        item_id: UUID,
        query_id: UUID,
        search_attempt_id: UUID,
        attempt_id: UUID,
        result: ExtractBatchResponse,
    ) -> int:
        if not result.extract_id.strip():
            raise ResearchPersistenceError(
                "Successful Extract metadata omitted authentic provider identity."
            )
        async with session_scope() as session:
            attempt = await self._require_pending_attempt(
                session,
                attempt_id=attempt_id,
                org_id=org_id,
                project_id=project_id,
                run_id=run_id,
                operation_kind="extract",
                query_id=query_id,
            )
            persisted_authorizing_attempt = attempt[
                "authorizing_search_attempt_id"
            ]
            if (
                persisted_authorizing_attempt is None
                or self._uuid(persisted_authorizing_attempt) != search_attempt_id
                or str(attempt["authorizing_operation_kind"]) != "search"
            ):
                raise ResearchPersistenceError(
                    "The Extract result does not match its persisted authorizing Search."
                )
            target_rows = (
                await session.execute(
                    sa.text(
                        """
                        SELECT target.canonical_url, authorization.id,
                               authorization.publisher,
                               search_attempt.provider_session_id
                        FROM extract_target_authorizations target
                        JOIN search_result_authorizations authorization
                          ON authorization.id = target.authorization_id
                         AND authorization.run_id = target.run_id
                         AND authorization.org_id = target.org_id
                         AND authorization.project_id = target.project_id
                         AND authorization.item_id = target.item_id
                         AND authorization.query_id = target.query_id
                         AND authorization.search_attempt_id =
                             target.authorizing_search_attempt_id
                         AND authorization.canonical_url = target.canonical_url
                        JOIN provider_attempts search_attempt
                          ON search_attempt.id = target.authorizing_search_attempt_id
                         AND search_attempt.run_id = target.run_id
                         AND search_attempt.org_id = target.org_id
                         AND search_attempt.project_id = target.project_id
                         AND search_attempt.item_id = target.item_id
                         AND search_attempt.query_id = target.query_id
                         AND search_attempt.operation_kind = 'search'
                         AND search_attempt.status = 'succeeded'
                        WHERE target.extract_attempt_id = :extract_attempt_id
                          AND target.org_id = :org_id
                          AND target.project_id = :project_id
                          AND target.item_id = :item_id
                          AND target.run_id = :run_id
                          AND target.query_id = :query_id
                          AND target.authorizing_search_attempt_id = :search_id
                          AND target.extract_operation_kind = 'extract'
                        ORDER BY target.ordinal
                        """
                    ),
                    {
                        "extract_attempt_id": str(attempt_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "item_id": str(item_id),
                        "run_id": str(run_id),
                        "query_id": str(query_id),
                        "search_id": str(search_attempt_id),
                    },
                )
            ).mappings().all()
            authorizations = {
                str(row["canonical_url"]): row for row in target_rows
            }
            expected_sessions = {
                str(row["provider_session_id"])
                for row in target_rows
                if row["provider_session_id"] is not None
            }
            if (
                not authorizations
                or len(expected_sessions) != 1
                or result.session_id not in expected_sessions
            ):
                raise ResearchPersistenceError(
                    "The Extract result session does not match its persisted Search intent."
                )
            now = datetime.now(UTC)
            persisted = 0
            seen: set[str] = set()
            for page in result.results:
                canonical_url = canonicalize_https_url(page.url)
                excerpt = self._bounded_excerpt(page.content)
                if (
                    canonical_url is None
                    or canonical_url not in authorizations
                    or canonical_url in seen
                ):
                    raise ResearchPersistenceError(
                        "The Extract result URL is outside its persisted target intent."
                    )
                authorization = authorizations[canonical_url]
                if not page.title.strip() or not excerpt:
                    continue
                seen.add(canonical_url)
                await self._insert_snapshot(
                    session,
                    snapshot_id=uuid6.uuid7(),
                    org_id=org_id,
                    project_id=project_id,
                    item_id=item_id,
                    run_id=run_id,
                    query_id=query_id,
                    provider_attempt_id=attempt_id,
                    authorization_id=self._uuid(authorization["id"]),
                    authorizing_search_attempt_id=search_attempt_id,
                    url=canonical_url,
                    title=page.title,
                    publisher=str(authorization["publisher"]),
                    excerpt=excerpt,
                    origin="extract",
                    published_date=page.published_date,
                    retrieved_at=now,
                )
                persisted += 1
            warnings = self._safe_extract_diagnostics(
                result,
                set(authorizations),
            )
            updated = (
                await session.execute(
                    sa.text(
                        """
                        UPDATE provider_attempts SET status = 'succeeded',
                            receipt_id = :extract_id,
                            provider_session_id = :session_id,
                            duration_ms = 0,
                            warnings = :warnings,
                            completed_at = :completed_at
                        WHERE id = :attempt_id AND status = 'pending'
                        RETURNING id
                        """
                    ).bindparams(sa.bindparam("warnings", type_=sa.JSON())),
                    {
                        "attempt_id": str(attempt_id),
                        "extract_id": result.extract_id,
                        "session_id": result.session_id,
                        "warnings": warnings,
                        "completed_at": now,
                    },
                )
            ).first()
            if updated is None:
                raise ResearchPersistenceError("The Extract attempt was already finalized.")
            await self._fence_active_lease(
                session,
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                job_attempt_number=job_attempt_number,
                lease_owner=lease_owner,
            )
        return persisted

    async def persist_provider_failure(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        attempt_id: UUID,
        operation_kind: str,
        result: ProviderFailure,
    ) -> None:
        await self._persist_failure(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            job_attempt_number=job_attempt_number,
            lease_owner=lease_owner,
            run_id=run_id,
            attempt_id=attempt_id,
            operation_kind=operation_kind,
            code=result.kind,
            message=result.message,
            retryable=result.kind in {"retryable", "rate_limited"},
            duration_ms=0,
        )

    async def load_active_judge_configuration(
        self,
        *,
        org_id: UUID,
    ) -> tuple[str, str]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT policy_version, prompt_version "
                        "FROM protected_configurations WHERE org_id = :org_id "
                        "AND lifecycle = 'active' ORDER BY created_at DESC, id DESC"
                    ),
                    {"org_id": str(org_id)},
                )
            ).mappings().all()
        if len(rows) != 1:
            raise ResearchPersistenceError(
                "Exactly one active organization policy and prompt binding is required."
            )
        policy_version = str(rows[0]["policy_version"]).strip()
        prompt_version = str(rows[0]["prompt_version"]).strip()
        if not policy_version or not prompt_version:
            raise ResearchPersistenceError(
                "The active organization policy or prompt binding is incomplete."
            )
        return policy_version, prompt_version

    async def load_admissible_evidence(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        item_id: UUID,
    ) -> tuple[tuple[ResearchEvidence, ...], list[GateResult]]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        """
                        SELECT s.id, s.url, s.publisher, s.excerpt
                        FROM source_snapshots s
                        JOIN provider_attempts attempt
                          ON attempt.id = s.provider_attempt_id
                         AND attempt.run_id = s.run_id
                         AND attempt.org_id = s.org_id
                         AND attempt.project_id = s.project_id
                         AND attempt.item_id = s.item_id
                         AND attempt.query_id = s.query_id
                         AND attempt.operation_kind = 'extract'
                         AND attempt.status = 'succeeded'
                         AND attempt.authorizing_search_attempt_id =
                             s.authorizing_search_attempt_id
                         AND attempt.authorizing_operation_kind = 'search'
                        JOIN search_result_authorizations authorization
                          ON authorization.id = s.authorization_id
                         AND authorization.run_id = s.run_id
                         AND authorization.org_id = s.org_id
                         AND authorization.project_id = s.project_id
                         AND authorization.item_id = s.item_id
                         AND authorization.query_id = s.query_id
                         AND authorization.search_attempt_id =
                             s.authorizing_search_attempt_id
                         AND authorization.search_operation_kind = 'search'
                         AND authorization.canonical_url = s.url
                        JOIN provider_attempts search_attempt
                          ON search_attempt.id = authorization.search_attempt_id
                         AND search_attempt.run_id = authorization.run_id
                         AND search_attempt.org_id = authorization.org_id
                         AND search_attempt.project_id = authorization.project_id
                         AND search_attempt.item_id = authorization.item_id
                         AND search_attempt.query_id = authorization.query_id
                         AND search_attempt.operation_kind = 'search'
                         AND search_attempt.status = 'succeeded'
                        WHERE s.org_id = :org_id AND s.project_id = :project_id
                          AND s.run_id = :run_id AND s.item_id = :item_id
                          AND s.origin = 'extract' AND length(trim(s.excerpt)) > 0
                        ORDER BY s.retrieved_at, s.id
                        """
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "run_id": str(run_id),
                        "item_id": str(item_id),
                    },
                )
            ).mappings().all()
        evidence = tuple(
            ResearchEvidence(
                snapshot_id=self._uuid(row["id"]),
                url=str(row["url"]),
                publisher=str(row["publisher"]),
                excerpt=str(row["excerpt"]),
                authority_tier=self._authority_tier(str(row["url"])),
                stance="context",
                claim_text=str(row["excerpt"]),
            )
            for row in rows
        )
        gates: list[GateResult] = []
        for item in evidence:
            gates.extend(
                (
                    GateResult.create(
                        candidate_id=item.snapshot_id,
                        gate_name="AttributableExcerptGate",
                        passed=True,
                        severity=GateSeverity.INFO,
                        details="Claim wording exactly matches the attributable excerpt.",
                    ),
                    GateResult.create(
                        candidate_id=item.snapshot_id,
                        gate_name="SearchAuthorizationGate",
                        passed=True,
                        severity=GateSeverity.INFO,
                        details="Extract snapshot is linked to its same-run Search URL.",
                    ),
                    GateResult.create(
                        candidate_id=item.snapshot_id,
                        gate_name="ResearchScopeGate",
                        passed=True,
                        severity=GateSeverity.INFO,
                        details="Snapshot matches organization, project, item, and run scope.",
                    ),
                )
            )
        return evidence, gates

    async def persist_context_claims(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        item_id: UUID,
        evidence: tuple[ResearchEvidence, ...],
    ) -> int:
        if not evidence:
            return 0
        snapshot_ids = [str(item.snapshot_id) for item in evidence]
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT id, query_id, provider_attempt_id, excerpt, url "
                        "FROM source_snapshots WHERE org_id = :org_id "
                        "AND project_id = :project_id AND run_id = :run_id "
                        "AND item_id = :item_id AND origin = 'extract'"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "run_id": str(run_id),
                        "item_id": str(item_id),
                    },
                )
            ).mappings().all()
            snapshots = {str(row["id"]): row for row in rows}
            if set(snapshot_ids) != set(snapshots):
                raise ResearchPersistenceError(
                    "Evidence admission does not match the scoped Extract snapshots."
                )
            await self._fence_active_lease(
                session,
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                job_attempt_number=job_attempt_number,
                lease_owner=lease_owner,
            )
            now = datetime.now(UTC)
            await session.execute(
                sa.text(
                    """
                    INSERT INTO evidence_claims (
                        id, org_id, project_id, item_id, snapshot_id, stance,
                        authority_tier, claim_text, provenance_excerpt, created_at,
                        run_id, query_id, provider_attempt_id
                    ) VALUES (
                        :id, :org_id, :project_id, :item_id, :snapshot_id, 'context',
                        :authority_tier, :claim_text, :provenance_excerpt, :created_at,
                        :run_id, :query_id, :provider_attempt_id
                    )
                    """
                ),
                [
                    {
                        "id": str(uuid6.uuid7()),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "item_id": str(item_id),
                        "snapshot_id": str(item.snapshot_id),
                        "authority_tier": item.authority_tier,
                        "claim_text": item.claim_text,
                        "provenance_excerpt": item.excerpt,
                        "created_at": now,
                        "run_id": str(run_id),
                        "query_id": str(snapshots[str(item.snapshot_id)]["query_id"]),
                        "provider_attempt_id": str(
                            snapshots[str(item.snapshot_id)]["provider_attempt_id"]
                        ),
                    }
                    for item in evidence
                    if item.claim_text == item.excerpt
                ],
            )
            await self._fence_active_lease(
                session,
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                job_attempt_number=job_attempt_number,
                lease_owner=lease_owner,
            )
        return len(evidence)

    async def complete_run(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        item_id: UUID,
    ) -> None:
        async with session_scope() as session:
            updated = (
                await session.execute(
                    sa.text(
                        "UPDATE research_runs SET status = 'succeeded', "
                        "completed_at = :completed_at WHERE id = :run_id "
                        "AND org_id = :org_id AND project_id = :project_id "
                        "AND item_id = :item_id AND status = 'running' RETURNING id"
                    ),
                    {
                        "completed_at": datetime.now(UTC),
                        "run_id": str(run_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "item_id": str(item_id),
                    },
                )
            ).first()
            if updated is None:
                raise ResearchPersistenceError("The research run is not active.")
            await session.execute(
                sa.text(
                    "UPDATE clearance_items SET research_status = 'completed' "
                    "WHERE id = :item_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "item_id": str(item_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
            await self._fence_active_lease(
                session,
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                job_attempt_number=job_attempt_number,
                lease_owner=lease_owner,
            )

    async def fail_run(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        item_id: UUID,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "UPDATE research_runs SET status = 'failed', safe_error = :error, "
                    "completed_at = :completed_at WHERE id = :run_id "
                    "AND org_id = :org_id AND project_id = :project_id"
                ).bindparams(sa.bindparam("error", type_=sa.JSON())),
                {
                    "error": {
                        "code": code,
                        "message": message,
                        "retryable": retryable,
                    },
                    "completed_at": datetime.now(UTC),
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
            await session.execute(
                sa.text(
                    "UPDATE clearance_items SET research_status = 'failed' "
                    "WHERE id = :item_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "item_id": str(item_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
            await self._fence_active_lease(
                session,
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                job_attempt_number=job_attempt_number,
                lease_owner=lease_owner,
            )

    async def _close_superseded_runs(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        current_job_attempt_number: int,
    ) -> None:
        safe_error = {
            "code": "interrupted",
            "message": "A replacement job attempt superseded this research execution.",
            "retryable": True,
        }
        now = datetime.now(UTC)
        superseded_runs = (
            "SELECT id FROM research_runs WHERE job_id = :job_id "
            "AND org_id = :org_id AND project_id = :project_id "
            "AND job_attempt_number < :current_job_attempt_number "
            "AND status IN ('planning', 'running')"
        )
        await session.execute(
            sa.text(
                "UPDATE provider_attempts SET status = 'failed', "
                "safe_error = :safe_error, completed_at = :completed_at "
                "WHERE status = 'pending' AND run_id IN (" + superseded_runs + ")"
            ).bindparams(sa.bindparam("safe_error", type_=sa.JSON())),
            {
                "safe_error": safe_error,
                "completed_at": now,
                "job_id": str(job_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "current_job_attempt_number": current_job_attempt_number,
            },
        )
        await session.execute(
            sa.text(
                "UPDATE research_runs SET status = 'failed', "
                "safe_error = :safe_error, completed_at = :completed_at "
                "WHERE id IN (" + superseded_runs + ")"
            ).bindparams(sa.bindparam("safe_error", type_=sa.JSON())),
            {
                "safe_error": safe_error,
                "completed_at": now,
                "job_id": str(job_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "current_job_attempt_number": current_job_attempt_number,
            },
        )

    async def _prepare_provider_attempt(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        correlation_id: UUID,
        run_id: UUID,
        item_id: UUID,
        query_id: UUID,
        operation_kind: str,
        input_sha256: str,
        authorizing_search_attempt_id: UUID | None = None,
        extract_targets: list[tuple[UUID, str]] | None = None,
    ) -> PreparedProviderAttempt:
        attempt_id = uuid6.uuid7()
        effective_authorizing_attempt_id = (
            attempt_id
            if operation_kind == "search"
            else authorizing_search_attempt_id
        )
        if operation_kind == "extract":
            if (
                effective_authorizing_attempt_id is None
                or extract_targets is None
                or not 1 <= len(extract_targets) <= 3
            ):
                raise ResearchPersistenceError(
                    "Extract intent requires one to three persisted targets."
                )
        elif extract_targets is not None:
            raise ResearchPersistenceError(
                "Only Extract attempts may persist target authorizations."
            )
        try:
            async with session_scope() as session:
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    job_id=job_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
                query = (
                    await session.execute(
                        sa.text(
                            "SELECT id FROM research_queries WHERE id = :query_id "
                            "AND run_id = :run_id AND org_id = :org_id "
                            "AND project_id = :project_id AND item_id = :item_id"
                        ),
                        {
                            "query_id": str(query_id),
                            "run_id": str(run_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "item_id": str(item_id),
                        },
                    )
                ).first()
                if query is None:
                    raise ResearchPersistenceError(
                        "The provider attempt query is outside the scoped run."
                    )
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO provider_attempts (
                            id, run_id, operation_kind, status, created_at,
                            org_id, project_id, item_id, query_id,
                            job_attempt_number, lease_owner, correlation_id,
                            input_sha256, authorizing_search_attempt_id,
                            authorizing_operation_kind
                        ) VALUES (
                            :id, :run_id, :operation_kind, 'pending', :created_at,
                            :org_id, :project_id, :item_id, :query_id,
                            :job_attempt_number, :lease_owner, :correlation_id,
                            :input_sha256, :authorizing_search_attempt_id,
                            :authorizing_operation_kind
                        )
                        """
                    ),
                    {
                        "id": str(attempt_id),
                        "run_id": str(run_id),
                        "operation_kind": operation_kind,
                        "created_at": datetime.now(UTC),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "item_id": str(item_id),
                        "query_id": str(query_id),
                        "job_attempt_number": job_attempt_number,
                        "lease_owner": lease_owner,
                        "correlation_id": str(correlation_id),
                        "input_sha256": input_sha256,
                        "authorizing_search_attempt_id": (
                            str(effective_authorizing_attempt_id)
                            if effective_authorizing_attempt_id is not None
                            else None
                        ),
                        "authorizing_operation_kind": (
                            "search"
                            if effective_authorizing_attempt_id is not None
                            else None
                        ),
                    },
                )
                if extract_targets is not None:
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO extract_target_authorizations (
                                id, org_id, project_id, item_id, run_id, query_id,
                                extract_attempt_id, extract_operation_kind,
                                authorization_id, authorizing_search_attempt_id,
                                canonical_url, ordinal, created_at
                            ) VALUES (
                                :id, :org_id, :project_id, :item_id, :run_id,
                                :query_id, :extract_attempt_id, 'extract',
                                :authorization_id, :authorizing_search_attempt_id,
                                :canonical_url, :ordinal, :created_at
                            )
                            """
                        ),
                        [
                            {
                                "id": str(uuid6.uuid7()),
                                "org_id": str(org_id),
                                "project_id": str(project_id),
                                "item_id": str(item_id),
                                "run_id": str(run_id),
                                "query_id": str(query_id),
                                "extract_attempt_id": str(attempt_id),
                                "authorization_id": str(authorization_id),
                                "authorizing_search_attempt_id": str(
                                    effective_authorizing_attempt_id
                                ),
                                "canonical_url": canonical_url,
                                "ordinal": ordinal,
                                "created_at": datetime.now(UTC),
                            }
                            for ordinal, (authorization_id, canonical_url) in enumerate(
                                extract_targets,
                                start=1,
                            )
                        ],
                    )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    job_id=job_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
        except IntegrityError as error:
            raise ResearchPersistenceError(
                "Provider attempt intent conflicts with scoped database state."
            ) from error
        return PreparedProviderAttempt(attempt_id, ResearchAttemptState.READY)

    async def _persist_failure(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        run_id: UUID,
        attempt_id: UUID,
        operation_kind: str,
        code: str,
        message: str,
        retryable: bool,
        duration_ms: int,
        returned_model: str | None = None,
        response_id: str | None = None,
        usage: PlanningTokenUsage | None = None,
    ) -> None:
        async with session_scope() as session:
            await self._require_pending_attempt(
                session,
                attempt_id=attempt_id,
                org_id=org_id,
                project_id=project_id,
                run_id=run_id,
                operation_kind=operation_kind,
            )
            updated = (
                await session.execute(
                    sa.text(
                        """
                        UPDATE provider_attempts SET status = 'failed',
                            returned_model = :returned_model,
                            response_id = :response_id,
                            input_tokens = :input_tokens,
                            output_tokens = :output_tokens,
                            total_tokens = :total_tokens,
                            duration_ms = :duration_ms,
                            safe_error = :safe_error,
                            completed_at = :completed_at
                        WHERE id = :attempt_id AND status = 'pending'
                        RETURNING id
                        """
                    ).bindparams(sa.bindparam("safe_error", type_=sa.JSON())),
                    {
                        "attempt_id": str(attempt_id),
                        "returned_model": returned_model,
                        "response_id": response_id,
                        "input_tokens": usage.input_tokens if usage else None,
                        "output_tokens": usage.output_tokens if usage else None,
                        "total_tokens": usage.total_tokens if usage else None,
                        "duration_ms": duration_ms,
                        "safe_error": {
                            "code": code,
                            "message": message,
                            "retryable": retryable,
                        },
                        "completed_at": datetime.now(UTC),
                    },
                )
            ).first()
            if updated is None:
                raise ResearchPersistenceError(
                    "The provider attempt was already finalized."
                )
            await self._fence_active_lease(
                session,
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                job_attempt_number=job_attempt_number,
                lease_owner=lease_owner,
            )

    async def _replay_planning(
        self,
        session: AsyncSession,
        run: RowMapping,
        *,
        research_input: ResearchInput,
        job_attempt_number: int,
        requested_model: str,
        input_sha256: str,
    ) -> PreparedPlanning:
        if (
            self._uuid(run["item_id"]) != research_input.item_id
            or self._uuid(run["version_id"]) != research_input.version_id
            or int(run["job_attempt_number"]) != job_attempt_number
            or str(run["input_sha256"]) != input_sha256
        ):
            raise ResearchPersistenceError(
                "A replay cannot change immutable research input bindings."
            )
        attempt = (
            await session.execute(
                sa.text(
                    "SELECT * FROM provider_attempts WHERE run_id = :run_id "
                    "AND operation_kind = 'planning' ORDER BY created_at, id LIMIT 1"
                ),
                {"run_id": str(run["id"])},
            )
        ).mappings().one()
        if str(attempt["requested_model"]) != requested_model:
            raise ResearchPersistenceError(
                "A replay cannot change the research planning model."
            )
        state = ResearchAttemptState(str(attempt["status"]))
        if state is ResearchAttemptState.SUCCEEDED:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT query FROM research_queries WHERE run_id = :run_id "
                        "ORDER BY ordinal"
                    ),
                    {"run_id": str(run["id"])},
                )
            ).mappings().all()
            metadata = PlanningAttemptMetadata(
                status="succeeded",
                requested_model=requested_model,
                returned_model=str(attempt["returned_model"]),
                response_id=str(attempt["response_id"]),
                usage=PlanningTokenUsage(
                    self._optional_int(attempt["input_tokens"]),
                    self._optional_int(attempt["output_tokens"]),
                    self._optional_int(attempt["total_tokens"]),
                ),
                latency_ms=int(attempt["duration_ms"]),
                error=None,
            )
            return PreparedPlanning(
                run_id=self._uuid(run["id"]),
                attempt_id=self._uuid(attempt["id"]),
                state=state,
                result=ResearchPlanningSuccess(
                    plan=ResearchPlan(
                        objective=str(run["objective"]),
                        search_queries=[str(row["query"]) for row in rows],
                    ),
                    metadata=metadata,
                ),
            )
        if state is ResearchAttemptState.FAILED:
            error = self._planning_error(attempt["safe_error"])
            return PreparedPlanning(
                run_id=self._uuid(run["id"]),
                attempt_id=self._uuid(attempt["id"]),
                state=state,
                error=error,
            )
        return PreparedPlanning(
            run_id=self._uuid(run["id"]),
            attempt_id=self._uuid(attempt["id"]),
            state=state,
        )

    async def _require_pending_attempt(
        self,
        session: AsyncSession,
        *,
        attempt_id: UUID,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        operation_kind: str,
        query_id: UUID | None = None,
    ) -> RowMapping:
        row = (
            await session.execute(
                sa.text(
                    "SELECT * FROM provider_attempts WHERE id = :attempt_id "
                    "AND org_id = :org_id AND project_id = :project_id "
                    "AND run_id = :run_id AND operation_kind = :operation_kind"
                ),
                {
                    "attempt_id": str(attempt_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                    "operation_kind": operation_kind,
                },
            )
        ).mappings().first()
        if row is None or str(row["status"]) != "pending":
            raise ResearchPersistenceError(
                "The scoped provider attempt is not pending."
            )
        if query_id is not None and self._uuid(row["query_id"]) != query_id:
            raise ResearchPersistenceError(
                "The provider attempt does not match the persisted query."
            )
        return row

    async def _insert_snapshot(
        self,
        session: AsyncSession,
        *,
        snapshot_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        run_id: UUID,
        query_id: UUID,
        provider_attempt_id: UUID,
        authorization_id: UUID,
        authorizing_search_attempt_id: UUID,
        url: str,
        title: str,
        publisher: str,
        excerpt: str,
        origin: str,
        published_date: str | None,
        retrieved_at: datetime,
    ) -> None:
        await session.execute(
            sa.text(
                """
                INSERT INTO source_snapshots (
                    id, org_id, project_id, item_id, run_id, url, title,
                    publisher, excerpt, origin, sha256_hash, published_date,
                    retrieved_at, query_id, provider_attempt_id, authorization_id,
                    authorizing_search_attempt_id
                ) VALUES (
                    :id, :org_id, :project_id, :item_id, :run_id, :url, :title,
                    :publisher, :excerpt, :origin, :sha256_hash, :published_date,
                    :retrieved_at, :query_id, :provider_attempt_id, :authorization_id,
                    :authorizing_search_attempt_id
                )
                """
            ),
            {
                "id": str(snapshot_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "run_id": str(run_id),
                "url": url,
                "title": title,
                "publisher": publisher,
                "excerpt": excerpt,
                "origin": origin,
                "sha256_hash": hashlib.sha256(
                    f"{url}|{title}|{excerpt}".encode()
                ).hexdigest(),
                "published_date": published_date,
                "retrieved_at": retrieved_at,
                "query_id": str(query_id),
                "provider_attempt_id": str(provider_attempt_id),
                "authorization_id": str(authorization_id),
                "authorizing_search_attempt_id": str(
                    authorizing_search_attempt_id
                ),
            },
        )

    async def _fence_active_lease(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
    ) -> None:
        clock_sql = database_wall_clock_sql(session.get_bind().dialect.name)
        fenced = (
            await session.execute(
                sa.text(
                    f"UPDATE jobs SET updated_at = {clock_sql} "
                    "WHERE id = :job_id AND org_id = :org_id "
                    "AND project_id = :project_id AND status = 'running' "
                    "AND attempt_count = :attempt_count AND lease_owner = :lease_owner "
                    f"AND lease_expires_at > {clock_sql} RETURNING id"
                ),
                {
                    "job_id": str(job_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "attempt_count": job_attempt_number,
                    "lease_owner": lease_owner,
                },
            )
        ).first()
        if fenced is None:
            raise ResearchPersistenceError(
                "The research write does not match an active job lease."
            )

    @staticmethod
    def _validate_planning_success(result: ResearchPlanningSuccess) -> None:
        metadata = result.metadata
        if (
            metadata.status != "succeeded"
            or metadata.error is not None
            or not metadata.requested_model.strip()
            or metadata.returned_model is None
            or not metadata.returned_model.strip()
            or metadata.response_id is None
            or not metadata.response_id.strip()
            or metadata.latency_ms < 0
        ):
            raise ResearchPersistenceError(
                "Successful research-planning metadata is incomplete."
            )

    @staticmethod
    def _planning_error(value: Any) -> PlanningSafeError:
        payload = json.loads(value) if isinstance(value, str) else value
        if not isinstance(payload, dict):
            raise ResearchPersistenceError("Persisted planning error is invalid.")
        return PlanningSafeError(
            code=str(payload["code"]),
            message=str(payload["message"]),
            retryable=bool(payload["retryable"]),
        )

    @staticmethod
    def _bounded_excerpt(content: str) -> str:
        return content.strip()[:_MAX_EXTRACT_EXCERPT_CHARS].rstrip()

    @staticmethod
    def _safe_extract_diagnostics(
        result: ExtractBatchResponse,
        authorized_urls: set[str],
    ) -> list[str]:
        diagnostics: list[str] = []
        if result.warnings:
            warning_count = len(result.warnings)
            diagnostics.append(
                "provider_warning_count:3+"
                if warning_count > 3
                else f"provider_warning_count:{warning_count}"
            )
        seen_urls: set[str] = set()
        for error in result.errors:
            canonical_url = canonicalize_https_url(error.url)
            if (
                canonical_url is None
                or canonical_url not in authorized_urls
                or canonical_url in seen_urls
            ):
                continue
            seen_urls.add(canonical_url)
            error_kind = error.error_kind.lower()
            diagnostics.append(
                f"extract_error:{error_kind}"
                if error_kind in _SAFE_EXTRACT_ERROR_KINDS
                else "extract_error:unknown"
            )
            if len(seen_urls) == 3:
                break
        return diagnostics

    @staticmethod
    def _authority_tier(url: str) -> str:
        host = url.split("/", 3)[2].split(":", 1)[0].lower()
        if host.endswith(".gov") or host == "gov":
            return "primary_official"
        return "secondary_informal"

    @staticmethod
    def _hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _uuid(value: Any) -> UUID:
        return value if isinstance(value, UUID) else UUID(str(value))

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return int(value) if value is not None else None
