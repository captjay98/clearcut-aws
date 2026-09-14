"""Scheduled source-watch recheck through the authorized provider ports.

A recheck must actually retrieve evidence through the injected search/extract
ports. It never fabricates snapshot content: a provider failure, a missing
watch target, or a raised error produces a FAILED run with the reason, and a
query-based watch that honestly finds nothing persists no snapshot. The
comparison against the prior snapshot only happens when fresh provider content
exists to compare.
"""

import uuid6
from clearcut.monitoring.application.compare_snapshots import compare_snapshots
from clearcut.monitoring.domain.materiality import SourceDelta
from clearcut.monitoring.domain.models import (
    MonitoringRun,
    MonitoringRunStatus,
    WatchConfig,
    WatchKind,
)
from clearcut.research.domain.extraction import ExtractBatchResponse, ExtractRequest
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import (
    ProviderFailure,
    SourceSnapshot,
)
from clearcut.research.ports.url_extract import UrlExtractPort
from clearcut.research.ports.web_search import WebSearchPort

_EXCERPT_LIMIT = 280
_ERROR_LIMIT = 200


def _publisher_for(url: str) -> str:
    return url.split("//")[-1].split("/")[0]


class ScheduledWatchService:
    def __init__(
        self,
        extract_port: UrlExtractPort,
        search_port: WebSearchPort,
    ) -> None:
        self.extract_port = extract_port
        self.search_port = search_port

    async def execute_watch_recheck(
        self,
        watch: WatchConfig,
        prior_snapshot: SourceSnapshot | None = None,
    ) -> tuple[MonitoringRun, SourceSnapshot | None, SourceDelta | None]:
        """Re-retrieve the watched source and compare it with the prior snapshot.

        Returns a FAILED run with no snapshot when the watch cannot be executed
        honestly (missing target, provider failure, unexpected error). When real
        content is retrieved and ``prior_snapshot`` is supplied, the comparison
        yields the change signal between them.
        """
        try:
            if watch.watch_kind == WatchKind.EXACT_SOURCE:
                run, snapshot = self._recheck_exact_source(watch)
            else:
                run, snapshot = self._recheck_event_topic(watch)
        except Exception as exc:  # noqa: BLE001 - bounded, reported as run failure
            run = self._failed_run(watch, f"Source recheck raised: {exc!s}")
            snapshot = None

        delta = (
            compare_snapshots(prior_snapshot, snapshot)
            if prior_snapshot is not None and snapshot is not None
            else None
        )
        return run, snapshot, delta

    def _recheck_exact_source(
        self, watch: WatchConfig
    ) -> tuple[MonitoringRun, SourceSnapshot | None]:
        url = watch.target_url
        if not url:
            return (
                self._failed_run(
                    watch,
                    "Exact-source watch has no target URL; refusing to invent one.",
                ),
                None,
            )

        result = self.extract_port.extract(self._extract_request(watch, url))
        if isinstance(result, ProviderFailure):
            return self._provider_failed_run(watch, result), None

        assert isinstance(result, ExtractBatchResponse)
        page = next((p for p in result.results if p.url == url), None)
        if page is None:
            return (
                self._failed_run(
                    watch, "Provider returned no content for the watched URL."
                ),
                None,
            )

        snapshot = SourceSnapshot.create(
            org_id=watch.org_id,
            project_id=watch.project_id,
            item_id=watch.item_id,
            run_id=uuid6.uuid7(),
            url=page.url,
            title=page.title,
            publisher=_publisher_for(page.url),
            excerpt=page.content[:_EXCERPT_LIMIT].strip(),
            origin="extract",
            published_date=page.published_date,
        )
        return self._completed_run(watch, snapshot), snapshot

    def _recheck_event_topic(
        self, watch: WatchConfig
    ) -> tuple[MonitoringRun, SourceSnapshot | None]:
        query = watch.query_text
        if not query:
            return (
                self._failed_run(
                    watch,
                    "Event-topic watch has no query text; refusing to search blindly.",
                ),
                None,
            )

        result = self.search_port.search(self._search_request(watch, query))
        if isinstance(result, ProviderFailure):
            return self._provider_failed_run(watch, result), None

        # The search ran honestly and found nothing new: a completed run with no
        # snapshot, rather than fabricated content standing in for evidence.
        if not result.results:
            return (
                MonitoringRun.create(
                    watch_id=watch.watch_id,
                    org_id=watch.org_id,
                    project_id=watch.project_id,
                    status=MonitoringRunStatus.COMPLETED,
                ),
                None,
            )

        first = result.results[0]
        snapshot = SourceSnapshot.create(
            org_id=watch.org_id,
            project_id=watch.project_id,
            item_id=watch.item_id,
            run_id=uuid6.uuid7(),
            url=first.url,
            title=first.title,
            publisher=first.publisher,
            excerpt=first.snippet[:_EXCERPT_LIMIT].strip(),
            origin="search",
            published_date=first.published_date,
        )
        return self._completed_run(watch, snapshot), snapshot

    def _extract_request(self, watch: WatchConfig, url: str) -> ExtractRequest:
        # The correlation identifiers below identify this recheck itself; they
        # deliberately do not claim membership in any research run.
        return ExtractRequest(
            urls=[url],
            objective=self._objective(watch),
            session_id=f"watch:{watch.watch_id}",
            correlation_id=uuid6.uuid7(),
            research_run_id=uuid6.uuid7(),
            research_query_id=uuid6.uuid7(),
            search_attempt_id=uuid6.uuid7(),
        )

    def _search_request(self, watch: WatchConfig, query: str) -> SearchRequest:
        return SearchRequest(
            query=query,
            objective=self._objective(watch),
            correlation_id=uuid6.uuid7(),
            research_run_id=uuid6.uuid7(),
            research_query_id=uuid6.uuid7(),
        )

    @staticmethod
    def _objective(watch: WatchConfig) -> str:
        return (
            f"Monitoring recheck of clearance item {watch.item_id} "
            "for source changes."
        )

    @staticmethod
    def _completed_run(watch: WatchConfig, snapshot: SourceSnapshot) -> MonitoringRun:
        return MonitoringRun.create(
            watch_id=watch.watch_id,
            org_id=watch.org_id,
            project_id=watch.project_id,
            status=MonitoringRunStatus.COMPLETED,
            new_snapshot_id=snapshot.snapshot_id,
        )

    @staticmethod
    def _provider_failed_run(watch: WatchConfig, failure: ProviderFailure) -> MonitoringRun:
        return ScheduledWatchService._failed_run(
            watch, f"Provider failure ({failure.kind}): {failure.message}"
        )

    @staticmethod
    def _failed_run(watch: WatchConfig, message: str) -> MonitoringRun:
        return MonitoringRun.create(
            watch_id=watch.watch_id,
            org_id=watch.org_id,
            project_id=watch.project_id,
            status=MonitoringRunStatus.FAILED,
            error_message=message[:_ERROR_LIMIT],
        )
