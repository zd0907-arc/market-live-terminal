from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import candidate_atomic_db_paths
from backend.scripts.export_atomic_day_delta import TABLE_SPECS, _normalize_trade_date
from backend.scripts.run_atomic_backfill_windows import ensure_atomic_db


def _resolve_target_db(explicit: str) -> Path:
    if explicit:
        return Path(explicit)
    for raw in candidate_atomic_db_paths():
        if raw:
            return Path(raw)
    raise FileNotFoundError("未解析到 target atomic db")


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _table_columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> List[str]:
    rows = conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def merge_atomic_day_delta(trade_date: str, delta_db: str, target_db: str = "") -> Dict[str, object]:
    normalized_date = _normalize_trade_date(trade_date)
    delta_path = Path(delta_db)
    delta_literal = str(delta_path).replace("'", "''")
    if not delta_path.exists():
        raise FileNotFoundError(f"atomic day delta 不存在: {delta_db}")
    target_path = _resolve_target_db(target_db)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_atomic_db(target_path)

    counts: Dict[str, int] = {}
    with sqlite3.connect(target_path) as conn:
        conn.execute(f"ATTACH DATABASE '{delta_literal}' AS delta")
        for table, date_col in TABLE_SPECS:
            if not _table_exists(conn, table, "delta") or not _table_exists(conn, table):
                counts[table] = 0
                continue
            columns = _table_columns(conn, table)
            if not columns:
                counts[table] = 0
                continue
            column_sql = ", ".join(columns)
            conn.execute(f"DELETE FROM {table} WHERE {date_col}=?", (normalized_date,))
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({column_sql}) SELECT {column_sql} FROM delta.{table} WHERE {date_col}=?",
                (normalized_date,),
            )
            row = conn.execute("SELECT changes()").fetchone()
            counts[table] = int(row[0] or 0) if row else 0
        conn.commit()

    return {
        "trade_date": normalized_date,
        "delta_db": str(delta_path),
        "target_db": str(target_path),
        "row_counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="合并 atomic 单日增量 DB 到目标 atomic 主库")
    parser.add_argument("trade_date")
    parser.add_argument("--delta-db", required=True)
    parser.add_argument("--target-db", default="")
    args = parser.parse_args()
    report = merge_atomic_day_delta(args.trade_date, args.delta_db, target_db=args.target_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
