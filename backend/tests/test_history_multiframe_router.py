import importlib
import sqlite3

from backend.app.db.l2_history_db import replace_history_5m_l2_rows, replace_history_daily_l2_row
from backend.scripts.l2_daily_backfill import backfill_day_package
from backend.tests.test_l2_daily_backfill import _build_sample_day


def _reload_runtime_modules(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))
    monkeypatch.setenv("USER_DB_PATH", str(tmp_path / "user_data.db"))

    import backend.app.core.config as config
    import backend.app.db.crud as crud
    import backend.app.db.database as database
    import backend.app.db.l2_history_db as l2_history_db
    import backend.app.db.realtime_preview_db as realtime_preview_db
    import backend.app.routers.analysis as analysis
    import backend.app.services.analysis as analysis_service

    importlib.reload(config)
    importlib.reload(l2_history_db)
    importlib.reload(realtime_preview_db)
    importlib.reload(database)
    importlib.reload(crud)
    importlib.reload(analysis_service)
    importlib.reload(analysis)
    return config, database, crud, analysis


def test_history_multiframe_returns_finalized_intraday_rows(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()
    package_path = _build_sample_day(tmp_path)
    backfill_day_package(package_path, mode="unit-test")

    monkeypatch.setattr("backend.app.routers.analysis.MOCK_DATA_DATE", None)
    monkeypatch.setattr(
        "backend.app.routers.analysis.MarketClock._now_china",
        lambda: type("T", (), {"strftime": lambda self, fmt: "2026-03-12"})(),
    )

    resp = analysis.get_history_multiframe(
        "sz000833",
        granularity="30m",
        days=5,
        include_today_preview=False,
    )

    assert resp.code == 200
    assert resp.data["granularity"] == "30m"
    assert resp.data["count"] >= 1
    item = resp.data["items"][0]
    assert item["datetime"] == "2026-03-11 09:30:00"
    assert item["source"] == "l2_history"
    assert item["is_finalized"] is True
    assert item["preview_level"] is None
    assert item["quality_info"] == "该区间包含缺失 5m，聚合值可能偏小"
    assert item["is_placeholder"] is False
    assert item["l1_main_buy"] > 0
    assert item["l2_main_buy"] > 0
    assert any(row["is_placeholder"] is True for row in resp.data["items"][1:])


def test_history_multiframe_appends_today_daily_preview(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()
    package_path = _build_sample_day(tmp_path)
    backfill_day_package(package_path, mode="unit-test")

    conn = sqlite3.connect(config.DB_FILE)
    conn.execute(
        """
        INSERT INTO trade_ticks (symbol, time, price, volume, amount, type, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("sz000833", "10:01:00", 25.8, 100, 300000.0, "buy", "2026-03-12"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("backend.app.routers.analysis.MOCK_DATA_DATE", None)
    monkeypatch.setattr(
        "backend.app.routers.analysis.MarketClock._now_china",
        lambda: type("T", (), {"strftime": lambda self, fmt: "2026-03-12"})(),
    )

    resp = analysis.get_history_multiframe(
        "sz000833",
        granularity="1d",
        days=5,
        include_today_preview=True,
    )

    assert resp.code == 200
    assert resp.data["granularity"] == "1d"
    assert resp.data["count"] == 2
    assert [item["trade_date"] for item in resp.data["items"]] == ["2026-03-11", "2026-03-12"]
    preview_item = resp.data["items"][-1]
    assert preview_item["source"] == "realtime_ticks"
    assert preview_item["is_finalized"] is False
    assert preview_item["preview_level"] == "l1_only"
    assert preview_item["quality_info"] is None
    assert preview_item["is_placeholder"] is False
    assert preview_item["l1_main_buy"] == 300000.0
    assert preview_item["l2_main_buy"] is None


def test_history_multiframe_injects_daily_placeholder(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()

    replace_history_daily_l2_row(
        "sz000833",
        "2026-03-11",
        (
            "sz000833", "2026-03-11", 25.0, 25.5, 24.8, 25.2, 1000000.0,
            100.0, 90.0, 10.0, 50.0, 40.0, 10.0,
            120.0, 80.0, 40.0, 60.0, 30.0, 30.0,
            19.0, 9.0, 20.0, 10.0, 12.0, 8.0, 14.0, 6.0,
            None,
        ),
    )
    replace_history_daily_l2_row(
        "sz000833",
        "2026-03-13",
        (
            "sz000833", "2026-03-13", 26.0, 26.5, 25.8, 26.2, 1200000.0,
            110.0, 95.0, 15.0, 55.0, 43.0, 12.0,
            130.0, 85.0, 45.0, 66.0, 33.0, 33.0,
            18.0, 8.0, 21.0, 11.0, 13.0, 8.0, 15.0, 7.0,
            None,
        ),
    )

    monkeypatch.setattr("backend.app.routers.analysis.MOCK_DATA_DATE", None)
    monkeypatch.setattr("backend.app.routers.analysis.TradeCalendar.is_trade_day", lambda date_str: date_str in {"2026-03-11", "2026-03-12", "2026-03-13"})

    resp = analysis.get_history_multiframe(
        "sz000833",
        granularity="1d",
        start_date="2026-03-11",
        end_date="2026-03-13",
        include_today_preview=False,
    )

    assert resp.code == 200
    assert [item["trade_date"] for item in resp.data["items"]] == ["2026-03-11", "2026-03-12", "2026-03-13"]
    placeholder = resp.data["items"][1]
    assert placeholder["is_placeholder"] is True
    assert placeholder["quality_info"] == "该日缺失正式数据"
    assert placeholder["open"] is None
    assert placeholder["l2_main_buy"] is None


def test_history_multiframe_aggregates_intraday_quality_info(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()

    replace_history_5m_l2_rows(
        "sz000833",
        "2026-03-11",
        [
            (
                "sz000833",
                "2026-03-11 09:30:00",
                "2026-03-11",
                25.0,
                25.2,
                24.9,
                25.1,
                1000000.0,
                100.0,
                50.0,
                10.0,
                5.0,
                200.0,
                100.0,
                20.0,
                10.0,
                "L2 买边单边回退，数值可能偏小",
            ),
        ],
    )

    monkeypatch.setattr("backend.app.routers.analysis.MOCK_DATA_DATE", None)
    monkeypatch.setattr("backend.app.routers.analysis.TradeCalendar.is_trade_day", lambda date_str: date_str == "2026-03-11")

    resp = analysis.get_history_multiframe(
        "sz000833",
        granularity="30m",
        start_date="2026-03-11",
        end_date="2026-03-11",
        include_today_preview=False,
    )

    assert resp.code == 200
    assert resp.data["count"] >= 1
    first_item = resp.data["items"][0]
    assert first_item["datetime"] == "2026-03-11 09:30:00"
    assert first_item["quality_info"] is not None


def test_history_multiframe_prefers_finalized_today_daily_even_if_trade_calendar_false(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()

    replace_history_daily_l2_row(
        "sz000833",
        "2026-03-16",
        (
            "sz000833", "2026-03-16", 28.5, 29.23, 26.86, 27.58, 1886212818.0,
            698078129.0, 823173357.0, -125095228.0, 464694215.0, 546786924.0, -82092709.0,
            765863513.84, 801627748.55, -35764234.71, 268785465.4, 288291142.66, -19505677.26,
            21.0, 10.0, 84.4, 30.0, 12.0, 9.0, 41.2, 43.1,
            None,
        ),
    )

    conn = sqlite3.connect(config.DB_FILE)
    conn.execute(
        """
        INSERT INTO trade_ticks (symbol, time, price, volume, amount, type, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("sz000833", "10:01:00", 27.8, 100, 300000.0, "buy", "2026-03-16"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("backend.app.routers.analysis.MOCK_DATA_DATE", None)
    monkeypatch.setattr(
        "backend.app.routers.analysis.MarketClock._now_china",
        lambda: type("T", (), {"strftime": lambda self, fmt: "2026-03-16"})(),
    )
    monkeypatch.setattr("backend.app.routers.analysis.TradeCalendar.is_trade_day", lambda date_str: False)

    resp = analysis.get_history_multiframe(
        "sz000833",
        granularity="1d",
        start_date="2026-03-16",
        end_date="2026-03-16",
        include_today_preview=True,
    )

    assert resp.code == 200
    assert resp.data["count"] == 1
    item = resp.data["items"][0]
    assert item["trade_date"] == "2026-03-16"
    assert item["source"] == "l2_history"
    assert item["is_finalized"] is True
    assert item["preview_level"] is None
    assert item["l2_main_buy"] == 765863513.84


def test_history_multiframe_prefers_finalized_today_intraday_without_preview_mix(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()

    replace_history_5m_l2_rows(
        "sz000833",
        "2026-03-16",
        [
            (
                "sz000833",
                "2026-03-16 09:30:00",
                "2026-03-16",
                28.5,
                29.25,
                28.15,
                29.04,
                358055909.5,
                45415911.0,
                36460585.13,
                12318133.0,
                11448669.0,
                158227560.0,
                173617942.33,
                65828785.0,
                60594091.94,
                None,
            ),
        ],
    )

    conn = sqlite3.connect(config.DB_FILE)
    conn.execute(
        """
        INSERT INTO trade_ticks (symbol, time, price, volume, amount, type, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("sz000833", "09:25:00", 28.5, 100, 29369250.0, "sell", "2026-03-16"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("backend.app.routers.analysis.MOCK_DATA_DATE", None)
    monkeypatch.setattr(
        "backend.app.routers.analysis.MarketClock._now_china",
        lambda: type("T", (), {"strftime": lambda self, fmt: "2026-03-16"})(),
    )
    monkeypatch.setattr("backend.app.routers.analysis.TradeCalendar.is_trade_day", lambda date_str: False)

    resp = analysis.get_history_multiframe(
        "sz000833",
        granularity="5m",
        start_date="2026-03-16",
        end_date="2026-03-16",
        include_today_preview=True,
    )

    assert resp.code == 200
    assert resp.data["count"] >= 1
    assert all(item["source"] != "realtime_ticks" for item in resp.data["items"])
    assert all(item["datetime"] != "2026-03-16 09:25:00" for item in resp.data["items"])
    item = resp.data["items"][0]
    assert item["datetime"] == "2026-03-16 09:30:00"
    assert item["source"] == "l2_history"
    assert item["is_finalized"] is True
    assert item["preview_level"] is None
