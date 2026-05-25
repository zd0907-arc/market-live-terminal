import sqlite3

from backend.scripts.merge_model_feature_store_day_delta import merge_model_feature_store_day_delta


def test_merge_model_feature_store_day_delta_uses_common_columns(tmp_path):
    target_db = tmp_path / "target.db"
    delta_db = tmp_path / "delta.db"

    with sqlite3.connect(target_db) as conn:
        conn.execute(
            """
            CREATE TABLE model_market_index_daily (
                index_code TEXT NOT NULL,
                index_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL NOT NULL,
                source TEXT NOT NULL,
                sync_run_id TEXT,
                updated_at TEXT,
                PRIMARY KEY(index_code, trade_date)
            )
            """
        )
        conn.commit()

    with sqlite3.connect(delta_db) as conn:
        conn.execute(
            """
            CREATE TABLE model_market_index_daily (
                index_code TEXT NOT NULL,
                index_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY(index_code, trade_date)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO model_market_index_daily (
                index_code, index_name, trade_date, close, source
            ) VALUES ('000852.SH', '中证1000', '2026-05-25', 1000.0, 'test')
            """
        )
        conn.commit()

    report = merge_model_feature_store_day_delta(
        "20260525",
        str(delta_db),
        str(target_db),
    )

    assert report["row_counts"]["model_market_index_daily"] == 1
    with sqlite3.connect(target_db) as conn:
        row = conn.execute(
            """
            SELECT index_code, trade_date, close, source, sync_run_id, updated_at
            FROM model_market_index_daily
            """
        ).fetchone()
    assert row == ("000852.SH", "2026-05-25", 1000.0, "test", None, None)
