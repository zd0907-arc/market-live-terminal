from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.aggressive_10cm_strategy import (  # noqa: E402
    _next_trade_date,
    _query_first_15m,
    _trade_dates_from_atomic,
    prepare_metrics,
)
from backend.app.services.selection_strategy_v2 import (  # noqa: E402
    SelectionV2Params,
    _apply_buy_costs,
    _apply_sell_costs,
    _compute_intent_profile,
    _is_limit_down_day,
    _is_limit_up_day,
)


DATA_OUT_DIR = ROOT / "data/selection/aggressive_10cm/trend_cont_agent"
DOC_OUT_DIR = ROOT / "docs/strategy-rework/strategies/aggressive-10cm/experiments/trend-cont-agent"


@dataclass(frozen=True)
class VariantSpec:
    code: str
    label: str
    thesis: str
    min_score: float
    max_positions: int
    max_new_positions_per_day: int
    max_total_exposure_pct: float
    per_position_pct: float
    open_gap_up_pct: float
    open_gap_down_pct: float
    first_15m_price_floor_pct: float
    first_15m_main_floor: float
    first_15m_super_floor: float
    stop_loss_pct: float
    take_profit_pct: float
    take_profit_fraction: float
    trailing_activate_pct: float
    trailing_drawdown_pct: float
    cum_super_peak_drawdown_pct: float
    trend_break_price_vs_ma10_pct: float
    max_holding_days: int


VARIANTS: tuple[VariantSpec, ...] = (
    VariantSpec(
        code="second_wave_reclaim",
        label="二波回踩转强",
        thesis="前期已有趋势，回踩不破核心均线，次日早盘资金继续承接。",
        min_score=63.0,
        max_positions=4,
        max_new_positions_per_day=2,
        max_total_exposure_pct=1.0,
        per_position_pct=0.25,
        open_gap_up_pct=5.5,
        open_gap_down_pct=-2.8,
        first_15m_price_floor_pct=0.2,
        first_15m_main_floor=-0.0025,
        first_15m_super_floor=-0.0015,
        stop_loss_pct=-6.5,
        take_profit_pct=9.0,
        take_profit_fraction=0.40,
        trailing_activate_pct=12.0,
        trailing_drawdown_pct=-5.5,
        cum_super_peak_drawdown_pct=18.0,
        trend_break_price_vs_ma10_pct=-1.2,
        max_holding_days=12,
    ),
    VariantSpec(
        code="platform_breakout",
        label="平台突破续强",
        thesis="平台整理后放量突破，次日早盘继续确认，不追一字和极端高开。",
        min_score=60.0,
        max_positions=4,
        max_new_positions_per_day=2,
        max_total_exposure_pct=1.0,
        per_position_pct=0.25,
        open_gap_up_pct=6.8,
        open_gap_down_pct=-3.0,
        first_15m_price_floor_pct=0.0,
        first_15m_main_floor=-0.0025,
        first_15m_super_floor=-0.0010,
        stop_loss_pct=-5.8,
        take_profit_pct=8.0,
        take_profit_fraction=0.50,
        trailing_activate_pct=10.0,
        trailing_drawdown_pct=-4.5,
        cum_super_peak_drawdown_pct=15.0,
        trend_break_price_vs_ma10_pct=-1.3,
        max_holding_days=10,
    ),
)


RUN_CONFIGS: tuple[dict[str, str], ...] = (
    {
        "run_id": "apr2026_signal_replay_to_0511",
        "signal_start": "2026-04-01",
        "signal_end": "2026-04-30",
        "replay_end": "2026-05-11",
    },
    {
        "run_id": "mar_to_may_available",
        "signal_start": "2026-03-02",
        "signal_end": "2026-05-11",
        "replay_end": "2026-05-11",
    },
)


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _score_linear(value: Any, low: float, high: float) -> float:
    try:
        if pd.isna(value) or high == low:
            return 0.0
        return 100.0 * _clip((float(value) - low) / (high - low))
    except Exception:
        return 0.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _mainboard_10cm(symbol: str) -> bool:
    s = str(symbol).lower()
    return s.startswith(("sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"))


def _trade_dates_between(all_trade_dates: Sequence[str], start: str, end: str) -> List[str]:
    return [d for d in all_trade_dates if start <= d <= end]


