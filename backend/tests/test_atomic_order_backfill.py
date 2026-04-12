import sqlite3
from pathlib import Path

from backend.scripts.backfill_atomic_order_from_raw import _apply_support_ratios, _build_order_rows
from backend.tests.test_l2_daily_backfill import _build_sample_day


def _init_atomic_db(path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    schema = (repo_root / "backend" / "scripts" / "sql" / "atomic_fact_p0_schema.sql").read_text(encoding="utf-8")
    with sqlite3.connect(path) as conn:
        conn.executescript(schema)
        conn.commit()


def test_build_atomic_order_rows_from_sample_day(tmp_path):
    package_path = _build_sample_day(tmp_path)
    symbol_dir = package_path / "000833.SZ"

    symbol, rows_5m, daily_row, diagnostics = _build_order_rows(symbol_dir, "2026-03-11")

    assert symbol == "sz000833"
    assert diagnostics["order_event_rows"] == 7
    assert len(rows_5m) == 2

    first = rows_5m[0]
    second = rows_5m[1]

    assert first[2] == "2026-03-11 09:30:00"
    assert first[3:9] == (250000.0, 250000.0, 50000.0, 25000.0, 0.0, -25000.0)
    assert first[9:17] == (1, 1, 1, 1, 10000.0, 10000.0, 2000.0, 1000.0)

    assert second[2] == "2026-03-11 09:35:00"
    assert second[3:9] == (753000.0, 753000.0, 0.0, 75300.0, 0.0, 75300.0)
    assert second[9:17] == (1, 1, 0, 1, 30000.0, 30000.0, 0.0, 3000.0)

    assert daily_row is not None
    assert daily_row[2:12] == (
        1003000.0,
        1003000.0,
        50000.0,
        100300.0,
        0.0,
        50300.0,
        2,
        2,
        1,
        2,
    )
    assert daily_row[12:22] == (50300.0, 0.0, 50300.0, 0.0, 0.0, 0.0, 1, 1, 0, 0)


def test_apply_support_ratios_uses_trade_total_amount(tmp_path):
    atomic_db = tmp_path / "market_atomic.db"
    _init_atomic_db(atomic_db)

    with sqlite3.connect(atomic_db) as conn:
        conn.execute(
            """
            INSERT INTO atomic_trade_daily (
                symbol, trade_date, open, high, low, close, total_amount, total_volume, trade_count,
                l1_main_buy_amount, l1_main_sell_amount, l1_main_net_amount,
                l1_super_buy_amount, l1_super_sell_amount, l1_super_net_amount,
                l2_main_buy_amount, l2_main_sell_amount, l2_main_net_amount,
                l2_super_buy_amount, l2_super_sell_amount, l2_super_net_amount,
                source_type, quality_info
            ) VALUES (
                'sz000833', '2026-03-11', 25, 25.1, 25, 25.1, 2006000, NULL, NULL,
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                'trade_order', NULL
            )
            """
        )
        conn.commit()

    package_path = _build_sample_day(tmp_path / "sample")
    symbol_dir = package_path / "000833.SZ"
    _, _, daily_row, _ = _build_order_rows(symbol_dir, "2026-03-11")
    assert daily_row is not None

    adjusted = _apply_support_ratios(daily_row, 2006000.0)
    assert round(adjusted[27], 6) == round(953000.0 / 2006000.0, 6)
    assert round(adjusted[28], 6) == round(902700.0 / 2006000.0, 6)
