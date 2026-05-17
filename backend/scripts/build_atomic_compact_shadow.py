#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COPY_TABLES = [
    "cfg_limit_rule_map",
    "atomic_trade_5m",
    "atomic_trade_daily",
    "atomic_order_5m",
    "atomic_order_daily",
    "atomic_book_state_5m",
    "atomic_book_state_daily",
    "atomic_limit_state_daily",
    "atomic_data_manifest",
]

DATE_FILTERED_TABLES = {
    "atomic_trade_5m",
    "atomic_trade_daily",
    "atomic_order_5m",
    "atomic_order_daily",
    "atomic_book_state_5m",
    "atomic_book_state_daily",
    "atomic_limit_state_daily",
}

SKIP_TABLES = {"atomic_limit_state_5m"}
EXPERIMENTAL_SKIP_INDEXES = {
    "idx_atomic_trade_5m_symbol_trade_date",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact shadow atomic DB without atomic_limit_state_5m.")
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--target-db", required=True, type=Path)
    parser.add_argument("--date-from", required=True, help="Inclusive YYYY-MM-DD")
    parser.add_argument("--date-to", required=True, help="Inclusive YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Replace existing target DB")
    parser.add_argument("--no-vacuum", action="store_true")
    parser.add_argument(
        "--skip-experimental-indexes",
        action="store_true",
        help="Skip indexes that are candidates for later removal; off by default for conservative shadow validation.",
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


def sqlite_master_sql(conn: sqlite3.Connection, obj_type: str, name: str, schema: str = "src") -> Optional[str]:
    row = conn.execute(
        f"SELECT sql FROM {schema}.sqlite_master WHERE type=? AND name=?",
        (obj_type, name),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def source_table_indexes(conn: sqlite3.Connection, table: str, *, skip_experimental_indexes: bool = False) -> List[str]:
    rows = conn.execute(
        "SELECT name, sql FROM src.sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL ORDER BY name",
        (table,),
    ).fetchall()
    out: List[str] = []
    for row in rows:
        name = str(row[0] or "")
        if not name or not row[1]:
            continue
        if skip_experimental_indexes and name in EXPERIMENTAL_SKIP_INDEXES:
            continue
        out.append(str(row[1]))
    return out


def attach_source(conn: sqlite3.Connection, source_db: Path) -> None:
    conn.execute("ATTACH DATABASE ? AS src", (str(source_db),))


def create_tables(conn: sqlite3.Connection, tables: Iterable[str]) -> List[str]:
    created: List[str] = []
    for table in tables:
        if table in SKIP_TABLES or not table_exists(conn, table, "src"):
            continue
        sql = sqlite_master_sql(conn, "table", table, "src")
        if not sql:
            continue
        conn.execute(sql)
        created.append(table)
    return created


def copy_table(conn: sqlite3.Connection, table: str, date_from: str, date_to: str) -> int:
    cols = table_columns(conn, table, "src")
    col_sql = ", ".join(cols)
    if table in DATE_FILTERED_TABLES and "trade_date" in cols:
        conn.execute(
            f"INSERT INTO {table} ({col_sql}) SELECT {col_sql} FROM src.{table} WHERE trade_date >= ? AND trade_date <= ?",
            (date_from, date_to),
        )
    else:
        conn.execute(f"INSERT INTO {table} ({col_sql}) SELECT {col_sql} FROM src.{table}")
    row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
    return int(row[0] or 0)


def create_indexes(conn: sqlite3.Connection, tables: Iterable[str], *, skip_experimental_indexes: bool = False) -> List[str]:
    created: List[str] = []
    for table in tables:
        for sql in source_table_indexes(conn, table, skip_experimental_indexes=skip_experimental_indexes):
            conn.execute(sql)
            created.append(sql.split()[2] if len(sql.split()) > 2 else sql)
    return created


def build(
    source_db: Path,
    target_db: Path,
    date_from: str,
    date_to: str,
    force: bool,
    vacuum: bool,
    *,
    skip_experimental_indexes: bool = False,
) -> Dict[str, Any]:
    if not source_db.exists():
        raise FileNotFoundError(f"source DB not found: {source_db}")
    if target_db.exists():
        if not force:
            raise FileExistsError(f"target DB exists; pass --force to replace: {target_db}")
        target_db.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(target_db) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    target_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(target_db), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=MEMORY")
        attach_source(conn, source_db)
        created_tables = create_tables(conn, COPY_TABLES)
        copied: Dict[str, int] = {}
        for table in created_tables:
            copied[table] = copy_table(conn, table, date_from, date_to)
        indexes = create_indexes(conn, created_tables, skip_experimental_indexes=skip_experimental_indexes)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS atomic_compact_manifest (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        manifest = {
            "source_db": str(source_db),
            "target_db": str(target_db),
            "date_from": date_from,
            "date_to": date_to,
            "skipped_tables": sorted(SKIP_TABLES),
            "skip_experimental_indexes": bool(skip_experimental_indexes),
            "experimental_skip_indexes": sorted(EXPERIMENTAL_SKIP_INDEXES) if skip_experimental_indexes else [],
            "copied_rows": copied,
        }
        conn.execute(
            "INSERT OR REPLACE INTO atomic_compact_manifest(key, value) VALUES ('build', ?)",
            (json.dumps(manifest, ensure_ascii=False, sort_keys=True),),
        )
        conn.commit()
        conn.execute("DETACH DATABASE src")
    if vacuum:
        with sqlite3.connect(str(target_db), timeout=60) as conn:
            conn.execute("VACUUM")
    return {
        "source_db": str(source_db),
        "target_db": str(target_db),
        "date_from": date_from,
        "date_to": date_to,
        "copied_rows": copied,
        "created_indexes": indexes,
        "skip_experimental_indexes": bool(skip_experimental_indexes),
        "target_size_bytes": target_db.stat().st_size if target_db.exists() else None,
    }


def main() -> None:
    args = parse_args()
    result = build(
        args.source_db,
        args.target_db,
        args.date_from,
        args.date_to,
        force=bool(args.force),
        vacuum=not bool(args.no_vacuum),
        skip_experimental_indexes=bool(args.skip_experimental_indexes),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
