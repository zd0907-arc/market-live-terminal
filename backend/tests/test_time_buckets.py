from datetime import datetime

from backend.app.core.time_buckets import is_canonical_30m_start, map_to_30m_bucket_start


def test_map_to_30m_bucket_start_trade_session():
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 9, 31)).strftime("%H:%M:%S") == "09:30:00"
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 10, 29, 59)).strftime("%H:%M:%S") == "10:00:00"
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 11, 29, 59)).strftime("%H:%M:%S") == "11:00:00"
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 14, 59, 59)).strftime("%H:%M:%S") == "14:30:00"
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 15, 0, 0)).strftime("%H:%M:%S") == "14:30:00"


def test_map_to_30m_bucket_start_outside_session():
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 9, 0, 0)) is None
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 11, 30, 0)) is None
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 12, 45, 0)) is None
    assert map_to_30m_bucket_start(datetime(2026, 3, 6, 15, 1, 0)) is None


def test_is_canonical_30m_start():
    assert is_canonical_30m_start("2026-03-06 09:30:00") is True
    assert is_canonical_30m_start("2026-03-06 14:30:00") is True
    assert is_canonical_30m_start("2026-03-06 11:30:00") is False
    assert is_canonical_30m_start("2026-03-06 15:00:00") is False
