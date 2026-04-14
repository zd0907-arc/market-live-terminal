import json
import importlib
import sqlite3
from pathlib import Path

from backend.app.db.database import init_db
import backend.app.db.database as database_module
import backend.app.db.selection_db as selection_db_module
from backend.app.db.l2_history_db import replace_history_5m_l2_rows, replace_history_daily_l2_row, replace_stock_universe_meta
from backend.app.routers.selection import selection_backtest_detail, selection_backtests_run, selection_candidates, selection_health, selection_profile
from backend.app.services.selection_research import FEATURE_VERSION, get_backtest_run, refresh_selection_research
from backend.app.models.schemas import SelectionBacktestRunRequest


def _init_atomic_selection_db(tmp_path: Path) -> Path:
    atomic_db = tmp_path / 'atomic_mainboard.db'
    schema_path = Path(__file__).resolve().parents[1] / 'scripts' / 'sql' / 'atomic_fact_p0_schema.sql'
    conn = sqlite3.connect(str(atomic_db))
    try:
        conn.executescript(schema_path.read_text(encoding='utf-8'))
        conn.execute(
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
            (
                'sz000833', '2025-03-27', 15.0, 15.6, 14.9, 15.5, 200000000.0, 5000000.0, 22,
                1, 1, 1, 1, 1, 1, 1, 1,
                45000000.0, 22000000.0, 23000000.0,
                15000000.0, 6000000.0, 9000000.0,
                52000000.0, 18000000.0, 34000000.0,
                21000000.0, 7000000.0, 14000000.0,
                33.0, 35.0, 22.0, 11.0, 26.0, 9.0,
                5000000.0, 100000.0, 7000000.0, 0.5,
                12000000.0, 22000000.0, 8000000.0, 9000000.0,
                6, 1, 'unit-test', None,
            ),
        )
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
                    'sz000833', '2025-03-27', '2025-03-27 14:30:00', 15.0, 15.2, 14.9, 15.1,
                    20000000.0, 1500000.0, 10,
                    1, 1, 1, 1, 1, 1, 1, 1,
                    4500000.0, 2000000.0, 2500000.0,
                    1500000.0, 600000.0, 900000.0,
                    5200000.0, 1800000.0, 3400000.0,
                    2100000.0, 700000.0, 1400000.0,
                    1000000.0, 200000.0, 2500000.0, 0.5, 'unit-test', None,
                ),
                (
                    'sz000833', '2025-03-27', '2025-03-27 14:35:00', 15.1, 15.5, 15.0, 15.5,
                    28000000.0, 1800000.0, 12,
                    1, 1, 1, 1, 1, 1, 1, 1,
                    6500000.0, 2400000.0, 4100000.0,
                    2000000.0, 700000.0, 1300000.0,
                    7300000.0, 2200000.0, 5100000.0,
                    2500000.0, 800000.0, 1700000.0,
                    1200000.0, 220000.0, 3200000.0, 0.6, 'unit-test', None,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO atomic_order_5m (
                symbol, trade_date, bucket_start,
                add_buy_amount, add_sell_amount, cancel_buy_amount, cancel_sell_amount,
                cvd_delta_amount, oib_delta_amount, add_buy_count, add_sell_count, cancel_buy_count, cancel_sell_count,
                add_buy_volume, add_sell_volume, cancel_buy_volume, cancel_sell_volume, order_event_count,
                buy_add_cancel_net_amount, sell_add_cancel_net_amount, source_type, quality_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    'sz000833', '2025-03-27', '2025-03-27 14:30:00',
                    5000000.0, 1200000.0, 400000.0, 300000.0,
                    2500000.0, 5100000.0, 1, 1, 1, 1, 1000.0, 900.0, 100.0, 80.0, 4,
                    4600000.0, 900000.0, 'unit-test', None,
                ),
                (
                    'sz000833', '2025-03-27', '2025-03-27 14:35:00',
                    7000000.0, 1000000.0, 300000.0, 400000.0,
                    4200000.0, 6300000.0, 1, 1, 1, 1, 1100.0, 920.0, 90.0, 70.0, 4,
                    6700000.0, 600000.0, 'unit-test', None,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return atomic_db


def _seed_local_history(db_path: Path, symbol: str, start_price: float, trend_bias: float, inflow_bias: float, days: int = 90):
    conn = sqlite3.connect(str(db_path))
    try:
        rows = []
        price = start_price
        for idx in range(days):
            trade_date = f"2025-01-{idx + 1:02d}" if idx < 31 else f"2025-02-{idx - 30:02d}" if idx < 59 else f"2025-03-{idx - 58:02d}"
            if idx > 75:
                price += trend_bias * 1.8
            else:
                price += trend_bias
            net_inflow = inflow_bias + (idx * 50000.0)
            if idx > 75:
                net_inflow += 4_000_000.0
            main_buy = 18_000_000.0 + idx * 50_000.0
            main_sell = max(4_000_000.0, main_buy - net_inflow)
            activity_ratio = 28.0 + (idx % 7)
            rows.append((symbol, trade_date, net_inflow, main_buy, main_sell, price, 0.0, activity_ratio, 'fixed_200k_1m_v1'))
        conn.executemany(
            "INSERT OR REPLACE INTO local_history (symbol, date, net_inflow, main_buy_amount, main_sell_amount, close, change_pct, activity_ratio, config_signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _seed_sentiment_events(db_path: Path, symbol: str, date_text: str, count: int):
    conn = sqlite3.connect(str(db_path))
    try:
        rows = [
            (
                f"{symbol}-{date_text}-{idx}",
                'guba',
                symbol,
                'post',
                None,
                None,
                f'{symbol} event {idx}',
                'tester',
                f'{date_text} 15:00:00',
                f'{date_text} 16:00:00',
                10,
                1,
                1,
                0,
                None,
                f'{symbol}-{date_text}-{idx}',
                None,
            )
            for idx in range(count)
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO sentiment_events (event_id, source, symbol, event_type, thread_id, parent_id, content, author_name, pub_time, crawl_time, view_count, reply_count, like_count, repost_count, raw_url, source_event_id, extra_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_selection_refresh_and_candidate_routes(monkeypatch, tmp_path):
    db_path = tmp_path / 'market_data.db'
    user_db_path = tmp_path / 'user_data.db'
    selection_db_path = tmp_path / 'selection_research.db'
    monkeypatch.setenv('DB_PATH', str(db_path))
    monkeypatch.setenv('USER_DB_PATH', str(user_db_path))
    monkeypatch.setenv('SELECTION_DB_PATH', str(selection_db_path))
    database_module.DB_FILE = str(db_path)
    database_module.USER_DB_FILE = str(user_db_path)
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)
    init_db()

    _seed_local_history(db_path, 'sz000833', 10.0, 0.08, 2_500_000.0)
    _seed_local_history(db_path, 'sh603629', 8.0, 0.02, 500_000.0)
    _seed_sentiment_events(db_path, 'sz000833', '2025-03-27', 15)

    replace_history_daily_l2_row(
        'sz000833', '2025-03-27',
        ('sz000833', '2025-03-27', 15.0, 15.6, 14.9, 15.5, 200000000.0,
         45000000.0, 22000000.0, 23000000.0, 15000000.0, 6000000.0, 9000000.0,
         52000000.0, 18000000.0, 34000000.0, 21000000.0, 7000000.0, 14000000.0,
         33.0, 10.0, 35.0, 12.0, 22.0, 11.0, 26.0, 9.0, None)
    )
    replace_history_5m_l2_rows(
        'sz000833', '2025-03-27',
        [
            ('sz000833', '2025-03-27 14:30:00', '2025-03-27', 15.0, 15.2, 14.9, 15.1, 20000000.0, 1500000.0,
             4500000.0, 2000000.0, 1500000.0, 600000.0, 5200000.0, 1800000.0, 2100000.0, 700000.0,
             5000000.0, 1200000.0, 400000.0, 300000.0, 2500000.0, 5100000.0, None),
            ('sz000833', '2025-03-27 14:35:00', '2025-03-27', 15.1, 15.5, 15.0, 15.5, 28000000.0, 1800000.0,
             6500000.0, 2400000.0, 2000000.0, 700000.0, 7300000.0, 2200000.0, 2500000.0, 800000.0,
             7000000.0, 1000000.0, 300000.0, 400000.0, 4200000.0, 6300000.0, None),
        ],
    )
    replace_stock_universe_meta([('sz000833', '粤桂股份', 7_800_000_000.0), ('sh603629', '利通电子', 6_600_000_000.0)], '2025-03-27', 'unit-test')

    result = refresh_selection_research(start_date='2025-01-15', end_date='2025-03-27')
    assert result.feature_rows > 0
    assert result.signal_rows > 0

    health = selection_health()
    assert health.code == 200
    assert health.data['feature_version'] == FEATURE_VERSION

    candidates = selection_candidates(date='2025-03-27', strategy='breakout', limit=20)
    assert candidates.code == 200
    assert candidates.data['trade_date'] == '2025-03-27'
    assert isinstance(candidates.data['items'], list)
    assert any(item['symbol'] == 'sz000833' for item in candidates.data['items'])

    profile = selection_profile('sz000833', date='2025-03-27')
    assert profile.code == 200
    assert profile.data['symbol'] == 'sz000833'
    assert len(profile.data['series']) > 0


def test_selection_backtest_run_and_detail(monkeypatch, tmp_path):
    db_path = tmp_path / 'market_data.db'
    user_db_path = tmp_path / 'user_data.db'
    selection_db_path = tmp_path / 'selection_research.db'
    monkeypatch.setenv('DB_PATH', str(db_path))
    monkeypatch.setenv('USER_DB_PATH', str(user_db_path))
    monkeypatch.setenv('SELECTION_DB_PATH', str(selection_db_path))
    database_module.DB_FILE = str(db_path)
    database_module.USER_DB_FILE = str(user_db_path)
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)
    init_db()

    _seed_local_history(db_path, 'sz000833', 10.0, 0.07, 2_800_000.0)
    _seed_local_history(db_path, 'sz300017', 11.0, 0.06, 2_000_000.0)
    _seed_sentiment_events(db_path, 'sz000833', '2025-03-27', 8)
    _seed_sentiment_events(db_path, 'sz300017', '2025-03-27', 5)

    request = SelectionBacktestRunRequest(
        strategy_name='stealth',
        start_date='2025-02-10',
        end_date='2025-03-27',
        holding_days_set=[5, 10],
        max_positions_per_day=5,
    )
    resp = selection_backtests_run(request)
    assert resp.code == 200
    assert resp.data['run']['strategy_name'] == 'stealth'
    assert len(resp.data['summaries']) == 2

    run_id = resp.data['run']['id']
    detail = selection_backtest_detail(run_id)
    assert detail.code == 200
    assert detail.data['run']['id'] == run_id
    assert all(item['holding_days'] in {5, 10} for item in detail.data['summaries'])


def test_selection_profile_falls_back_to_latest_available_feature_date(monkeypatch, tmp_path):
    db_path = tmp_path / 'market_data.db'
    user_db_path = tmp_path / 'user_data.db'
    selection_db_path = tmp_path / 'selection_research.db'
    monkeypatch.setenv('DB_PATH', str(db_path))
    monkeypatch.setenv('USER_DB_PATH', str(user_db_path))
    monkeypatch.setenv('SELECTION_DB_PATH', str(selection_db_path))
    database_module.DB_FILE = str(db_path)
    database_module.USER_DB_FILE = str(user_db_path)
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)
    init_db()

    _seed_local_history(db_path, 'sh603629', 8.0, 0.08, 1_500_000.0)
    replace_stock_universe_meta([('sh603629', '利通电子', 6_600_000_000.0)], '2025-03-27', 'unit-test')
    refresh_selection_research(start_date='2025-01-15', end_date='2025-03-27')

    profile = selection_profile('sh603629', date='2025-03-31')
    assert profile.code == 200
    assert profile.data['symbol'] == 'sh603629'
    assert profile.data['requested_trade_date'] == '2025-03-31'
    assert profile.data['trade_date'] == '2025-03-27'
    assert profile.data['profile_date_fallback_used'] is True


def test_selection_research_loaders_fall_back_to_atomic(monkeypatch, tmp_path):
    db_path = tmp_path / 'market_data.db'
    user_db_path = tmp_path / 'user_data.db'
    atomic_db_path = _init_atomic_selection_db(tmp_path)
    monkeypatch.setenv('DB_PATH', str(db_path))
    monkeypatch.setenv('USER_DB_PATH', str(user_db_path))
    monkeypatch.setenv('ATOMIC_DB_PATH', str(atomic_db_path))

    import backend.app.services.selection_research as selection_research_module
    importlib.reload(selection_research_module)

    conn = sqlite3.connect(str(db_path))
    try:
        daily_df = selection_research_module._load_l2_daily(conn, '2025-03-27', '2025-03-27')
        order_df = selection_research_module._load_l2_5m_daily(conn, '2025-03-27', '2025-03-27')
    finally:
        conn.close()

    assert len(daily_df) == 1
    assert float(daily_df.iloc[0]['l2_main_net']) == 34000000.0
    assert len(order_df) == 1
    assert float(order_df.iloc[0]['l2_add_buy']) == 12000000.0
    assert int(order_df.iloc[0]['event_points']) == 2
