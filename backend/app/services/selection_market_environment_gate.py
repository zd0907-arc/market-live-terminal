from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_DIR = ROOT / "docs" / "selection" / "market_environment_gate_2026-06-10"
POLICY_ID = "market_gate_v0_20260610"
POLICY_VERSION = "research_v0"


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _read_csv(name: str) -> List[Dict[str, Any]]:
    path = RESEARCH_DIR / name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in row.items():
        text = str(value or "").strip()
        if text == "":
            out[key] = None
            continue
        number = _safe_float(text, default=None)
        if number is not None and key not in {"trade_date", "market_regime", "market_detail", "market_detail_label", "default_action", "reason_top3", "policy", "source_id", "business_source_name", "metric", "metric_label", "confidence"}:
            out[key] = number
        else:
            out[key] = text
    return out


@lru_cache(maxsize=1)
def market_state_by_date() -> Dict[str, Dict[str, Any]]:
    rows = [_clean_row(row) for row in _read_csv("market_state_daily.csv")]
    return {str(row.get("trade_date")): row for row in rows if row.get("trade_date")}


@lru_cache(maxsize=1)
def gate_policy_summary() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "5d": [_clean_row(row) for row in _read_csv("gate_policy_comparison_5d.csv")],
        "10d": [_clean_row(row) for row in _read_csv("gate_policy_comparison_10d.csv")],
        "22d": [_clean_row(row) for row in _read_csv("gate_policy_comparison.csv")],
    }


@lru_cache(maxsize=1)
def source_regime_summary() -> List[Dict[str, Any]]:
    return [_clean_row(row) for row in _read_csv("gate_summary_by_source_regime.csv")]


@lru_cache(maxsize=1)
def source_metric_scorecard() -> List[Dict[str, Any]]:
    return [_clean_row(row) for row in _read_csv("market_metric_source_day_scorecard.csv")]


@lru_cache(maxsize=1)
def metric_leaderboard() -> List[Dict[str, Any]]:
    return [_clean_row(row) for row in _read_csv("market_metric_source_day_leaderboard.csv")]


def _latest_trade_date() -> Optional[str]:
    dates = sorted(market_state_by_date())
    return dates[-1] if dates else None


def _compact_market_point(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "trade_date": row.get("trade_date"),
        "water_score": row.get("water_score"),
        "market_regime": row.get("market_regime"),
        "market_detail": row.get("market_detail"),
        "market_detail_label": row.get("market_detail_label"),
        "default_action": row.get("default_action"),
        "action_code": _market_action_code(row),
        "all_up_ratio_5d": row.get("all_up_ratio_5d"),
        "small_up_ratio_5d": row.get("small_up_ratio_5d"),
        "all_med_ret_5d": row.get("all_med_ret_5d"),
        "csi1000_return_5d_pct": row.get("csi1000_return_5d_pct"),
    }


def _recent_market_points(target: str, limit: int = 90) -> List[Dict[str, Any]]:
    rows = market_state_by_date()
    dates = [date for date in sorted(rows) if not target or date <= target]
    return [_compact_market_point(rows[date]) for date in dates[-limit:]]


def _split_reasons(value: Any) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("；", ";").split(";") if part.strip()]


def _market_action_code(env: Dict[str, Any]) -> str:
    action = str(env.get("default_action") or "")
    regime = str(env.get("market_regime") or "")
    detail = str(env.get("market_detail") or "")
    if "暂停" in action or regime == "defense" or detail.startswith("defense_"):
        return "blocked"
    if "观察" in action or regime == "caution":
        return "watch_only"
    return "allowed"


def get_market_environment(trade_date: Optional[str]) -> Dict[str, Any]:
    target = str(trade_date or _latest_trade_date() or "")
    row = market_state_by_date().get(target)
    if not row:
        return {
            "trade_date": target,
            "available": False,
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "message": "暂无市场环境水位数据",
        }
    metrics = {
        key: row.get(key)
        for key in (
            "all_up_ratio_3d",
            "all_up_ratio_5d",
            "all_up_ratio_10d",
            "all_med_ret_5d",
            "small_up_ratio_3d",
            "small_up_ratio_5d",
            "small_med_ret_3d",
            "small_med_ret_5d",
            "large_up_ratio_5d",
            "large_med_ret_5d",
            "csi1000_return_5d_pct",
            "csi1000_return_20d_pct",
        )
        if key in row
    }
    return {
        "trade_date": target,
        "available": True,
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "water_score": row.get("water_score"),
        "market_regime": row.get("market_regime"),
        "market_detail": row.get("market_detail"),
        "market_detail_label": row.get("market_detail_label"),
        "default_action": row.get("default_action"),
        "action_code": _market_action_code(row),
        "reason_top3": _split_reasons(row.get("reason_top3")),
        "metrics": metrics,
        "recent": _recent_market_points(target),
    }


