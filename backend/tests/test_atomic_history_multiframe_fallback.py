import importlib
import sqlite3
from pathlib import Path


def _reload_runtime_modules(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))
    monkeypatch.setenv("USER_DB_PATH", str(tmp_path / "user_data.db"))
    monkeypatch.setenv("ATOMIC_DB_PATH", str(tmp_path / "atomic_mainboard.db"))

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
    return config, database, analysis


def _init_atomic_db(tmp_path: Path) -> Path:
    atomic_db = tmp_path / "atomic_mainboard.db"
    schema_path = Path(__file__).resolve().parents[1] / "scripts" / "sql" / "atomic_fact_p0_schema.sql"
    conn = sqlite3.connect(atomic_db)
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.executemany(
            """
            INSERT INTO atomic_trade_5m (
                symbol, trade_date, bucket_start, open, high, low, close,
                total_amount, total_volume, trade_count,
                l1_main_buy_count, l1_main_sell_count, l1_super_buy_count, l1_super_sell_count,
                l2_main_buy_count, l2_main_sell_count, l2_super_buy_count, l2_super_sell_count,
                l1_main_buy_amount, l1_main_sell_amount, l1_main_net_amount,
                l1_super_buy_amount, l1_super_sell_amount, l1_super_net_amount,
                l2_main_buy_amount, l2_main_sell_amount, l2_main_net_amount,
                l2_super_buy_amount, l2_super_sell_amount, l2_super_net_amount,
                max_trade_amount, avg_trade_amount, max_parent_order_amount, top5_parent_concentration_ratio,
                source_type, quality_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "sh603629", "2026-04-10", "2026-04-10 09:30:00", 10.0, 10.2, 9.9, 10.1,
                    1_000_000.0, 1000.0, 10,
                    1, 1, 1, 1, 1, 1, 1, 1,
                    300_000.0, 180_000.0, 120_000.0,
                    120_000.0, 40_000.0, 80_000.0,
                    360_000.0, 150_000.0, 210_000.0,
                    140_000.0, 50_000.0, 90_000.0,
                    100_000.0, 10_000.0, 200_000.0, 0.5,
                    "unit-test", None,
                ),
                (
                    "sh603629", "2026-04-10", "2026-04-10 09:35:00", 10.1, 10.3, 10.0, 10.2,
                    1_200_000.0, 1200.0, 12,
                    1, 1, 1, 1, 1, 1, 1, 1,
                    320_000.0, 200_000.0, 120_000.0,
                    150_000.0, 50_000.0, 100_000.0,
                    380_000.0, 180_000.0, 200_000.0,
                    160_000.0, 60_000.0, 100_000.0,
                    110_000.0, 11_000.0, 220_000.0, 0.6,
                    "unit-test", "trade quality ok",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO atomic_trade_daily (
                symbol, trade_date, open, high, low, close, total_amount, total_volume, trade_count,
                l1_main_buy_count, l1_main_sell_count, l1_super_buy_count, l1_super_sell_count,
                l2_main_buy_count, l2_main_sell_count, l2_super_buy_count, l2_super_sell_count,
                l1_main_buy_amount, l1_main_sell_amount, l1_main_net_amount,
                l1_super_buy_amount, l1_super_sell_amount, l1_super_net_amount,
                l2_main_buy_amount, l2_main_sell_amount, l2_main_net_amount,
                l2_super_buy_amount, l2_super_sell_amount, l2_super_net_amount,
                l1_activity_ratio, l2_activity_ratio, l1_buy_ratio, l1_sell_ratio, l2_buy_ratio, l2_sell_ratio,
                max_trade_amount, avg_trade_amount, max_parent_order_amount, top5_parent_concentration_ratio,
                am_l2_main_net_amount, pm_l2_main_net_amount, open_30m_l2_main_net_amount, last_30m_l2_main_net_amount,
                positive_l2_net_bar_count, negative_l2_net_bar_count, source_type, quality_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "sh603629", "2026-04-09", 9.8, 10.0, 9.7, 9.95, 1_500_000.0, 1500.0, 15,
                    1, 1, 1, 1, 1, 1, 1, 1,
                    400_000.0, 250_000.0, 150_000.0,
                    160_000.0, 70_000.0, 90_000.0,
                    500_000.0, 280_000.0, 220_000.0,
                    220_000.0, 100_000.0, 120_000.0,
                    43.3, 52.0, 26.7, 16.7, 33.3, 18.7,
                    120_000.0, 10_000.0, 220_000.0, 0.5,
                    100_000.0, 120_000.0, 80_000.0, 60_000.0,
                    4, 2, "unit-test", None,
                ),
                (
                    "sh603629", "2026-04-10", 10.0, 10.3, 9.9, 10.2, 2_200_000.0, 2200.0, 22,
                    1, 1, 1, 1, 1, 1, 1, 1,
                    620_000.0, 380_000.0, 240_000.0,
                    270_000.0, 90_000.0, 180_000.0,
                    740_000.0, 330_000.0, 410_000.0,
                    300_000.0, 110_000.0, 190_000.0,
                    45.0, 49.0, 28.0, 17.0, 33.0, 15.0,
                    130_000.0, 11_000.0, 240_000.0, 0.6,
                    180_000.0, 230_000.0, 150_000.0, 90_000.0,
                    5, 1, "unit-test", "daily trade ok",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO atomic_order_5m (
                symbol, trade_date, bucket_start,
                add_buy_amount, add_sell_amount, cancel_buy_amount, cancel_sell_amount,
                cvd_delta_amount, oib_delta_amount,
                add_buy_count, add_sell_count, cancel_buy_count, cancel_sell_count,
                add_buy_volume, add_sell_volume, cancel_buy_volume, cancel_sell_volume,
                order_event_count, buy_add_cancel_net_amount, sell_add_cancel_net_amount,
                source_type, quality_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "sh603629", "2026-04-10", "2026-04-10 09:30:00",
                    100_000.0, 80_000.0, 20_000.0, 15_000.0,
                    30_000.0, 18_000.0,
                    1, 1, 1, 1, 1000.0, 900.0, 200.0, 150.0,
                    4, 80_000.0, 65_000.0, "unit-test", None,
                ),
                (
                    "sh603629", "2026-04-10", "2026-04-10 09:35:00",
                    120_000.0, 85_000.0, 25_000.0, 18_000.0,
                    35_000.0, 20_000.0,
                    1, 1, 1, 1, 1200.0, 920.0, 250.0, 180.0,
                    4, 95_000.0, 67_000.0, "unit-test", "order quality ok",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO atomic_order_daily (
                symbol, trade_date, add_buy_amount, add_sell_amount, cancel_buy_amount, cancel_sell_amount,
                cvd_delta_amount, oib_delta_amount, add_buy_count, add_sell_count, cancel_buy_count, cancel_sell_count,
                am_oib_delta_amount, pm_oib_delta_amount, open_60m_oib_delta_amount, last_30m_oib_delta_amount,
                open_60m_cvd_delta_amount, last_30m_cvd_delta_amount, positive_oib_bar_count, negative_oib_bar_count,
                positive_cvd_bar_count, negative_cvd_bar_count, order_event_count, oib_top3_concentration_ratio,
                moderate_positive_oib_bar_count, moderate_positive_oib_bar_ratio, positive_oib_streak_max,
                buy_support_ratio, sell_pressure_ratio, quality_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sh603629", "2026-04-10", 220_000.0, 165_000.0, 45_000.0, 33_000.0,
                65_000.0, 38_000.0, 2, 2, 2, 2,
                20_000.0, 18_000.0, 16_000.0, 12_000.0,
                35_000.0, 30_000.0, 2, 0, 2, 0, 8, 0.7,
                2, 0.5, 2, 0.6, 0.4, "order daily ok",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return atomic_db


def test_history_multiframe_daily_falls_back_to_atomic(monkeypatch, tmp_path):
    _init_atomic_db(tmp_path)
    _, database, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()

    monkeypatch.setattr("backend.app.routers.analysis.MOCK_DATA_DATE", None)
    monkeypatch.setattr("backend.app.routers.analysis.TradeCalendar.is_trade_day", lambda date_str: date_str in {"2026-04-09", "2026-04-10"})

    resp = analysis.get_history_multiframe(
        "sh603629",
        granularity="1d",
        start_date="2026-04-09",
        end_date="2026-04-10",
        include_today_preview=False,
    )

    assert resp.code == 200
    assert [item["trade_date"] for item in resp.data["items"]] == ["2026-04-09", "2026-04-10"]
    assert all(item["source"] == "l2_history" for item in resp.data["items"])
    assert resp.data["items"][-1]["l2_main_buy"] == 740_000.0
    assert resp.data["items"][-1]["quality_info"] == "daily trade ok；order daily ok"


def test_history_multiframe_30m_falls_back_to_atomic(monkeypatch, tmp_path):
    _init_atomic_db(tmp_path)
    _, database, analysis = _reload_runtime_modules(monkeypatch, tmp_path)
    database.init_db()

    monkeypatch.setattr("backend.app.routers.analysis.MOCK_DATA_DATE", None)
    monkeypatch.setattr("backend.app.routers.analysis.TradeCalendar.is_trade_day", lambda date_str: date_str == "2026-04-10")

    resp = analysis.get_history_multiframe(
        "sh603629",
        granularity="30m",
        start_date="2026-04-10",
        end_date="2026-04-10",
        include_today_preview=False,
    )

    assert resp.code == 200
    assert resp.data["count"] == 8
    item = resp.data["items"][0]
    assert item["datetime"] == "2026-04-10 09:30:00"
    assert item["source"] == "l2_history"
    assert item["is_finalized"] is True
    assert item["l2_main_buy"] == 740_000.0
    assert item["add_buy_amount"] == 220_000.0
    assert item["l2_oib_delta"] == 38_000.0
    assert item["quality_info"] == "该区间包含缺失 5m，聚合值可能偏小"
    assert any(extra["is_placeholder"] is True for extra in resp.data["items"][1:])