def _row_map(metrics: pd.DataFrame) -> Dict[Tuple[str, str], pd.Series]:
    return {(str(row["symbol"]), str(row["trade_date"])): row for _, row in metrics.iterrows()}


def _symbol_groups(metrics: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    return {str(symbol): g.sort_values("trade_date").reset_index(drop=True) for symbol, g in metrics.groupby("symbol", sort=False)}


def _compute_variant_signal(row: pd.Series, variant: VariantSpec) -> Optional[dict[str, Any]]:
    if not _mainboard_10cm(str(row.get("symbol") or "")):
        return None
    if str(row.get("risk_flag_type") or "normal") != "normal":
        return None

    amount = _safe_float(row.get("total_amount"))
    if amount < 220_000_000:
        return None

    ret1 = _safe_float(row.get("return_1d_pct"))
    ret5 = _safe_float(row.get("return_5d_pct"))
    ret20 = _safe_float(row.get("return_20d_pct"))
    drawdown20h = _safe_float(row.get("max_drawdown_from_20d_high_pct"))
    price_vs_ma10 = _safe_float(row.get("price_vs_ma10_pct"))
    close_vs_high20 = _safe_float(row.get("close_vs_prev_high20_pct"))
    breakout20 = _safe_float(row.get("breakout_vs_prev20_high_pct"))
    amount_anom = _safe_float(row.get("amount_anomaly_20d"))
    active = _safe_float(row.get("active_buy_strength"))
    support = _safe_float(row.get("support_pressure_spread"))
    main10 = _safe_float(row.get("main_net_10d_ratio"))
    super5 = _safe_float(row.get("super_net_5d_ratio"))
    super10 = _safe_float(row.get("super_net_10d_ratio"))
    main_day = _safe_float(row.get("l2_main_net_ratio"))
    super_day = _safe_float(row.get("l2_super_net_ratio"))
    pos_super_ratio = _safe_float(row.get("positive_super_day_ratio_10d"))
    pos_l2_ratio = _safe_float(row.get("positive_l2_bar_ratio"))

    intent = _compute_intent_profile(row, SelectionV2Params())
    attack = _safe_float(intent.get("attack_score"))
    repair = _safe_float(intent.get("repair_score"))
    accumulation = _safe_float(intent.get("accumulation_score"))
    distribution = _safe_float(intent.get("distribution_score"))

    if distribution >= 82.0:
        return None

    if variant.code == "second_wave_reclaim":
        if not (12.0 <= ret20 <= 70.0):
            return None
        if not (-15.5 <= drawdown20h <= -3.5):
            return None
        if price_vs_ma10 < -2.0 or price_vs_ma10 > 8.0:
            return None
        if ret1 < 1.2:
            return None
        if amount_anom < 0.88:
            return None
        if main10 < -0.004 or super5 < -0.008:
            return None
        if support < -0.06 or active < -0.8:
            return None
        if max(attack, repair) < 44.0:
            return None

        score = (
            0.24 * _score_linear(ret20, 12.0, 52.0)
            + 0.16 * _score_linear(drawdown20h, -15.5, -5.0)
            + 0.14 * _score_linear(price_vs_ma10, -1.5, 4.5)
            + 0.12 * _score_linear(ret1, 1.2, 6.5)
            + 0.10 * _score_linear(amount_anom, 0.88, 1.8)
            + 0.10 * _score_linear(main10, -0.004, 0.03)
            + 0.06 * _score_linear(super10, -0.006, 0.02)
            + 0.04 * _score_linear(active, -0.5, 5.0)
            + 0.04 * _score_linear(support, -0.04, 0.08)
            + 0.04 * _score_linear(max(attack, repair), 44.0, 75.0)
        )
        reasons = [
            "20日趋势已形成且回撤仍可控",
            "贴近10日线后的转强日",
            "中短期主力/超大单未明显撤退",
        ]
    elif variant.code == "platform_breakout":
        if not (8.0 <= ret20 <= 48.0):
            return None
        if drawdown20h < -10.0 or drawdown20h > -0.5:
            return None
        if abs(ret5) > 12.0:
            return None
        if close_vs_high20 < -4.0:
            return None
        if breakout20 < -1.2:
            return None
        if ret1 < 1.0:
            return None
        if amount_anom < 0.95:
            return None
        if main10 < -0.002 or active < -0.5 or support < -0.05:
            return None
        if attack < 40.0 or pos_l2_ratio < 0.48:
            return None

        score = (
            0.20 * _score_linear(ret20, 8.0, 36.0)
            + 0.18 * _score_linear(close_vs_high20, -4.0, 1.0)
            + 0.18 * _score_linear(breakout20, -1.2, 3.0)
            + 0.14 * _score_linear(amount_anom, 0.95, 1.9)
            + 0.10 * _score_linear(main_day, -0.003, 0.03)
            + 0.08 * _score_linear(main10, -0.002, 0.03)
            + 0.04 * _score_linear(super_day, -0.002, 0.02)
            + 0.04 * _score_linear(active, -0.5, 5.0)
            + 0.04 * _score_linear(support, -0.05, 0.08)
            + 0.04 * _score_linear(attack, 40.0, 78.0)
        )
        reasons = [
            "平台末端接近前高，具备突破条件",
            "放量和主动买盘同步抬升",
            "10日资金结构保持正向",
        ]
    else:
        return None

    score = round(max(0.0, min(100.0, score)), 2)
    if score < variant.min_score:
        return None
    return {
        "symbol": str(row["symbol"]),
        "signal_date": str(row["trade_date"]),
        "variant_code": variant.code,
        "variant_label": variant.label,
        "score": score,
        "signal_reason_1": reasons[0],
        "signal_reason_2": reasons[1],
        "signal_reason_3": reasons[2],
        "ret_1d_pct": round(ret1, 2),
        "ret_5d_pct": round(ret5, 2),
        "ret_20d_pct": round(ret20, 2),
        "drawdown_from_20d_high_pct": round(drawdown20h, 2),
        "price_vs_ma10_pct": round(price_vs_ma10, 2),
        "close_vs_prev_high20_pct": round(close_vs_high20, 2),
        "breakout_vs_prev20_high_pct": round(breakout20, 2),
        "amount_yi": round(amount / 100_000_000.0, 2),
        "amount_anomaly_20d": round(amount_anom, 3),
        "active_buy_strength": round(active, 4),
        "support_pressure_spread": round(support, 5),
        "main_net_10d_ratio": round(main10, 5),
        "super_net_5d_ratio": round(super5, 5),
        "super_net_10d_ratio": round(super10, 5),
        "l2_main_net_ratio": round(main_day, 5),
        "l2_super_net_ratio": round(super_day, 5),
        "positive_super_day_ratio_10d": round(pos_super_ratio, 3),
        "positive_l2_bar_ratio": round(pos_l2_ratio, 3),
        "attack_score": round(attack, 2),
        "repair_score": round(repair, 2),
        "accumulation_score": round(accumulation, 2),
        "distribution_score": round(distribution, 2),
        "close": round(_safe_float(row.get("close")), 4),
    }


def _screen_day(metrics: pd.DataFrame, signal_date: str, variant: VariantSpec, top_n: int) -> List[dict[str, Any]]:
    day_df = metrics[metrics["trade_date"] == signal_date].copy()
    items: List[dict[str, Any]] = []
    for _, row in day_df.iterrows():
        signal = _compute_variant_signal(row, variant)
        if signal:
            items.append(signal)
    items = sorted(items, key=lambda item: (-float(item["score"]), item["symbol"]))[:top_n]
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    return items


def _confirm_entry(candidate: dict[str, Any], entry_row: pd.Series, variant: VariantSpec) -> Tuple[bool, float, dict[str, Any]]:
    signal_close = _safe_float(candidate.get("close"))
    open_price = _safe_float(entry_row.get("open"))
    if signal_close <= 0 or open_price <= 0:
        return False, 0.0, {"reason": "invalid_price"}
    if _is_limit_up_day(entry_row, SelectionV2Params()):
        return False, 0.0, {"reason": "entry_blocked_limit_up"}

    gap_pct = ((open_price / signal_close) - 1.0) * 100.0
    if gap_pct > variant.open_gap_up_pct:
        return False, 0.0, {"reason": "open_gap_too_high", "open_gap_pct": round(gap_pct, 2)}
    if gap_pct < variant.open_gap_down_pct:
        return False, 0.0, {"reason": "open_gap_too_low", "open_gap_pct": round(gap_pct, 2)}

    first_15m = _query_first_15m(str(candidate["symbol"]), str(entry_row["trade_date"]))
    if not first_15m:
        return True, open_price, {"reason": "fallback_daily_open", "open_gap_pct": round(gap_pct, 2)}

    confirm_price = _safe_float(first_15m.get("confirm_price"))
    price_ret = _safe_float(first_15m.get("first_15m_price_return_pct"))
    main_ratio = _safe_float(first_15m.get("first_15m_main_net_ratio"))
    super_ratio = _safe_float(first_15m.get("first_15m_super_net_ratio"))
    if price_ret < variant.first_15m_price_floor_pct:
        return False, confirm_price, {**first_15m, "reason": "first_15m_price_failed", "open_gap_pct": round(gap_pct, 2)}
    if main_ratio < variant.first_15m_main_floor and super_ratio < variant.first_15m_super_floor:
        return False, confirm_price, {**first_15m, "reason": "first_15m_flow_failed", "open_gap_pct": round(gap_pct, 2)}
    if variant.code == "platform_breakout" and confirm_price < signal_close * 0.995:
        return False, confirm_price, {**first_15m, "reason": "breakout_not_held", "open_gap_pct": round(gap_pct, 2)}
    if variant.code == "second_wave_reclaim" and confirm_price < signal_close * 0.99:
        return False, confirm_price, {**first_15m, "reason": "reclaim_not_held", "open_gap_pct": round(gap_pct, 2)}
    return True, confirm_price, {**first_15m, "reason": "confirmed_09_45", "open_gap_pct": round(gap_pct, 2)}


def _close_position(
    trades: List[dict[str, Any]],
    positions: Dict[str, dict[str, Any]],
    cash: float,
    pos: dict[str, Any],
    trade_date: str,
    gross_exit: float,
    reason: str,
    cost_params: SelectionV2Params,
) -> float:
    exit_price = _apply_sell_costs(float(gross_exit), cost_params)
    proceeds = float(pos["shares"]) * exit_price
    cash += proceeds
    realized_cash = _safe_float(pos.get("realized_cash")) + proceeds
    invested_cash = _safe_float(pos.get("invested_cash"))
    net_return_pct = ((realized_cash / invested_cash) - 1.0) * 100.0 if invested_cash else 0.0
    trades.append(
        {
            "run_id": pos["run_id"],
            "variant_code": pos["variant_code"],
            "variant_label": pos["variant_label"],
            "symbol": pos["symbol"],
            "signal_date": pos["signal_date"],
            "entry_date": pos["entry_date"],
            "exit_date": trade_date,
            "gross_entry_price": round(_safe_float(pos["gross_entry_price"]), 4),
            "gross_exit_price": round(float(gross_exit), 4),
            "invested_cash": round(invested_cash, 2),
            "realized_cash": round(realized_cash, 2),
            "net_return_pct": round(net_return_pct, 2),
            "max_runup_pct": round(_safe_float(pos.get("max_runup_pct")), 2),
            "max_drawdown_pct": round(_safe_float(pos.get("max_drawdown_pct")), 2),
            "holding_days": int(pos.get("holding_days") or 0),
            "exit_reason": reason,
            "score": pos["score"],
            "signal_reason_1": pos["signal_reason_1"],
            "signal_reason_2": pos["signal_reason_2"],
            "signal_reason_3": pos["signal_reason_3"],
        }
    )
    positions.pop(pos["symbol"], None)
    return cash


def _summarize_run(
    trades: Sequence[dict[str, Any]],
    equity_curve: Sequence[dict[str, Any]],
    initial_budget: float,
) -> dict[str, Any]:
    returns = pd.Series([_safe_float(t.get("net_return_pct")) for t in trades], dtype=float)
    final_equity = _safe_float(equity_curve[-1]["equity"]) if equity_curve else float(initial_budget)
    profit_sum = float(returns[returns > 0].sum()) if not returns.empty else 0.0
    loss_sum = float((-returns[returns < 0]).sum()) if not returns.empty else 0.0
    avg_holding = float(pd.Series([int(t.get("holding_days") or 0) for t in trades], dtype=float).mean()) if trades else 0.0
    equity = pd.Series([_safe_float(item["equity"]) for item in equity_curve], dtype=float) if equity_curve else pd.Series(dtype=float)
    max_drawdown = float((((equity / equity.cummax()) - 1.0) * 100.0).min()) if not equity.empty else 0.0
    return {
        "initial_budget": round(float(initial_budget), 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / float(initial_budget) - 1.0) * 100.0, 2) if initial_budget else 0.0,
        "trade_count": int(len(trades)),
        "win_rate_pct": round(float((returns > 0).mean() * 100.0), 2) if not returns.empty else 0.0,
        "avg_net_return_pct": round(float(returns.mean()), 2) if not returns.empty else 0.0,
        "median_net_return_pct": round(float(returns.median()), 2) if not returns.empty else 0.0,
        "max_net_return_pct": round(float(returns.max()), 2) if not returns.empty else 0.0,
        "min_net_return_pct": round(float(returns.min()), 2) if not returns.empty else 0.0,
        "profit_factor": round(profit_sum / loss_sum, 2) if loss_sum > 0 else (round(profit_sum, 2) if profit_sum > 0 else 0.0),
        "max_drawdown_pct": round(max_drawdown, 2),
        "avg_holding_days": round(avg_holding, 2),
    }


