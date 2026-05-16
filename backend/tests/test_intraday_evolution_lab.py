from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.app.services.intraday_evolution_lab import (
    ASharePPOTradingGym,
    IntradayStrategySpec,
    MarketReplayEnv,
    RLTradingEnv,
    RLTradingEnvConfig,
    RLTrainerConfig,
    RLPPOTrainerConfig,
    TrendPortfolioPPOGym,
    TrendPortfolioPPOTrainerConfig,
    load_intraday_panel,
    load_trend_daily_panel,
    run_evolution_arena,
    EvolutionConfig,
    train_rl_ppo_policy,
    train_rl_policy_search,
    train_trend_portfolio_ppo_policy,
)


def _init_db(path: Path) -> Path:
    db = path / "intraday_lab.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE atomic_trade_daily (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                PRIMARY KEY(symbol, trade_date)
            );
            CREATE TABLE atomic_trade_5m (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                bucket_start TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                total_volume REAL NULL,
                trade_count INTEGER NULL,
                l2_main_net_amount REAL NOT NULL,
                l2_super_net_amount REAL NOT NULL,
                l1_main_net_amount REAL NOT NULL,
                l1_super_net_amount REAL NOT NULL,
                PRIMARY KEY(symbol, bucket_start)
            );
            CREATE TABLE atomic_order_5m (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                bucket_start TEXT NOT NULL,
                add_buy_amount REAL NOT NULL,
                add_sell_amount REAL NOT NULL,
                cancel_buy_amount REAL NOT NULL,
                cancel_sell_amount REAL NOT NULL,
                cvd_delta_amount REAL NOT NULL,
                oib_delta_amount REAL NOT NULL,
                order_event_count INTEGER NULL,
                PRIMARY KEY(symbol, bucket_start)
            );
            CREATE TABLE atomic_book_state_5m (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                bucket_start TEXT NOT NULL,
                end_bid_resting_amount REAL NULL,
                end_ask_resting_amount REAL NULL,
                top5_bid_amount REAL NULL,
                top5_ask_amount REAL NULL,
                book_imbalance_ratio REAL NULL,
                book_depth_ratio REAL NULL,
                book_state_label TEXT NULL,
                PRIMARY KEY(symbol, bucket_start)
            );
            CREATE TABLE atomic_limit_state_5m (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                bucket_start TEXT NOT NULL,
                risk_flag_type TEXT NOT NULL,
                prev_close REAL NULL,
                up_limit_price REAL NULL,
                down_limit_price REAL NULL,
                touch_limit_up INTEGER NOT NULL DEFAULT 0,
                touch_limit_down INTEGER NOT NULL DEFAULT 0,
                is_limit_up_close_5m INTEGER NOT NULL DEFAULT 0,
                is_limit_down_close_5m INTEGER NOT NULL DEFAULT 0,
                near_limit_up_ratio REAL NULL,
                near_limit_down_ratio REAL NULL,
                state_label_5m TEXT NOT NULL,
                PRIMARY KEY(symbol, bucket_start)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _seed_day(conn: sqlite3.Connection, symbol: str, trade_date: str, *, base: float, signal_bucket_idx: int) -> None:
    buckets = ["09:30:00", "09:35:00", "09:40:00", "09:45:00", "09:50:00", "09:55:00", "10:00:00"]
    rows_trade = []
    rows_order = []
    rows_book = []
    rows_limit = []
    price = base
    total_day_amount = 0.0
    high_day = base
    low_day = base
    for idx, time_text in enumerate(buckets):
        bucket = f"{trade_date} {time_text}"
        if idx >= signal_bucket_idx:
            price *= 1.012
            amount = 20_000_000.0
            l2_main = 900_000.0
            l2_super = 300_000.0
            oib = 500_000.0
            cvd = 450_000.0
            book = 0.25
        else:
            price *= 0.999
            amount = 6_000_000.0
            l2_main = -100_000.0
            l2_super = -50_000.0
            oib = -50_000.0
            cvd = -60_000.0
            book = -0.1
        open_price = price
        close = price * 1.004
        high = close * 1.003
        low = open_price * 0.997
        total_day_amount += amount
        high_day = max(high_day, high)
        low_day = min(low_day, low)
        rows_trade.append((symbol, trade_date, bucket, open_price, high, low, close, amount, 200_000.0, 200, l2_main, l2_super, l2_main * 0.6, l2_super * 0.6))
        rows_order.append((symbol, trade_date, bucket, amount * 0.4, amount * 0.2, amount * 0.1, amount * 0.08, cvd, oib, 100))
        rows_book.append((symbol, trade_date, bucket, amount * 0.8, amount * 0.5, amount, amount * 0.7, book, 1.2, "bid_dominant"))
        rows_limit.append((symbol, trade_date, bucket, "normal", base, base * 1.1, base * 0.9, 0, 0, 0, 0, 0.0, 0.0, "normal"))
    conn.execute(
        "INSERT INTO atomic_trade_daily(symbol, trade_date, open, high, low, close, total_amount) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (symbol, trade_date, base, high_day, low_day, price, total_day_amount),
    )
    conn.executemany(
        """
        INSERT INTO atomic_trade_5m (
            symbol, trade_date, bucket_start, open, high, low, close, total_amount,
            total_volume, trade_count, l2_main_net_amount, l2_super_net_amount,
            l1_main_net_amount, l1_super_net_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_trade,
    )
    conn.executemany(
        """
        INSERT INTO atomic_order_5m (
            symbol, trade_date, bucket_start, add_buy_amount, add_sell_amount,
            cancel_buy_amount, cancel_sell_amount, cvd_delta_amount, oib_delta_amount, order_event_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_order,
    )
    conn.executemany(
        """
        INSERT INTO atomic_book_state_5m (
            symbol, trade_date, bucket_start, end_bid_resting_amount, end_ask_resting_amount,
            top5_bid_amount, top5_ask_amount, book_imbalance_ratio, book_depth_ratio, book_state_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_book,
    )
    conn.executemany(
        """
        INSERT INTO atomic_limit_state_5m (
            symbol, trade_date, bucket_start, risk_flag_type, prev_close, up_limit_price, down_limit_price,
            touch_limit_up, touch_limit_down, is_limit_up_close_5m, is_limit_down_close_5m,
            near_limit_up_ratio, near_limit_down_ratio, state_label_5m
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_limit,
    )


def test_universe_uses_prior_day_amount_not_current_day_amount(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        _seed_day(conn, "sh600001", "2026-03-02", base=10.0, signal_bucket_idx=2)
        _seed_day(conn, "sh600002", "2026-03-02", base=10.0, signal_bucket_idx=2)
        conn.execute(
            "UPDATE atomic_trade_daily SET total_amount = ? WHERE symbol = ? AND trade_date = ?",
            (999_000_000.0, "sh600001", "2026-03-02"),
        )
        conn.execute(
            "UPDATE atomic_trade_daily SET total_amount = ? WHERE symbol = ? AND trade_date = ?",
            (1_000_000.0, "sh600002", "2026-03-02"),
        )
        _seed_day(conn, "sh600001", "2026-03-03", base=10.2, signal_bucket_idx=2)
        _seed_day(conn, "sh600002", "2026-03-03", base=10.2, signal_bucket_idx=2)
        conn.execute(
            "UPDATE atomic_trade_daily SET total_amount = ? WHERE symbol = ? AND trade_date = ?",
            (1_000_000.0, "sh600001", "2026-03-03"),
        )
        conn.execute(
            "UPDATE atomic_trade_daily SET total_amount = ? WHERE symbol = ? AND trade_date = ?",
            (999_000_000.0, "sh600002", "2026-03-03"),
        )
        conn.commit()
    finally:
        conn.close()

    panel = load_intraday_panel("2026-03-03", "2026-03-03", db_path=str(db), max_symbols_per_day=1)

    assert sorted(panel["symbol"].unique().tolist()) == ["sh600001"]


def test_universe_is_filtered_per_trade_date(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        _seed_day(conn, "sh600001", "2026-03-02", base=10.0, signal_bucket_idx=2)
        _seed_day(conn, "sh600002", "2026-03-02", base=10.0, signal_bucket_idx=2)
        conn.execute(
            "UPDATE atomic_trade_daily SET total_amount = ? WHERE symbol = ? AND trade_date = ?",
            (999_000_000.0, "sh600001", "2026-03-02"),
        )
        conn.execute(
            "UPDATE atomic_trade_daily SET total_amount = ? WHERE symbol = ? AND trade_date = ?",
            (1_000_000.0, "sh600002", "2026-03-02"),
        )
        _seed_day(conn, "sh600001", "2026-03-03", base=10.2, signal_bucket_idx=2)
        _seed_day(conn, "sh600002", "2026-03-03", base=10.2, signal_bucket_idx=2)
        conn.execute(
            "UPDATE atomic_trade_daily SET total_amount = ? WHERE symbol = ? AND trade_date = ?",
            (1_000_000.0, "sh600001", "2026-03-03"),
        )
        conn.execute(
            "UPDATE atomic_trade_daily SET total_amount = ? WHERE symbol = ? AND trade_date = ?",
            (999_000_000.0, "sh600002", "2026-03-03"),
        )
        _seed_day(conn, "sh600001", "2026-03-04", base=10.4, signal_bucket_idx=2)
        _seed_day(conn, "sh600002", "2026-03-04", base=10.4, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    panel = load_intraday_panel("2026-03-03", "2026-03-04", db_path=str(db), max_symbols_per_day=1)

    by_date = {date: sorted(group["symbol"].unique().tolist()) for date, group in panel.groupby("trade_date")}
    assert by_date == {"2026-03-03": ["sh600001"], "2026-03-04": ["sh600002"]}


def test_market_replay_uses_next_bucket_entry_and_t1_sell(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        _seed_day(conn, "sh600001", "2026-03-02", base=10.0, signal_bucket_idx=2)
        _seed_day(conn, "sh600001", "2026-03-03", base=10.8, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    panel = load_intraday_panel("2026-03-02", "2026-03-03", db_path=str(db), symbols=["sh600001"])
    spec = IntradayStrategySpec(
        name="unit",
        min_bucket_amount=10_000_000,
        min_cum_amount=20_000_000,
        min_l2_main_ratio=0.01,
        min_l2_super_ratio=0.0,
        min_oib_ratio=0.0,
        min_cvd_ratio=0.0,
        min_book_imbalance=0.0,
        max_new_positions_per_day=1,
        max_positions=1,
        take_profit_pct=0.5,
    )
    payload = MarketReplayEnv(panel, budget=100_000).backtest(spec)

    assert payload["summary"]["trade_count"] >= 1
    first_trade = payload["trades"][0]
    assert first_trade["signal_bucket"] < first_trade["entry_bucket"]
    assert first_trade["exit_date"] > first_trade["entry_date"]
    assert payload["equity_curve"][-1]["open_positions"] == 0
    assert payload["summary"]["final_equity"] > 0


def test_rl_env_simulates_cash_positions_add_reduce_and_t1(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        _seed_day(conn, "sh600001", "2026-03-02", base=10.0, signal_bucket_idx=2)
        _seed_day(conn, "sz000001", "2026-03-02", base=20.0, signal_bucket_idx=2)
        _seed_day(conn, "sh600001", "2026-03-03", base=10.8, signal_bucket_idx=2)
        _seed_day(conn, "sz000001", "2026-03-03", base=20.8, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    panel = load_intraday_panel("2026-03-02", "2026-03-03", db_path=str(db), symbols=["sh600001", "sz000001"])
    env = RLTradingEnv(
        panel,
        config=RLTradingEnvConfig(
            budget=1_000_000,
            max_positions=4,
            max_position_pct=0.6,
            max_total_exposure_pct=1.0,
            min_order_cash=1_000,
        ),
    )
    obs = env.reset()
    assert obs["cash"] == 1_000_000

    _, _, _, info1 = env.step(
        [
            {"type": "buy", "symbol": "sh600001", "cash_amount": 300_000},
            {"type": "buy", "symbol": "sz000001", "cash_amount": 200_000},
        ]
    )
    assert info1["cash"] < 501_000
    assert env.actions_log[0]["decision_bucket"] < env.actions_log[0]["bucket_start"]
    assert set(env.positions.keys()) == {"sh600001", "sz000001"}

    _, _, _, info2 = env.step({"type": "sell", "symbol": "sh600001", "fraction": 0.5})
    assert info2["invalid_actions"] == 1
    assert not env.trades

    for _ in range(6):
        env.step({"type": "hold"})

    _, _, _, info3 = env.step({"type": "sell", "symbol": "sh600001", "fraction": 0.5})
    assert info3["invalid_actions"] == 0
    assert len(env.trades) == 1
    assert "sh600001" in env.positions
    assert env.summary()["final_equity"] > 0


def test_rl_env_terminal_reward_prefers_higher_final_equity_with_drawdown_penalty(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        _seed_day(conn, "sh600001", "2026-03-02", base=10.0, signal_bucket_idx=2)
        _seed_day(conn, "sh600001", "2026-03-03", base=11.0, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    panel = load_intraday_panel("2026-03-02", "2026-03-03", db_path=str(db), symbols=["sh600001"])
    buy_env = RLTradingEnv(panel, config=RLTradingEnvConfig(budget=100_000, max_position_pct=1.0, min_order_cash=1_000))
    hold_env = RLTradingEnv(panel, config=RLTradingEnvConfig(budget=100_000, max_position_pct=1.0, min_order_cash=1_000))
    buy_env.step({"type": "buy", "symbol": "sh600001", "cash_fraction": 1.0})
    hold_env.step({"type": "hold"})

    buy_reward = 0.0
    hold_reward = 0.0
    done = False
    while not done:
        _, reward, done, _ = buy_env.step({"type": "hold"})
        buy_reward += reward
    done = False
    while not done:
        _, reward, done, _ = hold_env.step({"type": "hold"})
        hold_reward += reward

    assert buy_env.summary()["final_equity"] > hold_env.summary()["final_equity"]
    assert buy_reward > hold_reward


def test_rl_policy_search_smoke(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        for day_idx in range(4):
            date = f"2026-03-{day_idx + 2:02d}"
            _seed_day(conn, "sh600001", date, base=10.0 + day_idx * 0.2, signal_bucket_idx=2)
            _seed_day(conn, "sz000001", date, base=20.0 + day_idx * 0.2, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    payload = train_rl_policy_search(
        RLTrainerConfig(
            start_date="2026-03-02",
            end_date="2026-03-05",
            budget=100_000,
            population_size=4,
            generations=2,
            max_symbols_per_day=2,
            max_observation_symbols=2,
        ),
        db_path=str(db),
        symbols=["sh600001", "sz000001"],
    )

    assert payload["mode"] == "rl_policy_search"
    assert len(payload["history"]) == 2
    assert payload["best"]["summary"]["final_equity"] > 0
    assert payload["policy"]["best_weights"]


def test_rl_ppo_policy_smoke(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        for day_idx in range(3):
            date = f"2026-03-{day_idx + 2:02d}"
            _seed_day(conn, "sh600001", date, base=10.0 + day_idx * 0.2, signal_bucket_idx=2)
            _seed_day(conn, "sz000001", date, base=20.0 + day_idx * 0.2, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    payload = train_rl_ppo_policy(
        RLPPOTrainerConfig(
            start_date="2026-03-02",
            end_date="2026-03-04",
            budget=100_000,
            total_timesteps=32,
            n_steps=16,
            batch_size=16,
            n_epochs=1,
            max_symbols_per_day=2,
            max_observation_symbols=2,
        ),
        db_path=str(db),
        symbols=["sh600001", "sz000001"],
        model_out=tmp_path / "ppo_smoke_model.zip",
    )

    assert payload["mode"] == "rl_ppo_target_policy"
    assert payload["summary"]["final_equity"] > 0
    assert payload["model_path"]


def test_ppo_feature_sets_exclude_order_book_when_weak_l2(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        _seed_day(conn, "sh600001", "2026-03-02", base=10.0, signal_bucket_idx=2)
        _seed_day(conn, "sz000001", "2026-03-02", base=20.0, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    panel = load_intraday_panel("2026-03-02", "2026-03-02", db_path=str(db), symbols=["sh600001", "sz000001"])
    weak_env = ASharePPOTradingGym(panel, env_config=RLTradingEnvConfig(max_observation_symbols=2), top_n=2, feature_set="weak_l2")
    full_env = ASharePPOTradingGym(panel, env_config=RLTradingEnvConfig(max_observation_symbols=2), top_n=2, feature_set="full_l2_order_book")

    assert "oib_ratio" not in weak_env.feature_names
    assert "cvd_ratio" not in weak_env.feature_names
    assert "book_imbalance_ratio" not in weak_env.feature_names
    assert "oib_ratio" in full_env.feature_names
    assert full_env.observation_space.shape[0] > weak_env.observation_space.shape[0]


def test_trend_portfolio_env_uses_next_day_execution_and_t1(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        for day_idx in range(3):
            date = f"2026-03-{day_idx + 2:02d}"
            _seed_day(conn, "sh600001", date, base=10.0 + day_idx * 0.5, signal_bucket_idx=2)
            _seed_day(conn, "sz000001", date, base=20.0 + day_idx * 0.4, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    panel = load_trend_daily_panel("2026-03-02", "2026-03-04", db_path=str(db), symbols=["sh600001", "sz000001"])
    env = TrendPortfolioPPOGym(
        panel,
        env_config=RLTradingEnvConfig(budget=100_000, max_positions=2, max_position_pct=0.6, min_order_cash=1_000),
        top_n=2,
        episode_min_days=2,
        episode_max_days=3,
        random_episode=False,
    )
    obs, _ = env.reset(seed=7)
    assert obs.shape[0] == env.observation_space.shape[0]

    obs, _, _, _, info1 = env.step([1.0, 0.0, 0.0])
    assert info1["decision_date"] == "2026-03-02"
    assert info1["trade_date"] == "2026-03-03"
    assert env.env is not None
    assert env.env.actions_log[0]["decision_date"] < env.env.actions_log[0]["trade_date"]
    assert env.env.positions

    held_symbol = next(iter(env.env.positions.keys()))
    ok, _ = env.env._sell_to_weight(held_symbol, "2026-03-03", 0.0, "2026-03-03")
    assert not ok
    assert any(item.get("reason") == "t1_locked" for item in env.env.actions_log)

    _, _, _, _, info2 = env.step([0.0, 0.0, 1.0])
    assert info2["invalid_actions"] == 0
    assert env.env.trades
    assert env.env.trades[0]["exit_date"] > env.env.trades[0]["entry_date"]


def test_trend_portfolio_ppo_policy_smoke(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        for day_idx in range(6):
            date = f"2026-03-{day_idx + 2:02d}"
            _seed_day(conn, "sh600001", date, base=10.0 + day_idx * 0.2, signal_bucket_idx=2)
            _seed_day(conn, "sz000001", date, base=20.0 + day_idx * 0.1, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    payload = train_trend_portfolio_ppo_policy(
        TrendPortfolioPPOTrainerConfig(
            start_date="2026-03-02",
            end_date="2026-03-07",
            budget=100_000,
            total_timesteps=32,
            n_steps=16,
            batch_size=16,
            n_epochs=1,
            max_symbols_per_day=2,
            max_observation_symbols=2,
            episode_min_days=3,
            episode_max_days=5,
        ),
        db_path=str(db),
        symbols=["sh600001", "sz000001"],
        model_out=tmp_path / "trend_ppo_smoke_model.zip",
    )

    assert payload["mode"] == "trend_portfolio_ppo_policy"
    assert payload["summary"]["final_equity"] > 0
    assert payload["model_path"]
    assert payload["feature_names"]


def test_evolution_arena_smoke(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        for day_idx in range(12):
            date = f"2026-03-{day_idx + 2:02d}"
            _seed_day(conn, "sh600001", date, base=10.0 + day_idx * 0.1, signal_bucket_idx=2)
            _seed_day(conn, "sz000001", date, base=15.0 + day_idx * 0.1, signal_bucket_idx=3)
        conn.commit()
    finally:
        conn.close()

    payload = run_evolution_arena(
        EvolutionConfig(
            start_date="2026-03-02",
            end_date="2026-03-13",
            population_size=4,
            generations=1,
            elite_size=2,
            train_days=4,
            validation_days=3,
            test_days=3,
            step_days=2,
            max_symbols_per_day=2,
        ),
        db_path=str(db),
        symbols=["sh600001", "sz000001"],
    )

    assert payload["leaderboard"]
    assert payload["best"]["aggregate"]["fold_count"] >= 1
    assert payload["data"]["rows"] > 0


def test_arena_ranks_by_validation_not_test(tmp_path):
    db = _init_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        for day_idx in range(10):
            date = f"2026-03-{day_idx + 2:02d}"
            _seed_day(conn, "sh600001", date, base=10.0 + day_idx * 0.1, signal_bucket_idx=2)
        conn.commit()
    finally:
        conn.close()

    payload = run_evolution_arena(
        EvolutionConfig(
            start_date="2026-03-02",
            end_date="2026-03-11",
            population_size=3,
            generations=1,
            elite_size=1,
            train_days=3,
            validation_days=3,
            test_days=3,
            step_days=1,
            max_symbols_per_day=1,
        ),
        db_path=str(db),
        symbols=["sh600001"],
    )

    best = payload["best"]["aggregate"]
    assert "mean_validation_return_pct" in best
    assert "mean_test_return_pct" in best
    assert payload["leaderboard"][0]["mean_score"] == best["mean_score"]
