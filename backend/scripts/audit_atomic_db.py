#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_TABLES = [
    "atomic_trade_5m",
    "atomic_trade_daily",
    "atomic_order_5m",
    "atomic_order_daily",
    "atomic_book_state_5m",
    "atomic_book_state_daily",
    "atomic_limit_state_daily",
    "atomic_limit_state_5m",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit atomic SQLite database shape without modifying it.")
    parser.add_argument("--db", required=True, type=Path, help="Atomic SQLite database path")
    parser.add_argument("--date-from", default="", help="Optional inclusive YYYY-MM-DD for sampled stats")
    parser.add_argument("--date-to", default="", help="Optional inclusive YYYY-MM-DD for sampled stats")
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON output path")
    parser.add_argument("--full-counts", action="store_true", help="Run full table count/min/max stats; can be slow on large DBs")
    parser.add_argument("--include-dbstat", action="store_true", help="Include dbstat object sizes; can be slow on large DBs")
    return parser.parse_args()


def connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def table_indexes(conn: sqlite3.Connection, table: str) -> List[Dict[str, Any]]:
    rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        name = str(row[1])
        cols = [str(info[2]) for info in conn.execute(f"PRAGMA index_info({name})").fetchall()]
        out.append({"name": name, "unique": bool(row[2]), "origin": str(row[3]), "columns": cols})
    return out


def count_range(conn: sqlite3.Connection, table: str, date_from: str, date_to: str) -> Optional[int]:
    cols = table_columns(conn, table)
    if "trade_date" not in cols:
        return None
    clauses: List[str] = []
    params: List[Any] = []
    if date_from:
        clauses.append("trade_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("trade_date <= ?")
        params.append(date_to)
    if not clauses:
        return None
    row = conn.execute(f"SELECT count(*) FROM {table} WHERE {' AND '.join(clauses)}", params).fetchone()
    return int(row[0] or 0)


def table_summary(conn: sqlite3.Connection, table: str, date_from: str, date_to: str, full_counts: bool) -> Dict[str, Any]:
    if not table_exists(conn, table):
        return {"exists": False}
    cols = table_columns(conn, table)
    out: Dict[str, Any] = {
        "exists": True,
        "columns": cols,
        "indexes": table_indexes(conn, table),
    }
    if "trade_date" in cols:
        if full_counts:
            bounds = conn.execute(f"SELECT min(trade_date), max(trade_date), count(DISTINCT trade_date), count(*) FROM {table}").fetchone()
            out["min_trade_date"] = bounds[0]
            out["max_trade_date"] = bounds[1]
            out["distinct_trade_dates"] = int(bounds[2] or 0)
            out["rows"] = int(bounds[3] or 0)
        ranged = count_range(conn, table, date_from, date_to)
        if ranged is not None:
            out["rows_in_range"] = ranged
    elif full_counts:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
        out["rows"] = int(row[0] or 0)
    return out


def dbstat_sizes(conn: sqlite3.Connection, names: Iterable[str]) -> Dict[str, Dict[str, int]]:
    if not table_exists(conn, "dbstat"):
        return {}
    placeholders = ",".join("?" for _ in names)
    if not placeholders:
        return {}
    rows = conn.execute(
        f"SELECT name, sum(pgsize) AS bytes, count(*) AS pages FROM dbstat WHERE name IN ({placeholders}) GROUP BY name",
        list(names),
    ).fetchall()
    return {str(row[0]): {"bytes": int(row[1] or 0), "pages": int(row[2] or 0)} for row in rows}


def limit_5m_distribution(conn: sqlite3.Connection, date_from: str, date_to: str) -> Dict[str, Any]:
    if not table_exists(conn, "atomic_limit_state_5m"):
        return {"exists": False}
    clauses: List[str] = []
    params: List[Any] = []
    if date_from:
        clauses.append("trade_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("trade_date <= ?")
        params.append(date_to)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT state_label_5m, count(*) AS rows
        FROM atomic_limit_state_5m
        {where}
        GROUP BY state_label_5m
        ORDER BY rows DESC
        """,
        params,
    ).fetchall()
    return {"exists": True, "by_state_label_5m": {str(row[0]): int(row[1] or 0) for row in rows}}


def query_plans(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    plans: Dict[str, List[str]] = {}
    examples = {
        "trade_5m_symbol_trade_date": """
            EXPLAIN QUERY PLAN
            SELECT * FROM atomic_trade_5m
            WHERE symbol='sh600000' AND trade_date>='2026-03-01' AND trade_date<='2026-05-14'
            ORDER BY bucket_start
        """,
        "trade_5m_symbol_bucket_range": """
            EXPLAIN QUERY PLAN
            SELECT * FROM atomic_trade_5m
            WHERE symbol='sh600000' AND bucket_start>='2026-03-01 00:00:00' AND bucket_start<'2026-05-15 00:00:00'
            ORDER BY bucket_start
        """,
    }
    for name, sql in examples.items():
        try:
            plans[name] = [str(row[-1]) for row in conn.execute(sql).fetchall()]
        except sqlite3.Error as exc:
            plans[name] = [f"ERROR: {exc}"]
    return plans


def audit(path: Path, date_from: str, date_to: str, full_counts: bool, include_dbstat: bool) -> Dict[str, Any]:
    with connect_ro(path) as conn:
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        out: Dict[str, Any] = {
            "db_path": str(path),
            "file_size_bytes": path.stat().st_size if path.exists() else None,
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist_count,
            "sqlite_size_bytes": page_size * page_count,
            "full_counts": bool(full_counts),
            "tables": {table: table_summary(conn, table, date_from, date_to, full_counts) for table in DEFAULT_TABLES},
            "limit_5m_distribution": limit_5m_distribution(conn, date_from, date_to),
            "query_plans": query_plans(conn),
        }
        if include_dbstat:
            names = set(DEFAULT_TABLES)
            for table in DEFAULT_TABLES:
                if table_exists(conn, table):
                    names.update(index["name"] for index in table_indexes(conn, table))
            out["dbstat_sizes"] = dbstat_sizes(conn, sorted(names))
        return out


def main() -> None:
    args = parse_args()
    result = audit(args.db, args.date_from, args.date_to, bool(args.full_counts), bool(args.include_dbstat))
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
