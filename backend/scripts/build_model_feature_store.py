#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("DATA_DIR", "/Users/dong/Desktop/AIGC/market-data"))
DEFAULT_TARGET_DB = DATA_ROOT / "selection" / "model_feature_store.db"
DEFAULT_ATOMIC_DB = DATA_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"
DEFAULT_SELECTION_DB = DATA_ROOT / "selection" / "selection_research.db"
DEFAULT_HEAT_V2_DB = DATA_ROOT / "market_heat" / "fine_theme_heat_daily_v2.db"
DEFAULT_HEAT_DB = DEFAULT_HEAT_V2_DB
DEFAULT_TRADABLE_THEME_DB = DATA_ROOT / "market_heat" / "tradable_theme_map.db"
DEFAULT_INDEX_DB = DATA_ROOT / "selection" / "model_market_index_daily.db"
SCHEMA_SQL = REPO_ROOT / "backend" / "scripts" / "sql" / "model_feature_store_schema.sql"
SELECTION_FEATURE_VERSION = "selection_features_v1"
P0_TABLES = [
    "model_market_index_daily",
    "model_market_state_daily_v1",
    "model_feature_daily_v1",
    "model_feature_intraday_shape_v1",
    "model_label_forward_return_v1",
]
LABEL_HORIZONS = (3, 5, 10, 22)


class Median:
    def __init__(self) -> None:
        self.values: list[float] = []

    def step(self, value: Any) -> None:
        if value is None:
            return
        self.values.append(float(value))

    def finalize(self) -> float | None:
        if not self.values:
            return None
        values = sorted(self.values)
        mid = len(values) // 2
        if len(values) % 2:
            return values[mid]
        return (values[mid - 1] + values[mid]) / 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build model_feature_store.db P0 tables.")
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument("--date", help="Single trade date, YYYY-MM-DD")
    date_group.add_argument("--start-date", help="Start trade date, YYYY-MM-DD")
    parser.add_argument("--end-date", help="End trade date, YYYY-MM-DD; required with --start-date")
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--atomic-db", type=Path, default=Path(os.getenv("ATOMIC_COMPACT_DB_PATH", DEFAULT_ATOMIC_DB)))
    parser.add_argument("--selection-db", type=Path, default=Path(os.getenv("SELECTION_DB_PATH", DEFAULT_SELECTION_DB)))
    parser.add_argument("--heat-db", type=Path, default=Path(os.getenv("FINE_THEME_HEAT_DB", DEFAULT_HEAT_DB)))
    parser.add_argument("--heat-v2-db", type=Path, default=Path(os.getenv("FINE_THEME_HEAT_V2_DB", DEFAULT_HEAT_V2_DB)))
    parser.add_argument("--tradable-theme-db", type=Path, default=Path(os.getenv("TRADABLE_THEME_MAP_DB", DEFAULT_TRADABLE_THEME_DB)))
    parser.add_argument("--index-csv", type=Path, help="Optional index daily CSV")
    parser.add_argument("--index-db", type=Path, default=Path(os.getenv("MODEL_INDEX_DB", DEFAULT_INDEX_DB)))
    parser.add_argument("--index-table", default=os.getenv("MODEL_INDEX_TABLE", "model_market_index_daily"))
    parser.add_argument("--feature-version", default="v1")
    parser.add_argument("--warmup-days", type=int, default=60)
    parser.add_argument("--label-lookahead-days", type=int, default=22)
    parser.add_argument("--reset-target", action="store_true", help="Delete target DB before building")
    parser.add_argument("--skip-labels", action="store_true")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_date(raw: str, name: str) -> str:
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"{name} must be YYYY-MM-DD: {raw}") from exc
    return raw


def requested_window(args: argparse.Namespace) -> tuple[str, str]:
    if args.date:
        date = validate_date(args.date, "--date")
        if args.end_date:
            raise SystemExit("--end-date cannot be used with --date")
        return date, date
    if not args.end_date:
        raise SystemExit("--end-date is required with --start-date")
    start_date = validate_date(args.start_date, "--start-date")
    end_date = validate_date(args.end_date, "--end-date")
    if start_date > end_date:
        raise SystemExit("--start-date must be <= --end-date")
    return start_date, end_date


def quote_file_uri(path: Path, readonly: bool = True) -> str:
    resolved = path.expanduser().resolve()
    if os.name == "nt":
        return str(resolved)
    mode = "ro" if readonly else "rwc"
    return f"file:{quote(str(resolved))}?mode={mode}"


def connect_target(path: Path) -> sqlite3.Connection:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=120, uri=False)
    conn.row_factory = sqlite3.Row
    conn.create_aggregate("median", 1, Median)
    conn.create_function("minute_from_open", 1, minute_from_open)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def attach_ro(conn: sqlite3.Connection, alias: str, path: Path, required: bool = True) -> bool:
    path = path.expanduser()
    if not path.exists():
        if required:
            raise FileNotFoundError(str(path))
        return False
    conn.execute(f"ATTACH DATABASE ? AS {alias}", (quote_file_uri(path),))
    return True


def table_exists(conn: sqlite3.Connection, qualified: str) -> bool:
    if "." in qualified:
        schema, table = qualified.split(".", 1)
    else:
        schema, table = "main", qualified
    attached = {row[1] for row in conn.execute("PRAGMA database_list")}
    if schema not in attached:
        return False
    row = conn.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def fetch_scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Any:
    row = conn.execute(sql, tuple(params)).fetchone()
    if row is None:
        return None
    return row[0]


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def minute_from_open(raw: Any) -> int | None:
    if raw is None:
        return None
    text = str(raw)
    time_part = text[-8:] if len(text) >= 8 else text
    try:
        hour, minute, _second = [int(part) for part in time_part.split(":")]
    except ValueError:
        return None
    total = hour * 60 + minute
    morning_open = 9 * 60 + 30
    morning_close = 11 * 60 + 30
    afternoon_open = 13 * 60
    if total < morning_open:
        return None
    if total <= morning_close:
        return total - morning_open
    if total >= afternoon_open:
        return 120 + (total - afternoon_open)
    return 120


def load_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    ensure_schema_migrations(conn)


def ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "model_label_forward_return_v1"):
        return
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(model_label_forward_return_v1)").fetchall()
    }
    if "label_end_date" not in columns:
        conn.execute("ALTER TABLE model_label_forward_return_v1 ADD COLUMN label_end_date TEXT")
    if "label_complete_asof_date" not in columns:
        conn.execute("ALTER TABLE model_label_forward_return_v1 ADD COLUMN label_complete_asof_date TEXT")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_label_forward_return_v1_label_complete_asof
        ON model_label_forward_return_v1(horizon_days, label_complete_asof_date)
        """
    )


def all_trade_dates(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT trade_date FROM atomic.atomic_trade_daily ORDER BY trade_date").fetchall()
    return [str(row["trade_date"]) for row in rows]


def resolve_dates(conn: sqlite3.Connection, start_date: str, end_date: str, warmup_days: int, label_days: int) -> dict[str, Any]:
    dates = all_trade_dates(conn)
    requested = [date for date in dates if start_date <= date <= end_date]
    if not requested:
        raise RuntimeError(f"No atomic_trade_daily dates in requested range {start_date}..{end_date}")
    first_idx = dates.index(requested[0])
    last_idx = dates.index(requested[-1])
    warmup_start_idx = max(0, first_idx - warmup_days)
    label_end_idx = min(len(dates) - 1, last_idx + label_days)
    return {
        "requested_dates": requested,
        "date_from": requested[0],
        "date_to": requested[-1],
        "extended_start": dates[warmup_start_idx],
        "label_end": dates[label_end_idx],
        "available_label_days_after_end": max(0, label_end_idx - last_idx),
    }


def create_temp_date_table(conn: sqlite3.Connection, dates: list[str]) -> None:
    conn.execute("DROP TABLE IF EXISTS temp.tmp_request_dates")
    conn.execute("CREATE TEMP TABLE tmp_request_dates(trade_date TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO tmp_request_dates(trade_date) VALUES (?)", [(date,) for date in dates])


def start_run(conn: sqlite3.Connection, args: argparse.Namespace, run_id: str, date_info: dict[str, Any]) -> None:
    config = {
        "date_from": date_info["date_from"],
        "date_to": date_info["date_to"],
        "requested_dates": date_info["requested_dates"],
        "extended_start": date_info["extended_start"],
        "label_end": date_info["label_end"],
        "warmup_days": args.warmup_days,
        "label_lookahead_days": args.label_lookahead_days,
        "skip_labels": args.skip_labels,
        "index_csv": str(args.index_csv) if args.index_csv else None,
        "index_db": str(args.index_db) if args.index_db else None,
        "index_table": args.index_table,
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO model_feature_build_runs (
          run_id, feature_version, date_from, date_to, status,
          source_atomic_db, source_selection_db, source_heat_db, source_market_db,
          git_commit, config_json, started_at
        )
        VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            args.feature_version,
            date_info["date_from"],
            date_info["date_to"],
            str(args.atomic_db),
            str(args.selection_db),
            json.dumps({"heat_db": str(args.heat_db), "heat_v2_db": str(args.heat_v2_db)}, ensure_ascii=False),
            None,
            git_commit(),
            json.dumps(config, ensure_ascii=False, sort_keys=True),
            utc_now(),
        ),
    )


def finish_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    row_counts: dict[str, int] | None = None,
    validation: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE model_feature_build_runs
        SET status=?,
            row_counts_json=?,
            validation_json=?,
            finished_at=?,
            error_message=?
        WHERE run_id=?
        """,
        (
            status,
            json.dumps(row_counts or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(validation or {}, ensure_ascii=False, sort_keys=True),
            utc_now(),
            error,
            run_id,
        ),
    )


