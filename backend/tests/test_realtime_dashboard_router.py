import asyncio

from backend.app.routers.market import get_intraday_fusion, get_realtime_dashboard


def test_realtime_dashboard_prefers_history_on_weekend_backfill(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-14",
            "is_trade_day": False,
            "market_status": "closed_day",
            "market_status_label": "休盘日",
            "default_display_date": "2026-03-13",
            "default_display_scope": "previous_trade_day",
            "default_display_scope_label": "默认展示上一交易日数据",
            "should_use_realtime_path": False,
        },
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
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-14",
            "is_trade_day": False,
            "market_status": "closed_day",
            "market_status_label": "休盘日",
            "default_display_date": "2026-03-13",
            "default_display_scope": "previous_trade_day",
            "default_display_scope_label": "默认展示上一交易日数据",
            "should_use_realtime_path": False,
        },
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
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-14",
            "is_trade_day": False,
            "market_status": "closed_day",
            "market_status_label": "休盘日",
            "default_display_date": "2026-03-12",
            "default_display_scope": "previous_trade_day",
            "default_display_scope_label": "默认展示上一交易日数据",
            "should_use_realtime_path": False,
        },
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
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-16",
            "is_trade_day": True,
            "market_status": "trading",
            "market_status_label": "盘中交易",
            "default_display_date": "2026-03-16",
            "default_display_scope": "today",
            "default_display_scope_label": "默认展示今日实时数据",
            "should_use_realtime_path": True,
        },
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


def test_realtime_dashboard_post_close_defaults_to_today_review_not_realtime(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-18",
            "is_trade_day": True,
            "market_status": "post_close",
            "market_status_label": "盘后复盘",
            "default_display_date": "2026-03-18",
            "default_display_scope": "today",
            "default_display_scope_label": "默认展示今日收盘后数据",
            "should_use_realtime_path": False,
        },
    )

    called = {"history": 0, "realtime": 0}

    def fake_history(symbol, date_str):
        called["history"] += 1
        assert symbol == "sz300017"
        assert date_str == "2026-03-18"
        return {"chart_data": [{"time": "15:00"}], "cumulative_data": [], "latest_ticks": [], "source": "history_1m"}

    def fake_realtime(symbol, date_str):
        called["realtime"] += 1
        return {"chart_data": [{"time": "15:00"}], "cumulative_data": [], "latest_ticks": []}

    monkeypatch.setattr(
        "backend.app.services.analysis.get_history_1m_dashboard",
        fake_history,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.get_history_l2_dashboard",
        lambda symbol, date_str: None,
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.calculate_realtime_aggregation",
        fake_realtime,
    )

    resp = asyncio.run(get_realtime_dashboard(symbol="sz300017", date=None))

    assert resp.code == 200
    assert resp.data["display_date"] == "2026-03-18"
    assert resp.data["market_status"] == "post_close"
    assert resp.data["view_mode"] == "today_postclose_review"
    assert called["history"] == 1
    assert called["realtime"] == 0


def test_intraday_fusion_returns_intraday_l1_only_preview(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-18",
            "is_trade_day": True,
            "market_status": "trading",
            "market_status_label": "盘中交易",
            "default_display_date": "2026-03-18",
            "default_display_scope": "today",
            "default_display_scope_label": "默认展示今日实时数据",
            "should_use_realtime_path": True,
        },
    )
    monkeypatch.setattr(
        "backend.app.routers.market.query_l2_history_5m_rows",
        lambda symbol, start_date=None, end_date=None, limit_days=None: [],
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.refresh_realtime_preview",
        lambda symbol, date_str: {"rows_5m": 1},
    )
    monkeypatch.setattr(
        "backend.app.routers.market.query_realtime_5m_preview_rows",
        lambda symbol, start_date=None, end_date=None, limit_days=None: [
            {
                "symbol": symbol,
                "datetime": "2026-03-18 09:30:00",
                "trade_date": "2026-03-18",
                "open": 25.0,
                "high": 25.2,
                "low": 24.9,
                "close": 25.1,
                "total_amount": 500000.0,
                "total_volume": 20000.0,
                "l1_main_buy": 300000.0,
                "l1_main_sell": 100000.0,
                "l1_super_buy": 100000.0,
                "l1_super_sell": 0.0,
                "source": "realtime_ticks",
                "preview_level": "l1_only",
                "updated_at": "2026-03-18 09:35:00",
            }
        ],
    )

    resp = asyncio.run(get_intraday_fusion(symbol="sz000833", date=None, include_today_preview=True))

    assert resp.code == 200
    assert resp.data["mode"] == "intraday_l1_only"
    assert resp.data["source"] == "realtime_preview"
    assert resp.data["is_l2_finalized"] is False
    assert len(resp.data["bars"]) == 1
    bar = resp.data["bars"][0]
    assert bar["total_volume"] == 20000.0
    assert bar["l1_net_inflow"] == 200000.0
    assert bar["l2_main_buy"] is None
    assert bar["cancel_buy_amount"] is None


