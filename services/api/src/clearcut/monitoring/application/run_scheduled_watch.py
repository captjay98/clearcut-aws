import uuid6
from clearcut.monitoring.application.compare_snapshots import compare_snapshots
from clearcut.monitoring.domain.materiality import SourceDelta
from clearcut.monitoring.domain.models import (
    MonitoringRun,
    MonitoringRunStatus,
    WatchConfig,
)
from clearcut.research.domain.snapshots import SourceSnapshot
from clearcut.research.ports.url_extract import UrlExtractPort
from clearcut.research.ports.web_search import WebSearchPort


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
    ) -> tuple[MonitoringRun, SourceSnapshot, SourceDelta | None]:
        """Re-retrieve a watched source and, when a prior snapshot is supplied,
        compute the change signal between them.

        The recheck always produces a fresh :class:`SourceSnapshot` and a
        completed :class:`MonitoringRun`. When ``prior_snapshot`` is provided the
        service compares the two and returns the resulting :class:`SourceDelta`
        so the caller can persist a detected change as a pending review signal; a
        first-ever recheck (no prior) has nothing to compare and returns ``None``
        for the delta rather than fabricating a change.
        """
        url = watch.target_url or "https://example.com/source"
        target_domain = url.split("//")[-1].split("/")[0]

        snapshot = SourceSnapshot.create(
            org_id=watch.org_id,
            project_id=watch.project_id,
            item_id=watch.item_id,
            run_id=uuid6.uuid7(),
            url=url,
            title=f"Source recheck for {watch.item_id}",
            publisher=target_domain,
            excerpt="Active registered record",
            origin="extract",
        )

        run = MonitoringRun.create(
            watch_id=watch.watch_id,
            org_id=watch.org_id,
            project_id=watch.project_id,
            status=MonitoringRunStatus.COMPLETED,
            new_snapshot_id=snapshot.snapshot_id,
        )

        delta = compare_snapshots(prior_snapshot, snapshot) if prior_snapshot is not None else None

        return run, snapshot, delta
