#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote


DEFAULT_DB = Path("/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db")
DEFAULT_SCAN_REGEX = "|".join(
    [
        "atomic_" + "limit_state" + "_5m",
        "limit_state" + "_5m",
    ]
)
P0_TABLES = [
    "model_feature_build_runs",
    "model_feature_manifest",
    "model_market_index_daily",
    "model_market_state_daily_v1",
    "model_feature_daily_v1",
    "model_feature_intraday_shape_v1",
    "model_label_forward_return_v1",
]
TEXT_SUFFIX_ALLOWLIST = {
    ".py",
    ".sql",
    ".sh",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
}
TABLE_SPECS: dict[str, dict[str, Any]] = {
    "model_feature_build_runs": {
        "required_columns": ["run_id", "feature_version", "date_from", "date_to", "status", "started_at"],
        "range_columns": ("date_from", "date_to"),
    },
    "model_feature_manifest": {
        "required_columns": [
            "table_name",
            "feature_version",
            "date_from",
            "date_to",
            "trade_day_count",
            "row_count",
            "coverage_json",
        ],
        "range_columns": ("date_from", "date_to"),
    },
    "model_market_index_daily": {
        "required_columns": ["index_code", "trade_date", "close"],
        "date_column": "trade_date",
    },
    "model_market_state_daily_v1": {
        "required_columns": [
            "trade_date",
            "feature_version",
            "csi1000_close",
            "csi1000_ma20",
            "csi1000_above_ma20",
            "csi1000_dist_ma20_pct",
            "has_index_data",
            "has_order_data",
            "has_book_data",
        ],
        "date_column": "trade_date",
    },
    "model_feature_daily_v1": {
        "required_columns": [
            "symbol",
            "trade_date",
            "feature_version",
            "has_trade_daily",
            "has_trade_5m",
            "has_order_daily",
            "has_order_5m",
            "has_book_daily",
            "has_book_5m",
            "has_limit_daily",
            "has_heat",
            "has_market_state",
        ],
        "date_column": "trade_date",
    },
    "model_feature_intraday_shape_v1": {
        "required_columns": [
            "symbol",
            "trade_date",
            "feature_version",
            "has_order_5m",
            "has_book_5m",
        ],
        "date_column": "trade_date",
    },
    "model_label_forward_return_v1": {
        "required_columns": [
            "symbol",
            "trade_date",
            "label_end_date",
            "label_complete_asof_date",
            "horizon_days",
            "feature_version",
            "max_runup_pct",
            "hit_15pct",
        ],
        "date_column": "trade_date",
    },
}
FEATURE_TABLES = [
    "model_market_state_daily_v1",
    "model_feature_daily_v1",
    "model_feature_intraday_shape_v1",
]
FORBIDDEN_FEATURE_COLUMN_PATTERNS: dict[str, str] = {
    "future": r"(^|_)future(_|$)",
    "max_runup": r"(^|_)max_runup(_|$)",
    "hit": r"(^hit_)|(^first_hit_)|(_hit_)|(worst_before_first_hit)",
}
MONTH_PROBES = ["2024-10", "2026-02", "2026-03"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate model_feature_store.db for P0 readiness.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("--feature-version", default="v1", help="Feature version to inspect where applicable")
    parser.add_argument(
        "--mode",
        choices=["prediction", "training"],
        default="prediction",
        help="prediction allows incomplete forward labels; training requires complete labels; index data is optional in P0",
    )
    parser.add_argument(
        "--scan-path",
        action="append",
        default=[],
        help="Optional file or directory to text-scan for forbidden limit-state 5m references",
    )
    parser.add_argument(
        "--scan-regex",
        default=DEFAULT_SCAN_REGEX,
        help="Regex used by optional text scan",
    )
    parser.add_argument("--scan-max-hits", type=int, default=50, help="Max reported text-scan hits")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def connect_ro(db_path: Path) -> sqlite3.Connection:
    db_uri = f"file:{quote(str(db_path.resolve()))}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    if not table_exists(conn, table):
        return []
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row["name"]) for row in rows]


def fetch_scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Any:
    row = conn.execute(sql, tuple(params)).fetchone()
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return row[0]
    return row[0]


