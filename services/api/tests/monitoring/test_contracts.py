import uuid6
from clearcut.monitoring.domain.models import (
    WatchCadence,
    WatchConfig,
    WatchKind,
)


def test_watch_config_and_statuses():
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

    assert watch.cadence == WatchCadence.DAILY
    assert watch.watch_kind == WatchKind.EXACT_SOURCE
    assert watch.target_url == "https://uspto.gov/trademarks/coca-cola"