def clear_target_range(conn: sqlite3.Connection, feature_version: str, date_from: str, date_to: str) -> None:
    conn.execute("DELETE FROM model_market_state_daily_v1 WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)")
    for table in ["model_feature_daily_v1", "model_feature_intraday_shape_v1", "model_label_forward_return_v1"]:
        conn.execute(
            f"""
            DELETE FROM {table}
            WHERE feature_version = ?
              AND trade_date IN (SELECT trade_date FROM tmp_request_dates)
            """,
            (feature_version,),
        )
    conn.execute(
        """
        DELETE FROM model_feature_manifest
        WHERE feature_version = ? AND date_from = ? AND date_to = ?
        """,
        (feature_version, date_from, date_to),
    )


def normalize_index_code(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in {"000852", "SH000852", "000852.SH"}:
        return "000852.SH"
    if upper in {"000905", "SH000905", "000905.SH"}:
        return "000905.SH"
    if upper in {"000300", "SH000300", "000300.SH"}:
        return "000300.SH"
    if upper in {"000001", "SH000001", "000001.SH"}:
        return "000001.SH"
    if upper in {"399006", "SZ399006", "399006.SZ"}:
        return "399006.SZ"
    if upper.startswith("SH") and len(upper) == 8:
        return f"{upper[2:]}.SH"
    if upper.startswith("SZ") and len(upper) == 8:
        return f"{upper[2:]}.SZ"
    return upper


def import_index_sources(conn: sqlite3.Connection, args: argparse.Namespace, run_id: str, date_info: dict[str, Any]) -> int:
    rows = 0
    if args.index_db and args.index_db.expanduser().exists():
        attach_ro(conn, "idxsrc", args.index_db, required=False)
        rows += import_index_db(conn, args.index_table, run_id, date_info["extended_start"], date_info["date_to"])
    rows += import_index_csv(conn, args.index_csv, run_id)
    return rows


def import_index_db(conn: sqlite3.Connection, table: str, run_id: str, start_date: str, end_date: str) -> int:
    if not table or not table_exists(conn, f"idxsrc.{table}"):
        return 0
    columns = {
        str(row["name"])
        for row in conn.execute(f"PRAGMA idxsrc.table_info({table})").fetchall()
    }
    code_col = next((item for item in ["index_code", "code", "symbol"] if item in columns), "")
    date_col = next((item for item in ["trade_date", "date"] if item in columns), "")
    close_col = "close" if "close" in columns else ""
    if not code_col or not date_col or not close_col:
        return 0
    name_col = next((item for item in ["index_name", "name"] if item in columns), "")
    open_col = "open" if "open" in columns else "NULL"
    high_col = "high" if "high" in columns else "NULL"
    low_col = "low" if "low" in columns else "NULL"
    volume_col = "volume" if "volume" in columns else "NULL"
    amount_col = "amount" if "amount" in columns else "NULL"
    name_expr = name_col if name_col else code_col
    rows = conn.execute(
        f"""
        SELECT {code_col} AS code, {name_expr} AS name, {date_col} AS trade_date,
               {open_col} AS open, {high_col} AS high, {low_col} AS low,
               {close_col} AS close, {volume_col} AS volume, {amount_col} AS amount
        FROM idxsrc.{table}
        WHERE {date_col} BETWEEN ? AND ?
        """,
        (start_date, end_date),
    ).fetchall()
    payload = []
    for row in rows:
        index_code = normalize_index_code(row["code"])
        if not index_code:
            continue
        payload.append(
            (
                index_code,
                row["name"] or index_code,
                row["trade_date"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
                row["amount"],
                f"{table}@idxsrc",
                run_id,
            )
        )
    conn.executemany(
        """
        INSERT OR REPLACE INTO model_market_index_daily (
          index_code, index_name, trade_date, open, high, low, close, volume, amount, source, build_run_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )
    return len(payload)


def import_index_csv(conn: sqlite3.Connection, csv_path: Path | None, run_id: str) -> int:
    if not csv_path:
        return 0
    csv_path = csv_path.expanduser()
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))
    rows: list[tuple[Any, ...]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            trade_date = raw.get("trade_date") or raw.get("date")
            index_code = normalize_index_code(raw.get("index_code") or raw.get("code") or raw.get("symbol"))
            close = raw.get("close")
            if not trade_date or not index_code or close in (None, ""):
                continue
            rows.append(
                (
                    index_code,
                    raw.get("index_name") or raw.get("name") or index_code,
                    trade_date,
                    as_float(raw.get("open")),
                    as_float(raw.get("high")),
                    as_float(raw.get("low")),
                    as_float(close),
                    as_float(raw.get("volume")),
                    as_float(raw.get("amount")),
                    str(csv_path),
                    run_id,
                )
            )
    conn.executemany(
        """
        INSERT OR REPLACE INTO model_market_index_daily (
          index_code, index_name, trade_date, open, high, low, close, volume, amount, source, build_run_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def as_float(raw: Any) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_temp_heat_tables(conn: sqlite3.Connection, date_from: str, date_to: str) -> dict[str, Any]:
    conn.execute("DROP TABLE IF EXISTS temp.tmp_heat_feature")
    conn.execute(
        """
        CREATE TEMP TABLE tmp_heat_feature (
          symbol TEXT NOT NULL,
          trade_date TEXT NOT NULL,
          best_rank INTEGER,
          hot_score REAL,
          persistence_score REAL,
          member_count INTEGER,
          is_top10 INTEGER,
          is_new_hot INTEGER,
          is_continuing_hot INTEGER,
          is_climax_hot INTEGER,
          is_fading INTEGER,
          l2_main_net_yi REAL,
          PRIMARY KEY (symbol, trade_date)
        )
        """
    )
    conn.execute("DROP TABLE IF EXISTS temp.tmp_heat_market")
    conn.execute(
        """
        CREATE TEMP TABLE tmp_heat_market (
          trade_date TEXT PRIMARY KEY,
          hot_theme_top1_score REAL,
          hot_theme_top5_avg_score REAL,
          hot_theme_top10_amount_ratio REAL,
          hot_theme_top10_l2_net_yi REAL,
          hot_theme_new_count INTEGER,
          hot_theme_continuing_count INTEGER,
          hot_theme_climax_count INTEGER,
          hot_theme_fading_count INTEGER,
          hot_theme_concentration_top3 REAL
        )
        """
    )

    heat_feature_rows = 0
    heat_market_rows = 0
    if (
        table_exists(conn, "heat_v2.fine_theme_heat_daily_v2")
        and table_exists(conn, "theme_map.clean_stock_sector_memberships")
        and table_exists(conn, "theme_map.clean_sector_boards")
    ):
        conn.execute(
            """
            INSERT OR REPLACE INTO tmp_heat_feature (
              symbol, trade_date, best_rank, hot_score, persistence_score, member_count,
              is_top10, is_new_hot, is_continuing_hot, is_climax_hot, is_fading, l2_main_net_yi
            )
            WITH ranked AS (
              SELECT
                lower(m.symbol) AS symbol,
                h.trade_date,
                h.rank_today AS best_rank,
                h.hot_score,
                h.hot_score AS persistence_score,
                h.member_count,
                CASE WHEN h.rank_today <= 10 THEN 1 ELSE 0 END AS is_top10,
                h.first_hot AS is_new_hot,
                h.mainline_continue AS is_continuing_hot,
                h.today_strong AS is_climax_hot,
                h.fading_watch AS is_fading,
                h.l2_net_inflow_yi AS l2_main_net_yi,
                ROW_NUMBER() OVER (
                  PARTITION BY lower(m.symbol), h.trade_date
                  ORDER BY CASE WHEN h.rank_today IS NULL THEN 999999 ELSE h.rank_today END, h.hot_score DESC
                ) AS rn
              FROM heat_v2.fine_theme_heat_daily_v2 AS h
              JOIN theme_map.clean_stock_sector_memberships AS m
                ON m.sector_code=h.sector_code AND m.sector_type=h.sector_type
              JOIN theme_map.clean_sector_boards AS b
                ON b.sector_code=h.sector_code AND b.sector_type=h.sector_type
              WHERE h.trade_date BETWEEN ? AND ?
                AND b.clean_status != 'excluded'
            )
            SELECT
              symbol, trade_date, best_rank, hot_score, persistence_score, member_count,
              is_top10, is_new_hot, is_continuing_hot, is_climax_hot, is_fading, l2_main_net_yi
            FROM ranked
            WHERE rn = 1
            """,
            (date_from, date_to),
        )
        heat_feature_rows = int(fetch_scalar(conn, "SELECT COUNT(*) FROM tmp_heat_feature") or 0)

    if table_exists(conn, "heat.fine_theme_member_daily") and table_exists(conn, "heat.fine_theme_heat_daily"):
        conn.execute(
            """
            INSERT OR REPLACE INTO tmp_heat_feature (
              symbol, trade_date, best_rank, hot_score, persistence_score, member_count,
              is_top10, is_new_hot, is_continuing_hot, is_climax_hot, is_fading, l2_main_net_yi
            )
            WITH ranked AS (
              SELECT
                m.symbol,
                m.trade_date,
                h.hot_rank AS best_rank,
                h.hot_score,
                h.persistence_score,
                h.member_count,
                CASE WHEN h.hot_rank <= 10 THEN 1 ELSE 0 END AS is_top10,
                COALESCE(l.is_new_hot, 0) AS is_new_hot,
                COALESCE(l.is_continuing_hot, 0) AS is_continuing_hot,
                COALESCE(l.is_climax_hot, 0) AS is_climax_hot,
                COALESCE(l.is_fading, 0) AS is_fading,
                m.l2_main_net_yi,
                ROW_NUMBER() OVER (
                  PARTITION BY m.symbol, m.trade_date
                  ORDER BY CASE WHEN h.hot_rank IS NULL THEN 999999 ELSE h.hot_rank END, h.hot_score DESC
                ) AS rn
              FROM heat.fine_theme_member_daily AS m
              JOIN heat.fine_theme_heat_daily AS h
                ON h.trade_date=m.trade_date AND h.theme_id=m.theme_id
              LEFT JOIN heat.fine_theme_lifecycle_daily AS l
                ON l.trade_date=m.trade_date AND l.theme_id=m.theme_id
              WHERE m.trade_date BETWEEN ? AND ?
            )
            SELECT
              symbol, trade_date, best_rank, hot_score, persistence_score, member_count,
              is_top10, is_new_hot, is_continuing_hot, is_climax_hot, is_fading, l2_main_net_yi
            FROM ranked
            WHERE rn = 1
            """,
            (date_from, date_to),
        )
        heat_feature_rows = int(fetch_scalar(conn, "SELECT COUNT(*) FROM tmp_heat_feature") or 0)

        conn.execute(
            """
            INSERT OR REPLACE INTO tmp_heat_market
            WITH base AS (
              SELECT
                h.trade_date,
                h.hot_rank,
                h.hot_score,
                h.amount_ratio,
                h.l2_main_net_yi,
                COALESCE(l.is_new_hot, 0) AS is_new_hot,
                COALESCE(l.is_continuing_hot, 0) AS is_continuing_hot,
                COALESCE(l.is_climax_hot, 0) AS is_climax_hot,
                COALESCE(l.is_fading, 0) AS is_fading
              FROM heat.fine_theme_heat_daily AS h
              LEFT JOIN heat.fine_theme_lifecycle_daily AS l
                ON l.trade_date=h.trade_date AND l.theme_id=h.theme_id
              WHERE h.trade_date BETWEEN ? AND ?
            )
            SELECT
              trade_date,
              MAX(CASE WHEN hot_rank = 1 THEN hot_score END) AS hot_theme_top1_score,
              AVG(CASE WHEN hot_rank <= 5 THEN hot_score END) AS hot_theme_top5_avg_score,
              SUM(CASE WHEN hot_rank <= 10 THEN amount_ratio ELSE 0 END) AS hot_theme_top10_amount_ratio,
              SUM(CASE WHEN hot_rank <= 10 THEN l2_main_net_yi ELSE 0 END) AS hot_theme_top10_l2_net_yi,
              SUM(CASE WHEN hot_rank <= 10 THEN is_new_hot ELSE 0 END) AS hot_theme_new_count,
              SUM(CASE WHEN hot_rank <= 10 THEN is_continuing_hot ELSE 0 END) AS hot_theme_continuing_count,
              SUM(CASE WHEN hot_rank <= 10 THEN is_climax_hot ELSE 0 END) AS hot_theme_climax_count,
              SUM(CASE WHEN hot_rank <= 10 THEN is_fading ELSE 0 END) AS hot_theme_fading_count,
              SUM(CASE WHEN hot_rank <= 3 THEN amount_ratio ELSE 0 END) AS hot_theme_concentration_top3
            FROM base
            GROUP BY trade_date
            """,
            (date_from, date_to),
        )
        heat_market_rows = int(fetch_scalar(conn, "SELECT COUNT(*) FROM tmp_heat_market") or 0)

    if table_exists(conn, "heat_v2.fine_theme_heat_daily_v2"):
        conn.execute(
            """
            INSERT OR REPLACE INTO tmp_heat_market
            WITH base AS (
              SELECT *
              FROM heat_v2.fine_theme_heat_daily_v2
              WHERE trade_date BETWEEN ? AND ?
            )
            SELECT
              trade_date,
              MAX(CASE WHEN rank_today = 1 THEN hot_score END) AS hot_theme_top1_score,
              AVG(CASE WHEN rank_today <= 5 THEN hot_score END) AS hot_theme_top5_avg_score,
              SUM(CASE WHEN rank_today <= 10 THEN amount_ratio ELSE 0 END) AS hot_theme_top10_amount_ratio,
              SUM(CASE WHEN rank_today <= 10 THEN l2_net_inflow_yi ELSE 0 END) AS hot_theme_top10_l2_net_yi,
              SUM(CASE WHEN rank_today <= 10 THEN first_hot ELSE 0 END) AS hot_theme_new_count,
              SUM(CASE WHEN rank_today <= 10 THEN mainline_continue ELSE 0 END) AS hot_theme_continuing_count,
              SUM(CASE WHEN rank_today <= 10 THEN today_strong ELSE 0 END) AS hot_theme_climax_count,
              SUM(CASE WHEN rank_today <= 10 THEN fading_watch ELSE 0 END) AS hot_theme_fading_count,
              SUM(CASE WHEN rank_today <= 3 THEN amount_ratio ELSE 0 END) AS hot_theme_concentration_top3
            FROM base
            GROUP BY trade_date
            """,
            (date_from, date_to),
        )
        heat_market_rows = int(fetch_scalar(conn, "SELECT COUNT(*) FROM tmp_heat_market") or 0)

    return {"heat_feature_rows": heat_feature_rows, "heat_market_rows": heat_market_rows}


def build_market_state(conn: sqlite3.Connection, feature_version: str, run_id: str, extended_start: str, date_to: str) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO model_market_state_daily_v1 (
          trade_date, feature_version,
          market_total_amount_yi, market_total_amount_ma20_yi, market_amount_ratio_20d,
          market_mean_return_pct, market_median_return_pct, market_advancer_ratio, market_decliner_ratio,
          market_up_gt3_count, market_down_lt_minus3_count,
          limit_up_count, limit_down_count, touch_limit_up_count, broken_limit_up_count,
          sealed_limit_up_count, broken_limit_up_ratio,
          csi1000_close, csi1000_ma20, csi1000_above_ma20, csi1000_dist_ma20_pct,
          csi1000_ma20_slope_5d_pct, csi1000_return_1d_pct, csi1000_return_5d_pct, csi1000_return_20d_pct,
          csi500_above_ma20, hs300_above_ma20, sh_index_above_ma20, gem_index_above_ma20,
          hot_theme_top1_score, hot_theme_top5_avg_score, hot_theme_top10_amount_ratio,
          hot_theme_top10_l2_net_yi, hot_theme_new_count, hot_theme_continuing_count,
          hot_theme_climax_count, hot_theme_fading_count, hot_theme_concentration_top3,
          has_index_data, has_heat_data, has_order_data, has_book_data, build_run_id
        )
        WITH daily_returns AS (
          SELECT
            t.trade_date,
            t.total_amount,
            CASE
              WHEN COALESCE(l.prev_close, 0) > 0 THEN (t.close / l.prev_close - 1.0) * 100.0
              ELSE NULL
            END AS return_pct
          FROM atomic.atomic_trade_daily AS t
          LEFT JOIN atomic.atomic_limit_state_daily AS l
            ON l.symbol=t.symbol AND l.trade_date=t.trade_date
          WHERE t.trade_date BETWEEN ? AND ?
        ),
        trade_agg AS (
          SELECT
            trade_date,
            SUM(total_amount) / 1e8 AS market_total_amount_yi,
            AVG(return_pct) AS market_mean_return_pct,
            median(return_pct) AS market_median_return_pct,
            AVG(CASE WHEN return_pct > 0 THEN 1.0 ELSE 0.0 END) AS market_advancer_ratio,
            AVG(CASE WHEN return_pct < 0 THEN 1.0 ELSE 0.0 END) AS market_decliner_ratio,
            SUM(CASE WHEN return_pct > 3 THEN 1 ELSE 0 END) AS market_up_gt3_count,
            SUM(CASE WHEN return_pct < -3 THEN 1 ELSE 0 END) AS market_down_lt_minus3_count
          FROM daily_returns
          GROUP BY trade_date
        ),
        trade_window AS (
          SELECT
            *,
            AVG(market_total_amount_yi) OVER (
              ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS market_total_amount_ma20_yi
          FROM trade_agg
        ),
        limit_agg AS (
          SELECT
            trade_date,
            SUM(is_limit_up_close) AS limit_up_count,
            SUM(is_limit_down_close) AS limit_down_count,
            SUM(touch_limit_up) AS touch_limit_up_count,
            SUM(broken_limit_up) AS broken_limit_up_count,
            SUM(CASE WHEN is_limit_up_close=1 AND broken_limit_up=0 THEN 1 ELSE 0 END) AS sealed_limit_up_count
          FROM atomic.atomic_limit_state_daily
          WHERE trade_date BETWEEN ? AND ?
          GROUP BY trade_date
        ),
        order_cov AS (
          SELECT trade_date, 1 AS has_order_data
          FROM atomic.atomic_order_daily
          WHERE trade_date BETWEEN ? AND ?
          GROUP BY trade_date
        ),
        book_cov AS (
          SELECT trade_date, 1 AS has_book_data
          FROM atomic.atomic_book_state_daily
          WHERE trade_date BETWEEN ? AND ?
          GROUP BY trade_date
        ),
        idx_base AS (
          SELECT
            index_code,
            trade_date,
            close,
            AVG(close) OVER (PARTITION BY index_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
            LAG(close, 1) OVER (PARTITION BY index_code ORDER BY trade_date) AS prev_close,
            LAG(close, 5) OVER (PARTITION BY index_code ORDER BY trade_date) AS close_5d,
            LAG(close, 20) OVER (PARTITION BY index_code ORDER BY trade_date) AS close_20d
          FROM model_market_index_daily
          WHERE trade_date BETWEEN ? AND ?
        ),
        idx AS (
          SELECT
            *,
            LAG(ma20, 5) OVER (PARTITION BY index_code ORDER BY trade_date) AS ma20_5d
          FROM idx_base
        ),
        csi1000 AS (
          SELECT * FROM idx WHERE index_code = '000852.SH'
        )
        SELECT
          tw.trade_date,
          ? AS feature_version,
          tw.market_total_amount_yi,
          tw.market_total_amount_ma20_yi,
          CASE
            WHEN tw.market_total_amount_ma20_yi > 0 THEN tw.market_total_amount_yi / tw.market_total_amount_ma20_yi
            ELSE NULL
          END AS market_amount_ratio_20d,
          tw.market_mean_return_pct,
          tw.market_median_return_pct,
          tw.market_advancer_ratio,
          tw.market_decliner_ratio,
          tw.market_up_gt3_count,
          tw.market_down_lt_minus3_count,
          COALESCE(la.limit_up_count, 0),
          COALESCE(la.limit_down_count, 0),
          COALESCE(la.touch_limit_up_count, 0),
          COALESCE(la.broken_limit_up_count, 0),
          COALESCE(la.sealed_limit_up_count, 0),
          CASE
            WHEN la.touch_limit_up_count > 0 THEN CAST(la.broken_limit_up_count AS REAL) / la.touch_limit_up_count
            ELSE NULL
          END AS broken_limit_up_ratio,
          c.close AS csi1000_close,
          c.ma20 AS csi1000_ma20,
          CASE WHEN c.ma20 IS NULL THEN NULL WHEN c.close >= c.ma20 THEN 1 ELSE 0 END AS csi1000_above_ma20,
          CASE WHEN c.ma20 > 0 THEN (c.close / c.ma20 - 1.0) * 100.0 ELSE NULL END AS csi1000_dist_ma20_pct,
          CASE WHEN c.ma20_5d > 0 THEN (c.ma20 / c.ma20_5d - 1.0) * 100.0 ELSE NULL END AS csi1000_ma20_slope_5d_pct,
          CASE WHEN c.prev_close > 0 THEN (c.close / c.prev_close - 1.0) * 100.0 ELSE NULL END AS csi1000_return_1d_pct,
          CASE WHEN c.close_5d > 0 THEN (c.close / c.close_5d - 1.0) * 100.0 ELSE NULL END AS csi1000_return_5d_pct,
          CASE WHEN c.close_20d > 0 THEN (c.close / c.close_20d - 1.0) * 100.0 ELSE NULL END AS csi1000_return_20d_pct,
          NULL AS csi500_above_ma20,
          NULL AS hs300_above_ma20,
          NULL AS sh_index_above_ma20,
          NULL AS gem_index_above_ma20,
          hm.hot_theme_top1_score,
          hm.hot_theme_top5_avg_score,
          hm.hot_theme_top10_amount_ratio,
          hm.hot_theme_top10_l2_net_yi,
          hm.hot_theme_new_count,
          hm.hot_theme_continuing_count,
          hm.hot_theme_climax_count,
          hm.hot_theme_fading_count,
          hm.hot_theme_concentration_top3,
          CASE WHEN c.close IS NOT NULL THEN 1 ELSE 0 END AS has_index_data,
          CASE WHEN hm.trade_date IS NOT NULL THEN 1 ELSE 0 END AS has_heat_data,
          COALESCE(oc.has_order_data, 0) AS has_order_data,
          COALESCE(bc.has_book_data, 0) AS has_book_data,
          ? AS build_run_id
        FROM trade_window AS tw
        JOIN tmp_request_dates AS rd ON rd.trade_date=tw.trade_date
        LEFT JOIN limit_agg AS la ON la.trade_date=tw.trade_date
        LEFT JOIN csi1000 AS c ON c.trade_date=tw.trade_date
        LEFT JOIN tmp_heat_market AS hm ON hm.trade_date=tw.trade_date
        LEFT JOIN order_cov AS oc ON oc.trade_date=tw.trade_date
        LEFT JOIN book_cov AS bc ON bc.trade_date=tw.trade_date
        """,
        (
            extended_start,
            date_to,
            extended_start,
            date_to,
            extended_start,
            date_to,
            extended_start,
            date_to,
            extended_start,
            date_to,
            feature_version,
            run_id,
        ),
    )
    return int(conn.execute("SELECT changes()").fetchone()[0])


def build_feature_daily(conn: sqlite3.Connection, feature_version: str, run_id: str, extended_start: str, date_to: str) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO model_feature_daily_v1 (
          symbol, trade_date, feature_version, name, board_type, risk_flag_type, market_cap,
          open, high, low, close, prev_close,
          return_1d_pct, return_3d_pct, return_5d_pct, return_10d_pct, return_20d_pct,
          volatility_10d, volatility_20d, ma20, ma60, dist_ma20_pct, dist_ma60_pct,
          price_position_20d, price_position_60d, breakout_vs_prev20_high_pct, drawdown_from_20d_high_pct,
          amount_yi, amount_ratio_20d, trade_count, trade_count_ratio_20d,
          l1_main_net_yi, l1_super_net_yi, l2_main_net_yi, l2_super_net_yi,
          l1_main_net_ratio, l1_super_net_ratio, l2_main_net_ratio, l2_super_net_ratio,
          active_buy_strength, open_30m_l2_main_net_ratio, last_30m_l2_main_net_ratio,
          am_l2_main_net_ratio, pm_l2_main_net_ratio, positive_l2_bar_ratio,
          oib_delta_yi, cvd_delta_yi, oib_ratio, cvd_ratio,
          add_buy_ratio, add_sell_ratio, cancel_buy_ratio, cancel_sell_ratio,
          open_60m_oib_ratio, last_30m_oib_ratio, open_60m_cvd_ratio, last_30m_cvd_ratio,
          positive_oib_bar_ratio, positive_cvd_bar_ratio, positive_oib_streak_max,
          oib_top3_concentration_ratio, buy_support_ratio, sell_pressure_ratio, support_pressure_spread,
          avg_book_imbalance_ratio, close_book_imbalance_ratio, avg_book_depth_ratio, close_book_depth_ratio,
          bid_dominant_bar_ratio, ask_dominant_bar_ratio, thin_book_bar_ratio,
          close_bid_resting_amount_yi, close_ask_resting_amount_yi, close_bid_ask_amount_ratio,
          touch_limit_up, touch_limit_down, is_limit_up_close, is_limit_down_close,
          broken_limit_up, broken_limit_down, limit_state_label,
          first_touch_limit_up_min, last_touch_limit_up_min,
          hot_theme_best_rank, hot_theme_score, hot_theme_persistence_score, hot_theme_member_count,
          hot_theme_is_top10, hot_theme_is_new_hot, hot_theme_is_continuing_hot,
          hot_theme_is_climax_hot, hot_theme_is_fading, hot_theme_l2_main_net_yi,
          csi1000_above_ma20, csi1000_dist_ma20_pct, market_advancer_ratio,
          market_median_return_pct, market_total_amount_yi, market_amount_ratio_20d,
          market_limit_up_count, market_broken_limit_up_ratio, hot_theme_concentration_top3,
          has_trade_daily, has_trade_5m, has_order_daily, has_order_5m,
          has_book_daily, has_book_5m, has_limit_daily, has_heat, has_market_state,
          build_run_id
        )
        WITH trade_base AS (
          SELECT
            t.*,
            AVG(t.total_amount) OVER (
              PARTITION BY t.symbol ORDER BY t.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS amount_ma20,
            AVG(t.trade_count) OVER (
              PARTITION BY t.symbol ORDER BY t.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS trade_count_ma20,
            MAX(t.high) OVER (
              PARTITION BY t.symbol ORDER BY t.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS high_20d
          FROM atomic.atomic_trade_daily AS t
          WHERE t.trade_date BETWEEN ? AND ?
        ),
        trade5_cov AS (
          SELECT symbol, trade_date, 1 AS has_trade_5m
          FROM atomic.atomic_trade_5m
          WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)
          GROUP BY symbol, trade_date
        ),
        order5_cov AS (
          SELECT symbol, trade_date, 1 AS has_order_5m
          FROM atomic.atomic_order_5m
          WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)
          GROUP BY symbol, trade_date
        ),
        book5_cov AS (
          SELECT symbol, trade_date, 1 AS has_book_5m
          FROM atomic.atomic_book_state_5m
          WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)
          GROUP BY symbol, trade_date
        )
        SELECT
          t.symbol,
          t.trade_date,
          ? AS feature_version,
          sf.name,
          l.board_type,
          l.risk_flag_type,
          sf.market_cap,
          t.open,
          t.high,
          t.low,
          t.close,
          COALESCE(sf.prev_close, l.prev_close),
          COALESCE(sf.daily_return_pct, CASE WHEN l.prev_close > 0 THEN (t.close / l.prev_close - 1.0) * 100.0 ELSE NULL END),
          sf.return_3d_pct,
          sf.return_5d_pct,
          sf.return_10d_pct,
          sf.return_20d_pct,
          sf.volatility_10d,
          sf.volatility_20d,
          sf.ma20,
          sf.ma60,
          sf.dist_ma20_pct,
          sf.dist_ma60_pct,
          sf.price_position_20d,
          sf.price_position_60d,
          sf.breakout_vs_prev20_high_pct,
          CASE WHEN t.high_20d > 0 THEN (t.close / t.high_20d - 1.0) * 100.0 ELSE NULL END,
          t.total_amount / 1e8,
          CASE WHEN t.amount_ma20 > 0 THEN t.total_amount / t.amount_ma20 ELSE NULL END,
          t.trade_count,
          CASE WHEN t.trade_count_ma20 > 0 THEN CAST(t.trade_count AS REAL) / t.trade_count_ma20 ELSE NULL END,
          t.l1_main_net_amount / 1e8,
          t.l1_super_net_amount / 1e8,
          t.l2_main_net_amount / 1e8,
          t.l2_super_net_amount / 1e8,
          CASE WHEN t.total_amount > 0 THEN t.l1_main_net_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN t.l1_super_net_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN t.l2_main_net_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN t.l2_super_net_amount / t.total_amount ELSE NULL END,
          CASE
            WHEN (t.l1_main_sell_amount + t.l2_main_sell_amount) > 0
            THEN (t.l1_main_buy_amount + t.l2_main_buy_amount) / (t.l1_main_sell_amount + t.l2_main_sell_amount)
            ELSE NULL
          END,
          CASE WHEN t.total_amount > 0 THEN t.open_30m_l2_main_net_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN t.last_30m_l2_main_net_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN t.am_l2_main_net_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN t.pm_l2_main_net_amount / t.total_amount ELSE NULL END,
          CASE
            WHEN (t.positive_l2_net_bar_count + t.negative_l2_net_bar_count) > 0
            THEN CAST(t.positive_l2_net_bar_count AS REAL) / (t.positive_l2_net_bar_count + t.negative_l2_net_bar_count)
            ELSE NULL
          END,
          o.oib_delta_amount / 1e8,
          o.cvd_delta_amount / 1e8,
          CASE WHEN t.total_amount > 0 THEN o.oib_delta_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.cvd_delta_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.add_buy_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.add_sell_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.cancel_buy_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.cancel_sell_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.open_60m_oib_delta_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.last_30m_oib_delta_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.open_60m_cvd_delta_amount / t.total_amount ELSE NULL END,
          CASE WHEN t.total_amount > 0 THEN o.last_30m_cvd_delta_amount / t.total_amount ELSE NULL END,
          CASE
            WHEN (o.positive_oib_bar_count + o.negative_oib_bar_count) > 0
            THEN CAST(o.positive_oib_bar_count AS REAL) / (o.positive_oib_bar_count + o.negative_oib_bar_count)
            ELSE NULL
          END,
          CASE
            WHEN (o.positive_cvd_bar_count + o.negative_cvd_bar_count) > 0
            THEN CAST(o.positive_cvd_bar_count AS REAL) / (o.positive_cvd_bar_count + o.negative_cvd_bar_count)
            ELSE NULL
          END,
          o.positive_oib_streak_max,
          o.oib_top3_concentration_ratio,
          o.buy_support_ratio,
          o.sell_pressure_ratio,
          CASE WHEN o.buy_support_ratio IS NOT NULL AND o.sell_pressure_ratio IS NOT NULL THEN o.buy_support_ratio - o.sell_pressure_ratio ELSE NULL END,
          b.avg_book_imbalance_ratio,
          b.close_book_imbalance_ratio,
          b.avg_book_depth_ratio,
          b.close_book_depth_ratio,
          CASE WHEN b.valid_bucket_count > 0 THEN CAST(b.bid_dominant_bar_count AS REAL) / b.valid_bucket_count ELSE NULL END,
          CASE WHEN b.valid_bucket_count > 0 THEN CAST(b.ask_dominant_bar_count AS REAL) / b.valid_bucket_count ELSE NULL END,
          CASE WHEN b.valid_bucket_count > 0 THEN CAST(b.thin_book_bar_count AS REAL) / b.valid_bucket_count ELSE NULL END,
          b.close_bid_resting_amount / 1e8,
          b.close_ask_resting_amount / 1e8,
          CASE WHEN b.close_ask_resting_amount > 0 THEN b.close_bid_resting_amount / b.close_ask_resting_amount ELSE NULL END,
          l.touch_limit_up,
          l.touch_limit_down,
          l.is_limit_up_close,
          l.is_limit_down_close,
          l.broken_limit_up,
          l.broken_limit_down,
          l.limit_state_label,
          minute_from_open(l.first_touch_limit_up_time),
          minute_from_open(l.last_touch_limit_up_time),
          hf.best_rank,
          hf.hot_score,
          hf.persistence_score,
          hf.member_count,
          hf.is_top10,
          hf.is_new_hot,
          hf.is_continuing_hot,
          hf.is_climax_hot,
          hf.is_fading,
          hf.l2_main_net_yi,
          ms.csi1000_above_ma20,
          ms.csi1000_dist_ma20_pct,
          ms.market_advancer_ratio,
          ms.market_median_return_pct,
          ms.market_total_amount_yi,
          ms.market_amount_ratio_20d,
          ms.limit_up_count,
          ms.broken_limit_up_ratio,
          ms.hot_theme_concentration_top3,
          1 AS has_trade_daily,
          COALESCE(t5.has_trade_5m, 0),
          CASE WHEN o.symbol IS NULL THEN 0 ELSE 1 END,
          COALESCE(o5.has_order_5m, 0),
          CASE WHEN b.symbol IS NULL THEN 0 ELSE 1 END,
          COALESCE(b5.has_book_5m, 0),
          CASE WHEN l.symbol IS NULL THEN 0 ELSE 1 END,
          CASE WHEN hf.symbol IS NULL THEN 0 ELSE 1 END,
          CASE WHEN ms.trade_date IS NULL THEN 0 ELSE 1 END,
          ? AS build_run_id
        FROM trade_base AS t
        JOIN tmp_request_dates AS rd ON rd.trade_date=t.trade_date
        LEFT JOIN selection.selection_feature_daily AS sf
          ON sf.symbol=t.symbol AND sf.trade_date=t.trade_date AND sf.feature_version=?
        LEFT JOIN atomic.atomic_order_daily AS o
          ON o.symbol=t.symbol AND o.trade_date=t.trade_date
        LEFT JOIN atomic.atomic_book_state_daily AS b
          ON b.symbol=t.symbol AND b.trade_date=t.trade_date
        LEFT JOIN atomic.atomic_limit_state_daily AS l
          ON l.symbol=t.symbol AND l.trade_date=t.trade_date
        LEFT JOIN model_market_state_daily_v1 AS ms
          ON ms.trade_date=t.trade_date
        LEFT JOIN tmp_heat_feature AS hf
          ON hf.symbol=t.symbol AND hf.trade_date=t.trade_date
        LEFT JOIN trade5_cov AS t5
          ON t5.symbol=t.symbol AND t5.trade_date=t.trade_date
        LEFT JOIN order5_cov AS o5
          ON o5.symbol=t.symbol AND o5.trade_date=t.trade_date
        LEFT JOIN book5_cov AS b5
          ON b5.symbol=t.symbol AND b5.trade_date=t.trade_date
        """,
        (extended_start, date_to, feature_version, run_id, SELECTION_FEATURE_VERSION),
    )
    return int(conn.execute("SELECT changes()").fetchone()[0])


def build_intraday_shape(conn: sqlite3.Connection, feature_version: str, run_id: str) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO model_feature_intraday_shape_v1 (
          symbol, trade_date, feature_version,
          valid_bar_count, missing_bar_count, first_bar_time, last_bar_time,
          intraday_range_pct, intraday_close_position, high_time_min, low_time_min,
          high_before_1030, low_after_1430,
          open_5m_return_pct, open_15m_return_pct, open_30m_return_pct, open_60m_return_pct,
          open_15m_high_from_open_pct, open_15m_low_from_open_pct,
          open_30m_amount_ratio, open_60m_amount_ratio,
          open_15m_l2_main_net_ratio, open_30m_l2_main_net_ratio, open_60m_l2_main_net_ratio,
          open_15m_l2_super_net_ratio, open_15m_oib_ratio, open_15m_cvd_ratio, open_15m_book_imbalance_avg,
          last_15m_return_pct, last_30m_return_pct, last_60m_return_pct,
          last_30m_amount_ratio, last_30m_l2_main_net_ratio, last_30m_l2_super_net_ratio,
          last_30m_oib_ratio, last_30m_cvd_ratio, last_30m_book_imbalance_avg,
          l2_main_net_positive_bar_ratio, l2_super_net_positive_bar_ratio,
          oib_positive_bar_ratio, cvd_positive_bar_ratio,
          longest_l2_main_positive_streak, longest_oib_positive_streak,
          l2_main_net_curve_slope, oib_curve_slope, cvd_curve_slope,
          front_loaded_l2_flow, back_loaded_l2_flow, late_day_reversal_up, late_day_distribution,
          has_order_5m, has_book_5m, build_run_id
        )
        WITH bars AS (
          SELECT
            t.symbol,
            t.trade_date,
            t.bucket_start,
            t.open,
            t.high,
            t.low,
            t.close,
            t.total_amount,
            t.l2_main_net_amount,
            t.l2_super_net_amount,
            o.oib_delta_amount,
            o.cvd_delta_amount,
            b.book_imbalance_ratio,
            minute_from_open(t.bucket_start) AS minute_open,
            ROW_NUMBER() OVER (PARTITION BY t.symbol, t.trade_date ORDER BY t.bucket_start) AS rn_asc,
            ROW_NUMBER() OVER (PARTITION BY t.symbol, t.trade_date ORDER BY t.bucket_start DESC) AS rn_desc,
            CASE WHEN o.symbol IS NULL THEN 0 ELSE 1 END AS has_order_bar,
            CASE WHEN b.symbol IS NULL THEN 0 ELSE 1 END AS has_book_bar
          FROM atomic.atomic_trade_5m AS t
          JOIN tmp_request_dates AS rd ON rd.trade_date=t.trade_date
          LEFT JOIN atomic.atomic_order_5m AS o
            ON o.symbol=t.symbol AND o.trade_date=t.trade_date AND o.bucket_start=t.bucket_start
          LEFT JOIN atomic.atomic_book_state_5m AS b
            ON b.symbol=t.symbol AND b.trade_date=t.trade_date AND b.bucket_start=t.bucket_start
        ),
        agg AS (
          SELECT
            symbol,
            trade_date,
            COUNT(*) AS valid_bar_count,
            MIN(bucket_start) AS first_bar_time,
            MAX(bucket_start) AS last_bar_time,
            MAX(high) AS max_high,
            MIN(low) AS min_low,
            SUM(total_amount) AS day_amount,
            MAX(CASE WHEN rn_asc = 1 THEN open END) AS first_open,
            MAX(CASE WHEN rn_desc = 1 THEN close END) AS last_close,
            MAX(CASE WHEN rn_asc = 1 THEN close END) AS close_rn1,
            MAX(CASE WHEN rn_asc = 3 THEN close END) AS close_rn3,
            MAX(CASE WHEN rn_asc = 6 THEN close END) AS close_rn6,
            MAX(CASE WHEN rn_asc = 12 THEN close END) AS close_rn12,
            MAX(CASE WHEN rn_desc = 3 THEN close END) AS last_start_15m_close,
            MAX(CASE WHEN rn_desc = 6 THEN close END) AS last_start_30m_close,
            MAX(CASE WHEN rn_desc = 12 THEN close END) AS last_start_60m_close,
            MAX(CASE WHEN rn_asc <= 3 THEN high END) AS open_15m_high,
            MIN(CASE WHEN rn_asc <= 3 THEN low END) AS open_15m_low,
            SUM(CASE WHEN rn_asc <= 6 THEN total_amount ELSE 0 END) AS open_30m_amount,
            SUM(CASE WHEN rn_asc <= 12 THEN total_amount ELSE 0 END) AS open_60m_amount,
            SUM(CASE WHEN rn_desc <= 6 THEN total_amount ELSE 0 END) AS last_30m_amount,
            SUM(CASE WHEN rn_asc <= 3 THEN l2_main_net_amount ELSE 0 END) AS open_15m_l2_main_net,
            SUM(CASE WHEN rn_asc <= 6 THEN l2_main_net_amount ELSE 0 END) AS open_30m_l2_main_net,
            SUM(CASE WHEN rn_asc <= 12 THEN l2_main_net_amount ELSE 0 END) AS open_60m_l2_main_net,
            SUM(CASE WHEN rn_asc <= 3 THEN l2_super_net_amount ELSE 0 END) AS open_15m_l2_super_net,
            SUM(CASE WHEN rn_desc <= 6 THEN l2_main_net_amount ELSE 0 END) AS last_30m_l2_main_net,
            SUM(CASE WHEN rn_desc <= 6 THEN l2_super_net_amount ELSE 0 END) AS last_30m_l2_super_net,
            SUM(CASE WHEN rn_asc <= 3 THEN oib_delta_amount ELSE 0 END) AS open_15m_oib,
            SUM(CASE WHEN rn_asc <= 3 THEN cvd_delta_amount ELSE 0 END) AS open_15m_cvd,
            AVG(CASE WHEN rn_asc <= 3 THEN book_imbalance_ratio END) AS open_15m_book_imbalance_avg,
            SUM(CASE WHEN rn_desc <= 6 THEN oib_delta_amount ELSE 0 END) AS last_30m_oib,
            SUM(CASE WHEN rn_desc <= 6 THEN cvd_delta_amount ELSE 0 END) AS last_30m_cvd,
            AVG(CASE WHEN rn_desc <= 6 THEN book_imbalance_ratio END) AS last_30m_book_imbalance_avg,
            AVG(CASE WHEN l2_main_net_amount > 0 THEN 1.0 ELSE 0.0 END) AS l2_main_net_positive_bar_ratio,
            AVG(CASE WHEN l2_super_net_amount > 0 THEN 1.0 ELSE 0.0 END) AS l2_super_net_positive_bar_ratio,
            AVG(CASE WHEN oib_delta_amount > 0 THEN 1.0 ELSE 0.0 END) AS oib_positive_bar_ratio,
            AVG(CASE WHEN cvd_delta_amount > 0 THEN 1.0 ELSE 0.0 END) AS cvd_positive_bar_ratio,
            MAX(has_order_bar) AS has_order_5m,
            MAX(has_book_bar) AS has_book_5m
          FROM bars
          GROUP BY symbol, trade_date
        )
        SELECT
          a.symbol,
          a.trade_date,
          ? AS feature_version,
          a.valid_bar_count,
          CASE WHEN 49 - a.valid_bar_count > 0 THEN 49 - a.valid_bar_count ELSE 0 END AS missing_bar_count,
          a.first_bar_time,
          a.last_bar_time,
          CASE WHEN a.min_low > 0 THEN (a.max_high / a.min_low - 1.0) * 100.0 ELSE NULL END AS intraday_range_pct,
          CASE WHEN a.max_high > a.min_low THEN (a.last_close - a.min_low) / (a.max_high - a.min_low) ELSE NULL END AS intraday_close_position,
          (SELECT MIN(minute_open) FROM bars AS b WHERE b.symbol=a.symbol AND b.trade_date=a.trade_date AND b.high=a.max_high),
          (SELECT MIN(minute_open) FROM bars AS b WHERE b.symbol=a.symbol AND b.trade_date=a.trade_date AND b.low=a.min_low),
          CASE
            WHEN (SELECT MIN(minute_open) FROM bars AS b WHERE b.symbol=a.symbol AND b.trade_date=a.trade_date AND b.high=a.max_high) <= 60
            THEN 1 ELSE 0
          END,
          CASE
            WHEN (SELECT MIN(minute_open) FROM bars AS b WHERE b.symbol=a.symbol AND b.trade_date=a.trade_date AND b.low=a.min_low) >= 210
            THEN 1 ELSE 0
          END,
          CASE WHEN a.first_open > 0 THEN (a.close_rn1 / a.first_open - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.first_open > 0 THEN (a.close_rn3 / a.first_open - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.first_open > 0 THEN (a.close_rn6 / a.first_open - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.first_open > 0 THEN (a.close_rn12 / a.first_open - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.first_open > 0 THEN (a.open_15m_high / a.first_open - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.first_open > 0 THEN (a.open_15m_low / a.first_open - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.day_amount > 0 THEN a.open_30m_amount / a.day_amount ELSE NULL END,
          CASE WHEN a.day_amount > 0 THEN a.open_60m_amount / a.day_amount ELSE NULL END,
          CASE WHEN a.open_30m_amount > 0 THEN a.open_15m_l2_main_net / a.open_30m_amount ELSE NULL END,
          CASE WHEN a.open_30m_amount > 0 THEN a.open_30m_l2_main_net / a.open_30m_amount ELSE NULL END,
          CASE WHEN a.open_60m_amount > 0 THEN a.open_60m_l2_main_net / a.open_60m_amount ELSE NULL END,
          CASE WHEN a.open_30m_amount > 0 THEN a.open_15m_l2_super_net / a.open_30m_amount ELSE NULL END,
          CASE WHEN a.open_30m_amount > 0 THEN a.open_15m_oib / a.open_30m_amount ELSE NULL END,
          CASE WHEN a.open_30m_amount > 0 THEN a.open_15m_cvd / a.open_30m_amount ELSE NULL END,
          a.open_15m_book_imbalance_avg,
          CASE WHEN a.last_start_15m_close > 0 THEN (a.last_close / a.last_start_15m_close - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.last_start_30m_close > 0 THEN (a.last_close / a.last_start_30m_close - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.last_start_60m_close > 0 THEN (a.last_close / a.last_start_60m_close - 1.0) * 100.0 ELSE NULL END,
          CASE WHEN a.day_amount > 0 THEN a.last_30m_amount / a.day_amount ELSE NULL END,
          CASE WHEN a.last_30m_amount > 0 THEN a.last_30m_l2_main_net / a.last_30m_amount ELSE NULL END,
          CASE WHEN a.last_30m_amount > 0 THEN a.last_30m_l2_super_net / a.last_30m_amount ELSE NULL END,
          CASE WHEN a.last_30m_amount > 0 THEN a.last_30m_oib / a.last_30m_amount ELSE NULL END,
          CASE WHEN a.last_30m_amount > 0 THEN a.last_30m_cvd / a.last_30m_amount ELSE NULL END,
          a.last_30m_book_imbalance_avg,
          a.l2_main_net_positive_bar_ratio,
          a.l2_super_net_positive_bar_ratio,
          a.oib_positive_bar_ratio,
          a.cvd_positive_bar_ratio,
          NULL AS longest_l2_main_positive_streak,
          NULL AS longest_oib_positive_streak,
          NULL AS l2_main_net_curve_slope,
          NULL AS oib_curve_slope,
          NULL AS cvd_curve_slope,
          NULL AS front_loaded_l2_flow,
          NULL AS back_loaded_l2_flow,
          NULL AS late_day_reversal_up,
          NULL AS late_day_distribution,
          a.has_order_5m,
          a.has_book_5m,
          ? AS build_run_id
        FROM agg AS a
        """,
        (feature_version, run_id),
    )
    return int(conn.execute("SELECT changes()").fetchone()[0])


def build_forward_labels(
    conn: sqlite3.Connection,
    feature_version: str,
    run_id: str,
    extended_start: str,
    label_end: str,
) -> int:
    conn.execute("DROP TABLE IF EXISTS temp.tmp_label_horizons")
    conn.execute("CREATE TEMP TABLE tmp_label_horizons(horizon_days INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO tmp_label_horizons(horizon_days) VALUES (?)", [(item,) for item in LABEL_HORIZONS])
    conn.execute(
        """
        INSERT OR REPLACE INTO model_label_forward_return_v1 (
          symbol, trade_date, entry_date, label_end_date, label_complete_asof_date,
          horizon_days, feature_version,
          signal_close, entry_open, entry_gap_pct, entry_buyable, entry_block_reason,
          max_high, min_low, exit_close, max_runup_pct, max_drawdown_pct, close_return_pct,
          hit_5pct, hit_8pct, hit_10pct, hit_15pct, hit_20pct,
          first_hit_8pct_day, first_hit_15pct_day, worst_before_first_hit_15pct,
          build_run_id
        )
        WITH ordered AS (
          SELECT
            symbol,
            trade_date,
            open,
            high,
            low,
            close,
            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date) AS rn
          FROM atomic.atomic_trade_daily
          WHERE trade_date BETWEEN ? AND ?
        ),
        signals AS (
          SELECT *
          FROM ordered
          WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)
        ),
        label_rows AS (
          SELECT
            s.symbol,
            s.trade_date,
            e.trade_date AS entry_date,
            h.horizon_days,
            s.close AS signal_close,
            e.open AS entry_open,
            MAX(CASE WHEN f.rn = s.rn + h.horizon_days THEN f.trade_date END) AS label_end_date,
            MAX(f.high) AS max_high,
            MIN(f.low) AS min_low,
            MAX(CASE WHEN f.rn = s.rn + h.horizon_days THEN f.close END) AS exit_close,
            MAX(el.up_limit_price) AS entry_up_limit_price,
            MAX(el.open_price) AS entry_limit_open_price,
            MAX(el.low_price) AS entry_limit_low_price,
            MAX(el.limit_pct) AS entry_limit_pct,
            MAX(el.board_type) AS entry_board_type,
            MAX(el.risk_flag_type) AS entry_risk_flag_type,
            MIN(CASE WHEN f.high >= e.open * 1.08 THEN f.rn - s.rn END) AS first_hit_8pct_day,
            MIN(CASE WHEN f.high >= e.open * 1.15 THEN f.rn - s.rn END) AS first_hit_15pct_day,
            COUNT(f.trade_date) AS future_day_count
          FROM signals AS s
          JOIN tmp_label_horizons AS h
          JOIN ordered AS e
            ON e.symbol=s.symbol AND e.rn=s.rn+1
          LEFT JOIN atomic.atomic_limit_state_daily AS el
            ON el.symbol=e.symbol AND el.trade_date=e.trade_date
          JOIN ordered AS f
            ON f.symbol=s.symbol AND f.rn BETWEEN s.rn+1 AND s.rn+h.horizon_days
          GROUP BY s.symbol, s.trade_date, e.trade_date, h.horizon_days, s.close, e.open, s.rn
          HAVING future_day_count = h.horizon_days
        )
        SELECT
          symbol,
          trade_date,
          entry_date,
          label_end_date,
          label_end_date AS label_complete_asof_date,
          horizon_days,
          ? AS feature_version,
          signal_close,
          entry_open,
          CASE WHEN signal_close > 0 THEN (entry_open / signal_close - 1.0) * 100.0 ELSE NULL END AS entry_gap_pct,
          CASE
            WHEN entry_open IS NULL THEN 0
            WHEN entry_up_limit_price IS NULL THEN 0
            WHEN entry_open >= entry_up_limit_price * 0.999 AND entry_limit_low_price >= entry_up_limit_price * 0.999 THEN 0
            ELSE 1
          END AS entry_buyable,
          CASE
            WHEN entry_open IS NULL THEN 'missing_entry_open'
            WHEN entry_up_limit_price IS NULL THEN 'missing_limit_state'
            WHEN entry_open >= entry_up_limit_price * 0.999 AND entry_limit_low_price >= entry_up_limit_price * 0.999
              THEN 'one_price_limit_up_' || CASE
                WHEN COALESCE(entry_limit_pct, 0) <= 0.06 OR entry_risk_flag_type <> 'normal' THEN '5cm'
                WHEN COALESCE(entry_limit_pct, 0) >= 0.19 THEN '20cm'
                ELSE '10cm'
              END
            WHEN entry_open >= entry_up_limit_price * 0.995
              THEN 'near_limit_up_risk_' || CASE
                WHEN COALESCE(entry_limit_pct, 0) <= 0.06 OR entry_risk_flag_type <> 'normal' THEN '5cm'
                WHEN COALESCE(entry_limit_pct, 0) >= 0.19 THEN '20cm'
                ELSE '10cm'
              END
            ELSE 'ok_' || CASE
              WHEN COALESCE(entry_limit_pct, 0) <= 0.06 OR entry_risk_flag_type <> 'normal' THEN '5cm'
              WHEN COALESCE(entry_limit_pct, 0) >= 0.19 THEN '20cm'
              ELSE '10cm'
            END
          END AS entry_block_reason,
          max_high,
          min_low,
          exit_close,
          CASE WHEN entry_open > 0 THEN (max_high / entry_open - 1.0) * 100.0 ELSE NULL END AS max_runup_pct,
          CASE WHEN entry_open > 0 THEN (min_low / entry_open - 1.0) * 100.0 ELSE NULL END AS max_drawdown_pct,
          CASE WHEN entry_open > 0 THEN (exit_close / entry_open - 1.0) * 100.0 ELSE NULL END AS close_return_pct,
          CASE WHEN entry_open IS NULL THEN NULL WHEN max_high >= entry_open * 1.05 THEN 1 ELSE 0 END AS hit_5pct,
          CASE WHEN entry_open IS NULL THEN NULL WHEN max_high >= entry_open * 1.08 THEN 1 ELSE 0 END AS hit_8pct,
          CASE WHEN entry_open IS NULL THEN NULL WHEN max_high >= entry_open * 1.10 THEN 1 ELSE 0 END AS hit_10pct,
          CASE WHEN entry_open IS NULL THEN NULL WHEN max_high >= entry_open * 1.15 THEN 1 ELSE 0 END AS hit_15pct,
          CASE WHEN entry_open IS NULL THEN NULL WHEN max_high >= entry_open * 1.20 THEN 1 ELSE 0 END AS hit_20pct,
          first_hit_8pct_day,
          first_hit_15pct_day,
          NULL AS worst_before_first_hit_15pct,
          ? AS build_run_id
        FROM label_rows
        """,
        (extended_start, label_end, feature_version, run_id),
    )
    return int(conn.execute("SELECT changes()").fetchone()[0])


def table_row_count(conn: sqlite3.Connection, table: str, feature_version: str | None = None) -> int:
    if table == "model_market_index_daily":
        return int(
            fetch_scalar(
                conn,
                """
                SELECT COUNT(*)
                FROM model_market_index_daily
                WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)
                """,
            )
            or 0
        )
    if table == "model_market_state_daily_v1":
        return int(
            fetch_scalar(
                conn,
                """
                SELECT COUNT(*)
                FROM model_market_state_daily_v1
                WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)
                """,
            )
            or 0
        )
    return int(
        fetch_scalar(
            conn,
            f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE feature_version=?
              AND trade_date IN (SELECT trade_date FROM tmp_request_dates)
            """,
            (feature_version,),
        )
        or 0
    )


def table_symbol_count(conn: sqlite3.Connection, table: str, feature_version: str | None = None) -> int | None:
    columns = [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if "symbol" not in columns:
        return None
    return int(
        fetch_scalar(
            conn,
            f"""
            SELECT COUNT(DISTINCT symbol)
            FROM {table}
            WHERE feature_version=?
              AND trade_date IN (SELECT trade_date FROM tmp_request_dates)
            """,
            (feature_version,),
        )
        or 0
    )


def build_coverage(conn: sqlite3.Connection, row_counts: dict[str, int], date_info: dict[str, Any]) -> dict[str, Any]:
    requested_days = len(date_info["requested_dates"])
    coverage = {
        "requested_trade_days": requested_days,
        "requested_dates": date_info["requested_dates"],
        "available_label_days_after_end": date_info["available_label_days_after_end"],
        "source_date_counts": {
            "atomic_trade_daily": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM atomic.atomic_trade_daily WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "atomic_trade_5m": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM atomic.atomic_trade_5m WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "atomic_order_daily": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM atomic.atomic_order_daily WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "atomic_order_5m": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM atomic.atomic_order_5m WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "atomic_book_daily": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM atomic.atomic_book_state_daily WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "atomic_book_5m": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM atomic.atomic_book_state_5m WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "atomic_limit_daily": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM atomic.atomic_limit_state_daily WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "heat_feature": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM tmp_heat_feature") or 0),
            "heat_market": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM tmp_heat_market") or 0),
            "index_daily": int(fetch_scalar(conn, "SELECT COUNT(DISTINCT trade_date) FROM model_market_index_daily WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
        },
        "row_counts": row_counts,
    }
    warnings: list[str] = []
    if coverage["source_date_counts"]["index_daily"] == 0:
        warnings.append("index_daily_missing: csi1000 fields degraded to NULL and has_index_data=0")
    if coverage["source_date_counts"]["heat_feature"] == 0:
        warnings.append("heat_feature_missing: symbol-level heat fields degraded to NULL and has_heat=0")
    if row_counts.get("model_label_forward_return_v1", 0) == 0:
        warnings.append("labels_empty: requested dates do not have enough forward data for configured horizons")
    coverage["warnings"] = warnings
    return coverage


def write_manifest(
    conn: sqlite3.Connection,
    feature_version: str,
    run_id: str,
    date_info: dict[str, Any],
    coverage: dict[str, Any],
) -> None:
    generated_at = utc_now()
    for table in P0_TABLES:
        row_count = table_row_count(conn, table, feature_version)
        symbol_count = table_symbol_count(conn, table, feature_version)
        table_coverage = {
            **coverage,
            "table": table,
            "table_row_count": row_count,
            "table_symbol_count": symbol_count,
        }
        conn.execute(
            """
            INSERT OR REPLACE INTO model_feature_manifest (
              table_name, feature_version, date_from, date_to, trade_day_count,
              row_count, symbol_count, coverage_json, source_tables_json, run_id, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table,
                feature_version,
                date_info["date_from"],
                date_info["date_to"],
                len(date_info["requested_dates"]),
                row_count,
                symbol_count,
                json.dumps(table_coverage, ensure_ascii=False, sort_keys=True),
                json.dumps(source_tables_for(table), ensure_ascii=False, sort_keys=True),
                run_id,
                generated_at,
            ),
        )


def source_tables_for(table: str) -> list[str]:
    mapping = {
        "model_market_index_daily": ["optional:index_csv"],
        "model_market_state_daily_v1": [
            "atomic_trade_daily",
            "atomic_limit_state_daily",
            "model_market_index_daily",
            "fine_theme_heat_daily_v2",
            "fine_theme_heat_daily",
        ],
        "model_feature_daily_v1": [
            "atomic_trade_daily",
            "atomic_order_daily",
            "atomic_book_state_daily",
            "atomic_limit_state_daily",
            "selection_feature_daily",
            "fine_theme_heat_daily_v2",
            "tradable_theme_map",
            "fine_theme_member_daily",
            "fine_theme_heat_daily",
            "model_market_state_daily_v1",
        ],
        "model_feature_intraday_shape_v1": [
            "atomic_trade_5m",
            "atomic_order_5m",
            "atomic_book_state_5m",
        ],
        "model_label_forward_return_v1": ["atomic_trade_daily"],
    }
    return mapping.get(table, [])


def build_validation_summary(conn: sqlite3.Connection, row_counts: dict[str, int], coverage: dict[str, Any]) -> dict[str, Any]:
    daily_rows = int(fetch_scalar(conn, "SELECT COUNT(*) FROM model_feature_daily_v1 WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0)
    return {
        "status": "built",
        "row_counts": row_counts,
        "warnings": coverage.get("warnings", []),
        "coverage_flags": {
            "feature_daily_rows": daily_rows,
            "has_order_daily_rows": int(fetch_scalar(conn, "SELECT SUM(has_order_daily) FROM model_feature_daily_v1 WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "has_order_5m_rows": int(fetch_scalar(conn, "SELECT SUM(has_order_5m) FROM model_feature_daily_v1 WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "has_book_daily_rows": int(fetch_scalar(conn, "SELECT SUM(has_book_daily) FROM model_feature_daily_v1 WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "has_book_5m_rows": int(fetch_scalar(conn, "SELECT SUM(has_book_5m) FROM model_feature_daily_v1 WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
            "has_heat_rows": int(fetch_scalar(conn, "SELECT SUM(has_heat) FROM model_feature_daily_v1 WHERE trade_date IN (SELECT trade_date FROM tmp_request_dates)") or 0),
        },
    }


def run_build(args: argparse.Namespace) -> dict[str, Any]:
    start_date, end_date = requested_window(args)
    if args.reset_target and args.target_db.exists():
        args.target_db.unlink()
    run_id = f"model_feature_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    with connect_target(args.target_db) as conn:
        load_schema(conn)
        attach_ro(conn, "atomic", args.atomic_db, required=True)
        attach_ro(conn, "selection", args.selection_db, required=True)
        attach_ro(conn, "heat", args.heat_db, required=False)
        attach_ro(conn, "heat_v2", args.heat_v2_db, required=False)
        attach_ro(conn, "theme_map", args.tradable_theme_db, required=False)
        date_info = resolve_dates(conn, start_date, end_date, args.warmup_days, args.label_lookahead_days)
        create_temp_date_table(conn, date_info["requested_dates"])
        start_run(conn, args, run_id, date_info)
        try:
            with conn:
                clear_target_range(conn, args.feature_version, date_info["date_from"], date_info["date_to"])
                index_rows = import_index_sources(conn, args, run_id, date_info)
                heat_rows = build_temp_heat_tables(conn, date_info["date_from"], date_info["date_to"])
                market_rows = build_market_state(
                    conn,
                    args.feature_version,
                    run_id,
                    date_info["extended_start"],
                    date_info["date_to"],
                )
                daily_rows = build_feature_daily(
                    conn,
                    args.feature_version,
                    run_id,
                    date_info["extended_start"],
                    date_info["date_to"],
                )
                intraday_rows = build_intraday_shape(conn, args.feature_version, run_id)
                label_rows = 0
                if not args.skip_labels:
                    label_rows = build_forward_labels(
                        conn,
                        args.feature_version,
                        run_id,
                        date_info["extended_start"],
                        date_info["label_end"],
                    )
                row_counts = {
                    "model_market_index_daily": index_rows,
                    "model_market_state_daily_v1": market_rows,
                    "model_feature_daily_v1": daily_rows,
                    "model_feature_intraday_shape_v1": intraday_rows,
                    "model_label_forward_return_v1": label_rows,
                    **heat_rows,
                }
                coverage = build_coverage(conn, row_counts, date_info)
                write_manifest(conn, args.feature_version, run_id, date_info, coverage)
                validation = build_validation_summary(conn, row_counts, coverage)
                finish_run(conn, run_id, "success", row_counts, validation)
            return {
                "status": "success",
                "run_id": run_id,
                "target_db": str(args.target_db),
                "date_from": date_info["date_from"],
                "date_to": date_info["date_to"],
                "row_counts": row_counts,
                "warnings": coverage.get("warnings", []),
            }
        except Exception as exc:
            conn.rollback()
            with conn:
                finish_run(conn, run_id, "failed", error=str(exc))
            raise


def main() -> None:
    args = parse_args()
    try:
        result = run_build(args)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
