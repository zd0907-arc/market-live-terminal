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

DATE_TABLE_SPECS: List[Tuple[str, str]] = [
    ("model_feature_daily_v1", "trade_date"),
    ("model_feature_intraday_shape_v1", "trade_date"),
    ("model_label_forward_return_v1", "trade_date"),
    ("model_market_state_daily_v1", "trade_date"),
    ("model_market_index_daily", "trade_date"),
]
META_TABLES = ("model_feature_build_runs", "model_feature_manifest")


def _normalize_trade_date(value: str) -> str:
    text = str(value or "").strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) == 10:
        return text
    raise ValueError(f"非法 trade_date: {value}")


def _resolve_target_db(explicit: str) -> Path:
    raw = explicit or os.getenv("MODEL_FEATURE_DB_PATH") or os.path.join(
        os.getenv("DATA_DIR", str(ROOT_DIR / "data")),
        "selection",
        "model_feature_store.db",
    )
    return Path(raw)


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _table_columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> List[str]:
    rows = conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def _ensure_table_from_delta(conn: sqlite3.Connection, table: str) -> None:
    if _table_exists(conn, table):
        return
    row = conn.execute(
        "SELECT sql FROM delta.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row and row[0]:
        conn.execute(str(row[0]))


def merge_model_feature_day_delta(trade_date: str, delta_db: str, target_db: str = "") -> Dict[str, object]:
    normalized_date = _normalize_trade_date(trade_date)
    delta_path = Path(delta_db)
    if not delta_path.exists():
        raise FileNotFoundError(f"model feature day delta 不存在: {delta_db}")
    target_path = _resolve_target_db(target_db)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        sqlite3.connect(target_path).close()

    delta_literal = str(delta_path).replace("'", "''")
    counts: Dict[str, int] = {}

    with sqlite3.connect(target_path) as conn:
        conn.execute(f"ATTACH DATABASE '{delta_literal}' AS delta")
        for table in META_TABLES:
            if not _table_exists(conn, table, "delta"):
                counts[table] = 0
                continue
            _ensure_table_from_delta(conn, table)
            columns = [col for col in _table_columns(conn, table) if col in set(_table_columns(conn, table, "delta"))]
            if not columns:
                counts[table] = 0
                continue
            column_sql = ", ".join(columns)
            conn.execute(f"INSERT OR REPLACE INTO {table} ({column_sql}) SELECT {column_sql} FROM delta.{table}")
            row = conn.execute("SELECT changes()").fetchone()
            counts[table] = int(row[0] or 0) if row else 0

        for table, date_col in DATE_TABLE_SPECS:
            if not _table_exists(conn, table, "delta"):
                counts[table] = 0
                continue
            _ensure_table_from_delta(conn, table)
            if not _table_exists(conn, table):
                counts[table] = 0
                continue
            delta_columns = set(_table_columns(conn, table, "delta"))
            columns = [col for col in _table_columns(conn, table) if col in delta_columns]
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
    parser = argparse.ArgumentParser(description="合并 model feature 单日增量 DB")
    parser.add_argument("trade_date")
    parser.add_argument("--delta-db", required=True)
    parser.add_argument("--target-db", default="")
    args = parser.parse_args()
    report = merge_model_feature_day_delta(args.trade_date, args.delta_db, target_db=args.target_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
