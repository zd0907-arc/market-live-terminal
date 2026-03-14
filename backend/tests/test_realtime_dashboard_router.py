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


def test_realtime_dashboard_uses_l2_history_when_1m_missing(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_display_date",
        lambda: "2026-03-12",
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock._now_china",
        lambda: type("T", (), {"strftime": lambda self, fmt: "2026-03-14"})(),
    )
    monkeypatch.setattr(
        "backend.app.routers.market.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-12",
    )

    called = {"history_1m": 0, "history_l2": 0, "realtime": 0}

    def fake_history_1m(symbol, date_str):
        called["history_1m"] += 1
        assert symbol == "sh600519"
        assert date_str == "2026-03-11"
        return None

    def fake_history_l2(symbol, date_str):
        called["history_l2"] += 1
        assert symbol == "sh600519"
        assert date_str == "2026-03-11"
        return {"chart_data": [{"time": "09:35"}], "cumulative_data": [{"time": "09:35"}], "latest_ticks": [], "source": "l2_history", "bucket_granularity": "5m"}

    def fake_realtime(symbol, date_str):
        called["realtime"] += 1
        return {"chart_data": [], "cumulative_data": [], "latest_ticks": []}

    monkeypatch.setattr(
        "backend.app.services.analysis.get_history_1m_dashboard",
        fake_history_1m,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.get_history_l2_dashboard",
        fake_history_l2,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.calculate_realtime_aggregation",
        fake_realtime,
    )

    resp = asyncio.run(get_realtime_dashboard(symbol="sh600519", date="2026-03-11"))

    assert resp.code == 200
    assert resp.data["display_date"] == "2026-03-11"
    assert resp.data["source"] == "l2_history"
    assert resp.data["bucket_granularity"] == "5m"
    assert called["history_1m"] == 1
    assert called["history_l2"] == 1
    assert called["realtime"] == 0


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
