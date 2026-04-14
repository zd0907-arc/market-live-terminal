#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.run_atomic_backfill_windows import daterange, discover_archive, load_config, parse_batches


SAMPLE_QUERIES = {
    "trade_daily": """
        SELECT symbol, trade_date, total_amount, quality_info
        FROM atomic_trade_daily
        ORDER BY trade_date DESC, symbol
        LIMIT ?
    """,
    "order_daily": """
        SELECT symbol, trade_date, add_buy_amount, cancel_buy_amount, oib_delta_amount
        FROM atomic_order_daily
        ORDER BY trade_date DESC, symbol
        LIMIT ?
    """,
    "book_daily": """
        SELECT symbol, trade_date, close_bid_resting_amount, close_ask_resting_amount, valid_bucket_count
        FROM atomic_book_state_daily
        ORDER BY trade_date DESC, symbol
        LIMIT ?
    """,
    "auction_l2_daily": """
        SELECT symbol, trade_date, auction_trade_amount_total, auction_trade_volume_total
        FROM atomic_open_auction_l2_daily
        ORDER BY trade_date DESC, symbol
        LIMIT ?
    """,
    "limit_daily": """
        SELECT symbol, trade_date, up_limit_price, down_limit_price, limit_state_label
        FROM atomic_limit_state_daily
        ORDER BY trade_date DESC, symbol
        LIMIT ?
    """,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an atomic backfill run.")
    parser.add_argument("--config", required=True, help="Config json path")
    parser.add_argument("--output", default="", help="Optional json output path")
    parser.add_argument("--sample-size", type=int, default=3)
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_cutoff_date(state: Dict[str, object]) -> Optional[str]:
    started_at = state.get("started_at")
    if not started_at or not isinstance(started_at, str):
        return None
    return started_at[:10]


def expected_keys(config: Dict[str, object], cutoff_date: Optional[str] = None) -> List[str]:
    batches = parse_batches(config.get("batches", []))
    market_root = Path(str(config["market_root"]))
    out: List[str] = []
    for batch in batches:
        for trade_date in daterange(batch.date_from, batch.date_to):
            if cutoff_date and trade_date > cutoff_date:
                continue
            archive_path = discover_archive(batch.kind, market_root, trade_date)
            if archive_path:
                out.append(f"{batch.name}:{trade_date}")
    return out


def daily_distinct_counts(conn: sqlite3.Connection, table: str) -> Dict[str, int]:
    rows = conn.execute(
        f"""
        SELECT substr(trade_date, 1, 7) AS month_key, count(DISTINCT trade_date) AS day_count
        FROM {table}
        GROUP BY substr(trade_date, 1, 7)
        ORDER BY month_key DESC
        """
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def sample_rows(conn: sqlite3.Connection, sample_size: int) -> Dict[str, List[Dict[str, object]]]:
    out: Dict[str, List[Dict[str, object]]] = {}
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    for name, sql in SAMPLE_QUERIES.items():
        rows = cur.execute(sql, (sample_size,)).fetchall()
        out[name] = [dict(row) for row in rows]
    return out


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)
    atomic_db = Path(str(config["atomic_db"]))
    state_path = Path(str(config["state_file"]))
    report_path = Path(str(config["report_file"]))

    state = load_json(state_path)
    report = load_json(report_path)
    completed = list(state.get("completed_days", [])) if isinstance(state.get("completed_days"), list) else []
    cutoff_date = parse_cutoff_date(state)
    expected = expected_keys(config, cutoff_date=cutoff_date)
    completed_set = set(completed)
    missing = [key for key in expected if key not in completed_set]

    with sqlite3.connect(atomic_db) as conn:
        counts = {
            "trade_daily": conn.execute("SELECT count(*) FROM atomic_trade_daily").fetchone()[0],
            "order_daily": conn.execute("SELECT count(*) FROM atomic_order_daily").fetchone()[0],
            "book_daily": conn.execute("SELECT count(*) FROM atomic_book_state_daily").fetchone()[0],
            "auction_manifest": conn.execute("SELECT count(*) FROM atomic_open_auction_manifest").fetchone()[0],
            "limit_daily": conn.execute("SELECT count(*) FROM atomic_limit_state_daily").fetchone()[0],
            "limit_5m": conn.execute("SELECT count(*) FROM atomic_limit_state_5m").fetchone()[0],
        }
        trade_month_days = daily_distinct_counts(conn, "atomic_trade_daily")
        limit_month_days = daily_distinct_counts(conn, "atomic_limit_state_daily")
        samples = sample_rows(conn, args.sample_size)

    payload = {
        "config": str(config_path),
        "atomic_db": str(atomic_db),
        "state_status": state.get("status"),
        "report_status": report.get("status"),
        "expected_cutoff_date": cutoff_date,
        "expected_day_count": len(expected),
        "completed_day_count": len(completed),
        "missing_day_count": len(missing),
        "missing_days": missing[:50],
        "counts": counts,
        "trade_month_day_counts": trade_month_days,
        "limit_month_day_counts": limit_month_days,
        "samples": samples,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
