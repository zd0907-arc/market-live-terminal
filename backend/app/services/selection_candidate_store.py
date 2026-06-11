from __future__ import annotations

import json
import math
import sqlite3
import time
from bisect import bisect_right
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.app.db.selection_db import ensure_selection_schema, get_selection_connection
from backend.app.db.selection_db import query_exit_watchlist_rows, replace_exit_watchlist_rows
from backend.app.services.spark_opportunity_exit import DEFAULT_DUAL_POLICY_ID, DEFAULT_DUAL_POLICY_NAME
from backend.app.services.spark_opportunity_selector import SOURCE_ID as SPARK_SOURCE_ID

ACTION_PRIORITY = {
    "candidate_buy": 3,
    "watch": 2,
    "blocked": 1,
}
SOURCE_PRIORITY = {
    SPARK_SOURCE_ID: 0,
    "stable_capital_callback": 1,
    "trend_continuation_callback": 2,
    "probe_d3_confirmed": 3,
    "probe_day0_watch": 4,
}
MAX_TRADE_DATE_WINDOW_DAYS = 540
DEFAULT_EXIT_POLICY_ID = DEFAULT_DUAL_POLICY_ID
_TRADE_DATE_CACHE_TTL_SECONDS = 60
_TRADE_DATE_CACHE: Dict[tuple, tuple[float, Dict[str, Any]]] = {}


def invalidate_daily_trade_dates_cache() -> None:
    _TRADE_DATE_CACHE.clear()


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else None, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mid = len(values) // 2
    if len(values) % 2:
        return float(values[mid])
    return (float(values[mid - 1]) + float(values[mid])) / 2.0


def _strength_label(percentile: float) -> str:
    if percentile >= 90:
        return "极强"
    if percentile >= 75:
        return "强"
    if percentile >= 55:
        return "中上"
    if percentile >= 35:
        return "中等"
    return "偏弱"


def _clean_symbol(value: Any) -> str:
    return str(value or "").strip().lower()


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _source_priority(source_id: Any) -> int:
    return int(SOURCE_PRIORITY.get(str(source_id or ""), 99))


def _list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None or value == "":
        return []
    return [value]


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sanitize_artifact_path(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    normalized = text.replace("\\", "/").rstrip("/")
    if "/" not in normalized:
        return normalized
    parts = [part for part in normalized.split("/") if part]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1]


def _exit_watch_row_to_candidate(row: Any) -> Dict[str, Any]:
    raw_payload = _json_load(row["raw_payload_json"], {})
    dual_exit_tracks = raw_payload.get("dual_exit_tracks") if isinstance(raw_payload.get("dual_exit_tracks"), list) else []
    spark_exit_meta = _dict(raw_payload.get("spark_exit_meta"))
    candidate_types = _list(raw_payload.get("candidate_types")) or ["spark_exit_watch"]
    return {
        "rank": int(row["rank"] or 0),
        "symbol": str(row["symbol"]),
        "name": str(row["name"] or row["symbol"]),
        "trade_date": str(row["trade_date"]),
        "score": _safe_float(row["score"]),
        "signal": int(row["signal"] or 0),
        "signal_label": str(row["signal_label"] or ""),
        "current_judgement": str(row["current_judgement"] or ""),
        "reason_summary": str(row["reason_summary"] or ""),
        "risk_level": str(row["risk_level"] or ""),
        "stealth_score": 0.0,
        "breakout_score": 0.0,
        "distribution_score": 0.0,
        "strategy_display_name": str(row["policy_name"] or raw_payload.get("strategy_display_name") or DEFAULT_DUAL_POLICY_NAME),
        "strategy_internal_id": str(row["source_id"] or raw_payload.get("strategy_internal_id") or ""),
        "feature_version": "spark_opportunity_exit_watchlist",
        "strategy_version": str(row["policy_id"] or DEFAULT_EXIT_POLICY_ID),
        "policy_id": str(row["policy_id"] or DEFAULT_EXIT_POLICY_ID),
        "policy_name": str(row["policy_name"] or DEFAULT_DUAL_POLICY_NAME),
        "candidate_types": candidate_types,
        "entry_allowed": bool(row["entry_allowed"]),
        "entry_block_reasons": [],
        "selection_rank_score": _safe_float(row["score"]),
        "source_score": _safe_float(row["score"]),
        "selection_rank_mode": "spark_exit_watch",
        "lifecycle_phase": str(row["lifecycle_phase"] or ""),
        "lifecycle_phase_label": str(row["lifecycle_phase_label"] or ""),
        "action_label": str(row["action_label"] or ""),
        "entry_signal_date": str(row["entry_signal_date"] or "") or None,
        "entry_date": str(row["entry_date"] or "") or None,
        "exit_signal_date": str(row["exit_signal_date"] or "") or None,
        "exit_date": str(row["exit_date"] or "") or None,
        "exit_plan_summary": str(row["exit_plan_summary"] or ""),
        "source_count": 1,
        "source_ids": _json_load(row["source_ids_json"], []),
        "source_types": _json_load(row["source_types_json"], []),
        "primary_source_id": str(row["source_id"] or ""),
        "primary_source_name": str(row["source_name"] or ""),
        "primary_source_type": str(row["source_type"] or ""),
        "source_details": _json_load(row["source_details_json"], []),
        "trade_plan": _json_load(row["trade_plan_json"], {}),
        "dual_exit_tracks": dual_exit_tracks,
        "spark_exit_meta": spark_exit_meta,
        "raw_payload": raw_payload,
    }


