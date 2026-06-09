from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window
from backend.scripts.research_combined_risk_stack_robustness import enrich_one
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams, build_v1_candidates, simulate_trade_v1_2
from backend.scripts.run_strategy_v1_3_orderbook_filter import launch_cancel_buy_vs_hist
from backend.scripts.run_strategy_v1_trend_reversal import add_ma

STRATEGY_INTERNAL_ID = "stable_capital_callback"
STRATEGY_DISPLAY_NAME = "资金流回调稳健"
STRATEGY_VERSION = "S01-M05-conservative-combined-risk"
MAX_LOOKBACK_DAYS = 200
MIN_FUTURE_DAYS = 10


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


def _load_metrics(end_date: str, start_date: Optional[str] = None) -> pd.DataFrame:
    start = start_date or (pd.Timestamp(end_date) - pd.Timedelta(days=MAX_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    raw = load_atomic_daily_window(start, end_date)
    metrics = add_ma(compute_v2_metrics(raw))
    return metrics.sort_values(["symbol", "trade_date"]).reset_index(drop=True)


@lru_cache(maxsize=32)
def _cached_metrics(end_date: str, start_date: Optional[str] = None) -> pd.DataFrame:
    return _load_metrics(end_date, start_date)


def _select_trade_date(trade_date: Optional[str], metrics: pd.DataFrame) -> str:
    dates = sorted(metrics["trade_date"].dropna().astype(str).unique().tolist())
    if not dates:
        return str(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    if trade_date in dates:
        return str(trade_date)
    if trade_date:
        return str(trade_date)
    return dates[-1]


def _build_candidates_for_date(metrics: pd.DataFrame, target_date: str, limit: int = 10) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    candidates, by_symbol = build_v1_candidates(metrics, target_date, target_date, top_n=max(1, int(limit) * 3))
    if not candidates:
        return pd.DataFrame()
    enriched_rows: List[Dict[str, Any]] = []
    for rec in candidates:
        sym = str(rec["symbol"]).lower()
        g = by_symbol.get(sym)
        if g is None or g.empty:
            continue
        idxs = g.index[g.trade_date == target_date].tolist()
        if not idxs:
            continue
        rec = {**rec, "symbol": sym}
        ob = launch_cancel_buy_vs_hist(g, str(rec.get("launch_start_date")), str(rec.get("launch_end_date")))
        enriched = {**rec, **ob}
        enriched = {**enriched, **enrich_one(g, pd.Series(enriched))}
        if bool(enriched.get("order_filter_available")) and _float(enriched.get("launch_cancel_buy_to_add_buy_vs_hist")) > 2.0:
            continue
        if _float(enriched.get("launch3_return_pct")) < 6.0 and _float(enriched.get("pullback_support_spread_avg")) < 0.0 and _float(enriched.get("confirm_distribution_score")) >= 45.0:
            enriched["risk_count_R1_R5"] = max(_int(enriched.get("risk_count_R1_R5")), 2)
        enriched_rows.append(enriched)

    if not enriched_rows:
        return pd.DataFrame()

    df = pd.DataFrame(enriched_rows)
    df["risk_count_R1_R5"] = pd.to_numeric(df.get("risk_count_R1_R5"), errors="coerce").fillna(0).astype(int)
    df["rank"] = pd.to_numeric(df.get("rank"), errors="coerce").fillna(0).astype(int)
    df["setup_score"] = pd.to_numeric(df.get("setup_score"), errors="coerce").fillna(0.0)
    df = df.sort_values(["rank", "setup_score", "symbol"], ascending=[True, False, True]).drop_duplicates(subset=["symbol"], keep="first")
    df = df.sort_values(["rank", "setup_score", "symbol"], ascending=[True, False, True]).head(max(1, int(limit)))
    return df.reset_index(drop=True)


def _row_to_candidate(row: pd.Series, rank: int) -> Dict[str, Any]:
    risk_count = _int(row.get("risk_count_R1_R5"))
    risk_labels = _split_labels(row.get("risk_labels"))
    entry_allowed = risk_count < 2
    trade_date = _date(row.get("entry_signal_date")) or _date(row.get("pullback_confirm_date")) or ""
    setup_reason = f"发现日前资金/价格结构分 {_float(row.get('setup_score')):.2f}，前 20 日价格未过热。"
    launch_reason = f"启动窗口涨幅 {_float(row.get('launch3_return_pct')):.2f}% ，超大单净流入占比 {_float(row.get('launch3_super_net_ratio')):.4f}。"
    pullback_reason = "启动后回调承接确认" if row.get("pullback_confirm_reason") == "pullback_absorption_confirm" else str(row.get("pullback_confirm_reason") or "回调承接确认")
    exit_plan_summary = "买入后观察累计超大单；累计值从峰值明显回撤或触发出货信号后，次日开盘退出。"
    reason_summary = f"{pullback_reason}；风险标签 {risk_count} 个"
    return {
        "rank": rank,
        "symbol": str(row.get("symbol") or "").lower(),
        "name": str(row.get("symbol") or "").lower(),
        "trade_date": trade_date,
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
        "entry_signal_date": trade_date,
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


def _find_trade_row(symbol: str, trade_date: Optional[str]) -> Optional[pd.Series]:
    target = str(symbol).lower()
    metrics = _cached_metrics(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    if metrics.empty:
        return None
    by_symbol = metrics[metrics["symbol"].astype(str).str.lower() == target].copy()
    if by_symbol.empty:
        return None
    candidates, _ = build_v1_candidates(metrics, metrics.trade_date.min(), metrics.trade_date.max(), top_n=20)
    if not candidates:
        return None
    cand_df = pd.DataFrame(candidates)
    cand_df["symbol"] = cand_df["symbol"].astype(str).str.lower()
    if trade_date:
        exact = cand_df[(cand_df["symbol"] == target) & (cand_df["pullback_confirm_date"] == trade_date)]
        if not exact.empty:
            return exact.iloc[0]
        exact = cand_df[(cand_df["symbol"] == target) & ((cand_df["entry_signal_date"] == trade_date) | (cand_df["discovery_date"] == trade_date))]
        if not exact.empty:
            return exact.iloc[0]
        earlier = cand_df[(cand_df["symbol"] == target) & (cand_df["entry_signal_date"] <= trade_date)].sort_values("entry_signal_date")
        if not earlier.empty:
            return earlier.iloc[-1]
    subset = cand_df[cand_df["symbol"] == target]
    if subset.empty:
        return None
    return subset.sort_values("entry_signal_date").iloc[-1]


def get_stable_callback_trade_dates(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    metrics = _cached_metrics(end_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    if metrics.empty:
        return {"start_date": start_date or "", "end_date": end_date or "", "strategy": STRATEGY_INTERNAL_ID, "items": []}
    resolved_start = start_date or metrics["trade_date"].min()
    resolved_end = end_date or metrics["trade_date"].max()
    if resolved_start > resolved_end:
        resolved_start, resolved_end = resolved_end, resolved_start
    days = pd.date_range(resolved_start, resolved_end, freq="D").strftime("%Y-%m-%d").tolist()
    items: List[Dict[str, Any]] = []
    for date in days:
        is_trade_day = date in set(metrics["trade_date"].astype(str).unique().tolist())
        day_items = _build_candidates_for_date(metrics, date, limit=10) if is_trade_day else pd.DataFrame()
        signal_count = int(len(day_items))
        selectable = is_trade_day
        disabled_reason = None if selectable else "休市/无原始数据"
        if is_trade_day and signal_count <= 0:
            disabled_reason = "当天无稳健策略候选"
        items.append(
            {
                "date": date,
                "is_trade_day": is_trade_day,
                "signal_count": signal_count,
                "selectable": selectable,
                "disabled_reason": disabled_reason,
            }
        )
    return {"start_date": resolved_start, "end_date": resolved_end, "strategy": STRATEGY_INTERNAL_ID, "items": items}


def get_stable_callback_candidates(trade_date: Optional[str], limit: int = 10) -> Dict[str, Any]:
    metrics = _cached_metrics(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    target = _select_trade_date(trade_date, metrics)
    day = _build_candidates_for_date(metrics, target, limit=limit)
    if day.empty:
        return {
            "trade_date": target,
            "strategy": STRATEGY_INTERNAL_ID,
            "strategy_display_name": STRATEGY_DISPLAY_NAME,
            "strategy_internal_id": STRATEGY_INTERNAL_ID,
            "rank_mode": "stable_callback_setup_rank",
            "items": [],
        }
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


def get_stable_callback_profile(symbol: str, trade_date: Optional[str]) -> Dict[str, Any]:
    row = _find_trade_row(symbol, trade_date)
    target = trade_date or pd.Timestamp.today().strftime("%Y-%m-%d")
    if row is None:
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
    profile_date = candidate["trade_date"]
    latest_metrics = _cached_metrics(pd.Timestamp.today().strftime("%Y-%m-%d"))
    metrics = _cached_metrics(profile_date)
    by_symbol = metrics[metrics["symbol"].astype(str).str.lower() == str(symbol).lower()].copy()
    latest_available_trade_date = None
    if not latest_metrics.empty:
        latest_available_trade_date = str(latest_metrics["trade_date"].max())
    elif not by_symbol.empty:
        latest_available_trade_date = str(by_symbol["trade_date"].max())
    return {
        "symbol": candidate["symbol"],
        "trade_date": profile_date,
        "latest_available_trade_date": latest_available_trade_date or _date(row.get("exit_date")) or profile_date,
        "requested_trade_date": trade_date or profile_date,
        "profile_date_fallback_used": bool(trade_date and trade_date != profile_date),
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


def evaluate_stable_callback_range(start_date: str, end_date: str, top_n: int = 10) -> Dict[str, Any]:
    metrics = _cached_metrics(end_date)
    if metrics.empty:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "strategy_version": STRATEGY_VERSION,
            "strategy_display_name": STRATEGY_DISPLAY_NAME,
            "strategy_internal_id": STRATEGY_INTERNAL_ID,
            "rank_mode": "stable_callback_setup_rank",
            "top_n": int(top_n),
            "summary": {"trade_count": 0, "win_rate": 0.0, "avg_return_pct": 0.0, "median_return_pct": 0.0, "max_loss_pct": 0.0, "avg_holding_days": 0.0, "big_loss_count": 0},
            "daily_results": [],
            "trades": [],
        }
    candidates, by_symbol = build_v1_candidates(metrics, start_date, end_date, top_n=max(1, int(top_n) * 3))
    trades: List[Dict[str, Any]] = []
    if candidates:
        exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
        trade_cost_params = __import__("backend.app.services.selection_strategy_v2", fromlist=["SelectionV2Params"]).SelectionV2Params()
        for rec in candidates:
            pull_date = rec.get("pullback_confirm_date")
            if not pull_date:
                continue
            g = by_symbol.get(str(rec["symbol"]).lower())
            if g is None or g.empty:
                continue
            trade = simulate_trade_v1_2(g, str(pull_date), exit_params, trade_cost_params)
            if trade and not trade.get("skipped"):
                trades.append(
                    {
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
                        "selection_rank_score": _clean_value(rec.get("setup_score")),
                        "risk_count": _int(rec.get("risk_count_R1_R5")),
                        "risk_labels": _split_labels(rec.get("risk_labels")),
                        "lifecycle_phase_label": "回调确认",
                        "action_label": "可买入",
                    }
                )
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
        "rank_mode": "stable_callback_setup_rank",
        "top_n": int(top_n),
        "summary": summary,
        "daily_results": [],
        "trades": trades,
    }
