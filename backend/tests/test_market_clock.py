from datetime import datetime, timedelta, timezone

from backend.app.core.http_client import MarketClock


CN_TZ = timezone(timedelta(hours=8))


def test_is_trading_time_uses_china_clock(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.http_client.MarketClock._now_china",
        lambda: datetime(2026, 3, 9, 10, 0, tzinfo=CN_TZ),
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-09",
    )

    assert MarketClock.is_trading_time() is True


def test_get_display_date_before_open_falls_back_prev_trade_day(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.http_client.MarketClock._now_china",
        lambda: datetime(2026, 3, 9, 8, 30, tzinfo=CN_TZ),
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-09",
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.get_last_trading_day",
        lambda _base: "2026-03-06",
    )

    assert MarketClock.get_display_date() == "2026-03-06"


def test_get_display_date_after_midnight_still_uses_prev_trade_day(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.http_client.MarketClock._now_china",
        lambda: datetime(2026, 3, 9, 0, 30, tzinfo=CN_TZ),
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-09",
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.get_last_trading_day",
        lambda _base: "2026-03-06",
    )

    assert MarketClock.get_display_date() == "2026-03-06"


def test_get_display_date_during_session_returns_today(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.http_client.MarketClock._now_china",
        lambda: datetime(2026, 3, 9, 10, 15, tzinfo=CN_TZ),
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-09",
    )

    assert MarketClock.get_display_date() == "2026-03-09"


def test_get_market_context_post_close_uses_today_but_not_realtime(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.http_client.MarketClock._now_china",
        lambda: datetime(2026, 3, 11, 22, 0, tzinfo=CN_TZ),
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-11",
    )

    context = MarketClock.get_market_context()

    assert context["market_status"] == "post_close"
    assert context["market_status_label"] == "盘后复盘"
    assert context["default_display_date"] == "2026-03-11"
    assert context["should_use_realtime_path"] is False


def test_get_market_context_lunch_break_uses_today_without_realtime(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.http_client.MarketClock._now_china",
        lambda: datetime(2026, 3, 11, 12, 0, tzinfo=CN_TZ),
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-11",
    )

    context = MarketClock.get_market_context()

    assert context["market_status"] == "lunch_break"
    assert context["default_display_date"] == "2026-03-11"
    assert context["should_use_realtime_path"] is False


def test_get_market_context_after_midnight_uses_previous_trade_day_review(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.http_client.MarketClock._now_china",
        lambda: datetime(2026, 3, 19, 0, 30, tzinfo=CN_TZ),
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-19",
    )
    monkeypatch.setattr(
        "backend.app.core.http_client.TradeCalendar.get_last_trading_day",
        lambda _base: "2026-03-18",
    )

    context = MarketClock.get_market_context()

    assert context["market_status"] == "post_close"
    assert context["market_status_label"] == "盘后复盘"
    assert context["default_display_date"] == "2026-03-18"
    assert context["default_display_scope"] == "previous_trade_day"
    assert context["should_use_realtime_path"] is False
