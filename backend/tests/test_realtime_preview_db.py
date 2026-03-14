import importlib
import sqlite3


def _reload_runtime_modules(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))
    monkeypatch.setenv("USER_DB_PATH", str(tmp_path / "user_data.db"))

    import backend.app.core.config as config
    import backend.app.db.crud as crud
    import backend.app.db.database as database
    import backend.app.db.realtime_preview_db as realtime_preview_db
    import backend.app.services.analysis as analysis

    importlib.reload(config)
    importlib.reload(realtime_preview_db)
    importlib.reload(database)
    importlib.reload(crud)
    importlib.reload(analysis)
    return config, database, crud, realtime_preview_db, analysis


def test_init_db_creates_realtime_preview_tables(monkeypatch, tmp_path):
    config, database, crud, realtime_preview_db, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()

    conn = sqlite3.connect(config.DB_FILE)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert "realtime_5m_preview" in tables
    assert "realtime_daily_preview" in tables


def test_refresh_realtime_preview_persists_5m_and_daily_rows(monkeypatch, tmp_path):
    config, database, crud, realtime_preview_db, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()

    conn = sqlite3.connect(config.DB_FILE)
    conn.executemany(
        """
        INSERT INTO trade_ticks (symbol, time, price, volume, amount, type, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("sz000833", "09:31:00", 25.10, 100, 250000.0, "buy", "2026-03-12"),
            ("sz000833", "09:34:00", 25.30, 100, 1200000.0, "sell", "2026-03-12"),
            ("sz000833", "09:36:00", 25.20, 100, 400000.0, "buy", "2026-03-12"),
        ],
    )
    conn.commit()
    conn.close()

    result = analysis.refresh_realtime_preview("sz000833", "2026-03-12")
    rows_5m = realtime_preview_db.query_realtime_5m_preview_rows("sz000833", "2026-03-12", "2026-03-12")
    daily_row = realtime_preview_db.query_realtime_daily_preview_row("sz000833", "2026-03-12")

    assert result == {"rows_5m": 2, "rows_daily": 1}
    assert len(rows_5m) == 2
    assert rows_5m[0]["datetime"] == "2026-03-12 09:30:00"
    assert rows_5m[0]["l1_main_buy"] == 250000.0
    assert rows_5m[0]["l1_main_sell"] == 1200000.0
    assert rows_5m[0]["l1_super_sell"] == 1200000.0
    assert rows_5m[1]["datetime"] == "2026-03-12 09:35:00"
    assert rows_5m[1]["l1_main_buy"] == 400000.0
    assert rows_5m[1]["preview_level"] == "l1_only"

    assert daily_row is not None
    assert daily_row["open"] == 25.10
    assert daily_row["high"] == 25.30
    assert daily_row["low"] == 25.10
    assert daily_row["close"] == 25.20
    assert daily_row["l1_main_buy"] == 650000.0
    assert daily_row["l1_main_sell"] == 1200000.0
    assert daily_row["l1_main_net"] == -550000.0
    assert daily_row["l1_super_sell"] == 1200000.0
    assert daily_row["source"] == "realtime_ticks"
    assert daily_row["preview_level"] == "l1_only"
