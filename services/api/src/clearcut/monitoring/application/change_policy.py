from datetime import datetime, timedelta

from clearcut.monitoring.domain.models import WatchCadence


def compute_next_watch_run(
    cadence: WatchCadence,
    current_time: datetime,
) -> datetime | None:
    if cadence == WatchCadence.OFF:
        return None
    if cadence == WatchCadence.DAILY:
        return current_time + timedelta(days=1)
    if cadence == WatchCadence.WEEKLY:
        return current_time + timedelta(days=7)
    return None
