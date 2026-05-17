from __future__ import annotations

import json
import math
import sqlite3
from bisect import bisect_right
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.app.db.selection_db import ensure_selection_schema, get_selection_connection
from backend.app.services.spark_opportunity_selector import SOURCE_ID as SPARK_SOURCE_ID

ACTION_PRIORITY = {
    "candidate_buy": 3,
    "watch": 2,
    "blocked": 1,
}


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
        "artifact_path": _clean_text(record.get("artifact_path"), ""),
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
        "artifact_path": str(row["artifact_path"] or ""),
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


def _daily_row_to_candidate(row: Any) -> Dict[str, Any]:
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
    entry_date = raw_payload.get("entry_date") or (_next_trade_date_from_selection(trade_date) if is_entry_allowed else None)
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
        return {
            "trade_date": target,
            "strategy": "daily_candidate_pool",
            "strategy_display_name": "每日综合候选池",
            "strategy_internal_id": "daily_candidate_pool",
            "rank_mode": "daily_candidate_pool",
            "items": [_daily_row_to_candidate(row) for row in rows],
        }
    finally:
        conn.close()


def query_daily_trade_dates(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    ensure_selection_schema()
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
            SELECT trade_date, COUNT(*) AS row_count
            FROM selection_feature_daily
            WHERE (? IS NULL OR trade_date >= ?)
              AND (? IS NULL OR trade_date <= ?)
            GROUP BY trade_date
            """,
            (start_date, start_date, end_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    feature_dates = {str(row["trade_date"]): int(row["row_count"] or 0) for row in feature_rows}
    signal_counts = {str(row["trade_date"]): int(row["signal_count"] or 0) for row in candidate_rows}
    resolved_start = start_date or (str(bounds["min_date"]) if bounds and bounds["min_date"] else None)
    resolved_end = end_date or (str(bounds["max_date"]) if bounds and bounds["max_date"] else None)
    if not resolved_start or not resolved_end:
        return {"start_date": resolved_start, "end_date": resolved_end, "strategy": "daily_candidate_pool", "items": []}
    if resolved_start > resolved_end:
        resolved_start, resolved_end = resolved_end, resolved_start

    from datetime import datetime, timedelta

    start_dt = datetime.strptime(resolved_start, "%Y-%m-%d")
    end_dt = datetime.strptime(resolved_end, "%Y-%m-%d")
    max_days = min((end_dt - start_dt).days, 540)
    items: List[Dict[str, Any]] = []
    for offset in range(max_days + 1):
        day = (start_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        has_feature = feature_dates.get(day, 0) > 0
        signal_count = signal_counts.get(day, 0)
        is_trade_day = has_feature or datetime.strptime(day, "%Y-%m-%d").weekday() < 5
        selectable = bool(has_feature)
        if not is_trade_day:
            disabled_reason = "休市"
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
                "selectable": selectable,
                "disabled_reason": disabled_reason,
            }
        )
    return {
        "start_date": resolved_start,
        "end_date": (start_dt + timedelta(days=max_days)).strftime("%Y-%m-%d"),
        "strategy": "daily_candidate_pool",
        "items": items,
    }


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
        return _daily_row_to_candidate(row)
    finally:
        conn.close()
