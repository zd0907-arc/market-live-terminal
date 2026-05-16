from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from backend.app.services.aggressive_10cm_strategy import (
    Aggressive10cmParams,
    backtest_range,
    build_trade_plan,
)


def _init_atomic_db(tmp_path: Path) -> Path:
    atomic_db = tmp_path / "atomic_aggressive.db"
    schema_path = Path(__file__).resolve().parents[1] / "scripts" / "sql" / "atomic_fact_p0_schema.sql"
    limit_schema_path = Path(__file__).resolve().parents[1] / "scripts" / "sql" / "limit_state_schema.sql"
    conn = sqlite3.connect(str(atomic_db))
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.executescript(limit_schema_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    return atomic_db


def _seed_symbol(conn: sqlite3.Connection, symbol: str, *, launch_index: int, base_price: float = 10.0) -> None:
    dates = pd.bdate_range("2026-04-01", periods=35)
    trade_rows = []
    order_rows = []
    limit_rows = []
    trade_5m_rows = []
    price = base_price
    previous_close = price
    for idx, dt in enumerate(dates):
        trade_date = dt.strftime("%Y-%m-%d")
        price *= 1.01
        total_amount = 300_000_000.0
        l2_main_net = 9_000_000.0
        l2_super_net = 3_000_000.0
        l2_buy_ratio = 36.0
        l2_sell_ratio = 31.0
        add_buy = 120_000_000.0
        add_sell = 80_000_000.0
        cancel_buy = 35_000_000.0
        cancel_sell = 25_000_000.0
        buy_support = 0.58
        sell_pressure = 0.37
        if idx == launch_index:
            price *= 1.075
            total_amount = 980_000_000.0
            l2_main_net = 68_000_000.0
            l2_super_net = 24_000_000.0
            l2_buy_ratio = 46.0
            l2_sell_ratio = 32.0
            add_buy = 430_000_000.0
            add_sell = 160_000_000.0
            cancel_buy = 60_000_000.0
            cancel_sell = 42_000_000.0
            buy_support = 0.78
            sell_pressure = 0.22
        if idx == launch_index + 1:
            price *= 1.045
            total_amount = 900_000_000.0
            l2_main_net = 42_000_000.0
            l2_super_net = 16_000_000.0
            l2_buy_ratio = 44.0
            l2_sell_ratio = 32.0
            add_buy = 350_000_000.0
            add_sell = 150_000_000.0
            cancel_buy = 50_000_000.0
            cancel_sell = 36_000_000.0
            buy_support = 0.72
            sell_pressure = 0.25
        if idx > launch_index + 4:
            price *= 0.995
            l2_main_net = -8_000_000.0
            l2_super_net = -6_000_000.0
        open_price = previous_close * (1.012 if idx == launch_index + 1 else 1.002)
        high = max(price * 1.02, open_price)
        low = min(price * 0.985, open_price)
        close = price
        trade_rows.append(
            (
                symbol,
                trade_date,
                open_price,
                high,
                low,
                close,
                total_amount,
                10_000_000.0 + idx * 20_000,
                30_000 + idx * 300,
                10,
                8,
                3,
                2,
                6,
                4,
                2,
                1,
                45_000_000.0,
                30_000_000.0,
                15_000_000.0,
                24_000_000.0,
                16_000_000.0,
                8_000_000.0,
                max(l2_main_net, 0) + 80_000_000.0,
                80_000_000.0,
                l2_main_net,
                max(l2_super_net, 0) + 30_000_000.0,
                30_000_000.0,
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
                l2_main_net * 0.5,
                l2_main_net * 0.5,
                l2_main_net * 0.3,
                l2_main_net * 0.2,
                32,
                16,
                "unit-test",
                None,
            )
        )
        order_rows.append(
            (
                symbol,
                trade_date,
                add_buy,
                add_sell,
                cancel_buy,
                cancel_sell,
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
                buy_support,
                sell_pressure,
                None,
            )
        )
        limit_rows.append(
            (
                symbol,
                trade_date,
                "sh_main" if symbol.startswith("sh") else "sz_main",
                "normal",
                previous_close,
                round(previous_close * 1.1, 2),
                round(previous_close * 0.9, 2),
                0.1,
                0.01,
                open_price,
                high,
                low,
                close,
                0,
                0,
                0,
                0,
                0,
                0,
                None,
                None,
                None,
                None,
                0,
                0,
                "normal",
                "unit-test",
                None,
            )
        )
        for slot, minute in enumerate(["09:30:00", "09:35:00", "09:40:00"]):
            bucket = f"{trade_date} {minute}"
            five_open = open_price if slot == 0 else open_price * (1 + 0.002 * slot)
            five_close = five_open * 1.003
            amount = total_amount / 60.0
            trade_5m_rows.append(
                (
                    symbol,
                    trade_date,
                    bucket,
                    five_open,
                    five_close * 1.002,
                    five_open * 0.998,
                    five_close,
                    amount,
                    100_000.0,
                    200,
                    10,
                    8,
                    3,
                    2,
                    6,
                    4,
                    2,
                    1,
                    5_000_000.0,
                    3_000_000.0,
                    2_000_000.0,
                    1_000_000.0,
                    500_000.0,
                    500_000.0,
                    amount * 0.04,
                    amount * 0.02,
                    amount * 0.02,
                    amount * 0.015,
                    amount * 0.008,
                    amount * 0.007,
                    2_000_000.0,
                    100_000.0,
                    2_000_000.0,
                    0.2,
                    "unit-test",
                    None,
                )
            )
        previous_close = close
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
    conn.executemany(
        """
        INSERT INTO atomic_limit_state_daily (
            symbol, trade_date, board_type, risk_flag_type, prev_close, up_limit_price, down_limit_price,
            limit_pct, tick_size, open_price, high_price, low_price, close_price,
            touch_limit_up, touch_limit_down, is_limit_up_close, is_limit_down_close,
            touch_limit_up_count_5m, touch_limit_down_count_5m, first_touch_limit_up_time,
            last_touch_limit_up_time, first_touch_limit_down_time, last_touch_limit_down_time,
            broken_limit_up, broken_limit_down, limit_state_label, source_type, quality_info
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        limit_rows,
    )
    conn.executemany(
        """
        INSERT INTO atomic_trade_5m (
            symbol, trade_date, bucket_start, open, high, low, close, total_amount, total_volume, trade_count,
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
        trade_5m_rows,
    )


def test_build_trade_plan_uses_signal_date_only_and_plans_next_entry(tmp_path):
    atomic_db = _init_atomic_db(tmp_path)
    conn = sqlite3.connect(str(atomic_db))
    try:
        _seed_symbol(conn, "sh600001", launch_index=23)
        _seed_symbol(conn, "sh600002", launch_index=33, base_price=20.0)
        conn.commit()
    finally:
        conn.close()

    payload = build_trade_plan(
        "2026-05-04",
        budget=1_000_000,
        params=Aggressive10cmParams(min_score=45.0, first_15m_price_floor_pct=-1.0, first_15m_main_net_floor=-0.02),
        db_path=str(atomic_db),
        selection_db_path=str(tmp_path / "missing_selection.db"),
        fine_heat_db_path=str(tmp_path / "missing_heat.db"),
    )

    symbols = {item["symbol"] for item in payload["items"]}
    assert "sh600001" in symbols
    assert "sh600002" not in symbols
    assert payload["planned_entry_date"] > payload["signal_date"]
    assert all(item["planned_capital"] > 0 for item in payload["items"])


def test_backtest_range_opens_and_closes_mock_positions(tmp_path):
    atomic_db = _init_atomic_db(tmp_path)
    conn = sqlite3.connect(str(atomic_db))
    try:
        _seed_symbol(conn, "sh600001", launch_index=23)
        _seed_symbol(conn, "sz000001", launch_index=24, base_price=15.0)
        conn.commit()
    finally:
        conn.close()

    payload = backtest_range(
        "2026-05-01",
        "2026-05-08",
        replay_end_date="2026-05-19",
        budget=1_000_000,
        params=Aggressive10cmParams(
            min_score=45.0,
            max_positions=2,
            max_new_positions_per_day=2,
            first_15m_price_floor_pct=-1.0,
            first_15m_main_net_floor=-0.02,
        ),
        db_path=str(atomic_db),
        selection_db_path=str(tmp_path / "missing_selection.db"),
        fine_heat_db_path=str(tmp_path / "missing_heat.db"),
    )

    assert payload["summary"]["trade_count"] >= 1
    assert payload["equity_curve"]
    assert all(trade["entry_date"] > trade["signal_date"] for trade in payload["trades"])
