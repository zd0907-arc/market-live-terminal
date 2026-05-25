#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.scripts.build_model_feature_store import (
    DEFAULT_HEAT_V2_DB,
    DEFAULT_TARGET_DB,
    DEFAULT_TRADABLE_THEME_DB,
    attach_ro,
    build_temp_heat_tables,
    table_exists,
)


HEAT_FEATURE_COLUMNS = [
    "hot_theme_best_rank",
    "hot_theme_score",
    "hot_theme_persistence_score",
    "hot_theme_member_count",
    "hot_theme_is_top10",
    "hot_theme_is_new_hot",
    "hot_theme_is_continuing_hot",
    "hot_theme_is_climax_hot",
    "hot_theme_is_fading",
    "hot_theme_l2_main_net_yi",
]

HEAT_MARKET_COLUMNS = [
    "hot_theme_top1_score",
    "hot_theme_top5_avg_score",
    "hot_theme_top10_amount_ratio",
    "hot_theme_top10_l2_net_yi",
    "hot_theme_new_count",
    "hot_theme_continuing_count",
    "hot_theme_climax_count",
    "hot_theme_fading_count",
    "hot_theme_concentration_top3",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill hot-theme fields in model_feature_store.db.")
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--heat-v2-db", type=Path, default=DEFAULT_HEAT_V2_DB)
    parser.add_argument("--tradable-theme-db", type=Path, default=DEFAULT_TRADABLE_THEME_DB)
    parser.add_argument("--start-date", help="Optional lower bound, YYYY-MM-DD")
    parser.add_argument("--end-date", help="Optional upper bound, YYYY-MM-DD")
    parser.add_argument("--feature-version", default="v1")
    parser.add_argument("--batch-days", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect_target(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.expanduser(), timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def fetch_scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = fetch_one(conn, sql, params)
    if row is None:
        return None
    return row[0]


def resolve_window(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[str, str]:
    if not table_exists(conn, "heat_v2.fine_theme_heat_daily_v2"):
        raise RuntimeError(f"heat db table not found: {args.heat_v2_db}")
    heat_bounds = fetch_one(
        conn,
        "SELECT MIN(trade_date), MAX(trade_date) FROM heat_v2.fine_theme_heat_daily_v2",
    )
    feature_bounds = fetch_one(
        conn,
        """
        SELECT MIN(trade_date), MAX(trade_date)
        FROM model_feature_daily_v1
        WHERE feature_version=?
        """,
        (args.feature_version,),
    )
    if not heat_bounds or not heat_bounds[0] or not feature_bounds or not feature_bounds[0]:
        raise RuntimeError("cannot resolve overlap window")
    start_date = max(args.start_date or heat_bounds[0], heat_bounds[0], feature_bounds[0])
    end_date = min(args.end_date or heat_bounds[1], heat_bounds[1], feature_bounds[1])
    if start_date > end_date:
        raise RuntimeError(f"empty overlap window: {start_date} > {end_date}")
    return start_date, end_date


def fetch_trade_dates(conn: sqlite3.Connection, start_date: str, end_date: str, feature_version: str) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            """
            WITH feature_dates AS (
              SELECT DISTINCT trade_date
              FROM model_feature_daily_v1
              WHERE feature_version=?
                AND trade_date BETWEEN ? AND ?
            ),
            heat_dates AS (
              SELECT DISTINCT trade_date
              FROM heat_v2.fine_theme_heat_daily_v2
              WHERE trade_date BETWEEN ? AND ?
            )
            SELECT f.trade_date
            FROM feature_dates AS f
            JOIN heat_dates AS h ON h.trade_date=f.trade_date
            ORDER BY f.trade_date
            """,
            (feature_version, start_date, end_date, start_date, end_date),
        )
    ]


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def clear_heat_fields(conn: sqlite3.Connection, feature_version: str, date_from: str, date_to: str) -> None:
    conn.execute(
        f"""
        UPDATE model_feature_daily_v1
        SET {", ".join(f"{column}=NULL" for column in HEAT_FEATURE_COLUMNS)},
            has_heat=0
        WHERE feature_version=?
          AND trade_date BETWEEN ? AND ?
        """,
        (feature_version, date_from, date_to),
    )
    conn.execute(
        f"""
        UPDATE model_market_state_daily_v1
        SET {", ".join(f"{column}=NULL" for column in HEAT_MARKET_COLUMNS)},
            has_heat_data=0
        WHERE feature_version=?
          AND trade_date BETWEEN ? AND ?
        """,
        (feature_version, date_from, date_to),
    )


def apply_heat_fields(conn: sqlite3.Connection, feature_version: str, date_from: str, date_to: str) -> dict[str, int]:
    conn.execute(
        """
        UPDATE model_feature_daily_v1
        SET
          hot_theme_best_rank = (
            SELECT hf.best_rank FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_score = (
            SELECT hf.hot_score FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_persistence_score = (
            SELECT hf.persistence_score FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_member_count = (
            SELECT hf.member_count FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_is_top10 = (
            SELECT hf.is_top10 FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_is_new_hot = (
            SELECT hf.is_new_hot FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_is_continuing_hot = (
            SELECT hf.is_continuing_hot FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_is_climax_hot = (
            SELECT hf.is_climax_hot FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_is_fading = (
            SELECT hf.is_fading FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          hot_theme_l2_main_net_yi = (
            SELECT hf.l2_main_net_yi FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          ),
          has_heat = 1
        WHERE feature_version=?
          AND trade_date BETWEEN ? AND ?
          AND EXISTS (
            SELECT 1 FROM tmp_heat_feature AS hf
            WHERE hf.symbol=model_feature_daily_v1.symbol AND hf.trade_date=model_feature_daily_v1.trade_date
          )
        """,
        (feature_version, date_from, date_to),
    )
    feature_changed = int(conn.execute("SELECT changes()").fetchone()[0])

    conn.execute(
        """
        UPDATE model_market_state_daily_v1
        SET
          hot_theme_top1_score = (
            SELECT hm.hot_theme_top1_score FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          hot_theme_top5_avg_score = (
            SELECT hm.hot_theme_top5_avg_score FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          hot_theme_top10_amount_ratio = (
            SELECT hm.hot_theme_top10_amount_ratio FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          hot_theme_top10_l2_net_yi = (
            SELECT hm.hot_theme_top10_l2_net_yi FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          hot_theme_new_count = (
            SELECT hm.hot_theme_new_count FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          hot_theme_continuing_count = (
            SELECT hm.hot_theme_continuing_count FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          hot_theme_climax_count = (
            SELECT hm.hot_theme_climax_count FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          hot_theme_fading_count = (
            SELECT hm.hot_theme_fading_count FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          hot_theme_concentration_top3 = (
            SELECT hm.hot_theme_concentration_top3 FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          ),
          has_heat_data = 1
        WHERE feature_version=?
          AND trade_date BETWEEN ? AND ?
          AND EXISTS (
            SELECT 1 FROM tmp_heat_market AS hm
            WHERE hm.trade_date=model_market_state_daily_v1.trade_date
          )
        """,
        (feature_version, date_from, date_to),
    )
    market_changed = int(conn.execute("SELECT changes()").fetchone()[0])
    return {"feature_rows_updated": feature_changed, "market_rows_updated": market_changed}


def summarize(conn: sqlite3.Connection, feature_version: str) -> dict[str, Any]:
    feature = dict(
        fetch_one(
            conn,
            """
            SELECT
              MIN(CASE WHEN has_heat=1 THEN trade_date END) AS min_heat_date,
              MAX(CASE WHEN has_heat=1 THEN trade_date END) AS max_heat_date,
              SUM(has_heat) AS has_heat_rows,
              COUNT(DISTINCT CASE WHEN has_heat=1 THEN trade_date END) AS has_heat_dates
            FROM model_feature_daily_v1
            WHERE feature_version=?
            """,
            (feature_version,),
        )
    )
    market = dict(
        fetch_one(
            conn,
            """
            SELECT
              MIN(CASE WHEN has_heat_data=1 THEN trade_date END) AS min_heat_date,
              MAX(CASE WHEN has_heat_data=1 THEN trade_date END) AS max_heat_date,
              SUM(has_heat_data) AS has_heat_dates
            FROM model_market_state_daily_v1
            WHERE feature_version=?
            """,
            (feature_version,),
        )
    )
    return {"feature": feature, "market": market}


def main() -> None:
    args = parse_args()
    if args.batch_days < 1:
        raise SystemExit("--batch-days must be >= 1")

    with connect_target(args.target_db) as conn:
        attach_ro(conn, "heat_v2", args.heat_v2_db, required=True)
        attach_ro(conn, "theme_map", args.tradable_theme_db, required=True)
        date_from, date_to = resolve_window(conn, args)
        trade_dates = fetch_trade_dates(conn, date_from, date_to, args.feature_version)
        result: dict[str, Any] = {
            "status": "dry_run" if args.dry_run else "success",
            "generated_at": utc_now(),
            "target_db": str(args.target_db),
            "heat_v2_db": str(args.heat_v2_db),
            "tradable_theme_db": str(args.tradable_theme_db),
            "feature_version": args.feature_version,
            "date_from": date_from,
            "date_to": date_to,
            "trade_day_count": len(trade_dates),
            "batch_days": args.batch_days,
            "rows": {"tmp_heat_feature": 0, "tmp_heat_market": 0, "feature_rows_updated": 0, "market_rows_updated": 0},
        }
        if not trade_dates:
            result["status"] = "no_overlap"
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.dry_run:
            result["summary"] = summarize(conn, args.feature_version)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        for batch in chunks(trade_dates, args.batch_days):
            batch_from = batch[0]
            batch_to = batch[-1]
            with conn:
                heat_rows = build_temp_heat_tables(conn, batch_from, batch_to)
                clear_heat_fields(conn, args.feature_version, batch_from, batch_to)
                changed = apply_heat_fields(conn, args.feature_version, batch_from, batch_to)
            result["rows"]["tmp_heat_feature"] += int(heat_rows.get("heat_feature_rows", 0) or 0)
            result["rows"]["tmp_heat_market"] += int(heat_rows.get("heat_market_rows", 0) or 0)
            result["rows"]["feature_rows_updated"] += changed["feature_rows_updated"]
            result["rows"]["market_rows_updated"] += changed["market_rows_updated"]

        result["summary"] = summarize(conn, args.feature_version)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1) from exc
