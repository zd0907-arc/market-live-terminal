from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.app.services import spark_opportunity_selector
from backend.app.services.selection_candidate_store import (
    query_daily_candidate_profile,
    query_daily_candidates,
    query_daily_trade_dates,
    rebuild_daily_candidates,
    record_source_run_error,
    replace_source_candidates,
    upsert_strategy_registry,
)
from backend.app.services.selection_research import get_profile
from backend.app.services.selection_stable_callback import (
    STRATEGY_DISPLAY_NAME as STABLE_SOURCE_NAME,
    STRATEGY_INTERNAL_ID as STABLE_SOURCE_ID,
    STRATEGY_VERSION as STABLE_SOURCE_VERSION,
    get_stable_callback_candidates,
)
from backend.app.services.spark_opportunity_exit import get_daily_exit_watchlist
from backend.app.services.selection_trend_continuation import (
    STRATEGY_DISPLAY_NAME as TREND_SOURCE_NAME,
    STRATEGY_INTERNAL_ID as TREND_SOURCE_ID,
    STRATEGY_VERSION as TREND_SOURCE_VERSION,
    get_trend_continuation_candidates,
)

DAILY_POOL_ID = "daily_candidate_pool"
SPARK_SOURCE_ID = spark_opportunity_selector.SOURCE_ID
ACTIVE_SOURCE_IDS = [SPARK_SOURCE_ID, STABLE_SOURCE_ID, TREND_SOURCE_ID]
SOURCE_DAILY_LIMITS = {
    SPARK_SOURCE_ID: 3,
    STABLE_SOURCE_ID: 10,
    TREND_SOURCE_ID: 8,
}
TREND_OBSERVATION_MIN_SCORE = 70.0
TREND_OBSERVATION_LIMIT = 5


def source_registry_records() -> List[Dict[str, Any]]:
    spark_record = spark_opportunity_selector.source_registry_record()
    return [
        spark_record,
        {
            "source_id": STABLE_SOURCE_ID,
            "source_name": STABLE_SOURCE_NAME,
            "source_type": "rule_strategy",
            "source_version": STABLE_SOURCE_VERSION,
            "artifact_version": STABLE_SOURCE_VERSION,
            "horizon": "swing",
            "status": "active",
            "owner_note": "P1 过渡接入：当前仍复用历史实验产物，后续改为每日真实跑数。",
            "description": "资金流回调稳健策略。",
        },
        {
            "source_id": TREND_SOURCE_ID,
            "source_name": TREND_SOURCE_NAME,
            "source_type": "rule_strategy",
            "source_version": TREND_SOURCE_VERSION,
            "artifact_version": TREND_SOURCE_VERSION,
            "horizon": "swing",
            "status": "active",
            "owner_note": "P1 过渡接入：当前仍复用历史实验产物，后续改为每日真实跑数。",
            "description": "趋势中继高质量回踩策略。",
        },
    ]


def ensure_daily_source_registry() -> int:
    return upsert_strategy_registry(source_registry_records())


def _standard_action_from_strategy_candidate(item: Dict[str, Any]) -> tuple[str, str, bool]:
    if item.get("entry_allowed") is not False:
        return "candidate_buy", str(item.get("action_label") or "明日可买"), True
    candidate_types = [str(value) for value in item.get("candidate_types") or []]
    action_label = str(item.get("action_label") or "")
    lifecycle = str(item.get("lifecycle_phase") or "")
    if "observe" in " ".join(candidate_types) or action_label == "观察中" or lifecycle == "trend_observation_pool":
        return "watch", action_label or "观察", False
    return "blocked", action_label or "风险拦截", False