def _next_trade_date_from_selection(trade_date: str) -> Optional[str]:
    conn = get_selection_connection()
    try:
        row = conn.execute(
            """
            SELECT MIN(trade_date) AS next_date
            FROM selection_feature_daily
            WHERE trade_date > ?
            """,
            (str(trade_date),),
        ).fetchone()
        return str(row["next_date"]) if row and row["next_date"] else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _next_trade_dates_from_selection(trade_dates: Sequence[str]) -> Dict[str, Optional[str]]:
    normalized = sorted({str(item) for item in trade_dates if item})
    if not normalized:
        return {}
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        placeholders = ",".join("?" for _ in normalized)
        rows = conn.execute(
            f"""
            SELECT base.trade_date AS trade_date, MIN(next.trade_date) AS next_date
            FROM (
                SELECT DISTINCT trade_date
                FROM selection_feature_daily
                WHERE trade_date IN ({placeholders})
            ) AS base
            LEFT JOIN selection_feature_daily AS next
              ON next.trade_date > base.trade_date
            GROUP BY base.trade_date
            """,
            normalized,
        ).fetchall()
        return {
            str(row["trade_date"]): (str(row["next_date"]) if row["next_date"] else None)
            for row in rows
        }
    finally:
        conn.close()


def normalize_source_record(record: Dict[str, Any]) -> Dict[str, Any]:
    source_id = _clean_text(record.get("source_id"))
    if not source_id:
        raise ValueError("source_id is required")
    return {
        "source_id": source_id,
        "source_name": _clean_text(record.get("source_name"), source_id),
        "source_type": _clean_text(record.get("source_type"), "rule_strategy"),
        "source_version": _clean_text(record.get("source_version"), "unknown"),
        "artifact_version": _clean_text(record.get("artifact_version"), ""),
        "horizon": _clean_text(record.get("horizon"), ""),
        "status": _clean_text(record.get("status"), "active"),
        "owner_note": _clean_text(record.get("owner_note"), ""),
        "description": _clean_text(record.get("description"), ""),
        "metadata": _dict(record.get("metadata")),
    }


def normalize_candidate_record(record: Dict[str, Any]) -> Dict[str, Any]:
    trade_date = _clean_text(record.get("trade_date"))
    symbol = _clean_symbol(record.get("symbol"))
    source_id = _clean_text(record.get("source_id"))
    if not trade_date or not symbol or not source_id:
        raise ValueError(f"candidate requires trade_date/symbol/source_id: {record}")
    source_name = _clean_text(record.get("source_name"), source_id)
    source_type = _clean_text(record.get("source_type"), "rule_strategy")
    suggested_action = _clean_text(record.get("suggested_action"), "watch")
    entry_allowed = bool(record.get("entry_allowed")) and suggested_action == "candidate_buy"
    if suggested_action not in ACTION_PRIORITY:
        suggested_action = "watch"
        entry_allowed = False
    return {
        "trade_date": trade_date,
        "symbol": symbol,
        "name": _clean_text(record.get("name"), symbol),
        "source_id": source_id,
        "source_name": source_name,
        "source_type": source_type,
        "source_version": _clean_text(record.get("source_version"), "unknown"),
        "artifact_version": _clean_text(record.get("artifact_version"), ""),
        "source_status": _clean_text(record.get("source_status") or record.get("status"), "active"),
        "rank": max(1, _safe_int(record.get("rank"), 1)),
        "score": _safe_float(record.get("score")),
        "score_scale": _clean_text(record.get("score_scale"), "raw"),
        "horizon": _clean_text(record.get("horizon"), ""),
        "suggested_action": suggested_action,
        "action_label": _clean_text(record.get("action_label"), "明日可买" if entry_allowed else "观察"),
        "entry_allowed": entry_allowed,
        "buy_rule": _clean_text(record.get("buy_rule"), ""),
        "reason_summary": _clean_text(record.get("reason_summary"), ""),
        "risk_tags": _list(record.get("risk_tags")),
        "entry_block_reasons": _list(record.get("entry_block_reasons")),
        "explain_factors": _dict(record.get("explain_factors")),
        "raw_payload": _dict(record.get("raw_payload")),
        "artifact_path": _sanitize_artifact_path(record.get("artifact_path")),
    }