def safe_json_loads(raw: Any) -> tuple[Optional[Any], Optional[str]]:
    if raw is None or raw == "":
        return None, None
    try:
        return json.loads(str(raw)), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def distinct_dates(
    conn: sqlite3.Connection,
    table: str,
    date_column: str,
    where: str = "",
    params: Iterable[Any] = (),
) -> list[str]:
    if not table_exists(conn, table):
        return []
    sql = f"SELECT DISTINCT {date_column} AS trade_date FROM {table}"
    if where:
        sql += f" WHERE {where}"
    sql += f" ORDER BY {date_column}"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [str(row["trade_date"]) for row in rows if row["trade_date"]]


def summarize_table(
    conn: sqlite3.Connection,
    table: str,
    spec: dict[str, Any],
    feature_version: str,
) -> dict[str, Any]:
    exists = table_exists(conn, table)
    columns = table_columns(conn, table) if exists else []
    required_columns = list(spec.get("required_columns", []))
    missing_columns = [column for column in required_columns if column not in columns]
    summary: dict[str, Any] = {
        "exists": exists,
        "required_columns_present": len(missing_columns) == 0,
        "missing_columns": missing_columns,
        "column_count": len(columns),
        "columns": columns,
        "row_count": 0,
    }
    if not exists:
        return summary

    row_count = int(fetch_scalar(conn, f"SELECT COUNT(*) FROM {table}") or 0)
    summary["row_count"] = row_count

    date_column = spec.get("date_column")
    if date_column and date_column in columns:
        filter_sql = ""
        params: list[Any] = []
        if "feature_version" in columns:
            filter_sql = " WHERE feature_version = ?"
            params.append(feature_version)
        summary["feature_version_row_count"] = int(
            fetch_scalar(
                conn,
                f"SELECT COUNT(*) FROM {table}{filter_sql}",
                params,
            )
            or 0
        )
        summary["date_coverage"] = {
            "min_trade_date": fetch_scalar(
                conn,
                f"SELECT MIN({date_column}) FROM {table}{filter_sql}",
                params,
            ),
            "max_trade_date": fetch_scalar(
                conn,
                f"SELECT MAX({date_column}) FROM {table}{filter_sql}",
                params,
            ),
            "distinct_trade_dates": int(
                fetch_scalar(
                    conn,
                    f"SELECT COUNT(DISTINCT {date_column}) FROM {table}{filter_sql}",
                    params,
                )
                or 0
            ),
        }

    range_columns = spec.get("range_columns")
    if range_columns and all(column in columns for column in range_columns):
        date_from_col, date_to_col = range_columns
        summary["range_coverage"] = {
            "min_date_from": fetch_scalar(conn, f"SELECT MIN({date_from_col}) FROM {table}"),
            "max_date_to": fetch_scalar(conn, f"SELECT MAX({date_to_col}) FROM {table}"),
        }

    if "symbol" in columns:
        summary["distinct_symbols"] = int(fetch_scalar(conn, f"SELECT COUNT(DISTINCT symbol) FROM {table}") or 0)
    if "index_code" in columns:
        summary["distinct_index_codes"] = int(fetch_scalar(conn, f"SELECT COUNT(DISTINCT index_code) FROM {table}") or 0)
    if "horizon_days" in columns:
        summary["distinct_horizons"] = sorted(
            int(row["horizon_days"])
            for row in conn.execute(
                f"SELECT DISTINCT horizon_days FROM {table} ORDER BY horizon_days"
            ).fetchall()
            if row["horizon_days"] is not None
        )
    return summary


OPTIONAL_EMPTY_TABLES = {
    "model_market_index_daily": "index source can be absent in P0; market state records has_index_data=0",
    "model_label_forward_return_v1": "recent samples can lack enough forward days; labels must be checked on older windows",
}


