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


def _resolve_source_db(explicit: str) -> Path:
    candidates = [
        explicit,
        os.getenv("MODEL_FEATURE_DB_PATH", ""),
        os.path.join(os.getenv("DATA_DIR", str(ROOT_DIR / "data")), "selection", "model_feature_store.db"),
    ]
    for raw in candidates:
        path = Path(str(raw or ""))
        if path.exists():
            return path
    raise FileNotFoundError("未找到 model feature source db")


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _create_table_like(conn: sqlite3.Connection, table: str) -> None:
    row = conn.execute(
        "SELECT sql FROM src.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row and row[0]:
        conn.execute(str(row[0]))


def export_model_feature_day_delta(trade_date: str, output_db: str, source_db: str = "") -> Dict[str, object]:
    normalized_date = _normalize_trade_date(trade_date)
    src_path = _resolve_source_db(source_db)
    out_path = Path(output_db)
    src_literal = str(src_path).replace("'", "''")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    counts: Dict[str, int] = {}
    build_run_ids: set[str] = set()

    with sqlite3.connect(out_path) as out_conn:
        out_conn.execute(f"ATTACH DATABASE '{src_literal}' AS src")
        for table, date_col in DATE_TABLE_SPECS:
            if not _table_exists(out_conn, table, "src"):
                counts[table] = 0
                continue
            _create_table_like(out_conn, table)
            out_conn.execute(
                f"INSERT INTO {table} SELECT * FROM src.{table} WHERE {date_col}=?",
                (normalized_date,),
            )
            row = out_conn.execute("SELECT changes()").fetchone()
            counts[table] = int(row[0] or 0) if row else 0
            if "build_run_id" in [item[1] for item in out_conn.execute(f"PRAGMA table_info({table})").fetchall()]:
                for run_row in out_conn.execute(
                    f"SELECT DISTINCT build_run_id FROM {table} WHERE build_run_id IS NOT NULL AND build_run_id<>''"
                ):
                    build_run_ids.add(str(run_row[0]))

        if _table_exists(out_conn, "model_feature_build_runs", "src"):
            _create_table_like(out_conn, "model_feature_build_runs")
            if build_run_ids:
                placeholders = ",".join(["?"] * len(build_run_ids))
                out_conn.execute(
                    f"INSERT OR REPLACE INTO model_feature_build_runs SELECT * FROM src.model_feature_build_runs WHERE run_id IN ({placeholders})",
                    tuple(sorted(build_run_ids)),
                )
            counts["model_feature_build_runs"] = int(
                out_conn.execute("SELECT COUNT(*) FROM model_feature_build_runs").fetchone()[0]
            )

        if _table_exists(out_conn, "model_feature_manifest", "src"):
            _create_table_like(out_conn, "model_feature_manifest")
            out_conn.execute(
                """
                INSERT OR REPLACE INTO model_feature_manifest
                SELECT * FROM src.model_feature_manifest
                WHERE date_from <= ? AND date_to >= ?
                """,
                (normalized_date, normalized_date),
            )
            counts["model_feature_manifest"] = int(
                out_conn.execute("SELECT COUNT(*) FROM model_feature_manifest").fetchone()[0]
            )

        out_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS model_feature_day_delta_manifest (
                trade_date TEXT PRIMARY KEY,
                source_db TEXT NOT NULL,
                generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                row_counts_json TEXT NOT NULL
            )
            """
        )
        out_conn.execute("DELETE FROM model_feature_day_delta_manifest WHERE trade_date=?", (normalized_date,))
        out_conn.execute(
            """
            INSERT INTO model_feature_day_delta_manifest(trade_date, source_db, row_counts_json)
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
    parser = argparse.ArgumentParser(description="导出 model feature 单日增量 DB")
    parser.add_argument("trade_date")
    parser.add_argument("--output-db", required=True)
    parser.add_argument("--source-db", default="")
    args = parser.parse_args()
    report = export_model_feature_day_delta(args.trade_date, args.output_db, source_db=args.source_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