def upsert_strategy_registry(records: Iterable[Dict[str, Any]]) -> int:
    normalized = [normalize_source_record(item) for item in records]
    if not normalized:
        return 0
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        with conn:
            conn.executemany(
                """
                INSERT INTO selection_strategy_registry (
                    source_id, source_name, source_type, source_version, artifact_version,
                    horizon, status, owner_note, description, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name=excluded.source_name,
                    source_type=excluded.source_type,
                    source_version=excluded.source_version,
                    artifact_version=excluded.artifact_version,
                    horizon=excluded.horizon,
                    status=excluded.status,
                    owner_note=excluded.owner_note,
                    description=excluded.description,
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                [
                    (
                        item["source_id"],
                        item["source_name"],
                        item["source_type"],
                        item["source_version"],
                        item["artifact_version"],
                        item["horizon"],
                        item["status"],
                        item["owner_note"],
                        item["description"],
                        _json_dump(item["metadata"]),
                    )
                    for item in normalized
                ],
            )
        return len(normalized)
    finally:
        conn.close()


def replace_source_candidates(trade_date: str, source_id: str, records: Sequence[Dict[str, Any]]) -> int:
    normalized = [normalize_candidate_record(item) for item in records]
    normalized = [item for item in normalized if item["trade_date"] == trade_date and item["source_id"] == source_id]
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM selection_candidate_sources WHERE trade_date=? AND source_id=?",
                (trade_date, source_id),
            )
            if normalized:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO selection_candidate_sources (
                        trade_date, symbol, name, source_id, source_name, source_type,
                        source_version, artifact_version, source_status, rank, score, score_scale,
                        horizon, suggested_action, action_label, entry_allowed, buy_rule,
                        reason_summary, risk_tags_json, entry_block_reasons_json,
                        explain_factors_json, raw_payload_json, artifact_path, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    [
                        (
                            item["trade_date"],
                            item["symbol"],
                            item["name"],
                            item["source_id"],
                            item["source_name"],
                            item["source_type"],
                            item["source_version"],
                            item["artifact_version"],
                            item["source_status"],
                            item["rank"],
                            item["score"],
                            item["score_scale"],
                            item["horizon"],
                            item["suggested_action"],
                            item["action_label"],
                            1 if item["entry_allowed"] else 0,
                            item["buy_rule"],
                            item["reason_summary"],
                            _json_dump(item["risk_tags"]),
                            _json_dump(item["entry_block_reasons"]),
                            _json_dump(item["explain_factors"]),
                            _json_dump(item["raw_payload"]),
                            item["artifact_path"],
                        )
                        for item in normalized
                    ],
                )
            conn.execute(
                """
                INSERT INTO selection_strategy_runs (
                    trade_date, source_id, source_version, run_status, candidate_count, finished_at
                ) VALUES (?, ?, ?, 'success', ?, CURRENT_TIMESTAMP)
                """,
                (
                    trade_date,
                    source_id,
                    normalized[0]["source_version"] if normalized else "",
                    len(normalized),
                ),
            )
        return len(normalized)
    finally:
        conn.close()


def record_source_run_error(trade_date: str, source_id: str, error_message: str, source_version: str = "") -> None:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO selection_strategy_runs (
                    trade_date, source_id, source_version, run_status, candidate_count, error_message, finished_at
                ) VALUES (?, ?, ?, 'failed', 0, ?, CURRENT_TIMESTAMP)
                """,
                (trade_date, source_id, source_version, str(error_message)[:1000]),
            )
    finally:
        conn.close()


