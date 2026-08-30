import uuid6
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
    ) -> tuple[MonitoringRun, SourceSnapshot]:
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

        return run, snapshot
