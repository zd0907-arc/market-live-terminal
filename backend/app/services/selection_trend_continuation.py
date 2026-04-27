from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

STRATEGY_INTERNAL_ID = "trend_continuation_callback"
STRATEGY_DISPLAY_NAME = "趋势中继高质量回踩"
STRATEGY_VERSION = "S02-current-candidate-20260427"
EXPERIMENT_DIR = Path(__file__).resolve().parents[3] / "docs" / "strategy-rework" / "strategies" / "S02-capital-breakout-continuation" / "experiments" / "EXP-20260427-trend-continuation-current-candidate"
OBSERVATION_CSV = EXPERIMENT_DIR / "observation_pool.csv"
BUY_SIGNALS_CSV = EXPERIMENT_DIR / "current_buy_signals.csv"
TRADES_CSV = EXPERIMENT_DIR / "mature_trades.csv"


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


@lru_cache(maxsize=1)
def _load_observation() -> pd.DataFrame:
    if not OBSERVATION_CSV.exists():
        raise FileNotFoundError(f"trend observation csv not found: {OBSERVATION_CSV}")
    df = pd.read_csv(OBSERVATION_CSV)
    if "signal_date" in df.columns:
        df["signal_date"] = df["signal_date"].map(_date)
    return df


@lru_cache(maxsize=1)
def _load_buy_signals() -> pd.DataFrame:
    if not BUY_SIGNALS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(BUY_SIGNALS_CSV)
    for col in ["signal_date", "observe_date", "entry_signal_date", "confirm_date"]:
        if col in df.columns:
            df[col] = df[col].map(_date)
    return df


@lru_cache(maxsize=1)
def _load_trades() -> pd.DataFrame:
    if not TRADES_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(TRADES_CSV)
    for col in ["signal_date", "observe_date", "entry_signal_date", "confirm_date", "entry_date", "exit_signal_date", "exit_date"]:
        if col in df.columns:
            df[col] = df[col].map(_date)
    if "is_mature_trade" in df.columns:
        df["is_mature_trade"] = df["is_mature_trade"].astype(bool)
    return df


def _row_to_candidate(row: pd.Series, rank: int, status: str) -> Dict[str, Any]:
    is_buy = status == "buy_signal"
    symbol = str(row.get("symbol") or "").lower()
    trade_date = _date(row.get("entry_signal_date")) if is_buy else _date(row.get("signal_date"))
    action_label = "可买入" if is_buy else "观察中"
    reason = (
        "严格高质量回踩确认；确认日主动买入和主力净流入为正"
        if is_buy
        else "进入趋势中继观察池；等待严格回踩和真承接确认"
    )
    return {
        "rank": rank,
        "symbol": symbol,
        "name": symbol,
        "trade_date": trade_date or "",
        "score": round(_float(row.get("score")), 2),
        "signal": 1 if is_buy else 0,
        "signal_label": "trend_continuation_buyable" if is_buy else "trend_continuation_observe",
        "current_judgement": action_label,
        "reason_summary": reason,
        "risk_level": "low" if is_buy else "watch",
        "stealth_score": round(_float(row.get("fund_score")), 2),
        "breakout_score": round(_float(row.get("trend_score")), 2),
        "distribution_score": round(_float(row.get("repair_score")), 2),
        "close": None,
        "return_5d_pct": _clean_value(row.get("pre5_return_pct")),
        "return_10d_pct": _clean_value(row.get("pre10_return_pct")),
        "return_20d_pct": _clean_value(row.get("pre20_return_pct")),
        "feature_version": STRATEGY_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "candidate_types": ["trend_continuation_buy"] if is_buy else ["trend_continuation_observe"],
        "entry_allowed": is_buy,
        "entry_block_reasons": [] if is_buy else ["观察池候选，尚未触发严格回踩买点"],
        "selection_rank_score": round(_float(row.get("score")), 2),
        "selection_rank_mode": "trend_continuation_quality_callback_rank",
        "lifecycle_phase": "trend_callback_confirmed" if is_buy else "trend_observation_pool",
        "lifecycle_phase_label": "回踩确认" if is_buy else "观察池",
        "action_label": action_label,
        "observe_date": _date(row.get("observe_date")) or _date(row.get("signal_date")),
        "entry_signal_date": _date(row.get("entry_signal_date")) if is_buy else None,
        "entry_date": _date(row.get("entry_date")) if "entry_date" in row else None,
        "exit_signal_date": _date(row.get("exit_signal_date")) if "exit_signal_date" in row else None,
        "exit_date": _date(row.get("exit_date")) if "exit_date" in row else None,
        "risk_count": 0,
        "risk_labels": [],
        "setup_reason": f"前20日涨幅 {_float(row.get('pre20_return_pct')):.2f}%，趋势中继观察分 {_float(row.get('score')):.2f}。",
        "launch_reason": f"趋势分 {_float(row.get('trend_score')):.2f}，资金留场分 {_float(row.get('fund_score')):.2f}。",
        "pullback_reason": reason,
        "exit_plan_summary": "买入后盯累计超大单；若单日大额超大单派发或累计峰值明显回撤，次日开盘退出。",
        "replay_return_pct": _clean_value(row.get("net_return_pct")),
        "replay_entry_date": _date(row.get("entry_date")) if "entry_date" in row else None,
        "replay_exit_signal_date": _date(row.get("exit_signal_date")) if "exit_signal_date" in row else None,
        "replay_exit_reason": _clean_value(row.get("exit_reason")),
        "trend_score": _clean_value(row.get("trend_score")),
        "fund_score": _clean_value(row.get("fund_score")),
        "repair_score": _clean_value(row.get("repair_score")),
        "confirm_active_buy_strength": _clean_value(row.get("confirm_active_buy_strength")),
        "confirm_main_net_ratio": _clean_value(row.get("confirm_main_net_ratio")),
    }