def _source_row_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "trade_date": str(row["trade_date"]),
        "symbol": str(row["symbol"]),
        "name": str(row["name"] or row["symbol"]),
        "source_id": str(row["source_id"]),
        "source_name": str(row["source_name"]),
        "source_type": str(row["source_type"]),
        "source_version": str(row["source_version"]),
        "artifact_version": str(row["artifact_version"] or ""),
        "source_status": str(row["source_status"] or "active"),
        "rank": int(row["rank"] or 0),
        "score": _safe_float(row["score"]),
        "score_scale": str(row["score_scale"] or "raw"),
        "horizon": str(row["horizon"] or ""),
        "suggested_action": str(row["suggested_action"] or "watch"),
        "action_label": str(row["action_label"] or ""),
        "entry_allowed": bool(row["entry_allowed"]),
        "buy_rule": str(row["buy_rule"] or ""),
        "reason_summary": str(row["reason_summary"] or ""),
        "risk_tags": _json_load(row["risk_tags_json"], []),
        "entry_block_reasons": _json_load(row["entry_block_reasons_json"], []),
        "explain_factors": _json_load(row["explain_factors_json"], {}),
        "raw_payload": _json_load(row["raw_payload_json"], {}),
        "artifact_path": _sanitize_artifact_path(row["artifact_path"]),
    }


def _merged_action(rows: List[Dict[str, Any]]) -> tuple[str, str, bool]:
    has_buy = any(item["suggested_action"] == "candidate_buy" and item["entry_allowed"] for item in rows)
    if has_buy:
        return "candidate_buy", "明日可买", True
    has_watch = any(item["suggested_action"] == "watch" for item in rows)
    if has_watch:
        return "watch", "观察", False
    return "blocked", "风险拦截", False


def _merge_unique(rows: List[Dict[str, Any]], key: str) -> List[Any]:
    out: List[Any] = []
    for row in rows:
        for item in _list(row.get(key)):
            if item not in out:
                out.append(item)
    return out