def _strategy_candidate_to_standard(
    item: Dict[str, Any],
    *,
    source_id: str,
    source_name: str,
    source_version: str,
    rank: int,
) -> Dict[str, Any]:
    suggested_action, action_label, entry_allowed = _standard_action_from_strategy_candidate(item)
    explain_keys = [
        "score",
        "selection_rank_score",
        "stealth_score",
        "breakout_score",
        "distribution_score",
        "return_5d_pct",
        "return_10d_pct",
        "return_20d_pct",
        "risk_count",
        "trend_score",
        "fund_score",
        "repair_score",
        "confirm_active_buy_strength",
        "confirm_main_net_ratio",
    ]
    explain_factors = {key: item.get(key) for key in explain_keys if item.get(key) is not None}
    return {
        "trade_date": str(item.get("trade_date") or ""),
        "symbol": str(item.get("symbol") or "").lower(),
        "name": str(item.get("name") or item.get("symbol") or "").lower(),
        "source_id": source_id,
        "source_name": source_name,
        "source_type": "rule_strategy",
        "source_version": source_version,
        "artifact_version": source_version,
        "source_status": "active",
        "rank": int(item.get("rank") or rank),
        "score": float(item.get("selection_rank_score") or item.get("score") or 0.0),
        "score_scale": "raw",
        "horizon": "swing",
        "suggested_action": suggested_action,
        "action_label": action_label,
        "entry_allowed": entry_allowed,
        "buy_rule": str(item.get("exit_plan_summary") or ""),
        "reason_summary": str(item.get("reason_summary") or item.get("pullback_reason") or ""),
        "risk_tags": item.get("risk_labels") or [],
        "entry_block_reasons": item.get("entry_block_reasons") or [],
        "explain_factors": explain_factors,
        "raw_payload": item,
    }


def _generate_stable_candidates(trade_date: str, limit: int) -> List[Dict[str, Any]]:
    payload = get_stable_callback_candidates(trade_date, limit=limit)
    return [
        _strategy_candidate_to_standard(
            item,
            source_id=STABLE_SOURCE_ID,
            source_name=STABLE_SOURCE_NAME,
            source_version=STABLE_SOURCE_VERSION,
            rank=idx,
        )
        for idx, item in enumerate(payload.get("items") or [], start=1)
    ]


def _generate_trend_candidates(trade_date: str, limit: int) -> List[Dict[str, Any]]:
    payload = get_trend_continuation_candidates(trade_date, limit=limit)
    candidates = [
        _strategy_candidate_to_standard(
            item,
            source_id=TREND_SOURCE_ID,
            source_name=TREND_SOURCE_NAME,
            source_version=TREND_SOURCE_VERSION,
            rank=idx,
        )
        for idx, item in enumerate(payload.get("items") or [], start=1)
    ]
    buyable = [item for item in candidates if item.get("entry_allowed") is True]
    observe = [
        item for item in candidates
        if item.get("entry_allowed") is not True and float(item.get("score") or 0.0) >= TREND_OBSERVATION_MIN_SCORE
    ][:TREND_OBSERVATION_LIMIT]
    ranked = buyable + observe
    for idx, item in enumerate(ranked, start=1):
        item["rank"] = idx
    return ranked


def _generate_spark_candidates(trade_date: str, limit: int) -> List[Dict[str, Any]]:
    try:
        return spark_opportunity_selector.generate_daily_candidates(trade_date, limit=limit)
    except Exception:
        return spark_opportunity_selector.generate_candidates_from_latest_csv(trade_date=trade_date, limit=limit)


def source_daily_limit(source_id: str, fallback: int = 50) -> int:
    return int(SOURCE_DAILY_LIMITS.get(source_id, fallback))


