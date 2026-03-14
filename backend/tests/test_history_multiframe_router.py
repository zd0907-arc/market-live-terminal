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
    assert resp.data["count"] == 1
    item = resp.data["items"][0]
    assert item["datetime"] == "2026-03-11 09:30:00"
    assert item["source"] == "l2_history"
    assert item["is_finalized"] is True
    assert item["preview_level"] is None
    assert item["l1_main_buy"] > 0
    assert item["l2_main_buy"] > 0


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
    assert preview_item["l1_main_buy"] == 300000.0
    assert preview_item["l2_main_buy"] is None
