#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote


FORMAL_MARKET_DATA_ROOT = Path(os.getenv("FORMAL_MARKET_DATA_ROOT", "/Users/dong/ZhangData/market-data"))
DEFAULT_RESEARCH_ROOT = FORMAL_MARKET_DATA_ROOT / "research" / "current"
DEFAULT_DATA_DIR = Path(os.getenv("DATA_DIR", str(DEFAULT_RESEARCH_ROOT if DEFAULT_RESEARCH_ROOT.is_dir() else FORMAL_MARKET_DATA_ROOT)))
DEFAULT_INDEX_DB = Path(os.getenv("MODEL_INDEX_DB", str(DEFAULT_DATA_DIR / "selection" / "model_market_index_daily.db")))
DEFAULT_FEATURE_DB = Path(
    os.getenv("MODEL_FEATURE_DB_PATH", str(DEFAULT_DATA_DIR / "selection" / "model_feature_store.db"))
)
P0_INDEX_CODES = ["000852.SH", "000905.SH", "000300.SH", "000001.SH", "399006.SZ"]
INDEX_FEATURE_PREFIXES = {
    "000852.SH": "csi1000",
    "000905.SH": "csi500",
    "000300.SH": "hs300",
    "000001.SH": "sh_index",
    "399006.SZ": "gem_index",
}
INDEX_DERIVED_SUFFIXES = [
    "close",
    "ma20",
    "above_ma20",
    "dist_ma20_pct",
    "ma20_slope_5d_pct",
    "return_1d_pct",
    "return_5d_pct",
    "return_20d_pct",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local model market index cache coverage.")
    parser.add_argument("--index-db", type=Path, default=DEFAULT_INDEX_DB)
    parser.add_argument("--feature-db", type=Path, default=DEFAULT_FEATURE_DB)
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path.resolve()))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def index_coverage(conn: sqlite3.Connection, start_date: str, end_date: str) -> dict[str, object]:
    where = []
    params: list[str] = []
    if start_date:
        where.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("trade_date <= ?")
        params.append(end_date)
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    expected_dates = [
        str(row["trade_date"])
        for row in conn.execute(
            f"SELECT DISTINCT trade_date FROM model_market_index_daily {where_sql} ORDER BY trade_date",
            params,
        ).fetchall()
    ]
    expected_set = set(expected_dates)
    by_index: dict[str, object] = {}
    for code in P0_INDEX_CODES:
        code_where = ["index_code = ?"]
        code_params = [code]
        if start_date:
            code_where.append("trade_date >= ?")
            code_params.append(start_date)
        if end_date:
            code_where.append("trade_date <= ?")
            code_params.append(end_date)
        dates = [
            str(row["trade_date"])
            for row in conn.execute(
                f"""
                SELECT trade_date
                FROM model_market_index_daily
                WHERE {' AND '.join(code_where)}
                ORDER BY trade_date
                """,
                code_params,
            ).fetchall()
        ]
        missing = sorted(expected_set - set(dates))
        by_index[code] = {
            "rows": len(dates),
            "min_trade_date": dates[0] if dates else None,
            "max_trade_date": dates[-1] if dates else None,
            "coverage_ratio": round(len(dates) / len(expected_dates), 6) if expected_dates else None,
            "missing_count": len(missing),
            "missing_sample": missing[:30],
        }
    return {
        "expected_trade_days": len(expected_dates),
        "date_range": {
            "min_trade_date": expected_dates[0] if expected_dates else None,
            "max_trade_date": expected_dates[-1] if expected_dates else None,
        },
        "by_index": by_index,
    }


def feature_store_coverage(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"available": False, "reason": "feature db missing"}
    with connect_ro(path) as conn:
        if not table_exists(conn, "model_market_state_daily_v1"):
            return {"available": False, "reason": "model_market_state_daily_v1 missing"}
        state_columns = table_columns(conn, "model_market_state_daily_v1")
        state = conn.execute(
            """
            SELECT
              COUNT(*) AS rows,
              SUM(COALESCE(has_index_data, 0)) AS has_index_rows,
              MIN(trade_date) AS min_trade_date,
              MAX(trade_date) AS max_trade_date
            FROM model_market_state_daily_v1
            """
        ).fetchone()
        feature = None
        feature_columns: set[str] = set()
        if table_exists(conn, "model_feature_daily_v1"):
            feature_columns = table_columns(conn, "model_feature_daily_v1")
            feature = conn.execute(
                """
                SELECT
                  COUNT(*) AS rows
                FROM model_feature_daily_v1
                """
            ).fetchone()
        state_rows = int(state["rows"] or 0)
        state_index_columns: dict[str, object] = {}
        for _code, prefix in INDEX_FEATURE_PREFIXES.items():
            state_index_columns[prefix] = {}
            for suffix in INDEX_DERIVED_SUFFIXES:
                column = f"{prefix}_{suffix}"
                if column not in state_columns:
                    state_index_columns[prefix][column] = {"available": False, "rows": 0, "ratio": None}
                    continue
                rows = int(
                    conn.execute(
                        f"SELECT SUM({column} IS NOT NULL) FROM model_market_state_daily_v1"
                    ).fetchone()[0]
                    or 0
                )
                state_index_columns[prefix][column] = {
                    "available": True,
                    "rows": rows,
                    "ratio": round(rows / state_rows, 6) if state_rows else None,
                }
        payload: dict[str, object] = {
            "available": True,
            "market_state": {
                "rows": state_rows,
                "min_trade_date": state["min_trade_date"],
                "max_trade_date": state["max_trade_date"],
                "has_index_rows": int(state["has_index_rows"] or 0),
                "has_index_ratio": round(float(state["has_index_rows"] or 0) / state_rows, 6) if state_rows else None,
                "index_columns": state_index_columns,
            },
        }
        if feature:
            feature_rows = int(feature["rows"] or 0)
            feature_index_columns: dict[str, object] = {}
            for _code, prefix in INDEX_FEATURE_PREFIXES.items():
                feature_index_columns[prefix] = {}
                for suffix in INDEX_DERIVED_SUFFIXES:
                    column = f"{prefix}_{suffix}"
                    if column not in feature_columns:
                        feature_index_columns[prefix][column] = {"available": False, "rows": 0, "ratio": None}
                        continue
                    rows = int(
                        conn.execute(
                            f"SELECT SUM({column} IS NOT NULL) FROM model_feature_daily_v1"
                        ).fetchone()[0]
                        or 0
                    )
                    feature_index_columns[prefix][column] = {
                        "available": True,
                        "rows": rows,
                        "ratio": round(rows / feature_rows, 6) if feature_rows else None,
                    }
            payload["feature_daily"] = {
                "rows": feature_rows,
                "index_columns": feature_index_columns,
            }
        return payload


def main() -> None:
    args = parse_args()
    if not args.index_db.exists():
        raise SystemExit(f"index db missing: {args.index_db}")
    with connect_ro(args.index_db) as conn:
        if not table_exists(conn, "model_market_index_daily"):
            raise SystemExit("model_market_index_daily table missing")
        payload = {
            "index_db": str(args.index_db),
            "feature_db": str(args.feature_db),
            "index_coverage": index_coverage(conn, args.start_date, args.end_date),
            "feature_store_coverage": feature_store_coverage(args.feature_db),
        }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