def _run_variant_backtest(
    metrics: pd.DataFrame,
    variant: VariantSpec,
    run_id: str,
    signal_start: str,
    signal_end: str,
    replay_end: str,
    budget: float,
    trade_dates_all: Sequence[str],
) -> dict[str, Any]:
    simulation_dates = _trade_dates_between(trade_dates_all, signal_start, replay_end)
    signal_dates = _trade_dates_between(trade_dates_all, signal_start, signal_end)
    row_by_symbol_date = _row_map(metrics)

    pending_entries: Dict[str, List[dict[str, Any]]] = {}
    daily_signals: List[dict[str, Any]] = []
    total_candidates = 0
    for signal_date in signal_dates:
        day_candidates = _screen_day(metrics, signal_date, variant, top_n=8)
        total_candidates += len(day_candidates)
        next_date = _next_trade_date(simulation_dates, signal_date)
        daily_signals.append(
            {
                "signal_date": signal_date,
                "candidate_count": len(day_candidates),
                "entry_date": next_date,
            }
        )
        if not next_date:
            continue
        for item in day_candidates:
            pending_entries.setdefault(next_date, []).append(item)

    cost_params = SelectionV2Params(buy_slippage_bp=15.0, sell_slippage_bp=15.0, round_trip_fee_bp=20.0)
    cash = float(budget)
    trades: List[dict[str, Any]] = []
    positions: Dict[str, dict[str, Any]] = {}
    equity_curve: List[dict[str, Any]] = []
    daily_results: List[dict[str, Any]] = []

    for trade_date in simulation_dates:
        opened = 0
        exited = 0
        skipped = 0

        for symbol, pos in list(positions.items()):
            row = row_by_symbol_date.get((symbol, trade_date))
            if row is None:
                continue
            if pos.get("pending_exit_reason"):
                if _is_limit_down_day(row, cost_params):
                    continue
                cash = _close_position(
                    trades,
                    positions,
                    cash,
                    pos,
                    trade_date,
                    _safe_float(row.get("open")),
                    str(pos["pending_exit_reason"]),
                    cost_params,
                )
                exited += 1
                continue

            pos["holding_days"] = int(pos.get("holding_days") or 0) + 1
            entry = _safe_float(pos["gross_entry_price"])
            high = _safe_float(row.get("high"))
            low = _safe_float(row.get("low"))
            close = _safe_float(row.get("close"))
            pos["peak_price"] = max(_safe_float(pos.get("peak_price"), entry), high)
            pos["max_runup_pct"] = max(_safe_float(pos.get("max_runup_pct")), ((high / entry) - 1.0) * 100.0 if entry else 0.0)
            pos["max_drawdown_pct"] = min(_safe_float(pos.get("max_drawdown_pct")), ((low / entry) - 1.0) * 100.0 if entry else 0.0)
            daily_super = _safe_float(row.get("l2_super_net_amount"))
            pos["cum_super"] = _safe_float(pos.get("cum_super")) + daily_super
            pos["cum_amount"] = _safe_float(pos.get("cum_amount")) + _safe_float(row.get("total_amount"))
            pos["cum_super_peak"] = max(_safe_float(pos.get("cum_super_peak")), _safe_float(pos["cum_super"]))
            close_return = ((close / entry) - 1.0) * 100.0 if entry else 0.0

            if not pos.get("partial_taken") and high >= entry * (1.0 + variant.take_profit_pct / 100.0):
                sell_shares = _safe_float(pos["shares"]) * variant.take_profit_fraction
                take_price = entry * (1.0 + variant.take_profit_pct / 100.0)
                proceeds = sell_shares * _apply_sell_costs(take_price, cost_params)
                cash += proceeds
                pos["shares"] = _safe_float(pos["shares"]) - sell_shares
                pos["realized_cash"] = _safe_float(pos.get("realized_cash")) + proceeds
                pos["partial_taken"] = True

            stop_price = entry * (1.0 + variant.stop_loss_pct / 100.0)
            if low <= stop_price:
                if _is_limit_down_day(row, cost_params):
                    pos["pending_exit_reason"] = "stop_blocked_limit_down"
                else:
                    same_day_exit = min(_safe_float(row.get("open")), stop_price) if _safe_float(row.get("open")) < stop_price else stop_price
                    cash = _close_position(
                        trades,
                        positions,
                        cash,
                        pos,
                        trade_date,
                        same_day_exit,
                        "hard_stop",
                        cost_params,
                    )
                    exited += 1
                continue

            peak_return = ((_safe_float(pos.get("peak_price"), entry) / entry) - 1.0) * 100.0 if entry else 0.0
            peak_drawdown = ((close / _safe_float(pos.get("peak_price"), entry)) - 1.0) * 100.0 if _safe_float(pos.get("peak_price"), entry) else 0.0
            cum_super_peak = _safe_float(pos.get("cum_super_peak"))
            cum_super = _safe_float(pos.get("cum_super"))
            super_peak_dd = ((cum_super_peak - cum_super) / cum_super_peak * 100.0) if cum_super_peak > 0 else 0.0
            price_vs_ma10 = _safe_float(row.get("price_vs_ma10_pct"))
            active = _safe_float(row.get("active_buy_strength"))
            main_day_ratio = _safe_float(row.get("l2_main_net_ratio"))
            intent = _compute_intent_profile(row, SelectionV2Params())
            distribution = _safe_float(intent.get("distribution_score"))

            if peak_return >= variant.trailing_activate_pct and peak_drawdown <= variant.trailing_drawdown_pct:
                pos["pending_exit_reason"] = "trailing_drawdown"
            elif cum_super_peak > 0 and super_peak_dd >= variant.cum_super_peak_drawdown_pct and close_return >= 0:
                pos["pending_exit_reason"] = "capital_peak_drawdown"
            elif price_vs_ma10 <= variant.trend_break_price_vs_ma10_pct and close_return > -3.0:
                pos["pending_exit_reason"] = "trend_break_ma10"
            elif distribution >= 80.0 and main_day_ratio < 0:
                pos["pending_exit_reason"] = "distribution_exit"
            elif active < -1.0 and main_day_ratio < -0.008:
                pos["pending_exit_reason"] = "active_sell_pressure"
            elif int(pos.get("holding_days") or 0) >= variant.max_holding_days:
                pos["pending_exit_reason"] = "max_holding_days"

        entries = sorted(pending_entries.get(trade_date, []), key=lambda item: (-float(item["score"]), item["symbol"]))
        for candidate in entries:
            if opened >= variant.max_new_positions_per_day:
                skipped += 1
                continue
            if candidate["symbol"] in positions:
                skipped += 1
                continue
            if len(positions) >= variant.max_positions:
                skipped += 1
                continue
            row = row_by_symbol_date.get((str(candidate["symbol"]), trade_date))
            if row is None:
                skipped += 1
                continue
            max_exposure = float(budget) * variant.max_total_exposure_pct
            current_exposure = sum(_safe_float(pos["shares"]) * _safe_float(pos["gross_entry_price"]) for pos in positions.values())
            available_exposure = max(0.0, max_exposure - current_exposure)
            target_cash = min(float(budget) * variant.per_position_pct, available_exposure, cash)
            if target_cash <= 5_000:
                skipped += 1
                continue
            ok, gross_entry, entry_meta = _confirm_entry(candidate, row, variant)
            if not ok or gross_entry <= 0:
                skipped += 1
                continue
            effective_entry = _apply_buy_costs(gross_entry, cost_params)
            shares = target_cash / effective_entry
            cash -= target_cash
            positions[str(candidate["symbol"])] = {
                **candidate,
                "run_id": run_id,
                "entry_date": trade_date,
                "gross_entry_price": gross_entry,
                "entry_price": effective_entry,
                "shares": shares,
                "invested_cash": target_cash,
                "realized_cash": 0.0,
                "holding_days": 0,
                "peak_price": gross_entry,
                "max_runup_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "partial_taken": False,
                "entry_meta": entry_meta,
                "cum_super": 0.0,
                "cum_super_peak": 0.0,
                "cum_amount": 0.0,
            }
            opened += 1

        mark_value = cash
        for symbol, pos in positions.items():
            row = row_by_symbol_date.get((symbol, trade_date))
            mark_price = _safe_float(row.get("close")) if row is not None else _safe_float(pos["gross_entry_price"])
            mark_value += _safe_float(pos["shares"]) * mark_price
        equity_curve.append(
            {
                "date": trade_date,
                "cash": round(cash, 2),
                "equity": round(mark_value, 2),
                "open_positions": len(positions),
            }
        )
        daily_results.append(
            {
                "trade_date": trade_date,
                "opened": opened,
                "exited": exited,
                "skipped_entries": skipped,
                "open_positions": len(positions),
                "equity": round(mark_value, 2),
            }
        )

    if simulation_dates:
        last_date = simulation_dates[-1]
        for symbol, pos in list(positions.items()):
            row = row_by_symbol_date.get((symbol, last_date))
            gross_exit = _safe_float(row.get("close")) if row is not None else _safe_float(pos["gross_entry_price"])
            cash = _close_position(
                trades,
                positions,
                cash,
                pos,
                last_date,
                gross_exit,
                "window_end_force_close",
                cost_params,
            )
        equity_curve[-1]["cash"] = round(cash, 2)
        equity_curve[-1]["equity"] = round(cash, 2)
        equity_curve[-1]["open_positions"] = 0

    summary = _summarize_run(trades, equity_curve, budget)
    return {
        "run_id": run_id,
        "variant_code": variant.code,
        "variant_label": variant.label,
        "variant": asdict(variant),
        "signal_start": signal_start,
        "signal_end": signal_end,
        "replay_end": replay_end,
        "candidate_count": total_candidates,
        "summary": summary,
        "daily_signals": daily_signals,
        "daily_results": daily_results,
        "equity_curve": equity_curve,
        "trades": trades,
    }