def _source_score_stats(conn: Any, source_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    ids = sorted({str(item) for item in source_ids if item})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT source_id, score
        FROM selection_candidate_sources
        WHERE source_id IN ({placeholders})
        ORDER BY source_id ASC, score ASC
        """,
        ids,
    ).fetchall()
    by_source: Dict[str, List[float]] = defaultdict(list)
    for row in rows:
        by_source[str(row["source_id"])].append(_safe_float(row["score"]))
    stats: Dict[str, Dict[str, Any]] = {}
    for source_id, values in by_source.items():
        clean_values = sorted(values)
        if not clean_values:
            continue
        stats[source_id] = {
            "scores": clean_values,
            "count": len(clean_values),
            "min": round(clean_values[0], 6),
            "median": round(_median(clean_values), 6),
            "avg": round(sum(clean_values) / len(clean_values), 6),
            "max": round(clean_values[-1], 6),
        }
    return stats


def _annotate_source_details(source_details: List[Dict[str, Any]], stats: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for item in source_details:
        source = dict(item)
        stat = stats.get(str(source.get("source_id") or ""))
        if stat:
            score = _safe_float(source.get("score"))
            scores = stat.get("scores") or []
            percentile = (bisect_right(scores, score) / len(scores) * 100.0) if scores else 0.0
            source["source_score_percentile"] = round(percentile, 1)
            source["source_strength_label"] = _strength_label(percentile)
            source["source_score_distribution"] = {
                "count": stat.get("count", 0),
                "min": stat.get("min", 0.0),
                "median": stat.get("median", 0.0),
                "avg": stat.get("avg", 0.0),
                "max": stat.get("max", 0.0),
            }
        annotated.append(source)
    return annotated


def rebuild_daily_candidates(trade_date: str) -> int:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        rows = [
            _source_row_to_dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM selection_candidate_sources
                WHERE trade_date=?
                ORDER BY source_type ASC, source_id ASC, rank ASC, symbol ASC
                """,
                (trade_date,),
            ).fetchall()
        ]
        by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in rows:
            by_source[item["source_id"]].append(item)
            by_symbol[item["symbol"]].append(item)
        source_stats = _source_score_stats(conn, by_source.keys())

        merged: List[Dict[str, Any]] = []
        for symbol, symbol_rows in by_symbol.items():
            ranked_rows = sorted(
                symbol_rows,
                key=lambda item: (
                    -ACTION_PRIORITY.get(item["suggested_action"], 0),
                    _source_priority(item["source_id"]),
                    item["rank"],
                    -item["score"],
                    item["source_id"],
                ),
            )
            primary = ranked_rows[0]
            source_count = len({item["source_id"] for item in symbol_rows})
            source_types = sorted({item["source_type"] for item in symbol_rows})
            model_rule_bonus = 10.0 if {"model", "rule_strategy"}.issubset(set(source_types)) else 0.0
            score_parts = [_safe_float(item.get("score")) for item in symbol_rows]
            combined_score = (max(score_parts) if score_parts else 0.0) + 15.0 * max(0, source_count - 1) + model_rule_bonus
            risk_tags = _merge_unique(symbol_rows, "risk_tags")
            block_reasons = _merge_unique(symbol_rows, "entry_block_reasons")
            suggested_action, action_label, entry_allowed = _merged_action(symbol_rows)
            if len(risk_tags) >= 2 or any(item["suggested_action"] == "blocked" for item in symbol_rows):
                combined_score -= 20.0
                if not entry_allowed:
                    suggested_action, action_label = "blocked", "风险提示"
            if suggested_action == "watch":
                combined_score -= 10.0
            merged.append(
                {
                    "trade_date": trade_date,
                    "symbol": symbol,
                    "name": primary["name"] or symbol,
                    "combined_score": round(combined_score, 6),
                    "source_score": round(max(score_parts) if score_parts else 0.0, 6),
                    "suggested_action": suggested_action,
                    "action_label": action_label,
                    "entry_allowed": entry_allowed,
                    "source_count": source_count,
                    "source_ids": [item["source_id"] for item in ranked_rows],
                    "source_types": source_types,
                    "primary_source_id": primary["source_id"],
                    "primary_source_name": primary["source_name"],
                    "primary_source_type": primary["source_type"],
                    "reason_summary": primary["reason_summary"],
                    "risk_tags": risk_tags,
                    "entry_block_reasons": block_reasons,
                    "buy_rule": primary["buy_rule"],
                    "source_details": _annotate_source_details(ranked_rows, source_stats),
                }
            )

        merged.sort(
            key=lambda item: (
                -ACTION_PRIORITY.get(item["suggested_action"], 0),
                _source_priority(item["primary_source_id"]),
                -item["combined_score"],
                item["symbol"],
            )
        )
        for idx, item in enumerate(merged, start=1):
            item["combined_rank"] = idx

        with conn:
            conn.execute("DELETE FROM selection_candidate_daily WHERE trade_date=?", (trade_date,))
            if merged:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO selection_candidate_daily (
                        trade_date, symbol, name, combined_rank, combined_score,
                        suggested_action, action_label, entry_allowed, source_count,
                        source_ids_json, source_types_json, primary_source_id,
                        primary_source_name, primary_source_type, reason_summary,
                        risk_tags_json, entry_block_reasons_json, buy_rule,
                        source_details_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    [
                        (
                            item["trade_date"],
                            item["symbol"],
                            item["name"],
                            item["combined_rank"],
                            item["combined_score"],
                            item["suggested_action"],
                            item["action_label"],
                            1 if item["entry_allowed"] else 0,
                            item["source_count"],
                            _json_dump(item["source_ids"]),
                            _json_dump(item["source_types"]),
                            item["primary_source_id"],
                            item["primary_source_name"],
                            item["primary_source_type"],
                            item["reason_summary"],
                            _json_dump(item["risk_tags"]),
                            _json_dump(item["entry_block_reasons"]),
                            item["buy_rule"],
                            _json_dump(item["source_details"]),
                        )
                        for item in merged
                    ],
                )
        return len(merged)
    finally:
        conn.close()
        invalidate_daily_trade_dates_cache()


