from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.research_trend_continuation_strategy import build_candidates, fnum, future_days_after_entry
from backend.scripts.research_trend_continuation_buy_points import add_confirmations
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams, simulate_trade_v1_2
from backend.scripts.run_strategy_v1_trend_reversal import add_ma

STRATEGY_INTERNAL_ID = "trend_continuation_callback"
STRATEGY_DISPLAY_NAME = "趋势中继高质量回踩"
STRATEGY_VERSION = "S02-current-candidate-20260427"
MAX_LOOKBACK_DAYS = 200
MIN_FUTURE_DAYS = 10
TREND_ARTIFACT_DIR = Path(
    "docs/strategy-rework/strategies/S02-capital-breakout-continuation/"
    "experiments/EXP-20260427-trend-continuation-current-candidate"
)
TREND_BUY_SIGNALS_PATH = TREND_ARTIFACT_DIR / "current_buy_signals.csv"
TREND_OBSERVATION_PATH = TREND_ARTIFACT_DIR / "observation_pool.csv"
TREND_MATURE_TRADES_PATH = TREND_ARTIFACT_DIR / "mature_trades.csv"
TREND_TRADES_PATH = TREND_ARTIFACT_DIR / "trades.csv"


@lru_cache(maxsize=1)
def _load_trend_artifacts() -> Dict[str, pd.DataFrame]:
    def read(path: Path) -> pd.DataFrame:
        return pd.read_csv(path) if path.exists() else pd.DataFrame()

    return {
        "buy": read(TREND_BUY_SIGNALS_PATH),
        "observe": read(TREND_OBSERVATION_PATH),
        "mature": read(TREND_MATURE_TRADES_PATH),
        "trades": read(TREND_TRADES_PATH),
    }


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return round(float(value), 6) if isinstance(value, float) and pd.notna(value) else value


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


