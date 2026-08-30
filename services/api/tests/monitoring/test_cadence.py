from datetime import UTC, datetime, timedelta

from clearcut.monitoring.application.change_policy import compute_next_watch_run
from clearcut.monitoring.domain.models import WatchCadence


def test_compute_next_watch_run():
    now = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)

    # OFF has no next run
    assert compute_next_watch_run(WatchCadence.OFF, now) is None

    # DAILY adds 24 hours
    daily_next = compute_next_watch_run(WatchCadence.DAILY, now)
    assert daily_next == now + timedelta(days=1)

    # WEEKLY adds 7 days
    weekly_next = compute_next_watch_run(WatchCadence.WEEKLY, now)
    assert weekly_next == now + timedelta(days=7)