def _daily_row_to_candidate(row: Any, next_trade_date_by_date: Optional[Dict[str, Optional[str]]] = None) -> Dict[str, Any]:
    source_details = _json_load(row["source_details_json"], [])
    explain_factors: Dict[str, Any] = {}
    raw_payload: Dict[str, Any] = {}
    if source_details:
        explain_factors = _dict(source_details[0].get("explain_factors"))
        raw_payload = _dict(source_details[0].get("raw_payload"))
    trade_date = str(row["trade_date"])
    primary_source_id = str(row["primary_source_id"] or "")
    is_entry_allowed = bool(row["entry_allowed"])
    entry_signal_date = raw_payload.get("entry_signal_date") or (trade_date if primary_source_id == SPARK_SOURCE_ID else None)
    fallback_entry_date = None
    if is_entry_allowed:
        if next_trade_date_by_date is not None:
            fallback_entry_date = next_trade_date_by_date.get(trade_date)
        else:
            fallback_entry_date = _next_trade_date_from_selection(trade_date)
    entry_date = raw_payload.get("entry_date") or fallback_entry_date
    return {
        "rank": int(row["combined_rank"] or 0),
        "symbol": str(row["symbol"]),
        "name": str(row["name"] or row["symbol"]),
        "trade_date": trade_date,
        "score": _safe_float(row["combined_score"]),
        "signal": 1 if is_entry_allowed else 0,
        "signal_label": str(row["suggested_action"] or ""),
        "current_judgement": str(row["action_label"] or ""),
        "reason_summary": str(row["reason_summary"] or ""),
        "risk_level": "high" if row["suggested_action"] == "blocked" else "watch" if row["suggested_action"] == "watch" else "low",
        "stealth_score": _safe_float(explain_factors.get("stealth_score")),
        "breakout_score": _safe_float(explain_factors.get("breakout_score")),
        "distribution_score": _safe_float(explain_factors.get("distribution_score")),
        "close": explain_factors.get("close"),
        "return_5d_pct": explain_factors.get("return_5d_pct"),
        "return_20d_pct": explain_factors.get("return_20d_pct"),
        "strategy_display_name": str(row["primary_source_name"] or ""),
        "strategy_internal_id": primary_source_id,
        "feature_version": "daily_candidate_pool",
        "strategy_version": primary_source_id,
        "candidate_types": _json_load(row["source_ids_json"], []),
        "entry_allowed": is_entry_allowed,
        "entry_block_reasons": _json_load(row["entry_block_reasons_json"], []),
        "selection_rank_score": _safe_float(row["combined_score"]),
        "source_score": _safe_float(source_details[0].get("score") if source_details else row["combined_score"]),
        "selection_rank_mode": "daily_candidate_pool",
        "lifecycle_phase": str(row["suggested_action"] or ""),
        "lifecycle_phase_label": str(row["action_label"] or ""),
        "action_label": str(row["action_label"] or ""),
        "risk_count": len(_json_load(row["risk_tags_json"], [])),
        "risk_labels": _json_load(row["risk_tags_json"], []),
        "setup_reason": str(row["reason_summary"] or ""),
        "launch_reason": "",
        "pullback_reason": "",
        "observe_date": raw_payload.get("observe_date"),
        "discovery_date": raw_payload.get("discovery_date"),
        "launch_start_date": raw_payload.get("launch_start_date"),
        "launch_end_date": raw_payload.get("launch_end_date"),
        "pullback_confirm_date": raw_payload.get("pullback_confirm_date"),
        "entry_signal_date": entry_signal_date,
        "entry_date": entry_date,
        "exit_signal_date": raw_payload.get("exit_signal_date"),
        "exit_date": raw_payload.get("exit_date"),
        "replay_return_pct": raw_payload.get("replay_return_pct"),
        "replay_entry_date": raw_payload.get("replay_entry_date"),
        "replay_exit_signal_date": raw_payload.get("replay_exit_signal_date"),
        "replay_exit_reason": raw_payload.get("replay_exit_reason"),
        "exit_plan_summary": str(row["buy_rule"] or ""),
        "source_count": int(row["source_count"] or 0),
        "source_ids": _json_load(row["source_ids_json"], []),
        "source_types": _json_load(row["source_types_json"], []),
        "primary_source_id": str(row["primary_source_id"] or ""),
        "primary_source_name": str(row["primary_source_name"] or ""),
        "primary_source_type": str(row["primary_source_type"] or ""),
        "source_details": source_details,
    }