def generate_source_candidates(source_id: str, trade_date: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    if source_id == SPARK_SOURCE_ID:
        return _generate_spark_candidates(trade_date, limit)
    if source_id == STABLE_SOURCE_ID:
        return _generate_stable_candidates(trade_date, limit)
    if source_id == TREND_SOURCE_ID:
        return _generate_trend_candidates(trade_date, limit)
    raise ValueError(f"unsupported selection source: {source_id}")


def run_daily_selection_sources(
    trade_date: str,
    *,
    limit: int = 50,
    source_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    target_sources = list(source_ids or ACTIVE_SOURCE_IDS)
    ensure_daily_source_registry()
    source_counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    for source_id in target_sources:
        try:
            records = generate_source_candidates(
                source_id,
                trade_date,
                limit=source_daily_limit(source_id, fallback=limit),
            )
            count = replace_source_candidates(trade_date, source_id, records)
            source_counts[source_id] = count
        except Exception as exc:
            errors[source_id] = str(exc)
            record_source_run_error(trade_date, source_id, str(exc))
    merged_count = rebuild_daily_candidates(trade_date)
    return {
        "trade_date": trade_date,
        "sources": source_counts,
        "errors": errors,
        "merged_count": merged_count,
    }


def get_daily_selection_candidates(
    trade_date: Optional[str],
    *,
    limit: int = 50,
    source_type: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_daily_source_registry()
    payload = query_daily_candidates(trade_date, limit=limit, source_type=source_type)
    target_date = str(payload.get("trade_date") or trade_date or "")
    if not target_date:
        payload["exit_watchlist"] = {
            "trade_date": "",
            "policy_id": "",
            "policy_name": "",
            "items": [],
        }
        return payload
    try:
        payload["exit_watchlist"] = get_daily_exit_watchlist(target_date)
    except Exception as exc:
        payload["exit_watchlist"] = {
            "trade_date": target_date,
            "policy_id": "pc_model_th6_stop12",
            "policy_name": "星火进攻版",
            "items": [],
            "error": str(exc),
        }
    return payload


def get_daily_selection_trade_dates(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    ensure_daily_source_registry()
    return query_daily_trade_dates(start_date, end_date)


def get_daily_selection_profile(symbol: str, trade_date: str) -> Dict[str, Any]:
    daily_candidate = query_daily_candidate_profile(symbol, trade_date)
    exit_watch_item: Optional[Dict[str, Any]] = None
    if daily_candidate is None:
        try:
            exit_watchlist_payload = get_daily_exit_watchlist(trade_date)
            exit_watch_item = next(
                (
                    item
                    for item in exit_watchlist_payload.get("items") or []
                    if str(item.get("symbol") or "").lower() == str(symbol or "").lower()
                ),
                None,
            )
        except Exception:
            exit_watch_item = None
    try:
        profile = get_profile(symbol, trade_date)
    except Exception:
        profile = {
            "symbol": str(symbol or "").lower(),
            "trade_date": trade_date,
            "requested_trade_date": trade_date,
            "name": str(symbol or "").lower(),
            "current_judgement": daily_candidate.get("current_judgement") if daily_candidate else "暂无画像",
            "series": [],
            "event_timeline": [],
            "trade_plan": {},
        }
    candidate_payload = daily_candidate or exit_watch_item
    if candidate_payload:
        trade_plan = dict(profile.get("trade_plan") or {})
        if not trade_plan and candidate_payload.get("entry_signal_date"):
            trade_plan = {"signal_date": candidate_payload.get("entry_signal_date")}
        trade_plan.update(candidate_payload.get("trade_plan") or {})
        profile.update(
            {
                "strategy_display_name": "每日综合候选池",
                "strategy_internal_id": DAILY_POOL_ID,
                "daily_candidate": candidate_payload,
                "daily_source_details": candidate_payload.get("source_details") or [],
                "source_count": candidate_payload.get("source_count"),
                "source_ids": candidate_payload.get("source_ids") or [],
                "entry_allowed": candidate_payload.get("entry_allowed"),
                "entry_block_reasons": candidate_payload.get("entry_block_reasons") or [],
                "current_judgement": candidate_payload.get("current_judgement") or profile.get("current_judgement"),
                "breakout_reason_summary": candidate_payload.get("reason_summary") or profile.get("breakout_reason_summary"),
                "distribution_reason_summary": "；".join(candidate_payload.get("risk_labels") or []) or profile.get("distribution_reason_summary"),
                "observe_date": candidate_payload.get("observe_date") or profile.get("observe_date"),
                "discovery_date": candidate_payload.get("discovery_date") or profile.get("discovery_date"),
                "launch_start_date": candidate_payload.get("launch_start_date") or profile.get("launch_start_date"),
                "launch_end_date": candidate_payload.get("launch_end_date") or profile.get("launch_end_date"),
                "pullback_confirm_date": candidate_payload.get("pullback_confirm_date") or profile.get("pullback_confirm_date"),
                "entry_signal_date": candidate_payload.get("entry_signal_date") or profile.get("entry_signal_date"),
                "entry_date": candidate_payload.get("entry_date") or profile.get("entry_date"),
                "exit_signal_date": candidate_payload.get("exit_signal_date") or profile.get("exit_signal_date"),
                "exit_date": candidate_payload.get("exit_date") or profile.get("exit_date"),
                "exit_plan_summary": candidate_payload.get("exit_plan_summary") or profile.get("exit_plan_summary"),
                "trade_plan": trade_plan or profile.get("trade_plan") or {},
            }
        )
    latest_available_trade_date = profile.get("latest_available_trade_date")
    if not latest_available_trade_date:
        latest_available_trade_date = profile.get("trade_date")
    profile["latest_available_trade_date"] = latest_available_trade_date
    return profile
