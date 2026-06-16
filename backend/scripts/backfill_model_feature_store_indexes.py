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

INDEX_SPECS = {
    "000852.SH": ("csi1000", "中证1000"),
    "000905.SH": ("csi500", "中证500"),
    "000300.SH": ("hs300", "沪深300"),
    "000001.SH": ("sh_index", "上证指数"),
    "399006.SZ": ("gem_index", "创业板指"),
}
DERIVED_SUFFIXES = [
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
    parser = argparse.ArgumentParser(description="Backfill five market index features into model_feature_store.")
    parser.add_argument("--index-db", type=Path, default=DEFAULT_INDEX_DB)
    parser.add_argument("--feature-db", type=Path, default=DEFAULT_FEATURE_DB)
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--feature-version", default="v1")
    return parser.parse_args()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=120000")
    return conn


def quote_ro_uri(path: Path) -> str:
    return f"file:{quote(str(path.resolve()))}?mode=ro"


def table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column not in columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def ensure_feature_schema(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "model_market_index_daily"):
        conn.execute(
            """
            CREATE TABLE model_market_index_daily (
              index_code TEXT NOT NULL,
              index_name TEXT NOT NULL,
              trade_date TEXT NOT NULL,
              open REAL,
              high REAL,
              low REAL,
              close REAL NOT NULL,
              volume REAL,
              amount REAL,
              source TEXT NOT NULL,
              build_run_id TEXT,
              sync_run_id TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (index_code, trade_date)
            )
            """
        )
    else:
        add_column(conn, "model_market_index_daily", "build_run_id", "TEXT")
        add_column(conn, "model_market_index_daily", "sync_run_id", "TEXT")
        add_column(conn, "model_market_index_daily", "updated_at", "TEXT")
        conn.execute("UPDATE model_market_index_daily SET updated_at=COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_market_index_daily_trade_date
        ON model_market_index_daily(trade_date)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_market_index_daily_sync_run_id
        ON model_market_index_daily(sync_run_id)
        """
    )

    state_cols = columns(conn, "model_market_state_daily_v1")
    if state_cols:
        for prefix, _name in INDEX_SPECS.values():
            for suffix in DERIVED_SUFFIXES:
                column = f"{prefix}_{suffix}"
                if column in state_cols:
                    continue
                ddl = "INTEGER" if suffix == "above_ma20" else "REAL"
                conn.execute(f"ALTER TABLE model_market_state_daily_v1 ADD COLUMN {column} {ddl}")
                state_cols.add(column)

    feature_cols = columns(conn, "model_feature_daily_v1")
    if feature_cols:
        for prefix, _name in INDEX_SPECS.values():
            for suffix in DERIVED_SUFFIXES:
                column = f"{prefix}_{suffix}"
                if column in feature_cols:
                    continue
                ddl = "INTEGER" if suffix == "above_ma20" else "REAL"
                conn.execute(f"ALTER TABLE model_feature_daily_v1 ADD COLUMN {column} {ddl}")
                feature_cols.add(column)


def build_where(alias: str, start_date: str, end_date: str) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if start_date:
        clauses.append(f"{alias}.trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append(f"{alias}.trade_date <= ?")
        params.append(end_date)
    return (" AND ".join(clauses) if clauses else "1=1"), params


def copy_index_snapshot(conn: sqlite3.Connection, start_date: str, end_date: str) -> int:
    src_cols = {
        str(row["name"])
        for row in conn.execute("PRAGMA idxsrc.table_info(model_market_index_daily)").fetchall()
    }
    select_sync_run_id = "sync_run_id" if "sync_run_id" in src_cols else "NULL"
    select_build_run_id = "build_run_id" if "build_run_id" in src_cols else "NULL"
    select_updated_at = "updated_at" if "updated_at" in src_cols else "created_at"
    where_sql, params = build_where("s", start_date, end_date)
    conn.execute(
        f"""
        INSERT OR REPLACE INTO model_market_index_daily (
          index_code, index_name, trade_date, open, high, low, close, volume, amount, source,
          build_run_id, sync_run_id, created_at, updated_at
        )
        SELECT
          s.index_code, s.index_name, s.trade_date, s.open, s.high, s.low, s.close, s.volume, s.amount, s.source,
          {select_build_run_id}, {select_sync_run_id},
          COALESCE(s.created_at, CURRENT_TIMESTAMP),
          COALESCE({select_updated_at}, s.created_at, CURRENT_TIMESTAMP)
        FROM idxsrc.model_market_index_daily AS s
        WHERE {where_sql}
        """,
        params,
    )
    return int(conn.execute("SELECT changes()").fetchone()[0] or 0)


def backfill_market_state(conn: sqlite3.Connection, start_date: str, end_date: str, feature_version: str) -> int:
    if not table_exists(conn, "model_market_state_daily_v1"):
        return 0
    date_filter, date_params = build_where("ms", start_date, end_date)
    conn.execute("DROP TABLE IF EXISTS temp.tmp_index_features")
    conn.execute(
        """
        CREATE TEMP TABLE tmp_index_features AS
        WITH idx_base AS (
          SELECT
            index_code,
            trade_date,
            close,
            AVG(close) OVER (PARTITION BY index_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
            LAG(close, 1) OVER (PARTITION BY index_code ORDER BY trade_date) AS prev_close,
            LAG(close, 5) OVER (PARTITION BY index_code ORDER BY trade_date) AS close_5d,
            LAG(close, 20) OVER (PARTITION BY index_code ORDER BY trade_date) AS close_20d
          FROM model_market_index_daily
        ),
        idx AS (
          SELECT
            *,
            LAG(ma20, 5) OVER (PARTITION BY index_code ORDER BY trade_date) AS ma20_5d
          FROM idx_base
        )
        SELECT
          index_code,
          trade_date,
          close,
          ma20,
          CASE WHEN ma20 IS NULL THEN NULL WHEN close >= ma20 THEN 1 ELSE 0 END AS above_ma20,
          CASE WHEN ma20 > 0 THEN (close / ma20 - 1.0) * 100.0 ELSE NULL END AS dist_ma20_pct,
          CASE WHEN ma20_5d > 0 THEN (ma20 / ma20_5d - 1.0) * 100.0 ELSE NULL END AS ma20_slope_5d_pct,
          CASE WHEN prev_close > 0 THEN (close / prev_close - 1.0) * 100.0 ELSE NULL END AS return_1d_pct,
          CASE WHEN close_5d > 0 THEN (close / close_5d - 1.0) * 100.0 ELSE NULL END AS return_5d_pct,
          CASE WHEN close_20d > 0 THEN (close / close_20d - 1.0) * 100.0 ELSE NULL END AS return_20d_pct
        FROM idx
        """
    )

    assignments: list[str] = ["has_index_data = CASE WHEN i_csi1000.close IS NOT NULL THEN 1 ELSE 0 END"]
    for code, (prefix, _name) in INDEX_SPECS.items():
        alias = f"i_{prefix}"
        for suffix in DERIVED_SUFFIXES:
            assignments.append(f"{prefix}_{suffix} = {alias}.{suffix}")

    conn.execute(
        f"""
        UPDATE model_market_state_daily_v1 AS ms
        SET {", ".join(assignments)}
        FROM tmp_index_features AS i_csi1000
        LEFT JOIN tmp_index_features AS i_csi500
          ON i_csi500.trade_date=i_csi1000.trade_date AND i_csi500.index_code='000905.SH'
        LEFT JOIN tmp_index_features AS i_hs300
          ON i_hs300.trade_date=i_csi1000.trade_date AND i_hs300.index_code='000300.SH'
        LEFT JOIN tmp_index_features AS i_sh_index
          ON i_sh_index.trade_date=i_csi1000.trade_date AND i_sh_index.index_code='000001.SH'
        LEFT JOIN tmp_index_features AS i_gem_index
          ON i_gem_index.trade_date=i_csi1000.trade_date AND i_gem_index.index_code='399006.SZ'
        WHERE i_csi1000.trade_date=ms.trade_date
          AND i_csi1000.index_code='000852.SH'
          AND ms.feature_version=?
          AND {date_filter}
        """,
        [feature_version, *date_params],
    )
    return int(conn.execute("SELECT changes()").fetchone()[0] or 0)


def backfill_feature_daily(conn: sqlite3.Connection, start_date: str, end_date: str, feature_version: str) -> int:
    if not table_exists(conn, "model_feature_daily_v1") or not table_exists(conn, "model_market_state_daily_v1"):
        return 0
    assignments: list[str] = []
    for _code, (prefix, _name) in INDEX_SPECS.items():
        for suffix in DERIVED_SUFFIXES:
            assignments.append(f"{prefix}_{suffix} = ms.{prefix}_{suffix}")
    date_filter, date_params = build_where("fd", start_date, end_date)
    conn.execute(
        f"""
        UPDATE model_feature_daily_v1 AS fd
        SET {", ".join(assignments)}
        FROM model_market_state_daily_v1 AS ms
        WHERE ms.trade_date=fd.trade_date
          AND ms.feature_version=fd.feature_version
          AND fd.feature_version=?
          AND {date_filter}
        """,
        [feature_version, *date_params],
    )
    return int(conn.execute("SELECT changes()").fetchone()[0] or 0)


def summarize(conn: sqlite3.Connection, start_date: str, end_date: str, feature_version: str) -> dict[str, object]:
    where_idx, idx_params = build_where("model_market_index_daily", start_date, end_date)
    index_rows = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT index_code, COUNT(*) AS rows, MIN(trade_date) AS min_trade_date, MAX(trade_date) AS max_trade_date
            FROM model_market_index_daily
            WHERE {where_idx}
            GROUP BY index_code
            ORDER BY index_code
            """,
            idx_params,
        ).fetchall()
    ]
    where_state, state_params = build_where("ms", start_date, end_date)
    state = conn.execute(
        f"""
        SELECT
          COUNT(*) AS rows,
          SUM(COALESCE(has_index_data, 0)) AS has_index_rows,
          SUM(csi1000_close IS NOT NULL) AS csi1000_close_rows,
          SUM(csi500_close IS NOT NULL) AS csi500_close_rows,
          SUM(hs300_close IS NOT NULL) AS hs300_close_rows,
          SUM(sh_index_close IS NOT NULL) AS sh_index_close_rows,
          SUM(gem_index_close IS NOT NULL) AS gem_index_close_rows
        FROM model_market_state_daily_v1 AS ms
        WHERE ms.feature_version=?
          AND {where_state}
        """,
        [feature_version, *state_params],
    ).fetchone()
    where_feature, feature_params = build_where("fd", start_date, end_date)
    feature = conn.execute(
        f"""
        SELECT
          COUNT(*) AS rows,
          SUM(csi1000_close IS NOT NULL) AS csi1000_close_rows,
          SUM(csi500_close IS NOT NULL) AS csi500_close_rows,
          SUM(hs300_close IS NOT NULL) AS hs300_close_rows,
          SUM(sh_index_close IS NOT NULL) AS sh_index_close_rows,
          SUM(gem_index_close IS NOT NULL) AS gem_index_close_rows
        FROM model_feature_daily_v1 AS fd
        WHERE fd.feature_version=?
          AND {where_feature}
        """,
        [feature_version, *feature_params],
    ).fetchone()
    return {
        "index_snapshot": index_rows,
        "market_state": dict(state) if state else {},
        "feature_daily": dict(feature) if feature else {},
    }


def main() -> None:
    args = parse_args()
    if not args.index_db.exists():
        raise SystemExit(f"index db missing: {args.index_db}")
    if not args.feature_db.exists():
        raise SystemExit(f"feature db missing: {args.feature_db}")
    with connect(args.feature_db) as conn:
        conn.execute("ATTACH DATABASE ? AS idxsrc", (quote_ro_uri(args.index_db),))
        if not table_exists(conn, "model_market_index_daily", "idxsrc"):
            raise SystemExit("source index db missing model_market_index_daily")
        with conn:
            ensure_feature_schema(conn)
            index_rows = copy_index_snapshot(conn, args.start_date, args.end_date)
            state_rows = backfill_market_state(conn, args.start_date, args.end_date, args.feature_version)
            feature_rows = backfill_feature_daily(conn, args.start_date, args.end_date, args.feature_version)
        payload = {
            "status": "success",
            "index_db": str(args.index_db),
            "feature_db": str(args.feature_db),
            "feature_version": args.feature_version,
            "start_date": args.start_date or None,
            "end_date": args.end_date or None,
            "rows_changed": {
                "model_market_index_daily": index_rows,
                "model_market_state_daily_v1": state_rows,
                "model_feature_daily_v1": feature_rows,
            },
            "summary": summarize(conn, args.start_date, args.end_date, args.feature_version),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
