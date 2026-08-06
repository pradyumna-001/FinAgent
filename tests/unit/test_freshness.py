from datetime import datetime, timedelta

from app.utils.freshness import is_data_fresh

FIXED_NOW = datetime(2026, 8, 5, 12, 0, 0)


def test_data_freshness_check() -> None:
    fresh = is_data_fresh("b3", FIXED_NOW - timedelta(hours=1), now=FIXED_NOW)
    boundary = is_data_fresh("b3", FIXED_NOW - timedelta(hours=24), now=FIXED_NOW)
    stale = is_data_fresh("b3", FIXED_NOW - timedelta(hours=48), now=FIXED_NOW)

    assert fresh is True
    assert boundary is True
    assert stale is False