def query_daily_candidates(trade_date: Optional[str] = None, *, limit: int = 50, source_type: Optional[str] = None) -> Dict[str, Any]:
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        target = trade_date
        if not target:
            row = conn.execute("SELECT MAX(trade_date) AS trade_date FROM selection_candidate_daily").fetchone()
            target = str(row["trade_date"]) if row and row["trade_date"] else None
        if not target:
            return {"trade_date": trade_date or "", "strategy": "daily_candidate_pool", "rank_mode": "daily_candidate_pool", "items": []}
        params: List[Any] = [target]
        source_filter = ""
        if source_type:
            source_filter = "AND source_types_json LIKE ?"
            params.append(f'%"{source_type}"%')
        params.append(int(limit))
        rows = conn.execute(
            f"""
            SELECT *
            FROM selection_candidate_daily
            WHERE trade_date=?
              {source_filter}
            ORDER BY combined_rank ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
        next_trade_date_by_date = _next_trade_dates_from_selection([str(row["trade_date"]) for row in rows])
        return {
            "trade_date": target,
            "strategy": "daily_candidate_pool",
            "strategy_display_name": "每日综合候选池",
            "strategy_internal_id": "daily_candidate_pool",
            "rank_mode": "daily_candidate_pool",
            "items": [_daily_row_to_candidate(row, next_trade_date_by_date) for row in rows],
        }
    finally:
        conn.close()


def query_daily_trade_dates(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    ensure_selection_schema()
    cache_key = (str(start_date or ""), str(end_date or ""))
    cached = _TRADE_DATE_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _TRADE_DATE_CACHE_TTL_SECONDS:
        return cached[1]
    conn = get_selection_connection()
    try:
        bounds = conn.execute(
            """
            SELECT
                MIN(trade_date) AS min_date,
                MAX(trade_date) AS max_date
            FROM selection_feature_daily
            """
        ).fetchone()
        candidate_rows = conn.execute(
            """
            SELECT trade_date, COUNT(*) AS signal_count
            FROM selection_candidate_daily
            WHERE (? IS NULL OR trade_date >= ?)
              AND (? IS NULL OR trade_date <= ?)
            GROUP BY trade_date
            """,
            (start_date, start_date, end_date, end_date),
        ).fetchall()
        feature_rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM selection_feature_daily
            WHERE (? IS NULL OR trade_date >= ?)
              AND (? IS NULL OR trade_date <= ?)
            """,
            (start_date, start_date, end_date, end_date),
        ).fetchall()
        run_rows = conn.execute(
            """
            SELECT
                trade_date,
                COUNT(*) AS run_count,
                SUM(CASE WHEN run_status='success' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN run_status='failed' THEN 1 ELSE 0 END) AS failed_count,
                SUM(candidate_count) AS run_candidate_count,
                MAX(finished_at) AS last_finished_at
            FROM selection_strategy_runs
            WHERE (? IS NULL OR trade_date >= ?)
              AND (? IS NULL OR trade_date <= ?)
            GROUP BY trade_date
            """,
            (start_date, start_date, end_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    feature_dates = {str(row["trade_date"]): 1 for row in feature_rows}
    signal_counts = {str(row["trade_date"]): int(row["signal_count"] or 0) for row in candidate_rows}
    run_counts = {str(row["trade_date"]): int(row["run_count"] or 0) for row in run_rows}
    success_counts = {str(row["trade_date"]): int(row["success_count"] or 0) for row in run_rows}
    failed_counts = {str(row["trade_date"]): int(row["failed_count"] or 0) for row in run_rows}
    run_candidate_counts = {str(row["trade_date"]): int(row["run_candidate_count"] or 0) for row in run_rows}
    last_finished_by_date = {
        str(row["trade_date"]): str(row["last_finished_at"] or "")
        for row in run_rows
        if row["last_finished_at"]
    }
    try:
        from backend.app.services.selection_market_environment_gate import market_state_by_date

        market_environment_dates = {
            date
            for date in market_state_by_date()
            if (not start_date or date >= start_date) and (not end_date or date <= end_date)
        }
    except Exception:
        market_environment_dates = set()
    resolved_start = start_date or (str(bounds["min_date"]) if bounds and bounds["min_date"] else None)
    resolved_end = end_date or (str(bounds["max_date"]) if bounds and bounds["max_date"] else None)
    if market_environment_dates:
        resolved_start = min([item for item in [resolved_start, min(market_environment_dates)] if item])
        resolved_end = max([item for item in [resolved_end, max(market_environment_dates)] if item])
    if not resolved_start or not resolved_end:
        return {"start_date": resolved_start, "end_date": resolved_end, "strategy": "daily_candidate_pool", "items": []}
    if resolved_start > resolved_end:
        resolved_start, resolved_end = resolved_end, resolved_start

    from datetime import datetime, timedelta

    start_dt = datetime.strptime(resolved_start, "%Y-%m-%d")
    end_dt = datetime.strptime(resolved_end, "%Y-%m-%d")
    total_days = (end_dt - start_dt).days
    truncated = total_days > MAX_TRADE_DATE_WINDOW_DAYS
    if truncated:
        start_dt = end_dt - timedelta(days=MAX_TRADE_DATE_WINDOW_DAYS)
        resolved_start = start_dt.strftime("%Y-%m-%d")
    items: List[Dict[str, Any]] = []
    for offset in range((end_dt - start_dt).days + 1):
        day = (start_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        feature_count = feature_dates.get(day, 0)
        has_feature = feature_count > 0
        signal_count = signal_counts.get(day, 0)
        run_count = run_counts.get(day, 0)
        success_count = success_counts.get(day, 0)
        failed_count = failed_counts.get(day, 0)
        has_market_environment = day in market_environment_dates
        is_trade_day = has_feature or has_market_environment or datetime.strptime(day, "%Y-%m-%d").weekday() < 5
        selectable = bool(has_feature or has_market_environment)
        if not is_trade_day:
            disabled_reason = "休市"
        elif has_market_environment and not has_feature:
            disabled_reason = "仅市场水位"
        elif not has_feature:
            disabled_reason = "无行情/评分数据"
        elif signal_count <= 0:
            disabled_reason = "当天无候选"
        else:
            disabled_reason = None
        items.append(
            {
                "date": day,
                "is_trade_day": is_trade_day,
                "signal_count": signal_count,
                "candidate_count": signal_count,
                "feature_count": feature_count,
                "has_feature": has_feature,
                "has_candidates": signal_count > 0,
                "has_market_environment": has_market_environment,
                "market_environment_only": has_market_environment and not has_feature,
                "can_generate": has_feature and signal_count <= 0,
                "has_run": run_count > 0,
                "run_count": run_count,
                "successful_run_count": success_count,
                "failed_run_count": failed_count,
                "run_candidate_count": run_candidate_counts.get(day, 0),
                "last_run_finished_at": last_finished_by_date.get(day) or None,
                "selectable": selectable,
                "disabled_reason": disabled_reason,
            }
        )
    payload = {
        "start_date": resolved_start,
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "strategy": "daily_candidate_pool",
        "truncated": truncated,
        "window_days": (end_dt - start_dt).days + 1,
        "items": items,
    }
    _TRADE_DATE_CACHE[cache_key] = (now, payload)
    return payload


def query_daily_candidate_profile(symbol: str, trade_date: str) -> Optional[Dict[str, Any]]:
    normalized = _clean_symbol(symbol)
    ensure_selection_schema()
    conn = get_selection_connection()
    try:
        row = conn.execute(
            """
            SELECT *
            FROM selection_candidate_daily
            WHERE symbol=? AND trade_date=?
            LIMIT 1
            """,
            (normalized, trade_date),
        ).fetchone()
        if not row:
            return None
        next_trade_date_by_date = _next_trade_dates_from_selection([trade_date])
        return _daily_row_to_candidate(row, next_trade_date_by_date)
    finally:
        conn.close()


def replace_daily_exit_watchlist(trade_date: str, payload: Dict[str, Any]) -> int:
    items = list(payload.get("items") or [])
    policy_id = str(payload.get("policy_id") or DEFAULT_EXIT_POLICY_ID)
    rows = []
    for item in items:
        row = dict(item)
        row["policy_name"] = str(payload.get("policy_name") or row.get("policy_name") or "")
        rows.append(row)
    return replace_exit_watchlist_rows(trade_date, policy_id, rows)


def query_daily_exit_watchlist(trade_date: str, policy_id: str = DEFAULT_EXIT_POLICY_ID) -> Dict[str, Any]:
    rows = query_exit_watchlist_rows(trade_date, policy_id=policy_id)
    if not rows and policy_id == DEFAULT_EXIT_POLICY_ID:
        rows = query_exit_watchlist_rows(trade_date, policy_id=None)
    return {
        "trade_date": str(trade_date),
        "policy_id": str(rows[0]["policy_id"]) if rows else str(policy_id),
        "policy_name": str(rows[0]["policy_name"]) if rows else DEFAULT_DUAL_POLICY_NAME,
        "items": [_exit_watch_row_to_candidate(row) for row in rows],
    }
