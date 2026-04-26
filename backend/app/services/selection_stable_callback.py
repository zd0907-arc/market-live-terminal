from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

STRATEGY_INTERNAL_ID = "stable_capital_callback"
STRATEGY_DISPLAY_NAME = "资金流回调稳健"
STRATEGY_VERSION = "S01-M05-conservative-combined-risk"
EXPERIMENT_DIR = Path(__file__).resolve().parents[3] / "docs" / "strategy-rework" / "strategies" / "S01-capital-trend-reversal" / "experiments" / "EXP-20260426-S01-M05-conservative-combined-risk"
TRADES_CSV = EXPERIMENT_DIR / "s01_m05_trades.csv"
FILTERED_CSV = EXPERIMENT_DIR / "s04_combined_risk_filtered_trades.csv"


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    return value


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def _date(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip()
    return text[:10] if text else None


def _split_labels(value: Any) -> List[str]:
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except Exception:
        pass
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.replace("；", ";").split(";") if item.strip()]


@lru_cache(maxsize=1)
def _load_trades() -> pd.DataFrame:
    if not TRADES_CSV.exists():
        raise FileNotFoundError(f"stable callback trades csv not found: {TRADES_CSV}")
    df = pd.read_csv(TRADES_CSV)
    for col in ["discovery_date", "launch_start_date", "launch_end_date", "pullback_confirm_date", "entry_signal_date", "entry_date", "exit_signal_date", "exit_date"]:
        if col in df.columns:
            df[col] = df[col].map(_date)
    if "is_mature_trade" in df.columns:
        df["is_mature_trade"] = df["is_mature_trade"].astype(bool)
    return df


@lru_cache(maxsize=1)
def _load_filtered() -> pd.DataFrame:
    if not FILTERED_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(FILTERED_CSV)
    for col in ["entry_signal_date", "entry_date", "pullback_confirm_date"]:
        if col in df.columns:
            df[col] = df[col].map(_date)
    return df


def _row_to_candidate(row: pd.Series, rank: int) -> Dict[str, Any]:
    risk_count = _int(row.get("risk_count_R1_R5"))
    risk_labels = _split_labels(row.get("risk_labels"))
    entry_allowed = risk_count < 2
    setup_reason = f"发现日前资金/价格结构分 { _float(row.get('setup_score')):.2f}，前 20 日价格未过热。"
    launch_reason = (
        f"启动窗口涨幅 { _float(row.get('launch3_return_pct')):.2f}% ，"
        f"超大单净流入占比 { _float(row.get('launch3_super_net_ratio')):.4f}。"
    )
    pullback_reason = (
        "启动后回调承接确认"
        if row.get("pullback_confirm_reason") == "pullback_absorption_confirm"
        else str(row.get("pullback_confirm_reason") or "回调承接确认")
    )
    exit_plan_summary = "买入后观察累计超大单；累计值从峰值明显回撤或触发出货信号后，次日开盘退出。"
    reason_summary = f"{pullback_reason}；风险标签 {risk_count} 个"
    return {
        "rank": rank,
        "symbol": str(row.get("symbol") or "").lower(),
        "name": str(row.get("symbol") or "").lower(),
        "trade_date": _date(row.get("entry_signal_date")) or _date(row.get("pullback_confirm_date")) or "",
        "score": round(_float(row.get("setup_score")), 2),
        "signal": 1 if entry_allowed else 0,
        "signal_label": "stable_callback_buyable" if entry_allowed else "stable_callback_risk_filtered",
        "current_judgement": "可买入" if entry_allowed else "风险过滤",
        "reason_summary": reason_summary,
        "risk_level": "low" if risk_count == 0 else "medium" if risk_count == 1 else "high",
        "stealth_score": round(_float(row.get("setup_score")), 2),
        "breakout_score": round(_float(row.get("launch3_return_pct")), 2),
        "distribution_score": round(_float(row.get("confirm_distribution_score")), 2),
        "close": _clean_value(row.get("gross_entry_price")),
        "return_5d_pct": _clean_value(row.get("pre5_return_pct")),
        "return_20d_pct": _clean_value(row.get("pre20_return_pct")),
        "feature_version": STRATEGY_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "candidate_types": ["stable_callback"],
        "entry_allowed": entry_allowed,
        "entry_block_reasons": [] if entry_allowed else ["组合风险标签达到过滤阈值"],
        "selection_rank_score": round(_float(row.get("setup_score")), 2),
        "selection_rank_mode": "stable_callback_setup_rank",
        "lifecycle_phase": "pullback_confirmed",
        "lifecycle_phase_label": "回调确认",
        "action_label": "可买入" if entry_allowed else "风险过滤",
        "entry_signal_date": _date(row.get("entry_signal_date")),
        "entry_date": _date(row.get("entry_date")),
        "discovery_date": _date(row.get("discovery_date")),
        "launch_start_date": _date(row.get("launch_start_date")),
        "launch_end_date": _date(row.get("launch_end_date")),
        "pullback_confirm_date": _date(row.get("pullback_confirm_date")),
        "exit_signal_date": _date(row.get("exit_signal_date")),
        "exit_date": _date(row.get("exit_date")),
        "risk_count": risk_count,
        "risk_labels": risk_labels,
        "setup_reason": setup_reason,
        "launch_reason": launch_reason,
        "pullback_reason": pullback_reason,
        "exit_plan_summary": exit_plan_summary,
        "replay_return_pct": _clean_value(row.get("net_return_pct")),
        "replay_entry_date": _date(row.get("entry_date")),
        "replay_exit_signal_date": _date(row.get("exit_signal_date")),
        "replay_exit_reason": _clean_value(row.get("exit_reason")),
    }