def validate_required_tables(conn: sqlite3.Connection, feature_version: str) -> tuple[dict[str, Any], bool]:
    table_summaries: dict[str, Any] = {}
    missing_tables: list[str] = []
    empty_tables: list[str] = []
    missing_columns_by_table: dict[str, list[str]] = {}

    for table in P0_TABLES:
        spec = TABLE_SPECS.get(table, {})
        summary = summarize_table(conn, table, spec, feature_version)
        table_summaries[table] = summary
        if not summary["exists"]:
            missing_tables.append(table)
            continue
        if summary["row_count"] == 0 and table not in OPTIONAL_EMPTY_TABLES:
            empty_tables.append(table)
        if summary["missing_columns"]:
            missing_columns_by_table[table] = summary["missing_columns"]

    details = {
        "required_tables": P0_TABLES,
        "missing_tables": missing_tables,
        "empty_tables": empty_tables,
        "allowed_empty_tables": {
            table: reason
            for table, reason in OPTIONAL_EMPTY_TABLES.items()
            if table_summaries.get(table, {}).get("exists") and table_summaries.get(table, {}).get("row_count") == 0
        },
        "missing_columns_by_table": missing_columns_by_table,
        "table_summaries": table_summaries,
    }
    ok = not missing_tables and not empty_tables and not missing_columns_by_table
    return details, ok


def choose_baseline_dates(conn: sqlite3.Connection) -> tuple[str, list[str]]:
    candidates: list[tuple[str, list[str]]] = []
    for table in [
        "model_market_state_daily_v1",
        "model_feature_daily_v1",
        "model_feature_intraday_shape_v1",
        "model_label_forward_return_v1",
    ]:
        if table_exists(conn, table) and "trade_date" in table_columns(conn, table):
            dates = distinct_dates(conn, table, "trade_date")
            candidates.append((table, dates))
    if table_exists(conn, "model_market_index_daily") and "trade_date" in table_columns(conn, "model_market_index_daily"):
        csi_dates = distinct_dates(conn, "model_market_index_daily", "trade_date", "index_code = ?", ("000852.SH",))
        all_index_dates = distinct_dates(conn, "model_market_index_daily", "trade_date")
        if csi_dates:
            candidates.append(("model_market_index_daily[000852.SH]", csi_dates))
        elif all_index_dates:
            candidates.append(("model_market_index_daily", all_index_dates))
    if not candidates:
        return "none", []
    baseline_source, baseline_dates = max(candidates, key=lambda item: len(item[1]))
    return baseline_source, baseline_dates


def validate_date_coverage(conn: sqlite3.Connection) -> tuple[dict[str, Any], bool]:
    baseline_source, baseline_dates = choose_baseline_dates(conn)
    baseline_set = set(baseline_dates)
    missing_by_table: dict[str, Any] = {}
    allowed_missing_by_table: dict[str, Any] = {}
    table_distinct_date_counts: dict[str, int] = {}

    for table in [
        "model_market_index_daily",
        "model_market_state_daily_v1",
        "model_feature_daily_v1",
        "model_feature_intraday_shape_v1",
        "model_label_forward_return_v1",
    ]:
        if not table_exists(conn, table):
            continue
        columns = table_columns(conn, table)
        if "trade_date" not in columns:
            continue
        where = ""
        params: tuple[Any, ...] = ()
        label = table
        if table == "model_market_index_daily" and "index_code" in columns:
            where = "index_code = ?"
            params = ("000852.SH",)
            csi_dates = distinct_dates(conn, table, "trade_date", where, params)
            if csi_dates:
                dates = csi_dates
                label = f"{table}[000852.SH]"
            else:
                dates = distinct_dates(conn, table, "trade_date")
        else:
            dates = distinct_dates(conn, table, "trade_date")
        table_distinct_date_counts[label] = len(dates)
        if not baseline_dates:
            missing = []
        else:
            missing = sorted(baseline_set - set(dates))
        item = {
            "missing_trade_dates_count": len(missing),
            "missing_trade_dates_sample": missing[:50],
        }
        if table in OPTIONAL_EMPTY_TABLES and len(dates) == 0:
            item["allowed_empty_reason"] = OPTIONAL_EMPTY_TABLES[table]
            allowed_missing_by_table[label] = item
        else:
            missing_by_table[label] = item

    ok = bool(baseline_dates) and all(item["missing_trade_dates_count"] == 0 for item in missing_by_table.values())
    details = {
        "baseline_source": baseline_source,
        "baseline_trade_date_count": len(baseline_dates),
        "baseline_date_range": {
            "min_trade_date": baseline_dates[0] if baseline_dates else None,
            "max_trade_date": baseline_dates[-1] if baseline_dates else None,
        },
        "table_distinct_date_counts": table_distinct_date_counts,
        "missing_by_table": missing_by_table,
        "allowed_missing_by_table": allowed_missing_by_table,
    }
    return details, ok


