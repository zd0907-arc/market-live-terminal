from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.export_model_feature_store_day_delta import TABLE_SPECS, _normalize_trade_date


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _table_columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> List[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()]


def _ensure_table_from_delta(conn: sqlite3.Connection, table: str) -> None:
    if _table_exists(conn, table):
        return
    row = conn.execute(
        "SELECT sql FROM delta.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row and row[0]:
        conn.execute(str(row[0]))


def merge_model_feature_store_day_delta(trade_date: str, delta_db: str, target_db: str) -> Dict[str, object]:
    normalized_date = _normalize_trade_date(trade_date)
    delta_path = Path(delta_db)
    if not delta_path.exists():
        raise FileNotFoundError(f"model feature day delta 不存在: {delta_db}")
    target_path = Path(target_db)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        sqlite3.connect(target_path).close()

    delta_literal = str(delta_path).replace("'", "''")
    counts: Dict[str, int] = {}
    with sqlite3.connect(target_path) as conn:
        conn.execute(f"ATTACH DATABASE '{delta_literal}' AS delta")
        for table, date_col in TABLE_SPECS:
            if not _table_exists(conn, table, "delta"):
                counts[table] = 0
                continue
            _ensure_table_from_delta(conn, table)
            columns = _table_columns(conn, table)
            if not columns:
                counts[table] = 0
                continue
            column_sql = ", ".join(columns)
            if table in {"model_feature_manifest", "model_feature_build_runs"}:
                delete_sql = "date_from <= ? AND date_to >= ?"
                params = (normalized_date, normalized_date)
            else:
                delete_sql = f"{date_col}=?"
                params = (normalized_date,)
            conn.execute(f"DELETE FROM {table} WHERE {delete_sql}", params)
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({column_sql}) SELECT {column_sql} FROM delta.{table}",
            )
            counts[table] = int(conn.execute("SELECT changes()").fetchone()[0] or 0)
        conn.commit()

    return {
        "trade_date": normalized_date,
        "delta_db": str(delta_path),
        "target_db": str(target_path),
        "row_counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="合并 model_feature_store 单日增量 DB")
    parser.add_argument("trade_date")
    parser.add_argument("--delta-db", required=True)
    parser.add_argument("--target-db", required=True)
    args = parser.parse_args()
    report = merge_model_feature_store_day_delta(args.trade_date, args.delta_db, args.target_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
