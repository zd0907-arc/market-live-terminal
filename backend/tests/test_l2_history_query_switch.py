import asyncio
import importlib
import sqlite3

from backend.scripts.l2_daily_backfill import backfill_day_package
from backend.tests.test_l2_daily_backfill import _build_sample_day


def _reload_runtime_modules(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))
    monkeypatch.setenv("USER_DB_PATH", str(tmp_path / "user_data.db"))

    import backend.app.core.config as config
    import backend.app.db.crud as crud
    import backend.app.db.database as database
    import backend.app.db.l2_history_db as l2_history_db
    import backend.app.routers.analysis as analysis

    importlib.reload(config)
    importlib.reload(l2_history_db)
    importlib.reload(database)
    importlib.reload(crud)
    importlib.reload(analysis)
    return config, database, crud, analysis


def test_history_trend_prefers_l2_history(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()
    package_path = _build_sample_day(tmp_path)
    backfill_day_package(package_path, mode="unit-test")

    monkeypatch.setattr(
        "backend.app.routers.analysis.MarketClock.get_display_date",
        lambda: "2026-03-12",
    )

    resp = analysis.get_history_trend("sz000833", days=5, granularity="30m")

    assert resp.code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["time"] == "2026-03-11 09:30:00"
    assert resp.data[0]["source"] == "l2_history"
    assert resp.data[0]["fallback_used"] is False
    assert resp.data[0]["total_amount"] == 2006000.0


def test_history_analysis_prefers_l2_history_without_sina(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()
    package_path = _build_sample_day(tmp_path)
    backfill_day_package(package_path, mode="unit-test")

    async def _should_not_call(*args, **kwargs):
        raise AssertionError("Sina fallback should not be called when L2 history exists")

    monkeypatch.setattr(
        "backend.app.routers.analysis.get_sina_money_flow",
        _should_not_call,
    )
    monkeypatch.setattr(
        "backend.app.routers.analysis.MarketClock.get_display_date",
        lambda: "2026-03-12",
    )

    resp = asyncio.run(analysis.get_history_analysis("sz000833", source="sina"))

    assert resp.code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["date"] == "2026-03-11"
    assert resp.data[0]["source"] == "l2_history"
    assert resp.data[0]["is_finalized"] is True
    assert resp.data[0]["fallback_used"] is False


def test_history_analysis_keeps_today_realtime_overlay(monkeypatch, tmp_path):
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

    monkeypatch.setattr(
        "backend.app.routers.analysis.MarketClock.get_display_date",
        lambda: "2026-03-12",
    )

    resp = asyncio.run(analysis.get_history_analysis("sz000833", source="sina"))

    assert resp.code == 200
    assert [row["date"] for row in resp.data] == ["2026-03-11", "2026-03-12"]
    assert resp.data[-1]["source"] == "realtime_ticks"
    assert resp.data[-1]["is_finalized"] is False
    assert resp.data[-1]["preview_level"] == "l1_only"
    assert resp.data[-1]["main_buy_amount"] == 300000.0


def test_history_local_merges_legacy_local_and_l2_history(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()
    package_path = _build_sample_day(tmp_path)
    backfill_day_package(package_path, mode="unit-test")

    conn = sqlite3.connect(config.DB_FILE)
    conn.execute(
        """
        INSERT INTO local_history (
            symbol, date, net_inflow, main_buy_amount, main_sell_amount, close, change_pct, activity_ratio, config_signature
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("sz000833", "2026-03-10", 120000.0, 280000.0, 160000.0, 24.8, 1.2, 18.0, "unit-test"),
    )
    conn.commit()
    conn.close()

    rows = analysis.get_local_history("sz000833")
    assert [row["date"] for row in rows] == ["2026-03-10", "2026-03-11"]
    assert rows[0]["source"] == "local_history"
    assert rows[1]["source"] == "l2_history"
    assert rows[1]["main_buy_amount"] > rows[0]["main_buy_amount"]


def test_history_analysis_local_uses_atomic_or_l2_payload(monkeypatch, tmp_path):
    config, database, crud, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()
    package_path = _build_sample_day(tmp_path)
    backfill_day_package(package_path, mode="unit-test")

    monkeypatch.setattr(
        "backend.app.routers.analysis.MarketClock.get_display_date",
        lambda: "2026-03-12",
    )

    resp = asyncio.run(analysis.get_history_analysis("sz000833", source="local"))

    assert resp.code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["date"] == "2026-03-11"
    assert resp.data[0]["source"] == "l2_history"
    assert resp.data[0]["fallback_used"] is False