def summarize_manifest(conn: sqlite3.Connection) -> dict[str, Any]:
    if not table_exists(conn, "model_feature_manifest"):
        return {"available": False}
    columns = set(table_columns(conn, "model_feature_manifest"))
    needed = {"table_name", "feature_version", "date_from", "date_to", "trade_day_count", "row_count", "coverage_json", "generated_at"}
    if not needed.issubset(columns):
        return {"available": False, "missing_columns": sorted(needed - columns)}

    rows = conn.execute(
        """
        SELECT table_name, feature_version, date_from, date_to, trade_day_count, row_count, coverage_json, generated_at
        FROM model_feature_manifest
        ORDER BY generated_at DESC, table_name
        """
    ).fetchall()
    latest_by_table: dict[str, Any] = {}
    for row in rows:
        table_name = str(row["table_name"])
        if table_name in latest_by_table:
            continue
        coverage_json, coverage_error = safe_json_loads(row["coverage_json"])
        latest_by_table[table_name] = {
            "feature_version": row["feature_version"],
            "date_from": row["date_from"],
            "date_to": row["date_to"],
            "trade_day_count": row["trade_day_count"],
            "row_count": row["row_count"],
            "coverage_json": coverage_json,
            "coverage_json_error": coverage_error,
            "generated_at": row["generated_at"],
        }
    return {
        "available": True,
        "row_count": len(rows),
        "latest_by_table": latest_by_table,
    }


def validate_csi1000_integrity(conn: sqlite3.Connection, feature_version: str) -> tuple[dict[str, Any], bool]:
    table = "model_market_state_daily_v1"
    if not table_exists(conn, table):
        return {"table": table, "available": False}, False

    columns = set(table_columns(conn, table))
    required_columns = {
        "trade_date",
        "csi1000_close",
        "csi1000_ma20",
        "csi1000_above_ma20",
        "csi1000_dist_ma20_pct",
    }
    missing_columns = sorted(required_columns - columns)
    if missing_columns:
        return {"table": table, "available": True, "missing_columns": missing_columns}, False

    sql = f"""
        SELECT trade_date, csi1000_close, csi1000_ma20, csi1000_above_ma20, csi1000_dist_ma20_pct
        FROM {table}
        {"WHERE feature_version = ?" if "feature_version" in columns else ""}
        ORDER BY trade_date
    """
    params: tuple[Any, ...] = (feature_version,) if "feature_version" in columns else ()
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return {"table": table, "available": True, "row_count": 0}, False

    has_index_column = "has_index_data" in columns
    has_index_rows = 0
    if has_index_column:
        has_index_rows = int(
            fetch_scalar(
                conn,
                f"""
                SELECT SUM(COALESCE(has_index_data, 0))
                FROM {table}
                {"WHERE feature_version = ?" if "feature_version" in columns else ""}
                """,
                params,
            )
            or 0
        )
        if has_index_rows == 0:
            return (
                {
                    "table": table,
                    "available": True,
                    "row_count": len(rows),
                    "has_index_data_rows": 0,
                    "degraded": True,
                    "warning": "index source missing; csi1000 fields are allowed to be NULL for P0 sample builds",
                },
                True,
            )

    all_null_close_dates: list[str] = []
    post_warmup_missing_rows: list[dict[str, Any]] = []
    invalid_above_ma20_rows: list[dict[str, Any]] = []
    warmup_rows = 20

    for index, row in enumerate(rows):
        trade_date = str(row["trade_date"])
        if row["csi1000_close"] is None:
            all_null_close_dates.append(trade_date)
        if row["csi1000_above_ma20"] not in (None, 0, 1):
            invalid_above_ma20_rows.append(
                {
                    "trade_date": trade_date,
                    "csi1000_above_ma20": row["csi1000_above_ma20"],
                }
            )
        if index >= warmup_rows:
            if (
                row["csi1000_close"] is None
                or row["csi1000_ma20"] is None
                or row["csi1000_above_ma20"] is None
                or row["csi1000_dist_ma20_pct"] is None
            ):
                post_warmup_missing_rows.append(
                    {
                        "trade_date": trade_date,
                        "csi1000_close": row["csi1000_close"],
                        "csi1000_ma20": row["csi1000_ma20"],
                        "csi1000_above_ma20": row["csi1000_above_ma20"],
                        "csi1000_dist_ma20_pct": row["csi1000_dist_ma20_pct"],
                    }
                )

    details = {
        "table": table,
        "available": True,
        "row_count": len(rows),
        "has_index_data_rows": has_index_rows if has_index_column else None,
        "degraded": False,
        "warmup_rows_allowed_null": warmup_rows,
        "date_range": {
            "min_trade_date": str(rows[0]["trade_date"]),
            "max_trade_date": str(rows[-1]["trade_date"]),
        },
        "null_close_count": len(all_null_close_dates),
        "null_close_dates_sample": all_null_close_dates[:30],
        "post_warmup_missing_count": len(post_warmup_missing_rows),
        "post_warmup_missing_sample": post_warmup_missing_rows[:30],
        "invalid_above_ma20_count": len(invalid_above_ma20_rows),
        "invalid_above_ma20_sample": invalid_above_ma20_rows[:30],
        "sample_rows": [dict(row) for row in rows[:10]],
    }
    ok = (
        len(rows) > warmup_rows
        and not all_null_close_dates
        and not post_warmup_missing_rows
        and not invalid_above_ma20_rows
    )
    return details, ok


