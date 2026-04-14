#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.build_limit_state_from_atomic import (
    build_limit_state,
    ensure_default_rules as ensure_limit_rules,
    ensure_schema as ensure_limit_schema,
    replace_rows as replace_limit_rows,
)
from backend.scripts.run_atomic_backfill_windows import daterange, discover_archive, load_config, parse_batches


TABLES_TO_COUNT = [
    "atomic_trade_daily",
    "atomic_trade_5m",
    "atomic_order_daily",
    "atomic_order_5m",
    "atomic_book_state_daily",
    "atomic_book_state_5m",
    "atomic_open_auction_l1_daily",
    "atomic_open_auction_l2_daily",
    "atomic_open_auction_phase_l1_daily",
    "atomic_open_auction_phase_l2_daily",
    "atomic_open_auction_manifest",
    "atomic_limit_state_daily",
    "atomic_limit_state_5m",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize an atomic backfill run after main data has landed.")
    parser.add_argument("--config", required=True, help="Config json path")
    parser.add_argument("--skip-limit-state", action="store_true", help="Skip rebuilding limit state")
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_cutoff_date(state: Dict[str, object]) -> Optional[str]:
    started_at = state.get("started_at")
    if not started_at or not isinstance(started_at, str):
        return None
    return started_at[:10]


def expected_day_keys(config: Dict[str, object], cutoff_date: Optional[str] = None) -> List[str]:
    batches = parse_batches(config.get("batches", []))
    market_root = Path(str(config["market_root"]))
    keys: List[str] = []
    for batch in batches:
        for trade_date in daterange(batch.date_from, batch.date_to):
            if cutoff_date and trade_date > cutoff_date:
                continue
            archive_path = discover_archive(batch.kind, market_root, trade_date)
            if archive_path:
                keys.append(f"{batch.name}:{trade_date}")
    return keys


def table_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    cur = conn.cursor()
    out: Dict[str, int] = {}
    for table in TABLES_TO_COUNT:
        out[table] = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return out


def month_counts(conn: sqlite3.Connection, table: str) -> Dict[str, int]:
    rows = conn.execute(
        f"""
        SELECT substr(trade_date, 1, 7) AS month_key, count(DISTINCT trade_date) AS day_count
        FROM {table}
        GROUP BY substr(trade_date, 1, 7)
        ORDER BY month_key DESC
        """
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)
    atomic_db = Path(str(config["atomic_db"]))
    state_path = Path(str(config["state_file"]))
    report_path = Path(str(config["report_file"]))

    if not atomic_db.exists():
        raise SystemExit(f"atomic db not found: {atomic_db}")

    state = load_json(state_path)
    completed_keys = list(state.get("completed_days", [])) if isinstance(state.get("completed_days"), list) else []
    failed_days = list(state.get("failed_days", [])) if isinstance(state.get("failed_days"), list) else []
    cutoff_date = parse_cutoff_date(state)
    expected_keys = expected_day_keys(config, cutoff_date=cutoff_date)
    missing_keys = [key for key in expected_keys if key not in set(completed_keys)]

    limit_rows_5m = 0
    limit_rows_daily = 0
    with sqlite3.connect(atomic_db) as conn:
        ensure_limit_schema(conn)
        ensure_limit_rules(conn)
        if not args.skip_limit_state:
            batches = parse_batches(config.get("batches", []))
            min_date = min(batch.date_from for batch in batches)
            max_date = max(batch.date_to for batch in batches)
            rows_5m_limit, daily_rows_limit = build_limit_state(conn, [], min_date, max_date)
            replace_limit_rows(conn, rows_5m_limit, daily_rows_limit, [], min_date, max_date)
            conn.commit()
            limit_rows_5m = len(rows_5m_limit)
            limit_rows_daily = len(daily_rows_limit)
        counts = table_counts(conn)
        trade_month_counts = month_counts(conn, "atomic_trade_daily")
        limit_month_counts = month_counts(conn, "atomic_limit_state_daily")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_status = "done"
    if failed_days or missing_keys:
        final_status = "partial_done"
    if not args.skip_limit_state and counts["atomic_limit_state_daily"] == 0:
        final_status = "partial_done"

    state["status"] = final_status
    state["finished_at"] = now
    state["last_completed_day"] = completed_keys[-1] if completed_keys else None
    state["expected_days"] = len(expected_keys)
    state["finalized_by"] = "finalize_atomic_backfill_run.py"
    state["limit_state_finalized_at"] = now if not args.skip_limit_state else state.get("limit_state_finalized_at")
    write_json(state_path, state)

    report = {
        "status": final_status,
        "config": str(config_path),
        "atomic_db": str(atomic_db),
        "state_file": str(state_path),
        "finished_at": now,
        "expected_day_count": len(expected_keys),
        "expected_cutoff_date": cutoff_date,
        "completed_day_count": len(completed_keys),
        "missing_day_count": len(missing_keys),
        "missing_days": missing_keys[:50],
        "failed_day_count": len(failed_days),
        "failed_days": failed_days[:20],
        "limit_state_rebuilt": not args.skip_limit_state,
        "limit_state_5m_rows": limit_rows_5m or counts["atomic_limit_state_5m"],
        "limit_state_daily_rows": limit_rows_daily or counts["atomic_limit_state_daily"],
        "table_counts": counts,
        "trade_month_day_counts": trade_month_counts,
        "limit_month_day_counts": limit_month_counts,
    }
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
