import asyncio

from backend.app.routers.market import get_realtime_dashboard


def test_realtime_dashboard_prefers_history_on_weekend_backfill(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_display_date",
        lambda: "2026-03-13",
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock._now_china",
        lambda: type("T", (), {"strftime": lambda self, fmt: "2026-03-14"})(),
    )
    monkeypatch.setattr(
        "backend.app.routers.market.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-13",
    )

    called = {"realtime": 0, "history": 0}

    def fake_realtime(symbol, date_str):
        called["realtime"] += 1
        return {"chart_data": [{"time": "09:30"}], "cumulative_data": [], "latest_ticks": []}

    def fake_history(symbol, date_str):
        called["history"] += 1
        assert symbol == "sh600519"
        assert date_str == "2026-03-13"
        return {"chart_data": [{"time": "09:30"}], "cumulative_data": [], "latest_ticks": []}

    monkeypatch.setattr(
        "backend.app.services.analysis.calculate_realtime_aggregation",
        fake_realtime,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.get_history_1m_dashboard",
        fake_history,
    )

    resp = asyncio.run(get_realtime_dashboard(symbol="sh600519", date=None))

    assert resp.code == 200
    assert resp.data["display_date"] == "2026-03-13"
    assert called["realtime"] == 0
    assert called["history"] == 1


def test_realtime_dashboard_weekend_backfill_falls_back_to_ticks_when_history_missing(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_display_date",
        lambda: "2026-03-13",
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock._now_china",
        lambda: type("T", (), {"strftime": lambda self, fmt: "2026-03-14"})(),
    )
    monkeypatch.setattr(
        "backend.app.routers.market.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-13",
    )

    called = {"realtime": 0, "history": 0}

    def fake_realtime(symbol, date_str):
        called["realtime"] += 1
        assert symbol == "sh600519"
        assert date_str == "2026-03-13"
        return {"chart_data": [{"time": "09:30"}], "cumulative_data": [], "latest_ticks": []}

    def fake_history(symbol, date_str):
        called["history"] += 1
        assert date_str == "2026-03-13"
        return None

    monkeypatch.setattr(
        "backend.app.services.analysis.calculate_realtime_aggregation",
        fake_realtime,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.get_history_1m_dashboard",
        fake_history,
    )

    resp = asyncio.run(get_realtime_dashboard(symbol="sh600519", date=None))

    assert resp.code == 200
    assert resp.data["display_date"] == "2026-03-13"
    assert called["history"] == 1
    assert called["realtime"] == 1


def test_realtime_dashboard_uses_realtime_on_trade_day_today(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_display_date",
        lambda: "2026-03-16",
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock._now_china",
        lambda: type("T", (), {"strftime": lambda self, fmt: "2026-03-16"})(),
    )
    monkeypatch.setattr(
        "backend.app.routers.market.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-16",
    )

    called = {"realtime": 0, "history": 0}

    def fake_realtime(symbol, date_str):
        called["realtime"] += 1
        assert symbol == "sh600519"
        assert date_str == "2026-03-16"
        return {"chart_data": [{"time": "09:31"}], "cumulative_data": [], "latest_ticks": []}

    def fake_history(symbol, date_str):
        called["history"] += 1
        return {"chart_data": [], "cumulative_data": [], "latest_ticks": []}

    monkeypatch.setattr(
        "backend.app.services.analysis.calculate_realtime_aggregation",
        fake_realtime,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.get_history_1m_dashboard",
        fake_history,
    )

    resp = asyncio.run(get_realtime_dashboard(symbol="sh600519", date=None))

    assert resp.code == 200
    assert resp.data["display_date"] == "2026-03-16"
    assert called["realtime"] == 1
    assert called["history"] == 0
