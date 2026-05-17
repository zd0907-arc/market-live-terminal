#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


APPEND_TABLES = [
    "atomic_trade_5m",
    "atomic_trade_daily",
    "atomic_order_5m",
    "atomic_order_daily",
    "atomic_book_state_5m",
    "atomic_book_state_daily",
    "atomic_limit_state_daily",
]

SKIP_TABLES = {"atomic_limit_state_5m"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append date-window rows into a compact shadow atomic DB.")
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--target-db", required=True, type=Path)
    parser.add_argument("--date-from", required=True, help="Inclusive YYYY-MM-DD")
    parser.add_argument("--date-to", required=True, help="Inclusive YYYY-MM-DD")
    parser.add_argument(
        "--tables",
        nargs="*",
        default=APPEND_TABLES,
        help="Tables to append. Defaults to compact atomic tables; atomic_limit_state_5m is always skipped.",
    )
    return parser.parse_args()


def table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def table_columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> List[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()]


def copy_window(conn: sqlite3.Connection, table: str, date_from: str, date_to: str) -> Dict[str, int]:
    if table in SKIP_TABLES:
        return {"deleted_rows": 0, "inserted_rows": 0}
    if not table_exists(conn, table, "src"):
        return {"deleted_rows": 0, "inserted_rows": 0}
    if not table_exists(conn, table, "main"):
        raise RuntimeError(f"target table missing: {table}")

    source_cols = table_columns(conn, table, "src")
    target_cols = table_columns(conn, table, "main")
    if source_cols != target_cols:
        raise RuntimeError(f"schema mismatch for {table}: source and target columns differ")
    if "trade_date" not in target_cols:
        raise RuntimeError(f"table has no trade_date and cannot be window-appended: {table}")

    deleted = conn.execute(
        f"DELETE FROM {table} WHERE trade_date >= ? AND trade_date <= ?",
        (date_from, date_to),
    ).rowcount
    col_sql = ", ".join(target_cols)
    inserted = conn.execute(
        f"""
        INSERT INTO {table} ({col_sql})
        SELECT {col_sql}
        FROM src.{table}
        WHERE trade_date >= ? AND trade_date <= ?
        """,
        (date_from, date_to),
    ).rowcount
    return {"deleted_rows": int(deleted or 0), "inserted_rows": int(inserted or 0)}


def table_bounds(conn: sqlite3.Connection, tables: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for table in tables:
        if table in SKIP_TABLES or not table_exists(conn, table, "main"):
            continue
        cols = table_columns(conn, table, "main")
        if "trade_date" not in cols:
            continue
        row = conn.execute(f"SELECT min(trade_date), max(trade_date), count(*) FROM {table}").fetchone()
        out[table] = {
            "min_trade_date": row[0],
            "max_trade_date": row[1],
            "rows": int(row[2] or 0),
        }
    return out


def update_manifest(
    conn: sqlite3.Connection,
    source_db: Path,
    target_db: Path,
    date_from: str,
    date_to: str,
    copied: Dict[str, Dict[str, int]],
    tables: List[str],
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS atomic_compact_manifest (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    existing = {}
    row = conn.execute("SELECT value FROM atomic_compact_manifest WHERE key='build'").fetchone()
    if row and row[0]:
        try:
            existing = json.loads(str(row[0]))
        except json.JSONDecodeError:
            existing = {}
    existing["date_to"] = max(str(existing.get("date_to") or ""), date_to)
    existing["target_db"] = str(target_db)
    existing["source_db"] = str(source_db)
    existing["skipped_tables"] = sorted(SKIP_TABLES)
    append_runs = list(existing.get("append_runs") or [])
    append_runs.append(
        {
            "appended_at": datetime.now().isoformat(timespec="seconds"),
            "date_from": date_from,
            "date_to": date_to,
            "copied_rows": copied,
            "tables": tables,
        }
    )
    existing["append_runs"] = append_runs
    conn.execute(
        "INSERT OR REPLACE INTO atomic_compact_manifest(key, value) VALUES ('build', ?)",
        (json.dumps(existing, ensure_ascii=False, sort_keys=True),),
    )


def append_window(
    source_db: Path,
    target_db: Path,
    date_from: str,
    date_to: str,
    tables: List[str],
) -> Dict[str, Any]:
    if not source_db.exists():
        raise FileNotFoundError(f"source DB not found: {source_db}")
    if not target_db.exists():
        raise FileNotFoundError(f"target DB not found: {target_db}")
    selected_tables = [table for table in tables if table not in SKIP_TABLES]

    with sqlite3.connect(str(target_db), timeout=120) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("ATTACH DATABASE ? AS src", (str(source_db),))
        copied = {table: copy_window(conn, table, date_from, date_to) for table in selected_tables}
        update_manifest(conn, source_db, target_db, date_from, date_to, copied, selected_tables)
        bounds = table_bounds(conn, selected_tables)
        conn.commit()
        conn.execute("DETACH DATABASE src")

    return {
        "source_db": str(source_db),
        "target_db": str(target_db),
        "date_from": date_from,
        "date_to": date_to,
        "copied_rows": copied,
        "bounds": bounds,
        "target_size_bytes": target_db.stat().st_size,
    }


def main() -> None:
    args = parse_args()
    result = append_window(args.source_db, args.target_db, args.date_from, args.date_to, list(args.tables))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
