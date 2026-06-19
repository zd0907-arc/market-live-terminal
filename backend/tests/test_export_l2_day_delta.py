from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.scripts.export_l2_day_delta import export_l2_day_delta


def test_export_l2_day_delta_matches_columns_by_name(tmp_path, monkeypatch):
    source_db = tmp_path / "source.db"
    output_db = tmp_path / "delta.db"
    monkeypatch.setenv("DB_PATH", str(tmp_path / "unused_live.db"))

    with sqlite3.connect(source_db) as conn:
        conn.executescript(
            """
            CREATE TABLE history_5m_l2 (
                symbol TEXT NOT NULL,
                datetime TEXT NOT NULL,
                source_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                l1_main_buy REAL NOT NULL,
                l1_main_sell REAL NOT NULL,
                l1_super_buy REAL NOT NULL,
                l1_super_sell REAL NOT NULL,
                l2_main_buy REAL NOT NULL,
                l2_main_sell REAL NOT NULL,
                l2_super_buy REAL NOT NULL,
                l2_super_sell REAL NOT NULL,
                quality_info TEXT NULL,
                total_volume REAL NULL,
                l2_add_buy_amount REAL NULL,
                l2_add_sell_amount REAL NULL,
                l2_cancel_buy_amount REAL NULL,
                l2_cancel_sell_amount REAL NULL,
                l2_cvd_delta REAL NULL,
                l2_oib_delta REAL NULL,
                PRIMARY KEY(symbol, datetime)
            );
            CREATE TABLE history_daily_l2 (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                l1_main_buy REAL NOT NULL,
                l1_main_sell REAL NOT NULL,
                l1_main_net REAL NOT NULL,
                l1_super_buy REAL NOT NULL,
                l1_super_sell REAL NOT NULL,
                l1_super_net REAL NOT NULL,
                l2_main_buy REAL NOT NULL,
                l2_main_sell REAL NOT NULL,
                l2_main_net REAL NOT NULL,
                l2_super_buy REAL NOT NULL,
                l2_super_sell REAL NOT NULL,
                l2_super_net REAL NOT NULL,
                l1_activity_ratio REAL NOT NULL,
                l1_super_ratio REAL NOT NULL,
                l2_activity_ratio REAL NOT NULL,
                l2_super_ratio REAL NOT NULL,
                l1_buy_ratio REAL NOT NULL,
                l1_sell_ratio REAL NOT NULL,
                l2_buy_ratio REAL NOT NULL,
                l2_sell_ratio REAL NOT NULL,
                quality_info TEXT NULL,
                PRIMARY KEY(symbol, date)
            );
            INSERT INTO history_5m_l2 VALUES (
                'sz000001', '2026-06-17 09:35:00', '2026-06-17',
                1, 2, 0.5, 1.5, 100,
                11, 12, 13, 14, 21, 22, 23, 24,
                'ok', 1000, 31, 32, 33, 34, 35, 36
            );
            INSERT INTO history_daily_l2 VALUES (
                'sz000001', '2026-06-17',
                1, 2, 0.5, 1.5, 100,
                11, 12, -1, 13, 14, -1, 21, 22, -1, 23, 24, -1,
                0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 'ok'
            );
            """
        )

    report = export_l2_day_delta("20260617", str(output_db), source_db=str(source_db))

    assert report["row_counts"]["history_5m_l2"] == 1
    with sqlite3.connect(output_db) as conn:
        row = conn.execute(
            """
            SELECT l1_main_buy, l2_super_sell, quality_info, total_volume, l2_oib_delta
            FROM history_5m_l2
            WHERE source_date='2026-06-17'
            """
        ).fetchone()
    assert row == (11, 24, "ok", 1000, 36)
