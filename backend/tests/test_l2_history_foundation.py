import importlib
import sqlite3
from pathlib import Path


def _reload_modules(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))
    monkeypatch.setenv("USER_DB_PATH", str(tmp_path / "user_data.db"))
    import backend.app.core.config as config
    import backend.app.db.l2_history_db as l2_history_db
    import backend.app.db.database as database

    importlib.reload(config)
    importlib.reload(l2_history_db)
    importlib.reload(database)
    return l2_history_db, database, config


def test_l2_history_schema_created_by_init_db(monkeypatch, tmp_path):
    l2_history_db, database, config = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    conn = sqlite3.connect(config.DB_FILE)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()

    assert "history_5m_l2" in tables
    assert "history_daily_l2" in tables
    assert "l2_daily_ingest_runs" in tables
    assert "l2_daily_ingest_failures" in tables


def test_replace_l2_history_rows_overwrites_same_trade_date(monkeypatch, tmp_path):
    l2_history_db, database, config = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    rows_day1 = [
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
        ),
        (
            "sz000833",
            "2026-03-11 09:35:00",
            "2026-03-11",
            25.1,
            25.3,
            25.0,
            25.2,
            2000000.0,
            120.0,
            60.0,
            12.0,
            6.0,
            210.0,
            90.0,
            21.0,
            9.0,
        ),
    ]
    rows_day1_rewrite = [
        (
            "sz000833",
            "2026-03-11 09:30:00",
            "2026-03-11",
            26.0,
            26.2,
            25.9,
            26.1,
            3000000.0,
            300.0,
            150.0,
            30.0,
            15.0,
            400.0,
            200.0,
            40.0,
            20.0,
        )
    ]

    l2_history_db.replace_history_5m_l2_rows("sz000833", "2026-03-11", rows_day1)
    l2_history_db.replace_history_5m_l2_rows("sz000833", "2026-03-11", rows_day1_rewrite)

    conn = sqlite3.connect(config.DB_FILE)
    rows = conn.execute(
        "SELECT datetime, close, total_amount FROM history_5m_l2 WHERE symbol=? AND source_date=? ORDER BY datetime",
        ("sz000833", "2026-03-11"),
    ).fetchall()
    conn.close()

    assert rows == [("2026-03-11 09:30:00", 26.1, 3000000.0)]


def test_replace_history_daily_l2_row_overwrites(monkeypatch, tmp_path):
    l2_history_db, database, config = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    first = (
        "sz000833", "2026-03-11", 25.0, 27.0, 24.8, 27.5, 1.4e9,
        1.0, 2.0, -1.0, 3.0, 4.0, -1.0,
        5.0, 6.0, -1.0, 7.0, 8.0, -1.0,
        10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0,
    )
    second = (
        "sz000833", "2026-03-11", 25.1, 27.2, 24.9, 27.6, 1.5e9,
        10.0, 20.0, -10.0, 30.0, 40.0, -10.0,
        50.0, 60.0, -10.0, 70.0, 80.0, -10.0,
        18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0,
    )

    l2_history_db.replace_history_daily_l2_row("sz000833", "2026-03-11", first)
    l2_history_db.replace_history_daily_l2_row("sz000833", "2026-03-11", second)

    conn = sqlite3.connect(config.DB_FILE)
    row = conn.execute(
        "SELECT close, total_amount, l2_activity_ratio FROM history_daily_l2 WHERE symbol=? AND date=?",
        ("sz000833", "2026-03-11"),
    ).fetchone()
    conn.close()

    assert row == (27.6, 1.5e9, 20.0)


def test_l2_daily_ingest_run_lifecycle(monkeypatch, tmp_path):
    l2_history_db, database, config = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    run_id = l2_history_db.create_l2_daily_ingest_run(
        trade_date="2026-03-11",
        source_root=r"D:\MarketData\202603\20260311",
        mode="manual",
        message="unit-test",
    )
    inserted = l2_history_db.add_l2_daily_ingest_failures(
        run_id,
        [("sz000833", "2026-03-11", r"D:\MarketData\202603\20260311\000833.SZ\逐笔成交.csv", "sample error")],
    )
    l2_history_db.finish_l2_daily_ingest_run(
        run_id,
        status="failed",
        symbol_count=1,
        rows_5m=50,
        rows_daily=1,
        message="done",
    )

    latest = l2_history_db.get_latest_l2_daily_ingest_run("2026-03-11")
    assert inserted == 1
    assert latest is not None
    assert latest["id"] == run_id
    assert latest["status"] == "failed"
    assert latest["rows_5m"] == 50
    assert latest["rows_daily"] == 1


def test_l2_package_layout_supports_legacy_and_month_day_paths(tmp_path):
    from backend.app.core.l2_package_layout import infer_trade_date_from_path, normalize_month_day_root

    legacy = tmp_path / "20260311" / "20260311" / "000833.SZ"
    legacy.mkdir(parents=True)
    normalized = tmp_path / "202603" / "20260311" / "000833.SZ"
    normalized.mkdir(parents=True)

    legacy_root, legacy_trade_date = normalize_month_day_root(tmp_path / "20260311")
    assert legacy_trade_date == "20260311"
    assert legacy_root == tmp_path / "20260311" / "20260311"

    normalized_root, normalized_trade_date = normalize_month_day_root(tmp_path / "202603" / "20260311")
    assert normalized_trade_date == "20260311"
    assert normalized_root == tmp_path / "202603" / "20260311"

    assert infer_trade_date_from_path(normalized / "逐笔成交.csv") == "20260311"
