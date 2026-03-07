from datetime import datetime

from backend.app.core.calendar import TradeCalendar


def test_is_trade_day_fail_closed_for_newer_unknown_date(monkeypatch):
    original_days = TradeCalendar._trade_days
    original_initialized = TradeCalendar._initialized
    original_last_refresh = TradeCalendar._last_refresh_at

    try:
        TradeCalendar._trade_days = {"2026-03-06"}
        TradeCalendar._initialized = True
        TradeCalendar._last_refresh_at = datetime.now()

        # Prevent network refresh path in test.
        monkeypatch.setattr("backend.app.core.calendar.TradeCalendar.init", lambda force=False: None)

        assert TradeCalendar.is_trade_day("2026-03-10") is False
    finally:
        TradeCalendar._trade_days = original_days
        TradeCalendar._initialized = original_initialized
        TradeCalendar._last_refresh_at = original_last_refresh