def _select_date(trade_date: Optional[str]) -> str:
    obs = _load_observation()
    buys = _load_buy_signals()
    dates = set(obs.get("signal_date", pd.Series(dtype=str)).dropna().astype(str).tolist())
    if not buys.empty:
        dates |= set(buys.get("entry_signal_date", pd.Series(dtype=str)).dropna().astype(str).tolist())
    sorted_dates = sorted(dates)
    if not sorted_dates:
        return str(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    if trade_date in dates:
        return str(trade_date)
    if trade_date:
        return str(trade_date)
    return sorted_dates[-1]


def get_trend_continuation_trade_dates(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    obs = _load_observation()
    buys = _load_buy_signals()
    dates = set(obs.get("signal_date", pd.Series(dtype=str)).dropna().astype(str).tolist())
    if not buys.empty:
        dates |= set(buys.get("entry_signal_date", pd.Series(dtype=str)).dropna().astype(str).tolist())
    min_date = start_date or (min(dates) if dates else None) or "2026-03-01"
    max_date = end_date or (max(dates) if dates else None) or "2026-04-24"
    obs_counts = obs.groupby("signal_date").size().to_dict() if not obs.empty else {}
    buy_counts = buys.groupby("entry_signal_date").size().to_dict() if not buys.empty else {}
    items: List[Dict[str, Any]] = []
    for date in pd.date_range(min_date, max_date).strftime("%Y-%m-%d"):
        is_trade_day = pd.Timestamp(date).weekday() < 5
        signal_count = int(obs_counts.get(date, 0)) + int(buy_counts.get(date, 0))
        selectable = is_trade_day and signal_count > 0
        items.append({
            "date": date,
            "is_trade_day": is_trade_day,
            "signal_count": signal_count,
            "selectable": selectable,
            "disabled_reason": None if selectable else ("当天无趋势中继候选" if is_trade_day else "休市/无原始数据"),
        })
    return {"start_date": min_date, "end_date": max_date, "strategy": STRATEGY_INTERNAL_ID, "items": items}


def get_trend_continuation_candidates(trade_date: Optional[str], limit: int = 20) -> Dict[str, Any]:
    target = _select_date(trade_date)
    obs = _load_observation()
    buys = _load_buy_signals()
    trade_rows = _load_trades()
    buy_day = buys[buys["entry_signal_date"] == target].copy() if not buys.empty else pd.DataFrame()
    if not trade_rows.empty and not buy_day.empty:
        buy_day = buy_day.merge(
            trade_rows[["symbol", "entry_signal_date", "entry_date", "exit_signal_date", "exit_date", "net_return_pct", "exit_reason"]],
            on=["symbol", "entry_signal_date"], how="left", suffixes=("", "_trade")
        )
    obs_day = obs[obs["signal_date"] == target].copy() if not obs.empty else pd.DataFrame()
    buy_symbols = set(buy_day["symbol"].astype(str).str.lower().tolist()) if not buy_day.empty else set()
    if not obs_day.empty:
        obs_day = obs_day[~obs_day["symbol"].astype(str).str.lower().isin(buy_symbols)]
    items: List[Dict[str, Any]] = []
    if not buy_day.empty:
        buy_day = buy_day.sort_values(["rank", "score", "symbol"], ascending=[True, False, True])
        for _, row in buy_day.iterrows():
            items.append(_row_to_candidate(row, len(items) + 1, "buy_signal"))
    if not obs_day.empty and len(items) < limit:
        obs_day = obs_day.sort_values(["rank", "score", "symbol"], ascending=[True, False, True]).head(max(0, int(limit) - len(items)))
        for _, row in obs_day.iterrows():
            items.append(_row_to_candidate(row, len(items) + 1, "observe"))
    return {
        "trade_date": target,
        "strategy": STRATEGY_INTERNAL_ID,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "strategy_version": STRATEGY_VERSION,
        "rank_mode": "trend_continuation_quality_callback_rank",
        "items": items,
    }


def _find_row(symbol: str, trade_date: Optional[str]) -> tuple[Optional[pd.Series], str]:
    normalized = str(symbol).lower()
    trades = _load_trades()
    buys = _load_buy_signals()
    obs = _load_observation()
    if not trades.empty:
        subset = trades[trades["symbol"].astype(str).str.lower() == normalized].copy()
        if trade_date:
            exact = subset[(subset["entry_signal_date"] == trade_date) | (subset["observe_date"] == trade_date)]
            if not exact.empty:
                return exact.iloc[0], "buy_signal"
            earlier = subset[subset["entry_signal_date"] <= trade_date].sort_values("entry_signal_date")
            if not earlier.empty:
                return earlier.iloc[-1], "buy_signal"
        if not subset.empty:
            return subset.sort_values("entry_signal_date").iloc[-1], "buy_signal"
    if not buys.empty:
        subset = buys[buys["symbol"].astype(str).str.lower() == normalized].copy()
        if trade_date:
            exact = subset[(subset["entry_signal_date"] == trade_date) | (subset["observe_date"] == trade_date)]
            if not exact.empty:
                return exact.iloc[0], "buy_signal"
            earlier = subset[subset["entry_signal_date"] <= trade_date].sort_values("entry_signal_date")
            if not earlier.empty:
                return earlier.iloc[-1], "buy_signal"
        if not subset.empty:
            return subset.sort_values("entry_signal_date").iloc[-1], "buy_signal"
    subset = obs[obs["symbol"].astype(str).str.lower() == normalized].copy()
    if trade_date:
        exact = subset[subset["signal_date"] == trade_date]
        if not exact.empty:
            return exact.iloc[0], "observe"
        earlier = subset[subset["signal_date"] <= trade_date].sort_values("signal_date")
        if not earlier.empty:
            return earlier.iloc[-1], "observe"
    if not subset.empty:
        return subset.sort_values("signal_date").iloc[-1], "observe"
    return None, "observe"


def get_trend_continuation_profile(symbol: str, trade_date: Optional[str]) -> Dict[str, Any]:
    row, status = _find_row(symbol, trade_date)
    if row is None:
        target = trade_date or pd.Timestamp.today().strftime("%Y-%m-%d")
        return {"symbol": symbol.lower(), "trade_date": target, "name": symbol.lower(), "strategy_display_name": STRATEGY_DISPLAY_NAME, "strategy_internal_id": STRATEGY_INTERNAL_ID, "current_judgement": "暂无趋势中继画像", "entry_allowed": False, "entry_block_reasons": ["无候选信号"], "research": {}}
    candidate = _row_to_candidate(row, _int(row.get("rank")), status)
    return {
        "symbol": candidate["symbol"],
        "trade_date": candidate["trade_date"],
        "latest_available_trade_date": candidate.get("exit_date") or candidate["trade_date"],
        "requested_trade_date": trade_date or candidate["trade_date"],
        "profile_date_fallback_used": bool(trade_date and trade_date != candidate["trade_date"]),
        "name": candidate["symbol"],
        "feature_version": STRATEGY_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "stealth_score": candidate["stealth_score"],
        "breakout_score": candidate["breakout_score"],
        "distribution_score": candidate["distribution_score"],
        "confirm_signal": 1 if status == "buy_signal" else 0,
        "exit_signal": 1 if row.get("exit_reason") else 0,
        "close": _clean_value(row.get("gross_entry_price")),
        "return_20d_pct": candidate["return_20d_pct"],
        "current_judgement": candidate["current_judgement"],
        "breakout_reason_summary": "；".join([candidate["setup_reason"], candidate["launch_reason"], candidate["pullback_reason"]]),
        "distribution_reason_summary": "趋势中继风险控制：买入后若单日大额超大单派发或累计超大单峰值回撤，则退出。",
        "trade_plan": {
            "signal_date": candidate.get("entry_signal_date"),
            "entry_date": candidate.get("entry_date"),
            "exit_signal_date": candidate.get("exit_signal_date"),
            "exit_date": candidate.get("exit_date"),
            "exit_reason": candidate.get("replay_exit_reason"),
            "return_pct": candidate.get("replay_return_pct"),
            "exit_is_simulated": True,
        },
        "series": [],
        "event_timeline": [],
        "entry_allowed": candidate["entry_allowed"],
        "entry_block_reasons": candidate["entry_block_reasons"],
        "intent_profile": {
            "intent_label": candidate["lifecycle_phase"],
            "trend_score": candidate.get("trend_score"),
            "fund_score": candidate.get("fund_score"),
            "repair_score": candidate.get("repair_score"),
            "confirm_active_buy_strength": candidate.get("confirm_active_buy_strength"),
            "confirm_main_net_ratio": candidate.get("confirm_main_net_ratio"),
        },
        "candidate_types": candidate["candidate_types"],
        "entry_signal_date": candidate.get("entry_signal_date"),
        "entry_date": candidate.get("entry_date"),
        "observe_date": candidate.get("observe_date"),
        "launch_start_date": candidate.get("observe_date"),
        "launch_end_date": candidate.get("entry_signal_date") or candidate.get("observe_date"),
        "exit_signal_date": candidate.get("exit_signal_date"),
        "exit_date": candidate.get("exit_date"),
        "risk_count": 0,
        "risk_labels": [],
        "setup_reason": candidate["setup_reason"],
        "launch_reason": candidate["launch_reason"],
        "pullback_reason": candidate["pullback_reason"],
        "exit_plan_summary": candidate["exit_plan_summary"],
        "research": {
            "strategy_explanation": [
                "先进入趋势中继观察池，不直接买。",
                "只有出现严格高质量回踩，且确认日主动买入和主力资金为正，才给可买入信号。",
                "买入后重点防单日大额超大单派发。",
            ],
            "final_cum_super_amount": _clean_value(row.get("final_cum_super_amount")),
            "final_super_peak_drawdown_pct": _clean_value(row.get("final_super_peak_drawdown_pct")),
        },
    }


def _summarize(rows: pd.DataFrame) -> Dict[str, Any]:
    if rows.empty:
        return {"trade_count": 0, "win_rate": 0.0, "avg_return_pct": 0.0, "median_return_pct": 0.0, "max_loss_pct": 0.0, "avg_holding_days": 0.0, "big_loss_count": 0}
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


def evaluate_trend_continuation_range(start_date: str, end_date: str, top_n: int = 20) -> Dict[str, Any]:
    df = _load_trades().copy()
    if df.empty:
        filtered = df
    else:
        filtered = df[(df["entry_signal_date"] >= start_date) & (df["entry_signal_date"] <= end_date)]
        if "is_mature_trade" in filtered.columns:
            filtered = filtered[filtered["is_mature_trade"] == True]
        filtered = filtered.sort_values(["entry_signal_date", "rank", "symbol"], ascending=[True, True, True])
    trades: List[Dict[str, Any]] = []
    for idx, (_, row) in enumerate(filtered.iterrows(), start=1):
        trades.append({
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
            "selection_rank_score": _clean_value(row.get("score")),
            "risk_count": 0,
            "risk_labels": [],
            "lifecycle_phase_label": "回踩确认",
            "action_label": "可买入",
        })
    return {
        "start_date": start_date,
        "end_date": end_date,
        "strategy_version": STRATEGY_VERSION,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "rank_mode": "trend_continuation_quality_callback_rank",
        "top_n": int(top_n),
        "summary": _summarize(filtered),
        "daily_results": [],
        "trades": trades,
    }