def _load_metrics(end_date: str, start_date: Optional[str] = None) -> pd.DataFrame:
    start = start_date or (pd.Timestamp(end_date) - pd.Timedelta(days=MAX_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    raw = load_atomic_daily_window(start, end_date)
    if raw.empty:
        return pd.DataFrame()
    metrics = compute_v2_metrics(raw)
    if metrics.empty:
        return pd.DataFrame()
    try:
        metrics = add_ma(metrics)
    except ValueError as exc:
        if "No objects to concatenate" in str(exc):
            return pd.DataFrame()
        raise
    return metrics.sort_values(["symbol", "trade_date"]).reset_index(drop=True)


@lru_cache(maxsize=32)
def _cached_metrics(end_date: str, start_date: Optional[str] = None) -> pd.DataFrame:
    return _load_metrics(end_date, start_date)


def _select_trade_date(trade_date: Optional[str], metrics: pd.DataFrame) -> str:
    if metrics.empty or "trade_date" not in metrics.columns:
        return str(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    dates = sorted(metrics["trade_date"].dropna().astype(str).unique().tolist())
    if not dates:
        return str(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    if trade_date in dates:
        return str(trade_date)
    if trade_date:
        return str(trade_date)
    return dates[-1]


def _build_candidates_for_date(metrics: pd.DataFrame, target_date: str, limit: int = 20) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    candidates, by_symbol = build_candidates(metrics, target_date, target_date, top_n=max(1, int(limit) * 4), min_score=58.0)
    if candidates.empty:
        return pd.DataFrame()
    confirmed = add_confirmations(candidates, by_symbol, window=8, mode="callback_only", cooldown=5)
    if confirmed.empty:
        return pd.DataFrame()
    confirmed = confirmed.sort_values(["rank", "score", "symbol"], ascending=[True, False, True]).drop_duplicates(subset=["symbol"], keep="first")
    confirmed = confirmed.sort_values(["rank", "score", "symbol"], ascending=[True, False, True]).head(max(1, int(limit)))
    return confirmed.reset_index(drop=True)


def _row_to_candidate(row: pd.Series, rank: int, status: str) -> Dict[str, Any]:
    is_buy = status == "buy_signal"
    symbol = str(row.get("symbol") or "").lower()
    trade_date = _date(row.get("entry_signal_date")) if is_buy else _date(row.get("signal_date"))
    action_label = "可买入" if is_buy else "观察中"
    reason = "严格高质量回踩确认；确认日主动买入和主力净流入为正" if is_buy else "进入趋势中继观察池；等待严格回踩和真承接确认"
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


def _summarize_trend_rows(trades_df: pd.DataFrame) -> Dict[str, Any]:
    valid = trades_df[trades_df.get("net_return_pct").notna()] if not trades_df.empty else pd.DataFrame()
    returns = pd.to_numeric(valid.get("net_return_pct"), errors="coerce").fillna(0.0) if not valid.empty else pd.Series(dtype=float)
    holding = pd.to_numeric(valid.get("holding_days"), errors="coerce").fillna(0.0) if not valid.empty else pd.Series(dtype=float)
    return {
        "trade_count": int(len(valid)),
        "win_rate": round(float((returns > 0).mean() * 100.0), 2) if not returns.empty else 0.0,
        "avg_return_pct": round(float(returns.mean()), 2) if not returns.empty else 0.0,
        "median_return_pct": round(float(returns.median()), 2) if not returns.empty else 0.0,
        "max_return_pct": round(float(returns.max()), 2) if not returns.empty else 0.0,
        "max_loss_pct": round(float(returns.min()), 2) if not returns.empty else 0.0,
        "avg_holding_days": round(float(holding.mean()), 2) if not holding.empty else 0.0,
        "big_loss_count": int((returns <= -8.0).sum()) if not returns.empty else 0,
    }


def _artifact_date_bounds() -> tuple[Optional[str], Optional[str]]:
    artifacts = _load_trend_artifacts()
    dates: List[str] = []
    buy = artifacts["buy"]
    observe = artifacts["observe"]
    if not buy.empty and "entry_signal_date" in buy.columns:
        dates.extend(buy["entry_signal_date"].dropna().astype(str).tolist())
    if not observe.empty and "signal_date" in observe.columns:
        dates.extend(observe["signal_date"].dropna().astype(str).tolist())
    return (min(dates), max(dates)) if dates else (None, None)


def _artifact_candidates_for_date(trade_date: Optional[str], limit: int) -> Optional[Dict[str, Any]]:
    artifacts = _load_trend_artifacts()
    buy = artifacts["buy"].copy()
    observe = artifacts["observe"].copy()
    start, end = _artifact_date_bounds()
    if not start or not end:
        return None
    target = str(trade_date or end)
    if target < start or target > end:
        return None

    items: List[Dict[str, Any]] = []
    buy_symbols = set()
    if not buy.empty and "entry_signal_date" in buy.columns:
        buy["entry_signal_date"] = buy["entry_signal_date"].astype(str)
        buy_day = buy[buy["entry_signal_date"] == target].copy()
        if not buy_day.empty:
            buy_day = buy_day.sort_values(["rank", "score", "symbol"], ascending=[True, False, True])
            buy_day = buy_day.drop_duplicates(subset=["symbol"], keep="first")
            for _, row in buy_day.iterrows():
                buy_symbols.add(str(row.get("symbol") or "").lower())
                items.append(_row_to_candidate(row, len(items) + 1, "buy_signal"))
    if not observe.empty and "signal_date" in observe.columns and len(items) < max(1, int(limit)):
        observe["signal_date"] = observe["signal_date"].astype(str)
        observe_day = observe[observe["signal_date"] == target].copy()
        if not observe_day.empty:
            observe_day["symbol_norm"] = observe_day["symbol"].astype(str).str.lower()
            observe_day = observe_day[~observe_day["symbol_norm"].isin(buy_symbols)]
            observe_day = observe_day.sort_values(["rank", "score", "symbol"], ascending=[True, False, True])
            observe_day = observe_day.drop_duplicates(subset=["symbol_norm"], keep="first")
            for _, row in observe_day.head(max(0, int(limit) - len(items))).iterrows():
                items.append(_row_to_candidate(row, len(items) + 1, "observe"))

    return {
        "trade_date": target,
        "strategy": STRATEGY_INTERNAL_ID,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "strategy_version": STRATEGY_VERSION,
        "rank_mode": "trend_continuation_artifact_signal_rank",
        "source_snapshot": str(TREND_ARTIFACT_DIR),
        "items": items[: max(1, int(limit))],
    }


def _artifact_trade_payload(row: pd.Series, idx: int) -> Dict[str, Any]:
    return {
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
        "future_days_available": _int(row.get("future_days_available")),
        "is_mature_trade": bool(row.get("is_mature_trade")),
    }


def _evaluate_trend_artifact(start_date: str, end_date: str, top_n: int) -> Optional[Dict[str, Any]]:
    mature = _load_trend_artifacts()["mature"].copy()
    if mature.empty or "entry_signal_date" not in mature.columns:
        return None
    mature["entry_signal_date"] = mature["entry_signal_date"].astype(str)
    scoped = mature[(mature["entry_signal_date"] >= start_date) & (mature["entry_signal_date"] <= end_date)].copy()
    if not scoped.empty:
        scoped = scoped.sort_values(["entry_signal_date", "rank", "symbol"], ascending=[True, True, True])
    trades = [_artifact_trade_payload(row, idx) for idx, (_, row) in enumerate(scoped.iterrows(), start=1)]
    return {
        "start_date": start_date,
        "end_date": end_date,
        "strategy_version": STRATEGY_VERSION,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "rank_mode": "trend_continuation_artifact_signal_rank",
        "top_n": int(top_n),
        "summary": _summarize_trend_rows(scoped),
        "daily_results": [],
        "trades": trades,
        "source_snapshot": str(TREND_MATURE_TRADES_PATH),
    }


def _artifact_profile(symbol: str, trade_date: Optional[str]) -> Optional[Dict[str, Any]]:
    artifacts = _load_trend_artifacts()
    target_symbol = str(symbol).lower()
    frames = [
        (artifacts["trades"], "buy_signal"),
        (artifacts["buy"], "buy_signal"),
        (artifacts["observe"], "observe"),
    ]
    for frame, status in frames:
        if frame.empty or "symbol" not in frame.columns:
            continue
        scoped = frame[frame["symbol"].astype(str).str.lower() == target_symbol].copy()
        if scoped.empty:
            continue
        if trade_date:
            date_text = str(trade_date)
            masks = []
            for col in ["entry_signal_date", "signal_date", "observe_date"]:
                if col in scoped.columns:
                    masks.append(scoped[col].astype(str).eq(date_text))
            if masks:
                mask = masks[0]
                for item in masks[1:]:
                    mask = mask | item
                scoped = scoped[mask].copy()
            if scoped.empty:
                continue
        sort_cols = [col for col in ["entry_signal_date", "signal_date", "rank"] if col in scoped.columns]
        if sort_cols:
            scoped = scoped.sort_values(sort_cols, ascending=[False] * len(sort_cols))
        row = scoped.iloc[0]
        candidate = _row_to_candidate(row, _int(row.get("rank")), status)
        return {
            "symbol": candidate["symbol"],
            "trade_date": candidate["trade_date"],
            "latest_available_trade_date": _date(row.get("exit_date")) or candidate["trade_date"],
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
                "source_snapshot": str(TREND_ARTIFACT_DIR),
            },
        }
    return None


def _find_row(symbol: str, trade_date: Optional[str]) -> tuple[Optional[pd.Series], str]:
    target = str(symbol).lower()
    metrics = _cached_metrics(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    if metrics.empty:
        return None, "observe"
    candidates, _ = build_candidates(metrics, metrics.trade_date.min(), metrics.trade_date.max(), top_n=20, min_score=58.0)
    if candidates.empty:
        return None, "observe"
    confirmed = add_confirmations(candidates, {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}, window=8, mode="callback_only", cooldown=5)
    if confirmed.empty:
        return None, "observe"
    subset = confirmed[confirmed["symbol"].astype(str).str.lower() == target].copy()
    if subset.empty:
        return None, "observe"
    if trade_date:
        exact = subset[(subset["entry_signal_date"] == trade_date) | (subset["observe_date"] == trade_date)]
        if not exact.empty:
            return exact.iloc[0], "buy_signal"
        earlier = subset[subset["entry_signal_date"] <= trade_date].sort_values("entry_signal_date")
        if not earlier.empty:
            return earlier.iloc[-1], "buy_signal"
    row = subset.sort_values("entry_signal_date").iloc[-1]
    return row, "buy_signal"


def get_trend_continuation_trade_dates(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    metrics = _cached_metrics(end_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    if metrics.empty:
        return {"start_date": start_date or "", "end_date": end_date or "", "strategy": STRATEGY_INTERNAL_ID, "items": []}
    resolved_start = start_date or metrics["trade_date"].min()
    resolved_end = end_date or metrics["trade_date"].max()
    if resolved_start > resolved_end:
        resolved_start, resolved_end = resolved_end, resolved_start
    days = pd.date_range(resolved_start, resolved_end, freq="D").strftime("%Y-%m-%d").tolist()
    available_dates = set(metrics["trade_date"].astype(str).unique().tolist())
    items: List[Dict[str, Any]] = []
    for date in days:
        is_trade_day = date in available_dates
        day_items = _build_candidates_for_date(metrics, date, limit=20) if is_trade_day else pd.DataFrame()
        signal_count = int(len(day_items))
        selectable = is_trade_day
        disabled_reason = None if selectable else "休市/无原始数据"
        if is_trade_day and signal_count <= 0:
            disabled_reason = "当天无趋势中继候选"
        items.append({"date": date, "is_trade_day": is_trade_day, "signal_count": signal_count, "selectable": selectable, "disabled_reason": disabled_reason})
    return {"start_date": resolved_start, "end_date": resolved_end, "strategy": STRATEGY_INTERNAL_ID, "items": items}


def get_trend_continuation_candidates(trade_date: Optional[str], limit: int = 20) -> Dict[str, Any]:
    artifact_payload = _artifact_candidates_for_date(trade_date, limit)
    if artifact_payload is not None:
        return artifact_payload

    metrics = _cached_metrics(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    target = _select_trade_date(trade_date, metrics)
    day = _build_candidates_for_date(metrics, target, limit=limit)
    if day.empty:
        return {
            "trade_date": target,
            "strategy": STRATEGY_INTERNAL_ID,
            "strategy_display_name": STRATEGY_DISPLAY_NAME,
            "strategy_internal_id": STRATEGY_INTERNAL_ID,
            "strategy_version": STRATEGY_VERSION,
            "rank_mode": "trend_continuation_quality_callback_rank",
            "items": [],
        }
    items: List[Dict[str, Any]] = []
    for idx, (_, row) in enumerate(day.iterrows(), start=1):
        items.append(_row_to_candidate(row, idx, "buy_signal"))
    return {
        "trade_date": target,
        "strategy": STRATEGY_INTERNAL_ID,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "strategy_version": STRATEGY_VERSION,
        "rank_mode": "trend_continuation_quality_callback_rank",
        "items": items,
    }


def get_trend_continuation_profile(symbol: str, trade_date: Optional[str]) -> Dict[str, Any]:
    artifact_payload = _artifact_profile(symbol, trade_date)
    if artifact_payload is not None:
        return artifact_payload

    row, status = _find_row(symbol, trade_date)
    target = trade_date or pd.Timestamp.today().strftime("%Y-%m-%d")
    if row is None:
        return {"symbol": symbol.lower(), "trade_date": target, "name": symbol.lower(), "strategy_display_name": STRATEGY_DISPLAY_NAME, "strategy_internal_id": STRATEGY_INTERNAL_ID, "current_judgement": "暂无趋势中继画像", "entry_allowed": False, "entry_block_reasons": ["无候选信号"], "research": {}}
    candidate = _row_to_candidate(row, _int(row.get("rank")), status)
    latest_metrics = _cached_metrics(pd.Timestamp.today().strftime("%Y-%m-%d"))
    latest_available_trade_date = str(latest_metrics["trade_date"].max()) if not latest_metrics.empty else candidate["trade_date"]
    return {
        "symbol": candidate["symbol"],
        "trade_date": candidate["trade_date"],
        "latest_available_trade_date": latest_available_trade_date,
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


def evaluate_trend_continuation_range(start_date: str, end_date: str, top_n: int = 20) -> Dict[str, Any]:
    artifact_payload = _evaluate_trend_artifact(start_date, end_date, top_n)
    if artifact_payload is not None:
        return artifact_payload

    metrics = _cached_metrics(end_date)
    if metrics.empty:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "strategy_version": STRATEGY_VERSION,
            "strategy_display_name": STRATEGY_DISPLAY_NAME,
            "strategy_internal_id": STRATEGY_INTERNAL_ID,
            "rank_mode": "trend_continuation_quality_callback_rank",
            "top_n": int(top_n),
            "summary": {"trade_count": 0, "win_rate": 0.0, "avg_return_pct": 0.0, "median_return_pct": 0.0, "max_loss_pct": 0.0, "avg_holding_days": 0.0, "big_loss_count": 0},
            "daily_results": [],
            "trades": [],
        }
    candidates, by_symbol = build_candidates(metrics, start_date, end_date, top_n=max(1, int(top_n) * 4), min_score=58.0)
    confirmed = add_confirmations(candidates, by_symbol, window=8, mode="callback_only", cooldown=5)
    exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    trade_cost_params = SelectionV2Params()
    trades: List[Dict[str, Any]] = []
    if not confirmed.empty:
        for _, rec in confirmed.iterrows():
            g = by_symbol[str(rec.symbol)]
            trade = simulate_trade_v1_2(g, str(rec.entry_signal_date), exit_params, trade_cost_params)
            if not trade or trade.get("skipped"):
                continue
            fdays = future_days_after_entry(g, str(trade["entry_date"]))
            trades.append({
                "id": len(trades) + 1,
                "symbol": str(rec.get("symbol") or "").lower(),
                "rank": _int(rec.get("rank")),
                "signal_date": _date(rec.get("entry_signal_date")),
                "entry_signal_date": _date(rec.get("entry_signal_date")),
                "entry_date": _date(trade.get("entry_date")),
                "exit_signal_date": _date(trade.get("exit_signal_date")),
                "exit_date": _date(trade.get("exit_date")),
                "entry_price": _clean_value(trade.get("entry_price")),
                "exit_price": _clean_value(trade.get("exit_price")),
                "return_pct": _clean_value(trade.get("return_pct")),
                "net_return_pct": _clean_value(trade.get("net_return_pct")),
                "max_drawdown_pct": _clean_value(trade.get("max_drawdown_pct")),
                "holding_days": _int(trade.get("holding_days")),
                "exit_reason": _clean_value(trade.get("exit_reason")),
                "selection_rank_score": _clean_value(rec.get("score")),
                "risk_count": 0,
                "risk_labels": [],
                "lifecycle_phase_label": "回踩确认",
                "action_label": "可买入",
                "future_days_available": fdays,
                "is_mature_trade": fdays >= MIN_FUTURE_DAYS,
            })
    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df = trades_df[(trades_df["entry_signal_date"] >= start_date) & (trades_df["entry_signal_date"] <= end_date)].copy()
        trades_df = trades_df.sort_values(["entry_signal_date", "rank", "symbol"], ascending=[True, True, True])
    valid = trades_df[trades_df.get("net_return_pct").notna()] if not trades_df.empty else pd.DataFrame()
    returns = pd.to_numeric(valid.get("net_return_pct"), errors="coerce").fillna(0.0) if not valid.empty else pd.Series(dtype=float)
    holding = pd.to_numeric(valid.get("holding_days"), errors="coerce").fillna(0.0) if not valid.empty else pd.Series(dtype=float)
    summary = {
        "trade_count": int(len(valid)),
        "win_rate": round(float((returns > 0).mean() * 100.0), 2) if not returns.empty else 0.0,
        "avg_return_pct": round(float(returns.mean()), 2) if not returns.empty else 0.0,
        "median_return_pct": round(float(returns.median()), 2) if not returns.empty else 0.0,
        "max_return_pct": round(float(returns.max()), 2) if not returns.empty else 0.0,
        "max_loss_pct": round(float(returns.min()), 2) if not returns.empty else 0.0,
        "avg_holding_days": round(float(holding.mean()), 2) if not holding.empty else 0.0,
        "big_loss_count": int((returns <= -8.0).sum()) if not returns.empty else 0,
    }
    return {
        "start_date": start_date,
        "end_date": end_date,
        "strategy_version": STRATEGY_VERSION,
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_internal_id": STRATEGY_INTERNAL_ID,
        "rank_mode": "trend_continuation_quality_callback_rank",
        "top_n": int(top_n),
        "summary": summary,
        "daily_results": [],
        "trades": trades,
    }