def validate_order_book_coverage(conn: sqlite3.Connection, feature_version: str) -> tuple[dict[str, Any], bool]:
    table = "model_feature_daily_v1"
    if not table_exists(conn, table):
        return {"table": table, "available": False}, False

    required_columns = {
        "trade_date",
        "has_order_daily",
        "has_book_daily",
        "has_order_5m",
        "has_book_5m",
    }
    columns = set(table_columns(conn, table))
    missing_columns = sorted(required_columns - columns)
    if missing_columns:
        return {"table": table, "available": True, "missing_columns": missing_columns}, False

    where_clauses = []
    params: list[Any] = []
    if "feature_version" in columns:
        where_clauses.append("feature_version = ?")
        params.append(feature_version)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    daily_rows = conn.execute(
        f"""
        SELECT
          trade_date,
          COUNT(*) AS rows,
          SUM(COALESCE(has_order_daily, 0)) AS order_daily_rows,
          SUM(COALESCE(has_book_daily, 0)) AS book_daily_rows,
          SUM(COALESCE(has_order_5m, 0)) AS order_5m_rows,
          SUM(COALESCE(has_book_5m, 0)) AS book_5m_rows
        FROM {table}
        {where_sql}
        GROUP BY trade_date
        ORDER BY trade_date
        """,
        params,
    ).fetchall()
    if not daily_rows:
        return {"table": table, "available": True, "row_count": 0}, False

    totals = {
        "rows": 0,
        "order_daily_rows": 0,
        "book_daily_rows": 0,
        "order_5m_rows": 0,
        "book_5m_rows": 0,
    }
    monthly: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "trade_days": 0,
            "rows": 0,
            "order_daily_rows": 0,
            "book_daily_rows": 0,
            "order_5m_rows": 0,
            "book_5m_rows": 0,
        }
    )
    daily_summary: list[dict[str, Any]] = []

    for row in daily_rows:
        trade_date = str(row["trade_date"])
        month_key = trade_date[:7]
        row_count = int(row["rows"] or 0)
        order_daily_rows = int(row["order_daily_rows"] or 0)
        book_daily_rows = int(row["book_daily_rows"] or 0)
        order_5m_rows = int(row["order_5m_rows"] or 0)
        book_5m_rows = int(row["book_5m_rows"] or 0)
        daily_summary.append(
            {
                "trade_date": trade_date,
                "rows": row_count,
                "order_daily_rows": order_daily_rows,
                "book_daily_rows": book_daily_rows,
                "order_5m_rows": order_5m_rows,
                "book_5m_rows": book_5m_rows,
            }
        )
        totals["rows"] += row_count
        totals["order_daily_rows"] += order_daily_rows
        totals["book_daily_rows"] += book_daily_rows
        totals["order_5m_rows"] += order_5m_rows
        totals["book_5m_rows"] += book_5m_rows
        monthly_item = monthly[month_key]
        monthly_item["trade_days"] += 1
        monthly_item["rows"] += row_count
        monthly_item["order_daily_rows"] += order_daily_rows
        monthly_item["book_daily_rows"] += book_daily_rows
        monthly_item["order_5m_rows"] += order_5m_rows
        monthly_item["book_5m_rows"] += book_5m_rows

    monthly_summary: dict[str, dict[str, Any]] = {}
    for month_key, item in sorted(monthly.items()):
        rows = int(item["rows"])
        monthly_summary[month_key] = {
            **item,
            "order_daily_ratio": round(item["order_daily_rows"] / rows, 6) if rows else None,
            "book_daily_ratio": round(item["book_daily_rows"] / rows, 6) if rows else None,
            "order_5m_ratio": round(item["order_5m_rows"] / rows, 6) if rows else None,
            "book_5m_ratio": round(item["book_5m_rows"] / rows, 6) if rows else None,
        }

    overall_ratio = {
        "order_daily_ratio": round(totals["order_daily_rows"] / totals["rows"], 6) if totals["rows"] else None,
        "book_daily_ratio": round(totals["book_daily_rows"] / totals["rows"], 6) if totals["rows"] else None,
        "order_5m_ratio": round(totals["order_5m_rows"] / totals["rows"], 6) if totals["rows"] else None,
        "book_5m_ratio": round(totals["book_5m_rows"] / totals["rows"], 6) if totals["rows"] else None,
    }
    month_probes = {month: monthly_summary.get(month) for month in MONTH_PROBES}
    month_202603 = monthly_summary.get("2026-03")
    has_positive_202603 = bool(
        month_202603
        and any((month_202603[key] or 0) > 0 for key in ["order_daily_rows", "book_daily_rows", "order_5m_rows", "book_5m_rows"])
    )

    details = {
        "table": table,
        "available": True,
        "trade_day_count": len(daily_summary),
        "overall_totals": totals,
        "overall_ratios": overall_ratio,
        "monthly_summary": monthly_summary,
        "month_probes": month_probes,
        "daily_summary_sample": daily_summary[:50],
        "expects_2026_03_positive_coverage": month_202603 is not None,
        "has_positive_2026_03_coverage": has_positive_202603 if month_202603 is not None else None,
    }
    ok = totals["rows"] > 0 and (month_202603 is None or has_positive_202603)
    return details, ok


