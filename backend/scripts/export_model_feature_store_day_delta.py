from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

TABLE_SPECS: List[Tuple[str, str]] = [
    ("model_market_index_daily", "trade_date"),
    ("model_market_state_daily_v1", "trade_date"),
    ("model_feature_daily_v1", "trade_date"),
    ("model_feature_intraday_shape_v1", "trade_date"),
    ("model_label_forward_return_v1", "trade_date"),
    ("model_feature_manifest", "date_from"),
    ("model_feature_build_runs", "date_from"),
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


def export_model_feature_store_day_delta(trade_date: str, output_db: str, source_db: str) -> Dict[str, object]:
    normalized_date = _normalize_trade_date(trade_date)
    src_path = Path(source_db)
    if not src_path.exists():
        raise FileNotFoundError(f"model feature source db 不存在: {source_db}")
    out_path = Path(output_db)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    src_literal = str(src_path).replace("'", "''")
    counts: Dict[str, int] = {}
    with sqlite3.connect(out_path) as out_conn:
        out_conn.execute(f"ATTACH DATABASE '{src_literal}' AS src")
        for table, date_col in TABLE_SPECS:
            if not _table_exists(out_conn, table, "src"):
                counts[table] = 0
                continue
            row = out_conn.execute(
                "SELECT sql FROM src.sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if row and row[0]:
                out_conn.execute(str(row[0]))
            if table in {"model_feature_manifest", "model_feature_build_runs"}:
                where_sql = "date_from <= ? AND date_to >= ?"
                params = (normalized_date, normalized_date)
            else:
                where_sql = f"{date_col}=?"
                params = (normalized_date,)
            out_conn.execute(f"INSERT INTO {table} SELECT * FROM src.{table} WHERE {where_sql}", params)
            counts[table] = int(out_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        out_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS model_feature_store_day_delta_manifest (
                trade_date TEXT PRIMARY KEY,
                source_db TEXT NOT NULL,
                generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                row_counts_json TEXT NOT NULL
            )
            """
        )
        out_conn.execute(
            """
            INSERT OR REPLACE INTO model_feature_store_day_delta_manifest(trade_date, source_db, row_counts_json)
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
    parser = argparse.ArgumentParser(description="导出 model_feature_store 单日增量 DB")
    parser.add_argument("trade_date")
    parser.add_argument("--output-db", required=True)
    parser.add_argument("--source-db", required=True)
    args = parser.parse_args()
    report = export_model_feature_store_day_delta(args.trade_date, args.output_db, args.source_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