def test_intraday_fusion_returns_postclose_dual_track_when_finalized_exists(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-18",
            "is_trade_day": True,
            "market_status": "post_close",
            "market_status_label": "盘后复盘",
            "default_display_date": "2026-03-18",
            "default_display_scope": "today",
            "default_display_scope_label": "默认展示今日收盘后数据",
            "should_use_realtime_path": False,
        },
    )
    monkeypatch.setattr(
        "backend.app.routers.market.query_l2_history_5m_rows",
        lambda symbol, start_date=None, end_date=None, limit_days=None: [
            {
                "symbol": symbol,
                "datetime": "2026-03-18 09:30:00",
                "source_date": "2026-03-18",
                "open": 25.0,
                "high": 25.3,
                "low": 24.9,
                "close": 25.2,
                "total_amount": 600000.0,
                "total_volume": 24000.0,
                "l1_main_buy": 320000.0,
                "l1_main_sell": 110000.0,
                "l1_super_buy": 120000.0,
                "l1_super_sell": 0.0,
                "l2_main_buy": 350000.0,
                "l2_main_sell": 90000.0,
                "l2_super_buy": 150000.0,
                "l2_super_sell": 10000.0,
                "l2_add_buy_amount": 500000.0,
                "l2_add_sell_amount": 300000.0,
                "l2_cancel_buy_amount": 50000.0,
                "l2_cancel_sell_amount": 70000.0,
                "l2_cvd_delta": 120000.0,
                "l2_oib_delta": 220000.0,
            }
        ],
    )

    resp = asyncio.run(get_intraday_fusion(symbol="sz000833", date=None, include_today_preview=True))

    assert resp.code == 200
    assert resp.data["mode"] == "postclose_dual_track"
    assert resp.data["source"] == "l2_history"
    assert resp.data["is_l2_finalized"] is True
    bar = resp.data["bars"][0]
    assert bar["l1_net_inflow"] == 210000.0
    assert bar["l2_net_inflow"] == 260000.0
    assert bar["cancel_sell_amount"] == 70000.0
    assert bar["l2_oib_delta"] == 220000.0


def test_intraday_fusion_returns_historical_dual_track_for_history_date(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-18",
            "is_trade_day": True,
            "market_status": "trading",
            "market_status_label": "盘中交易",
            "default_display_date": "2026-03-18",
            "default_display_scope": "today",
            "default_display_scope_label": "默认展示今日实时数据",
            "should_use_realtime_path": True,
        },
    )
    monkeypatch.setattr(
        "backend.app.routers.market.query_l2_history_5m_rows",
        lambda symbol, start_date=None, end_date=None, limit_days=None: [
            {
                "symbol": symbol,
                "datetime": "2026-03-17 09:30:00",
                "source_date": "2026-03-17",
                "open": 25.0,
                "high": 25.1,
                "low": 24.8,
                "close": 24.9,
                "total_amount": 400000.0,
                "total_volume": 18000.0,
                "l1_main_buy": 120000.0,
                "l1_main_sell": 150000.0,
                "l1_super_buy": 0.0,
                "l1_super_sell": 0.0,
                "l2_main_buy": 100000.0,
                "l2_main_sell": 180000.0,
                "l2_super_buy": 0.0,
                "l2_super_sell": 0.0,
                "l2_add_buy_amount": 220000.0,
                "l2_add_sell_amount": 310000.0,
                "l2_cancel_buy_amount": 40000.0,
                "l2_cancel_sell_amount": 80000.0,
                "l2_cvd_delta": -80000.0,
                "l2_oib_delta": -50000.0,
            }
        ],
    )

    resp = asyncio.run(get_intraday_fusion(symbol="sz000833", date="2026-03-17", include_today_preview=False))

    assert resp.code == 200
    assert resp.data["trade_date"] == "2026-03-17"
    assert resp.data["mode"] == "historical_dual_track"
    assert resp.data["is_l2_finalized"] is True
    assert resp.data["bars"][0]["total_volume"] == 18000.0


def test_intraday_fusion_falls_back_to_history_l1_when_finalized_missing(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.market.MOCK_DATA_DATE",
        None,
    )
    monkeypatch.setattr(
        "backend.app.routers.market.MarketClock.get_market_context",
        lambda: {
            "natural_today": "2026-03-19",
            "is_trade_day": True,
            "market_status": "post_close",
            "market_status_label": "盘后复盘",
            "default_display_date": "2026-03-18",
            "default_display_scope": "previous_trade_day",
            "default_display_scope_label": "默认展示上一交易日复盘数据",
            "should_use_realtime_path": False,
        },
    )
    monkeypatch.setattr(
        "backend.app.routers.market.query_l2_history_5m_rows",
        lambda symbol, start_date=None, end_date=None, limit_days=None: [],
    )
    monkeypatch.setattr(
        "backend.app.services.analysis.refresh_realtime_preview",
        lambda symbol, date_str: {"rows_5m": 1, "rows_daily": 0},
    )
    monkeypatch.setattr(
        "backend.app.routers.market.query_realtime_5m_preview_rows",
        lambda symbol, start_date=None, end_date=None, limit_days=None: [
            {
                "symbol": symbol,
                "datetime": "2026-03-18 09:30:00",
                "trade_date": "2026-03-18",
                "open": 25.0,
                "high": 25.1,
                "low": 24.8,
                "close": 24.9,
                "total_amount": 400000.0,
                "total_volume": 18000.0,
                "l1_main_buy": 120000.0,
                "l1_main_sell": 150000.0,
                "l1_super_buy": 0.0,
                "l1_super_sell": 0.0,
                "source": "realtime_ticks",
                "preview_level": "l1_only",
                "updated_at": "2026-03-19 00:58:00",
            }
        ],
    )

    resp = asyncio.run(get_intraday_fusion(symbol="sz000833", date=None, include_today_preview=True))

    assert resp.code == 200
    assert resp.data["trade_date"] == "2026-03-18"
    assert resp.data["mode"] == "historical_dual_track"
    assert resp.data["source"] == "history_l1_fallback"
    assert resp.data["fallback_used"] is True
    assert resp.data["is_l2_finalized"] is False
    bar = resp.data["bars"][0]
    assert bar["preview_level"] == "historical_l1_fallback"
    assert bar["l2_main_buy"] is None
    assert bar["total_volume"] == 18000.0