def _select_date(trade_date: Optional[str]) -> str:
    df = _load_trades()
    dates = sorted({d for d in df["entry_signal_date"].dropna().astype(str).tolist() if d})
    if not dates:
        return str(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    if trade_date in dates:
        return str(trade_date)
    if trade_date:
        return str(trade_date)
    return dates[-1]


def get_stable_callback_trade_dates(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    df = _load_trades()
    min_date = start_date or str(df["entry_signal_date"].dropna().min())
    max_date = end_date or str(df["entry_signal_date"].dropna().max())
    counts = df.groupby("entry_signal_date").size().to_dict()
    items: List[Dict[str, Any]] = []
    for date in pd.date_range(min_date, max_date).strftime("%Y-%m-%d"):
        is_trade_day = pd.Timestamp(date).weekday() < 5
        signal_count = int(counts.get(date, 0))
        selectable = is_trade_day and signal_count > 0
        items.append(
            {
                "date": date,
                "is_trade_day": is_trade_day,
                "signal_count": signal_count,
                "selectable": selectable,
                "disabled_reason": None if selectable else ("当天无稳健策略候选" if is_trade_day else "休市/无原始数据"),
            }
        )
    return {"start_date": min_date, "end_date": max_date, "strategy": STRATEGY_INTERNAL_ID, "items": items}


def get_stable_callback_candidates(trade_date: Optional[str], limit: int = 10) -> Dict[str, Any]:
    df = _load_trades()
    target = _select_date(trade_date)
    day = df[df["entry_signal_date"] == target].copy()
    if day.empty:
        return {
            "trade_date": target,
            "strategy": STRATEGY_INTERNAL_ID,
            "strategy_display_name": STRATEGY_DISPLAY_NAME,
            "strategy_internal_id": STRATEGY_INTERNAL_ID,
            "rank_mode": "stable_callback_setup_rank",
            "items": [],
        }
    day = (
        day.sort_values(["symbol", "rank", "setup_score"], ascending=[True, True, False])
        .drop_duplicates(subset=["symbol"], keep="first")
        .sort_values(["rank", "setup_score", "symbol"], ascending=[True, False, True])
        .head(max(1, int(limit)))
    )
    items = [_row_to_candidate(row, idx) for idx, (_, row) in enumerate(day.iterrows(), start=1)]
    return {
        "trade_date": target,
        "strategy": STRATEGY_INTERNAL_ID,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "strategy_version": STRATEGY_VERSION,
        "rank_mode": "stable_callback_setup_rank",
        "items": items,
    }


def _find_trade(symbol: str, trade_date: Optional[str]) -> Optional[pd.Series]:
    df = _load_trades()
    normalized = str(symbol).lower()
    subset = df[df["symbol"].astype(str).str.lower() == normalized].copy()
    if trade_date:
        exact = subset[subset["entry_signal_date"] == trade_date]
        if not exact.empty:
            return exact.iloc[0]
        earlier = subset[subset["entry_signal_date"] <= trade_date].sort_values("entry_signal_date")
        if not earlier.empty:
            return earlier.iloc[-1]
    if subset.empty:
        return None
    return subset.sort_values("entry_signal_date").iloc[-1]


def get_stable_callback_profile(symbol: str, trade_date: Optional[str]) -> Dict[str, Any]:
    row = _find_trade(symbol, trade_date)
    if row is None:
        target = trade_date or pd.Timestamp.today().strftime("%Y-%m-%d")
        return {
            "symbol": symbol.lower(),
            "trade_date": target,
            "requested_trade_date": target,
            "profile_date_fallback_used": False,
            "name": symbol.lower(),
            "feature_version": STRATEGY_VERSION,
            "strategy_version": STRATEGY_VERSION,
            "strategy_display_name": STRATEGY_DISPLAY_NAME,
            "strategy_internal_id": STRATEGY_INTERNAL_ID,
            "close": 0,
            "current_judgement": "暂无稳健策略画像",
            "breakout_reason_summary": "当前日期没有资金流回调稳健候选。",
            "distribution_reason_summary": "无风险标签。",
            "trade_plan": {},
            "series": [],
            "event_timeline": [],
            "entry_allowed": False,
            "entry_block_reasons": ["无候选信号"],
            "intent_profile": {},
            "candidate_types": [],
            "research": {},
        }
    candidate = _row_to_candidate(row, _int(row.get("rank"), 0))
    risk_labels = candidate["risk_labels"]
    target = candidate["trade_date"]
    return {
        "symbol": candidate["symbol"],
        "trade_date": target,
        "latest_available_trade_date": _date(row.get("exit_date")) or target,
        "requested_trade_date": trade_date or target,
        "profile_date_fallback_used": bool(trade_date and trade_date != target),
        "name": candidate["symbol"],
        "feature_version": STRATEGY_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "stealth_score": _float(row.get("setup_score")),
        "breakout_score": _float(row.get("launch3_return_pct")),
        "distribution_score": _float(row.get("confirm_distribution_score")),
        "confirm_signal": 1,
        "exit_signal": 1 if row.get("exit_reason") else 0,
        "close": _float(row.get("gross_entry_price")),
        "return_20d_pct": _clean_value(row.get("pre20_return_pct")),
        "breakout_vs_prev20_high_pct": _clean_value(row.get("launch3_return_pct")),
        "l2_vs_l1_strength": _clean_value(row.get("launch3_main_net_ratio")),
        "l2_order_event_available": 1 if bool(row.get("order_filter_available")) else 0,
        "current_judgement": candidate["current_judgement"],
        "breakout_reason_summary": "；".join([candidate["setup_reason"], candidate["launch_reason"], candidate["pullback_reason"]]),
        "distribution_reason_summary": "；".join(risk_labels) if risk_labels else "组合风险标签未达到过滤阈值。",
        "trade_plan": {
            "signal_date": candidate["entry_signal_date"],
            "entry_date": candidate["entry_date"],
            "entry_price": _clean_value(row.get("entry_price")),
            "exit_signal_date": _date(row.get("exit_signal_date")),
            "exit_date": _date(row.get("exit_date")),
            "exit_price": _clean_value(row.get("exit_price")),
            "exit_reason": _clean_value(row.get("exit_reason")),
            "exit_is_simulated": True,
            "return_pct": _clean_value(row.get("net_return_pct")),
        },
        "series": [],
        "event_timeline": [],
        "entry_allowed": candidate["entry_allowed"],
        "entry_block_reasons": candidate["entry_block_reasons"],
        "intent_profile": {
            "intent_label": "pullback_absorption_confirm",
            "setup_score": _clean_value(row.get("setup_score")),
            "launch3_return_pct": _clean_value(row.get("launch3_return_pct")),
            "pullback_support_spread_avg": _clean_value(row.get("pullback_support_spread_avg")),
            "risk_count": candidate["risk_count"],
            "risk_labels": risk_labels,
        },
        "candidate_types": candidate["candidate_types"],
        "entry_signal_date": candidate["entry_signal_date"],
        "entry_date": candidate["entry_date"],
        "discovery_date": candidate["discovery_date"],
        "launch_start_date": candidate["launch_start_date"],
        "launch_end_date": candidate["launch_end_date"],
        "pullback_confirm_date": candidate["pullback_confirm_date"],
        "exit_signal_date": candidate["exit_signal_date"],
        "exit_date": candidate["exit_date"],
        "risk_count": candidate["risk_count"],
        "risk_labels": risk_labels,
        "setup_reason": candidate["setup_reason"],
        "launch_reason": candidate["launch_reason"],
        "pullback_reason": candidate["pullback_reason"],
        "exit_plan_summary": candidate["exit_plan_summary"],
        "research": {
            "strategy_explanation": [
                "这不是追涨停策略，而是先发现资金异动。",
                "启动后等待回调承接确认，确认日收盘识别，次日开盘买入。",
                "买入后主要看累计超大单是否从峰值明显撤退。",
                "多个风险信号同时出现时过滤。",
            ],
            "final_cum_super_amount": _clean_value(row.get("final_cum_super_amount")),
            "final_super_peak_drawdown_pct": _clean_value(row.get("final_super_peak_drawdown_pct")),
        },
    }


def _summarize(rows: pd.DataFrame) -> Dict[str, Any]:
    if rows.empty:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "max_loss_pct": 0.0,
            "avg_holding_days": 0.0,
        }
    returns = pd.to_numeric(rows["net_return_pct"], errors="coerce").fillna(0.0)
    holding = pd.to_numeric(rows["holding_days"], errors="coerce").fillna(0.0)
    return {
        "trade_count": int(len(rows)),
        "win_rate": round(float((returns > 0).mean() * 100.0), 2),
        "avg_return_pct": round(float(returns.mean()), 2),
        "median_return_pct": round(float(returns.median()), 2),
        "max_return_pct": round(float(returns.max()), 2),
        "max_loss_pct": round(float(returns.min()), 2),
        "avg_holding_days": round(float(holding.mean()), 2),
        "big_loss_count": int((returns <= -8.0).sum()),
    }


def evaluate_stable_callback_range(start_date: str, end_date: str, top_n: int = 10) -> Dict[str, Any]:
    df = _load_trades().copy()
    mask = (df["entry_signal_date"] >= start_date) & (df["entry_signal_date"] <= end_date)
    df = df[mask]
    if "is_mature_trade" in df.columns:
        df = df[df["is_mature_trade"] == True]
    df = df.sort_values(["entry_signal_date", "rank", "symbol"], ascending=[True, True, True])
    trades: List[Dict[str, Any]] = []
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        trades.append(
            {
                "id": idx,
                "symbol": str(row.get("symbol") or "").lower(),
                "rank": _int(row.get("rank")),
                "signal_date": _date(row.get("entry_signal_date")),
                "entry_signal_date": _date(row.get("entry_signal_date")),
                "entry_date": _date(row.get("entry_date")),
                "exit_signal_date": _date(row.get("exit_signal_date")),
                "exit_date": _date(row.get("exit_date")),
                "entry_price": _clean_value(row.get("entry_price")),
                "exit_price": _clean_value(row.get("exit_price")),
                "return_pct": _clean_value(row.get("return_pct")),
                "net_return_pct": _clean_value(row.get("net_return_pct")),
                "max_drawdown_pct": _clean_value(row.get("max_drawdown_pct")),
                "holding_days": _int(row.get("holding_days")),
                "exit_reason": _clean_value(row.get("exit_reason")),
                "selection_rank_score": _clean_value(row.get("setup_score")),
                "risk_count": _int(row.get("risk_count_R1_R5")),
                "risk_labels": _split_labels(row.get("risk_labels")),
                "lifecycle_phase_label": "回调确认",
                "action_label": "可买入",
            }
        )
    return {
        "start_date": start_date,
        "end_date": end_date,
        "strategy_version": STRATEGY_VERSION,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "rank_mode": "stable_callback_setup_rank",
        "top_n": int(top_n),
        "summary": _summarize(df),
        "daily_results": [],
        "trades": trades,
    }
