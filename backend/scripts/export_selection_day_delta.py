from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.selection_db import SELECTION_DB_FILE, ensure_selection_schema

TABLE_SPECS: List[Tuple[str, str]] = [
    ("selection_feature_daily", "trade_date"),
    ("selection_signal_daily", "trade_date"),
]


def _normalize_trade_date(value: str) -> str:
    text = str(value or "").strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) == 10:
        return text
    raise ValueError(f"非法 trade_date: {value}")


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _resolve_selection_db(explicit: str) -> Path:
    candidates = [
        Path(explicit) if explicit else None,
        Path(SELECTION_DB_FILE),
        Path(str(SELECTION_DB_FILE).replace("selection_research.db", "selection_research_windows.db")),
    ]
    for item in candidates:
        if item and item.exists():
            return item
    raise FileNotFoundError("未找到 selection source db")


def export_selection_day_delta(trade_date: str, output_db: str, source_db: str = "") -> Dict[str, object]:
    normalized_date = _normalize_trade_date(trade_date)
    src_path = _resolve_selection_db(source_db)
    out_path = Path(output_db)
    src_literal = str(src_path).replace("'", "''")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    ensure_selection_schema()
    with sqlite3.connect(out_path) as out_conn:
        out_conn.execute(f"ATTACH DATABASE '{src_literal}' AS src")
        counts: Dict[str, int] = {}
        for table, date_col in TABLE_SPECS:
            if not _table_exists(out_conn, table, "src"):
                counts[table] = 0
                continue
            out_conn.execute(f"CREATE TABLE {table} AS SELECT * FROM src.{table} WHERE {date_col}=?", (normalized_date,))
            counts[table] = int(out_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        out_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS selection_day_delta_manifest (
                trade_date TEXT PRIMARY KEY,
                source_db TEXT NOT NULL,
                generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                row_counts_json TEXT NOT NULL
            )
            """
        )
        out_conn.execute(
            """
            INSERT OR REPLACE INTO selection_day_delta_manifest(trade_date, source_db, row_counts_json)
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
    parser = argparse.ArgumentParser(description="导出 selection 单日增量 DB")
    parser.add_argument("trade_date")
    parser.add_argument("--output-db", required=True)
    parser.add_argument("--source-db", default="")
    args = parser.parse_args()
    report = export_selection_day_delta(args.trade_date, args.output_db, source_db=args.source_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