def _pick_best_run(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    non_empty = [item for item in results if int(item.get("summary", {}).get("trade_count") or 0) > 0]
    pool = non_empty or list(results)
    ranked = sorted(
        pool,
        key=lambda item: (
            -_safe_float(item["summary"].get("total_return_pct")),
            _safe_float(item["summary"].get("max_drawdown_pct")),
            -_safe_float(item["summary"].get("win_rate_pct")),
            item["run_id"] != "apr2026_signal_replay_to_0511",
        ),
    )
    return ranked[0] if ranked else {}


def _render_readme(summary_payload: dict[str, Any]) -> str:
    lines = [
        "# 趋势中继 / 二波 / 平台突破实验",
        "",
        f"- 生成时间：{summary_payload['generated_at']}",
        f"- 数据可用区间：{summary_payload['data_available']['start']} ~ {summary_payload['data_available']['end']}",
        f"- 初始资金：{summary_payload['initial_budget']:.0f}",
        f"- 最优策略：{summary_payload['best_strategy'].get('variant_label', '')} @ {summary_payload['best_strategy'].get('run_id', '')}",
        "",
        "## 变体",
        "",
    ]
    for variant in summary_payload["variants"]:
        lines.append(f"- `{variant['code']}` {variant['label']}：{variant['thesis']}")
    lines.extend(["", "## 结果", "", "| run_id | 策略 | 收益% | 回撤% | 胜率% | 交易数 | PF |", "|---|---|---:|---:|---:|---:|---:|"])
    for result in summary_payload["results"]:
        s = result["summary"]
        lines.append(
            f"| {result['run_id']} | {result['variant_label']} | {s['total_return_pct']} | {s['max_drawdown_pct']} | {s['win_rate_pct']} | {s['trade_count']} | {s['profit_factor']} |"
        )
    lines.extend(
        [
            "",
            "## 无未来函数",
            "",
            "1. 信号只使用 `signal_date` 当日收盘及此前的日线/L2滚动指标。",
            "2. 买点确认使用下一交易日 09:45 前三根 5 分钟数据；未用当天后续分时来回填买点。",
            "3. 止损使用当日是否触发阈值；趋势破坏、资金走弱等非盘中硬止损信号统一在下一交易日开盘执行。",
            "4. 回放区间结束时才做强制平仓，不拿结束后的价格。",
            "",
            "## 文件",
            "",
            "- `summary.json`：两段区间、两套策略的汇总。",
            "- `trades.csv`：全部成交明细，含 run_id/variant 标识。",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_outputs(summary_payload: dict[str, Any], trades_df: pd.DataFrame) -> None:
    readme = _render_readme(summary_payload)
    for out_dir in (DATA_OUT_DIR, DOC_OUT_DIR):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        trades_df.to_csv(out_dir / "trades.csv", index=False)
        (out_dir / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    budget = 1_000_000.0
    trade_dates_all = _trade_dates_from_atomic()
    data_start = trade_dates_all[0]
    data_end = trade_dates_all[-1]
    overall_start = min(run["signal_start"] for run in RUN_CONFIGS)
    overall_end = max(run["replay_end"] for run in RUN_CONFIGS)
    metrics_start = (pd.Timestamp(overall_start) - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    metrics = prepare_metrics(metrics_start, overall_end)
    results: List[dict[str, Any]] = []
    for run in RUN_CONFIGS:
        resolved_signal_start = max(run["signal_start"], data_start)
        resolved_signal_end = min(run["signal_end"], data_end)
        resolved_replay_end = min(run["replay_end"], data_end)
        for variant in VARIANTS:
            results.append(
                _run_variant_backtest(
                    metrics=metrics,
                    variant=variant,
                    run_id=run["run_id"],
                    signal_start=resolved_signal_start,
                    signal_end=resolved_signal_end,
                    replay_end=resolved_replay_end,
                    budget=budget,
                    trade_dates_all=trade_dates_all,
                )
            )

    best = _pick_best_run(results)
    summary_payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "initial_budget": budget,
        "data_available": {"start": data_start, "end": data_end},
        "variants": [{"code": v.code, "label": v.label, "thesis": v.thesis, "params": asdict(v)} for v in VARIANTS],
        "runs": list(RUN_CONFIGS),
        "results": [
            {
                "run_id": item["run_id"],
                "variant_code": item["variant_code"],
                "variant_label": item["variant_label"],
                "signal_start": item["signal_start"],
                "signal_end": item["signal_end"],
                "replay_end": item["replay_end"],
                "candidate_count": item["candidate_count"],
                "summary": item["summary"],
            }
            for item in results
        ],
        "best_strategy": {
            "run_id": best.get("run_id"),
            "variant_code": best.get("variant_code"),
            "variant_label": best.get("variant_label"),
            "summary": best.get("summary"),
        },
        "no_lookahead": {
            "signal_data_cutoff": "只用 signal_date 及此前数据",
            "entry_confirmation": "next_trade_date 09:45 之前的前三根5分钟K",
            "exit_execution": "硬止损按当日阈值，趋势/资金转弱次日开盘执行",
        },
    }
    trades_df = pd.DataFrame(
        [
            trade
            for result in results
            for trade in result["trades"]
        ]
    )
    if not trades_df.empty:
        trades_df = trades_df.sort_values(["run_id", "variant_code", "entry_date", "symbol"]).reset_index(drop=True)
    _write_outputs(summary_payload, trades_df)
    print(json.dumps(summary_payload["best_strategy"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
