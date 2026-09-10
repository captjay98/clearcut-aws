import pytest
import uuid6
from clearcut.monitoring.application.run_scheduled_watch import ScheduledWatchService
from clearcut.monitoring.domain.models import (
    MonitoringRunStatus,
    WatchCadence,
    WatchConfig,
    WatchKind,
)
from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.adapters.hermetic_search import HermeticSearchAdapter


@pytest.mark.asyncio
async def test_scheduled_watch_executes_recheck():
    extract_port = HermeticExtractAdapter()
    search_port = HermeticSearchAdapter()
    service = ScheduledWatchService(extract_port=extract_port, search_port=search_port)

    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()

    watch = WatchConfig.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        cadence=WatchCadence.DAILY,
        watch_kind=WatchKind.EXACT_SOURCE,
        target_url="https://uspto.gov/trademarks/coca-cola",
    )

    run, snapshot, delta = await service.execute_watch_recheck(watch)

    assert run.status == MonitoringRunStatus.COMPLETED
    assert snapshot.url == "https://uspto.gov/trademarks/coca-cola"
    assert snapshot.item_id == item_id
    # No prior snapshot was supplied, so there is nothing to compare and no
    # change signal is fabricated.
    assert delta is None
