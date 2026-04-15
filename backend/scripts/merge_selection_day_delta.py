from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import backend.app.db.selection_db as selection_db_module
from backend.app.db.selection_db import SELECTION_DB_FILE, ensure_selection_schema
from backend.scripts.export_selection_day_delta import TABLE_SPECS, _normalize_trade_date


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _table_columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> List[str]:
    rows = conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def merge_selection_day_delta(trade_date: str, delta_db: str, target_db: str = "") -> Dict[str, object]:
    normalized_date = _normalize_trade_date(trade_date)
    delta_path = Path(delta_db)
    delta_literal = str(delta_path).replace("'", "''")
    if not delta_path.exists():
        raise FileNotFoundError(f"selection day delta 不存在: {delta_db}")
    target_path = Path(target_db or SELECTION_DB_FILE)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    previous = os.getenv("SELECTION_DB_PATH")
    previous_constant = selection_db_module.SELECTION_DB_FILE
    os.environ["SELECTION_DB_PATH"] = str(target_path)
    selection_db_module.SELECTION_DB_FILE = str(target_path)
    try:
        ensure_selection_schema()
    finally:
        selection_db_module.SELECTION_DB_FILE = previous_constant
        if previous is None:
            os.environ.pop("SELECTION_DB_PATH", None)
        else:
            os.environ["SELECTION_DB_PATH"] = previous

    counts: Dict[str, int] = {}
    with sqlite3.connect(target_path) as conn:
        conn.execute(f"ATTACH DATABASE '{delta_literal}' AS delta")
        for table, date_col in TABLE_SPECS:
            if not _table_exists(conn, table, "delta") or not _table_exists(conn, table):
                counts[table] = 0
                continue
            columns = _table_columns(conn, table)
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
    parser = argparse.ArgumentParser(description="合并 selection 单日增量 DB")
    parser.add_argument("trade_date")
    parser.add_argument("--delta-db", required=True)
    parser.add_argument("--target-db", default="")
    args = parser.parse_args()
    report = merge_selection_day_delta(args.trade_date, args.delta_db, target_db=args.target_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
