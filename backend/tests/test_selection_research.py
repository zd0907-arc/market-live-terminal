import json
import sqlite3
from pathlib import Path

from backend.app.db.database import init_db
import backend.app.db.database as database_module
import backend.app.db.selection_db as selection_db_module
from backend.app.db.l2_history_db import replace_history_5m_l2_rows, replace_history_daily_l2_row, replace_stock_universe_meta
from backend.app.routers.selection import selection_backtest_detail, selection_backtests_run, selection_candidates, selection_health, selection_profile
from backend.app.services.selection_research import FEATURE_VERSION, get_backtest_run, refresh_selection_research
from backend.app.models.schemas import SelectionBacktestRunRequest


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
