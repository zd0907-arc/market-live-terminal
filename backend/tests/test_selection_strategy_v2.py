import importlib
import sqlite3
from pathlib import Path

import pandas as pd


def _init_atomic_db(tmp_path: Path) -> Path:
    atomic_db = tmp_path / "atomic_v2.db"
    schema_path = Path(__file__).resolve().parents[1] / "scripts" / "sql" / "atomic_fact_p0_schema.sql"
    conn = sqlite3.connect(str(atomic_db))
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    return atomic_db


def _init_main_db(tmp_path: Path) -> Path:
    main_db = tmp_path / "market_data.db"
    conn = sqlite3.connect(str(main_db))
    try:
        conn.executescript(
            """
            CREATE TABLE stock_universe_meta (
                symbol TEXT,
                name TEXT,
                market_cap REAL,
                as_of_date TEXT,
                source TEXT,
                updated_at TEXT
            );
            CREATE TABLE stock_events (
                event_id TEXT,
                source TEXT,
                source_type TEXT,
                event_subtype TEXT,
                symbol TEXT,
                ts_code TEXT,
                title TEXT,
                content_text TEXT,
                question_text TEXT,
                answer_text TEXT,
                raw_url TEXT,
                pdf_url TEXT,
                published_at TEXT,
                ingested_at TEXT,
                importance INTEGER,
                is_official INTEGER,
                source_event_id TEXT,
                hash_digest TEXT,
                extra_json TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE sentiment_events (
                event_id TEXT,
                source TEXT,
                symbol TEXT,
                event_type TEXT,
                thread_id TEXT,
                parent_id TEXT,
                content TEXT,
                author_name TEXT,
                pub_time TEXT,
                crawl_time TEXT,
                view_count INTEGER,
                reply_count INTEGER,
                like_count INTEGER,
                repost_count INTEGER,
                raw_url TEXT,
                source_event_id TEXT,
                extra_json TEXT
            );
            CREATE TABLE sentiment_daily_scores (
                symbol TEXT,
                trade_date TEXT,
                sample_count INTEGER,
                sentiment_score REAL,
                direction_label TEXT,
                consensus_strength INTEGER,
                emotion_temperature INTEGER,
                risk_tag TEXT,
                summary_text TEXT,
                model_used TEXT,
                created_at TEXT,
                raw_payload TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    return main_db


def _seed_symbol_series(
    atomic_db: Path,
    symbol: str,
    *,
    launch_index: int = -1,
    event_index: int = -1,
    periods: int = 25,
) -> None:
    dates = pd.bdate_range("2026-02-02", periods=periods)
    conn = sqlite3.connect(str(atomic_db))
    try:
        trade_rows = []
        order_rows = []
        close_price = 10.0 if symbol == "sh600001" else 20.0
        for idx, dt in enumerate(dates):
            trade_date = dt.strftime("%Y-%m-%d")
            close_price += 0.08 if symbol == "sh600001" else 0.02
            total_amount = 350_000_000.0 if symbol == "sh600001" else 180_000_000.0
            trade_count = 30_000 + idx * 200
            l2_main_net = 8_000_000.0 if symbol == "sh600001" else 500_000.0
            l2_super_net = 4_000_000.0 if symbol == "sh600001" else 200_000.0
            l2_buy_ratio = 34.0 if symbol == "sh600001" else 28.0
            l2_sell_ratio = 29.0 if symbol == "sh600001" else 30.0
            add_buy_amount = 120_000_000.0 if symbol == "sh600001" else 40_000_000.0
            add_sell_amount = 90_000_000.0 if symbol == "sh600001" else 45_000_000.0
            cancel_buy_amount = 30_000_000.0 if symbol == "sh600001" else 20_000_000.0
            cancel_sell_amount = 18_000_000.0 if symbol == "sh600001" else 22_000_000.0
            buy_support_ratio = 0.62 if symbol == "sh600001" else 0.47
            sell_pressure_ratio = 0.35 if symbol == "sh600001" else 0.46
            return_boost = 0.0
            if launch_index >= 0 and idx == launch_index:
                close_price += 1.9
                total_amount = 950_000_000.0
                trade_count = 72_000
                l2_main_net = 58_000_000.0
                l2_super_net = 22_000_000.0
                l2_buy_ratio = 44.0
                l2_sell_ratio = 31.0
                add_buy_amount = 420_000_000.0
                add_sell_amount = 170_000_000.0
                cancel_buy_amount = 75_000_000.0
                cancel_sell_amount = 40_000_000.0
                buy_support_ratio = 0.78
                sell_pressure_ratio = 0.23
                return_boost = 1.0
            if event_index >= 0 and idx == event_index:
                close_price += 2.8
                total_amount = 1_200_000_000.0
                trade_count = 95_000
                l2_main_net = 45_000_000.0
                l2_super_net = 16_000_000.0
                l2_buy_ratio = 46.0
                l2_sell_ratio = 35.0
                add_buy_amount = 390_000_000.0
                add_sell_amount = 190_000_000.0
                cancel_buy_amount = 82_000_000.0
                cancel_sell_amount = 44_000_000.0
                buy_support_ratio = 0.74
                sell_pressure_ratio = 0.26
                return_boost = 1.0
            trade_rows.append(
                (
                    symbol,
                    trade_date,
                    close_price - 0.25,
                    close_price + 0.35,
                    close_price - 0.45,
                    close_price,
                    total_amount,
                    8_000_000.0 + idx * 10_000.0,
                    trade_count,
                    10,
                    8,
                    3,
                    2,
                    6,
                    4,
                    2,
                    1,
                    45_000_000.0,
                    35_000_000.0,
                    10_000_000.0,
                    12_000_000.0,
                    7_000_000.0,
                    5_000_000.0,
                    48_000_000.0 + return_boost * 10_000_000.0,
                    40_000_000.0,
                    l2_main_net,
                    22_000_000.0,
                    18_000_000.0,
                    l2_super_net,
                    25.0,
                    45.0,
                    13.0,
                    11.0,
                    l2_buy_ratio,
                    l2_sell_ratio,
                    8_000_000.0,
                    180_000.0,
                    12_000_000.0,
                    0.38,
                    l2_main_net * 0.4,
                    l2_main_net * 0.6,
                    l2_main_net * 0.3,
                    l2_main_net * 0.2,
                    31,
                    17,
                    "unit-test",
                    None,
                )
            )
            order_rows.append(
                (
                    symbol,
                    trade_date,
                    add_buy_amount,
                    add_sell_amount,
                    cancel_buy_amount,
                    cancel_sell_amount,
                    12_000_000.0,
                    14_000_000.0,
                    40,
                    30,
                    20,
                    18,
                    7_000_000.0,
                    7_000_000.0,
                    5_000_000.0,
                    4_000_000.0,
                    6_000_000.0,
                    6_000_000.0,
                    24,
                    16,
                    25,
                    15,
                    120,
                    0.55,
                    10,
                    0.6,
                    5,
                    buy_support_ratio,
                    sell_pressure_ratio,
                    None,
                )
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
            trade_rows,
        )
        conn.executemany(
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
            order_rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_screen_candidates_v2_identifies_launch_and_event(monkeypatch, tmp_path):
    atomic_db = _init_atomic_db(tmp_path)
    _seed_symbol_series(atomic_db, "sh600001", launch_index=24, periods=25)
    _seed_symbol_series(atomic_db, "sh600002", event_index=24, periods=25)
    monkeypatch.setenv("SELECTION_V2_ATOMIC_DB_PATH", str(atomic_db))
    import backend.app.services.selection_strategy_v2 as strategy_v2
    importlib.reload(strategy_v2)

    payload = strategy_v2.screen_candidates_v2("2026-03-06", limit=5)
    items = {item["symbol"]: item for item in payload["items"]}

    assert "sh600001" in items
    assert "launch_candidate" in items["sh600001"]["candidate_types"]
    assert items["sh600001"]["quant_score"] > 0
    assert items["sh600001"]["intent_profile"]["intent_label"] in {"launch_attack", "follow_through_attack"}
    assert "sh600002" in items
    assert "event_spike_candidate" in items["sh600002"]["candidate_types"]


def test_replay_symbol_v2_enters_and_exits_on_distribution(monkeypatch, tmp_path):
    atomic_db = _init_atomic_db(tmp_path)
    _seed_symbol_series(atomic_db, "sh600001", launch_index=20, periods=30)
    conn = sqlite3.connect(str(atomic_db))
    try:
        conn.execute(
            """
            UPDATE atomic_trade_daily
            SET close = close * 0.94,
                l2_main_net_amount = -38000000,
                l2_super_net_amount = -16000000,
                l2_buy_ratio = 28,
                l2_sell_ratio = 42
            WHERE symbol = 'sh600001' AND trade_date = '2026-03-09'
            """
        )
        conn.execute(
            """
            UPDATE atomic_order_daily
            SET add_sell_amount = 320000000,
                cancel_buy_amount = 180000000,
                buy_support_ratio = 0.22,
                sell_pressure_ratio = 0.71
            WHERE symbol = 'sh600001' AND trade_date = '2026-03-09'
            """
        )
        conn.execute(
            """
            UPDATE atomic_trade_daily
            SET close = close * 0.95,
                l2_main_net_amount = -42000000,
                l2_super_net_amount = -18000000,
                l2_buy_ratio = 27,
                l2_sell_ratio = 43
            WHERE symbol = 'sh600001' AND trade_date = '2026-03-10'
            """
        )
        conn.execute(
            """
            UPDATE atomic_order_daily
            SET add_sell_amount = 340000000,
                cancel_buy_amount = 200000000,
                buy_support_ratio = 0.18,
                sell_pressure_ratio = 0.76
            WHERE symbol = 'sh600001' AND trade_date = '2026-03-10'
            """
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setenv("SELECTION_V2_ATOMIC_DB_PATH", str(atomic_db))
    import backend.app.services.selection_strategy_v2 as strategy_v2
    importlib.reload(strategy_v2)

    payload = strategy_v2.replay_symbol_v2("sh600001", "2026-03-02", "2026-03-10")
    assert payload["daily_states"]
    assert payload["trades"]
    trade = payload["trades"][0]
    assert trade["entry_date"] >= "2026-03-03"
    assert trade["exit_reason"] in {"distribution_warning_confirmed", "panic_distribution_exit", "stop_loss"}
    day_map = {item["date"]: item for item in payload["daily_states"]}
    assert day_map["2026-03-09"]["distribution_score"] > 0
    assert day_map["2026-03-09"]["intent_label"] in {"panic_distribution", "distribution", "sharp_drop_unclear"}


def test_replay_trade_date_v2_returns_candidate_trade(monkeypatch, tmp_path):
    atomic_db = _init_atomic_db(tmp_path)
    _seed_symbol_series(atomic_db, "sh600001", launch_index=20, periods=30)
    monkeypatch.setenv("SELECTION_V2_ATOMIC_DB_PATH", str(atomic_db))
    import backend.app.services.selection_strategy_v2 as strategy_v2
    importlib.reload(strategy_v2)

    payload = strategy_v2.replay_trade_date_v2(
        "2026-03-02",
        limit=5,
        replay_end_date="2026-03-20",
    )
    assert payload["candidates"]
    first = payload["candidates"][0]
    assert first["symbol"] == "sh600001"
    assert first["trade"] is not None
    assert first["trade"]["signal_date"] == "2026-03-02"
    assert "intent_profile" in first


def test_backtest_range_v2_summarizes_trades(monkeypatch, tmp_path):
    atomic_db = _init_atomic_db(tmp_path)
    _seed_symbol_series(atomic_db, "sh600001", launch_index=20, periods=30)
    _seed_symbol_series(atomic_db, "sh600002", event_index=21, periods=30)
    monkeypatch.setenv("SELECTION_V2_ATOMIC_DB_PATH", str(atomic_db))
    import backend.app.services.selection_strategy_v2 as strategy_v2
    importlib.reload(strategy_v2)

    payload = strategy_v2.backtest_range_v2(
        "2026-03-02",
        "2026-03-06",
        limit=5,
        replay_end_date="2026-03-20",
    )
    assert payload["summary"]["trade_count"] >= 1
    assert "compounded_return_pct" in payload["summary"]
    assert "max_drawdown_pct" in payload["summary"]
    assert "equity_curve" in payload
    assert payload["daily_results"]
    assert payload["trades"]


def test_backtest_range_v2_respects_position_limits(monkeypatch, tmp_path):
    atomic_db = _init_atomic_db(tmp_path)
    _seed_symbol_series(atomic_db, "sh600001", launch_index=20, periods=30)
    _seed_symbol_series(atomic_db, "sh600002", event_index=21, periods=30)
    monkeypatch.setenv("SELECTION_V2_ATOMIC_DB_PATH", str(atomic_db))
    import backend.app.services.selection_strategy_v2 as strategy_v2
    importlib.reload(strategy_v2)

    payload = strategy_v2.backtest_range_v2(
        "2026-03-02",
        "2026-03-06",
        limit=5,
        replay_end_date="2026-03-20",
        params=strategy_v2.SelectionV2Params(
            max_open_positions=1,
            max_new_positions_per_day=1,
        ),
    )
    assert payload["summary"]["trade_count"] == 1
    assert any(day["skipped_position_limit"] >= 1 for day in payload["daily_results"])


def test_build_research_card_v2_uses_historical_company_and_event_context(monkeypatch, tmp_path):
    atomic_db = _init_atomic_db(tmp_path)
    main_db = _init_main_db(tmp_path)
    _seed_symbol_series(atomic_db, "sh600001", launch_index=20, periods=30)
    main_conn = sqlite3.connect(str(main_db))
    try:
        main_conn.execute(
            """
            INSERT INTO stock_universe_meta (symbol, name, market_cap, as_of_date, source, updated_at)
            VALUES ('sh600001', '测试股份', 12500000000, '2026-03-01', 'unit-test', '2026-03-01 20:00:00')
            """
        )
        main_conn.execute(
            """
            INSERT INTO stock_events (
                event_id, source, source_type, event_subtype, symbol, title, content_text,
                published_at, importance, is_official
            ) VALUES (
                'evt-1', 'exchange', 'announcement', 'contract', 'sh600001',
                '签订算力租赁合同', '公司披露算力租赁订单落地，预计提升利润弹性。',
                '2026-03-02 18:00:00', 5, 1
            )
            """
        )
        main_conn.execute(
            """
            INSERT INTO stock_events (
                event_id, source, source_type, event_subtype, symbol, title, content_text,
                published_at, importance, is_official
            ) VALUES (
                'evt-2', 'exchange', 'announcement', 'contract', 'sh600001',
                '未来事件', '这个事件不应出现在 2026-03-02 的研究卡片中。',
                '2026-03-03 09:00:00', 5, 1
            )
            """
        )
        main_conn.execute(
            """
            INSERT INTO sentiment_events (
                event_id, source, symbol, event_type, content, pub_time, reply_count, like_count
            ) VALUES (
                'sent-1', 'guba', 'sh600001', 'post',
                '市场讨论公司算力业务和利润释放节奏。',
                '2026-03-02 15:30:00', 12, 8
            )
            """
        )
        main_conn.execute(
            """
            INSERT INTO sentiment_daily_scores (
                symbol, trade_date, sample_count, sentiment_score, direction_label,
                consensus_strength, emotion_temperature, risk_tag, summary_text, model_used, created_at, raw_payload
            ) VALUES (
                'sh600001', '2026-03-02', 18, 52, '偏多',
                68, 72, '叙事强化', '市场开始把公司从旧业务切换到算力租赁叙事。', 'unit-test', '2026-03-02 22:00:00', '{}'
            )
            """
        )
        main_conn.commit()
    finally:
        main_conn.close()

    monkeypatch.setenv("SELECTION_V2_ATOMIC_DB_PATH", str(atomic_db))
    monkeypatch.setenv("SELECTION_V2_MAIN_DB_PATH", str(main_db))
    import backend.app.services.selection_strategy_v2 as strategy_v2
    importlib.reload(strategy_v2)

    day_payload = strategy_v2.replay_trade_date_v2(
        "2026-03-02",
        limit=5,
        replay_end_date="2026-03-20",
    )
    first = day_payload["candidates"][0]
    research = first["research"]

    assert first["symbol"] == "sh600001"
    assert research["name"] == "测试股份"
    assert research["market_cap"] == 12500000000.0
    assert research["event_strength"] == "strong"
    assert research["event_duration"] == "medium_term"
    assert research["fundamental_funding_consistency"] == "confirmed"
    assert research["sentiment_snapshot"]["available"] is True
    assert research["sentiment_snapshot"]["trade_date"] == "2026-03-02"
    assert "算力" in research["theme_tags"]
    assert len(research["event_timeline"]) == 2
    assert all("未来事件" not in item["title"] for item in research["event_timeline"])
