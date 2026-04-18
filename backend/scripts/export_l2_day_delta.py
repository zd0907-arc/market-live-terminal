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

from backend.app.core.config import DB_FILE
from backend.app.db.l2_history_db import ensure_l2_history_schema

TABLE_SPECS: List[Tuple[str, str]] = [
    ("history_5m_l2", "source_date"),
    ("history_daily_l2", "date"),
    ("l2_daily_ingest_runs", "trade_date"),
    ("l2_daily_ingest_failures", "trade_date"),
]


def _normalize_trade_date(value: str) -> str:
    text = str(value or "").strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) == 10:
        return text
    raise ValueError(f"非法 trade_date: {value}")


def _resolve_source_db(explicit: str) -> Path:
    path = Path(explicit or os.getenv("DB_PATH") or DB_FILE)
    if path.exists():
        return path
    raise FileNotFoundError(f"l2 source db 不存在: {path}")


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def export_l2_day_delta(trade_date: str, output_db: str, source_db: str = "") -> Dict[str, object]:
    normalized_date = _normalize_trade_date(trade_date)
    src_path = _resolve_source_db(source_db)
    out_path = Path(output_db)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    prev_db = os.environ.get("DB_PATH", "")
    os.environ["DB_PATH"] = str(out_path)
    ensure_l2_history_schema()
    if prev_db:
        os.environ["DB_PATH"] = prev_db
    else:
        os.environ.pop("DB_PATH", None)

    counts: Dict[str, int] = {}
    src_literal = str(src_path).replace("'", "''")
    with sqlite3.connect(out_path) as out_conn:
        out_conn.execute(f"ATTACH DATABASE '{src_literal}' AS src")
        for table, date_col in TABLE_SPECS:
            if not _table_exists(out_conn, table) or not _table_exists(out_conn, table, "src"):
                counts[table] = 0
                continue
            out_conn.execute(f"DELETE FROM {table} WHERE {date_col}=?", (normalized_date,))
            out_conn.execute(
                f"INSERT INTO {table} SELECT * FROM src.{table} WHERE {date_col}=?",
                (normalized_date,),
            )
            row = out_conn.execute("SELECT changes()").fetchone()
            counts[table] = int(row[0] or 0) if row else 0

        out_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS l2_day_delta_manifest (
                trade_date TEXT PRIMARY KEY,
                source_db TEXT NOT NULL,
                generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                row_counts_json TEXT NOT NULL
            )
            """
        )
        out_conn.execute("DELETE FROM l2_day_delta_manifest WHERE trade_date=?", (normalized_date,))
        out_conn.execute(
            """
            INSERT INTO l2_day_delta_manifest(trade_date, source_db, row_counts_json)
            VALUES (?, ?, ?)
            """,
            (normalized_date, str(src_path), json.dumps(counts, ensure_ascii=False, sort_keys=True)),
        )
        out_conn.commit()

    return {
        "trade_date": normalized_date,
        "source_db": str(src_path),
        "output_db": str(out_path),
        "row_counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 L2 单日增量 DB")
    parser.add_argument("trade_date")
    parser.add_argument("--output-db", required=True)
    parser.add_argument("--source-db", default="")
    args = parser.parse_args()
    report = export_l2_day_delta(args.trade_date, args.output_db, source_db=args.source_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