def validate_forbidden_feature_columns(conn: sqlite3.Connection) -> tuple[dict[str, Any], bool]:
    violations: dict[str, list[dict[str, str]]] = {}
    for table in FEATURE_TABLES:
        if not table_exists(conn, table):
            continue
        columns = table_columns(conn, table)
        table_violations: list[dict[str, str]] = []
        for column in columns:
            for rule_name, pattern in FORBIDDEN_FEATURE_COLUMN_PATTERNS.items():
                if re.search(pattern, column):
                    table_violations.append({"column": column, "rule": rule_name})
                    break
        if table_violations:
            violations[table] = table_violations
    details = {
        "feature_tables_checked": FEATURE_TABLES,
        "violations": violations,
    }
    ok = not violations
    return details, ok


def validate_heat_null_semantics(conn: sqlite3.Connection, feature_version: str) -> tuple[dict[str, Any], bool]:
    table = "model_feature_daily_v1"
    if not table_exists(conn, table):
        return {"table": table, "available": False}, False
    columns = set(table_columns(conn, table))
    heat_columns = [
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
    missing = [column for column in ["has_heat", *heat_columns] if column not in columns]
    if missing:
        return {"table": table, "available": True, "missing_columns": missing}, False
    params: list[Any] = []
    where = ""
    if "feature_version" in columns:
        where = "WHERE feature_version = ?"
        params.append(feature_version)
    zero_expr = " OR ".join([f"{column} = 0" for column in heat_columns])
    nonnull_expr = " OR ".join([f"{column} IS NOT NULL" for column in heat_columns])
    details = {
        "table": table,
        "rows": int(fetch_scalar(conn, f"SELECT COUNT(*) FROM {table} {where}", params) or 0),
        "has_heat_rows": int(fetch_scalar(conn, f"SELECT SUM(COALESCE(has_heat, 0)) FROM {table} {where}", params) or 0),
        "missing_heat_nonnull_rows": int(
            fetch_scalar(
                conn,
                f"""
                SELECT COUNT(*)
                FROM {table}
                {where}
                {"AND" if where else "WHERE"} has_heat = 0 AND ({nonnull_expr})
                """,
                params,
            )
            or 0
        ),
        "missing_heat_zero_filled_rows": int(
            fetch_scalar(
                conn,
                f"""
                SELECT COUNT(*)
                FROM {table}
                {where}
                {"AND" if where else "WHERE"} has_heat = 0 AND ({zero_expr})
                """,
                params,
            )
            or 0
        ),
    }
    ok = details["missing_heat_nonnull_rows"] == 0 and details["missing_heat_zero_filled_rows"] == 0
    return details, ok


def validate_training_labels(conn: sqlite3.Connection, feature_version: str) -> tuple[dict[str, Any], bool]:
    table = "model_label_forward_return_v1"
    if not table_exists(conn, table):
        return {"table": table, "available": False}, False
    columns = set(table_columns(conn, table))
    required = {
        "symbol",
        "trade_date",
        "entry_date",
        "label_end_date",
        "label_complete_asof_date",
        "horizon_days",
        "feature_version",
        "entry_buyable",
        "entry_block_reason",
        "max_runup_pct",
        "hit_15pct",
    }
    missing = sorted(required - columns)
    if missing:
        return {"table": table, "available": True, "missing_columns": missing}, False
    rows = conn.execute(
        f"""
        SELECT
          horizon_days,
          COUNT(*) AS rows,
          COUNT(DISTINCT trade_date) AS trade_days,
          MAX(trade_date) AS latest_signal_date,
          MAX(label_complete_asof_date) AS latest_label_complete_asof_date,
          SUM(CASE WHEN label_end_date IS NULL OR label_complete_asof_date IS NULL THEN 1 ELSE 0 END) AS missing_complete_rows,
          SUM(CASE WHEN entry_buyable IS NULL THEN 1 ELSE 0 END) AS null_entry_buyable_rows,
          SUM(CASE WHEN entry_block_reason IS NULL THEN 1 ELSE 0 END) AS null_entry_reason_rows
        FROM {table}
        WHERE feature_version = ?
        GROUP BY horizon_days
        ORDER BY horizon_days
        """,
        (feature_version,),
    ).fetchall()
    by_horizon = {int(row["horizon_days"]): dict(row) for row in rows}
    latest = {
        f"latest_labelable_signal_date_{horizon}d": by_horizon.get(horizon, {}).get("latest_signal_date")
        for horizon in [3, 5, 10, 22]
    }
    missing_horizons = [horizon for horizon in [3, 5, 10, 22] if horizon not in by_horizon]
    incomplete_horizons = [
        horizon
        for horizon, row in by_horizon.items()
        if int(row.get("missing_complete_rows") or 0) > 0
        or int(row.get("null_entry_buyable_rows") or 0) > 0
        or int(row.get("null_entry_reason_rows") or 0) > 0
    ]
    entry_reason_rows = conn.execute(
        f"""
        SELECT COALESCE(entry_block_reason, 'NULL') AS reason, COUNT(*) AS rows
        FROM {table}
        WHERE feature_version = ?
        GROUP BY COALESCE(entry_block_reason, 'NULL')
        ORDER BY rows DESC, reason
        """,
        (feature_version,),
    ).fetchall()
    blocked_reason_rows = conn.execute(
        f"""
        SELECT COALESCE(entry_block_reason, 'NULL') AS reason, COUNT(*) AS rows
        FROM {table}
        WHERE feature_version = ? AND entry_buyable = 0
        GROUP BY COALESCE(entry_block_reason, 'NULL')
        ORDER BY rows DESC, reason
        """,
        (feature_version,),
    ).fetchall()
    details = {
        "table": table,
        "available": True,
        "row_count": int(fetch_scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE feature_version = ?", (feature_version,)) or 0),
        "by_horizon": by_horizon,
        "missing_horizons": missing_horizons,
        "incomplete_horizons": incomplete_horizons,
        "entry_block_reason_distribution": [dict(row) for row in entry_reason_rows],
        "entry_buyable_0_reason_distribution": [dict(row) for row in blocked_reason_rows],
        **latest,
    }
    ok = details["row_count"] > 0 and not missing_horizons and not incomplete_horizons
    return details, ok


def scan_files(paths: list[str], pattern: str, max_hits: int) -> tuple[dict[str, Any], bool]:
    if not paths:
        return {"enabled": False, "paths": []}, True

    regex = re.compile(pattern)
    hits: list[dict[str, Any]] = []
    scanned_files = 0

    def iter_files(path: Path) -> Iterable[Path]:
        if path.is_file():
            yield path
            return
        for child in path.rglob("*"):
            if child.is_dir():
                if child.name in {".git", "node_modules", ".venv", "venv", "__pycache__"}:
                    continue
                continue
            if child.suffix.lower() in TEXT_SUFFIX_ALLOWLIST:
                yield child

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        for file_path in iter_files(path):
            scanned_files += 1
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if not regex.search(line):
                    continue
                hits.append(
                    {
                        "file": str(file_path),
                        "line": line_number,
                        "text": line.strip(),
                    }
                )
                if len(hits) >= max_hits:
                    break
            if len(hits) >= max_hits:
                break
        if len(hits) >= max_hits:
            break

    details = {
        "enabled": True,
        "paths": paths,
        "regex": pattern,
        "scanned_files": scanned_files,
        "hit_count": len(hits),
        "hits": hits,
    }
    ok = len(hits) == 0
    return details, ok


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db).expanduser()
    payload: dict[str, Any] = {
        "generated_at": utc_now(),
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "feature_version": args.feature_version,
        "checks": {},
    }

    if not db_path.exists():
        payload["status"] = "fail"
        payload["checks"]["db"] = {
            "ok": False,
            "details": {"error": "db_path_not_found"},
        }
        optional_scan, optional_scan_ok = scan_files(args.scan_path, args.scan_regex, args.scan_max_hits)
        payload["checks"]["optional_limit_state_scan"] = {"ok": optional_scan_ok, "details": optional_scan}
        return payload

    payload["db_size_bytes"] = db_path.stat().st_size

    try:
        with connect_ro(db_path) as conn:
            required_table_details, required_table_ok = validate_required_tables(conn, args.feature_version)
            date_coverage_details, date_coverage_ok = validate_date_coverage(conn)
            manifest_summary = summarize_manifest(conn)
            csi1000_details, csi1000_ok = validate_csi1000_integrity(conn, args.feature_version)
            order_book_details, order_book_ok = validate_order_book_coverage(conn, args.feature_version)
            heat_null_details, heat_null_ok = validate_heat_null_semantics(conn, args.feature_version)
            training_label_details, training_label_ok = validate_training_labels(conn, args.feature_version)
            forbidden_columns_details, forbidden_columns_ok = validate_forbidden_feature_columns(conn)
    except sqlite3.Error as exc:
        payload["status"] = "fail"
        payload["checks"]["db"] = {
            "ok": False,
            "details": {"error": f"sqlite_error: {exc}"},
        }
        optional_scan, optional_scan_ok = scan_files(args.scan_path, args.scan_regex, args.scan_max_hits)
        payload["checks"]["optional_limit_state_scan"] = {"ok": optional_scan_ok, "details": optional_scan}
        return payload

    payload["checks"]["p0_required_tables"] = {"ok": required_table_ok, "details": required_table_details}
    payload["checks"]["date_coverage"] = {"ok": date_coverage_ok, "details": date_coverage_details}
    payload["checks"]["manifest_coverage_summary"] = {
        "ok": bool(manifest_summary.get("available")),
        "details": manifest_summary,
    }
    payload["checks"]["csi1000_integrity"] = {"ok": csi1000_ok, "details": csi1000_details}
    payload["checks"]["order_book_coverage"] = {"ok": order_book_ok, "details": order_book_details}
    payload["checks"]["heat_null_semantics"] = {"ok": heat_null_ok, "details": heat_null_details}
    payload["checks"]["training_label_integrity"] = {
        "ok": training_label_ok if args.mode == "training" else True,
        "details": training_label_details,
    }
    payload["checks"]["feature_tables_without_label_fields"] = {
        "ok": forbidden_columns_ok,
        "details": forbidden_columns_details,
    }
    optional_scan, optional_scan_ok = scan_files(args.scan_path, args.scan_regex, args.scan_max_hits)
    payload["checks"]["optional_limit_state_scan"] = {"ok": optional_scan_ok, "details": optional_scan}

    payload["mode"] = args.mode
    failing_checks = [name for name, item in payload["checks"].items() if not item["ok"]]
    payload["failing_checks"] = failing_checks
    payload["status"] = "pass" if not failing_checks else "fail"
    return payload


def main() -> None:
    args = parse_args()
    payload = build_payload(args)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