def _source_gate_note(source_id: str, action_code: str) -> Optional[str]:
    if action_code == "allowed":
        return None
    if source_id == "spark_opportunity_selector":
        return "星火高分例外尚未被数据证明"
    if source_id == "stable_capital_callback":
        return "资金流回调稳健策略仅方向支持，弱市先观察"
    if source_id == "trend_continuation_callback":
        return "趋势延续策略近期样本不足，先不做弱市例外"
    if source_id in {"probe_day0_watch", "probe_d3_confirmed"}:
        return "试盘识别样本不足，弱市不作为直接买入依据"
    return None


def build_candidate_market_gate(candidate: Dict[str, Any], env: Dict[str, Any]) -> Dict[str, Any]:
    source_allowed = candidate.get("entry_allowed") is not False
    source_label = str(candidate.get("action_label") or ("明日可买" if source_allowed else "观察"))
    if not env.get("available"):
        return {
            "gate_applied": False,
            "market_gate_status": "unknown",
            "market_gate_label": "暂无市场水位",
            "market_gate_reasons": ["暂无市场环境水位数据"],
            "source_action_label": source_label,
            "source_entry_allowed": source_allowed,
            "final_entry_allowed": source_allowed,
            "final_action_label": source_label,
            "entry_decision_source": "rule",
            "gate_policy_id": POLICY_ID,
            "gate_policy_version": POLICY_VERSION,
        }
    action_code = str(env.get("action_code") or "allowed")
    source_id = str(candidate.get("primary_source_id") or candidate.get("strategy_internal_id") or "")
    reasons = [str(env.get("market_detail_label") or env.get("default_action") or "市场环境")]
    reasons += [str(item) for item in (env.get("reason_top3") or [])[:3]]
    source_note = _source_gate_note(source_id, action_code)
    if source_note:
        reasons.append(source_note)
    if not source_allowed:
        final_allowed = False
        final_label = source_label or "观察"
        decision_source = "rule"
        gate_status = "not_applicable" if action_code == "allowed" else action_code
        gate_label = "环境不覆盖原规则拦截" if action_code == "allowed" else str(env.get("default_action") or "环境观察")
    elif action_code == "blocked":
        final_allowed = False
        final_label = "仅观察"
        decision_source = "market_gate"
        gate_status = "blocked"
        gate_label = "暂停新开仓"
    elif action_code == "watch_only":
        final_allowed = False
        final_label = "观察为主"
        decision_source = "market_gate"
        gate_status = "watch_only"
        gate_label = "观察为主"
    else:
        final_allowed = True
        final_label = source_label
        decision_source = "rule"
        gate_status = "allowed"
        gate_label = "环境允许"
    return {
        "gate_applied": True,
        "market_gate_status": gate_status,
        "market_gate_label": gate_label,
        "market_gate_reasons": list(dict.fromkeys([item for item in reasons if item])),
        "market_regime": env.get("market_regime"),
        "market_detail": env.get("market_detail"),
        "market_detail_label": env.get("market_detail_label"),
        "market_default_action": env.get("default_action"),
        "source_action_label": source_label,
        "source_entry_allowed": source_allowed,
        "final_entry_allowed": final_allowed,
        "final_action_label": final_label,
        "entry_decision_source": decision_source,
        "gate_exception_status": "not_proven" if action_code != "allowed" and source_allowed else "not_applicable",
        "gate_policy_id": POLICY_ID,
        "gate_policy_version": POLICY_VERSION,
        "market_environment_snapshot": {key: value for key, value in env.items() if key != "recent"},
    }


def apply_market_gate_to_candidates(items: Sequence[Dict[str, Any]], env: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items:
        candidate = dict(item)
        candidate.update(build_candidate_market_gate(candidate, env))
        out.append(candidate)
    return out


def get_market_environment_backtest_summary() -> Dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "gate_policy_comparison": gate_policy_summary(),
        "metric_leaderboard": metric_leaderboard(),
    }


def get_market_environment_source_summary() -> Dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "source_regime_summary": source_regime_summary(),
        "source_metric_scorecard": source_metric_scorecard(),
    }
