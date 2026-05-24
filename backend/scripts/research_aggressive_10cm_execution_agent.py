from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.services.aggressive_10cm_strategy import (  # noqa: E402
    Aggressive10cmParams,
    _market_regime,
    _next_trade_date,
    _query_first_15m,
    _row_by_symbol_date,
    _selection_start,
    _trade_dates_from_atomic,
    prepare_metrics,
    screen_candidates,
)
from backend.app.services.selection_strategy_v2 import (  # noqa: E402
    SelectionV2Params,
    _apply_buy_costs,
    _apply_sell_costs,
    _compute_intent_profile,
    _is_limit_down_day,
    _is_limit_up_day,
)


DEFAULT_DATA_OUT = ROOT_DIR / "data/selection/aggressive_10cm/execution_agent"
DEFAULT_DOC_OUT = ROOT_DIR / "docs/strategy-rework/strategies/aggressive-10cm/experiments/execution-agent"
BASE_TOP_N = 12
INITIAL_BUDGET = 1_000_000.0


@dataclass(frozen=True)
class TakeProfitLevel:
    trigger_pct: float
    fraction_of_initial: float
    label: str


@dataclass(frozen=True)
class ExecutionVariant:
    name: str
    label: str
    thesis: str
    signal_skip_limit_up_close: bool
    signal_skip_touch_limit_up: bool
    signal_skip_return_1d_pct: Optional[float]
    signal_hot_return_20d_pct: float
    signal_hot_gap_cap_pct: float
    min_score_in_weak_market: float
    skip_new_entries_when_signal_market_weak: bool
    max_open_gap_up_pct: float
    max_open_gap_down_pct: float
    first_15m_price_floor_pct: float
    first_15m_main_net_floor: float
    first_15m_super_net_floor: float
    require_positive_15m_either: bool
    max_positions: int
    max_new_positions_per_day: int
    per_position_pct_by_regime: Dict[str, float]
    max_total_exposure_pct_by_regime: Dict[str, float]
    score_size_boosts: Sequence[Tuple[float, float]] = field(default_factory=tuple)
    hard_stop_pct: float = -6.0
    take_profit_levels: Sequence[TakeProfitLevel] = field(default_factory=tuple)
    trailing_activate_pct: float = 12.0
    trailing_drawdown_pct: float = -5.0
    distribution_exit_score: float = 82.0
    distribution_l2_main_ratio_max: float = 0.0
    max_holding_days: int = 8
    weak_close_after_days: Optional[int] = None
    weak_close_floor_pct: Optional[float] = None
    cum_super_peak_drawdown_pct: Optional[float] = None


WINDOWS: Sequence[Tuple[str, str]] = (
    ("2026-04-01", "2026-04-30"),
    ("2026-03-02", "2026-05-11"),
)


VARIANTS: Sequence[ExecutionVariant] = (
    ExecutionVariant(
        name="open15_trend",
        label="开盘15分钟确认",
        thesis="只做次日开盘后继续承接的主升候选，弱市自动收缩总仓位。",
        signal_skip_limit_up_close=False,
        signal_skip_touch_limit_up=False,
        signal_skip_return_1d_pct=None,
        signal_hot_return_20d_pct=60.0,
        signal_hot_gap_cap_pct=2.0,
        min_score_in_weak_market=86.0,
        skip_new_entries_when_signal_market_weak=False,
        max_open_gap_up_pct=4.5,
        max_open_gap_down_pct=-2.5,
        first_15m_price_floor_pct=0.2,
        first_15m_main_net_floor=-0.002,
        first_15m_super_net_floor=-0.001,
        require_positive_15m_either=True,
        max_positions=4,
        max_new_positions_per_day=2,
        per_position_pct_by_regime={"strong": 0.24, "neutral": 0.19, "defensive": 0.14, "weak": 0.10, "unknown": 0.14},
        max_total_exposure_pct_by_regime={"strong": 0.82, "neutral": 0.62, "defensive": 0.42, "weak": 0.22, "unknown": 0.42},
        score_size_boosts=((90.0, 1.10), (87.0, 1.0), (84.0, 0.9)),
        hard_stop_pct=-6.0,
        take_profit_levels=(
            TakeProfitLevel(8.0, 0.50, "tp8_half"),
            TakeProfitLevel(14.0, 0.25, "tp14_quarter"),
        ),
        trailing_activate_pct=12.0,
        trailing_drawdown_pct=-5.0,
        distribution_exit_score=82.0,
        distribution_l2_main_ratio_max=0.0,
        max_holding_days=8,
        weak_close_after_days=3,
        weak_close_floor_pct=-1.0,
        cum_super_peak_drawdown_pct=30.0,
    ),
    ExecutionVariant(
        name="no_chase_limit_gap",
        label="涨停次日不追",
        thesis="对信号日过热和次日高开最严格，优先控制回撤和追高失败。",
        signal_skip_limit_up_close=True,
        signal_skip_touch_limit_up=False,
        signal_skip_return_1d_pct=9.3,
        signal_hot_return_20d_pct=50.0,
        signal_hot_gap_cap_pct=2.2,
        min_score_in_weak_market=87.0,
        skip_new_entries_when_signal_market_weak=False,
        max_open_gap_up_pct=3.2,
        max_open_gap_down_pct=-2.0,
        first_15m_price_floor_pct=0.1,
        first_15m_main_net_floor=-0.001,
        first_15m_super_net_floor=-0.001,
        require_positive_15m_either=True,
        max_positions=3,
        max_new_positions_per_day=2,
        per_position_pct_by_regime={"strong": 0.20, "neutral": 0.15, "defensive": 0.11, "weak": 0.0, "unknown": 0.11},
        max_total_exposure_pct_by_regime={"strong": 0.58, "neutral": 0.42, "defensive": 0.28, "weak": 0.0, "unknown": 0.28},
        score_size_boosts=((90.0, 1.05), (87.0, 0.95)),
        hard_stop_pct=-4.8,
        take_profit_levels=(
            TakeProfitLevel(6.0, 0.35, "tp6_35"),
            TakeProfitLevel(10.0, 0.35, "tp10_35"),
        ),
        trailing_activate_pct=10.0,
        trailing_drawdown_pct=-4.0,
        distribution_exit_score=78.0,
        distribution_l2_main_ratio_max=0.002,
        max_holding_days=6,
        weak_close_after_days=2,
        weak_close_floor_pct=-0.5,
        cum_super_peak_drawdown_pct=22.0,
    ),
    ExecutionVariant(
        name="strong_scaleout",
        label="强势分批止盈",
        thesis="允许更强的续强开盘，靠分批止盈和趋势跟踪拉高月收益。",
        signal_skip_limit_up_close=False,
        signal_skip_touch_limit_up=False,
        signal_skip_return_1d_pct=None,
        signal_hot_return_20d_pct=72.0,
        signal_hot_gap_cap_pct=3.0,
        min_score_in_weak_market=87.0,
        skip_new_entries_when_signal_market_weak=False,
        max_open_gap_up_pct=5.8,
        max_open_gap_down_pct=-3.0,
        first_15m_price_floor_pct=-0.2,
        first_15m_main_net_floor=-0.004,
        first_15m_super_net_floor=-0.003,
        require_positive_15m_either=True,
        max_positions=4,
        max_new_positions_per_day=3,
        per_position_pct_by_regime={"strong": 0.26, "neutral": 0.22, "defensive": 0.16, "weak": 0.10, "unknown": 0.16},
        max_total_exposure_pct_by_regime={"strong": 0.90, "neutral": 0.74, "defensive": 0.50, "weak": 0.25, "unknown": 0.50},
        score_size_boosts=((91.0, 1.15), (88.0, 1.05), (85.0, 0.95)),
        hard_stop_pct=-7.0,
        take_profit_levels=(
            TakeProfitLevel(9.0, 0.33, "tp9_33"),
            TakeProfitLevel(16.0, 0.33, "tp16_33"),
        ),
        trailing_activate_pct=16.0,
        trailing_drawdown_pct=-7.0,
        distribution_exit_score=84.0,
        distribution_l2_main_ratio_max=-0.002,
        max_holding_days=10,
        weak_close_after_days=4,
        weak_close_floor_pct=-2.0,
        cum_super_peak_drawdown_pct=20.0,
    ),
)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


@lru_cache(maxsize=8192)
def _first_15m_cached(symbol: str, trade_date: str, db_path: str) -> Optional[Dict[str, Any]]:
    return _query_first_15m(symbol, trade_date, db_path=db_path)


def _score_multiplier(score: float, variant: ExecutionVariant) -> float:
    for threshold, multiplier in variant.score_size_boosts:
        if score >= threshold:
            return multiplier
    return 1.0


def _regime_of_market(market: Dict[str, Any]) -> str:
    label = str(market.get("label") or "unknown")
    return label if label in {"strong", "neutral", "defensive", "weak"} else "unknown"


def _signal_entry_filter(
    candidate: Dict[str, Any],
    signal_row: pd.Series,
    market: Dict[str, Any],
    variant: ExecutionVariant,
) -> Tuple[bool, str]:
    regime = _regime_of_market(market)
    score = _float(candidate.get("score"))
    if variant.skip_new_entries_when_signal_market_weak and regime == "weak":
        return False, "signal_market_weak_skip"
    if regime == "weak" and score < variant.min_score_in_weak_market:
        return False, "weak_market_score_not_enough"
    if variant.signal_skip_limit_up_close and _float(signal_row.get("is_limit_up_close")) > 0:
        return False, "signal_limit_up_close"
    if variant.signal_skip_touch_limit_up and _float(signal_row.get("touch_limit_up")) > 0:
        return False, "signal_touch_limit_up"
    if variant.signal_skip_return_1d_pct is not None and _float(signal_row.get("return_1d_pct")) >= variant.signal_skip_return_1d_pct:
        return False, "signal_return_too_hot"
    return True, "ok"


def _confirm_entry_variant(
    candidate: Dict[str, Any],
    signal_row: pd.Series,
    entry_row: pd.Series,
    variant: ExecutionVariant,
    db_path: str,
) -> Tuple[bool, float, Dict[str, Any]]:
    signal_close = _float(candidate.get("close"))
    open_price = _float(entry_row.get("open"))
    if signal_close <= 0 or open_price <= 0:
        return False, 0.0, {"reason": "invalid_price"}
    if _is_limit_up_day(entry_row, SelectionV2Params()):
        return False, 0.0, {"reason": "entry_blocked_limit_up"}
    gap_pct = ((open_price / signal_close) - 1.0) * 100.0
    max_gap_up = variant.max_open_gap_up_pct
    if _float(signal_row.get("return_20d_pct")) >= variant.signal_hot_return_20d_pct:
        max_gap_up = min(max_gap_up, variant.signal_hot_gap_cap_pct)
    if gap_pct > max_gap_up:
        return False, 0.0, {"reason": "open_gap_too_high", "open_gap_pct": round(gap_pct, 2)}
    if gap_pct < variant.max_open_gap_down_pct:
        return False, 0.0, {"reason": "open_gap_too_low", "open_gap_pct": round(gap_pct, 2)}

    first_15m = _first_15m_cached(str(candidate["symbol"]), str(entry_row["trade_date"]), db_path)
    if not first_15m:
        return True, open_price, {"reason": "fallback_daily_open", "open_gap_pct": round(gap_pct, 2)}
    price_ret = _float(first_15m["first_15m_price_return_pct"])
    main_ratio = _float(first_15m["first_15m_main_net_ratio"])
    super_ratio = _float(first_15m["first_15m_super_net_ratio"])
    if price_ret < variant.first_15m_price_floor_pct:
        return False, _float(first_15m["confirm_price"]), {**first_15m, "reason": "first_15m_price_below_floor", "open_gap_pct": round(gap_pct, 2)}
    if variant.require_positive_15m_either and main_ratio <= 0 and super_ratio <= 0:
        return False, _float(first_15m["confirm_price"]), {**first_15m, "reason": "first_15m_both_outflow", "open_gap_pct": round(gap_pct, 2)}
    if main_ratio < variant.first_15m_main_net_floor:
        return False, _float(first_15m["confirm_price"]), {**first_15m, "reason": "first_15m_main_outflow", "open_gap_pct": round(gap_pct, 2)}
    if super_ratio < variant.first_15m_super_net_floor:
        return False, _float(first_15m["confirm_price"]), {**first_15m, "reason": "first_15m_super_outflow", "open_gap_pct": round(gap_pct, 2)}
    return True, _float(first_15m["confirm_price"]), {**first_15m, "reason": "confirmed_09_45", "open_gap_pct": round(gap_pct, 2)}


def _compute_equity(cash: float, positions: Dict[str, Dict[str, Any]], trade_date: str, row_map: Dict[Tuple[str, str], pd.Series]) -> float:
    equity = cash
    for symbol, pos in positions.items():
        row = row_map.get((symbol, trade_date))
        mark_price = _float(row.get("close")) if row is not None else _float(pos["gross_entry_price"])
        equity += _float(pos["shares"]) * mark_price
    return equity


def _profit_factor(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    gains = trades.loc[trades["pnl_cash"] > 0, "pnl_cash"].sum()
    losses = trades.loc[trades["pnl_cash"] < 0, "pnl_cash"].sum()
    if losses == 0:
        return 999.0 if gains > 0 else 0.0
    return float(gains / abs(losses))


def _make_summary(
    trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
    initial_budget: float,
    filled_entries: int,
    planned_entries: int,
) -> Dict[str, Any]:
    trades_df = pd.DataFrame(trades)
    final_equity = _float(equity_curve[-1]["equity"]) if equity_curve else initial_budget
    if equity_curve:
        equity_series = pd.Series([_float(row["equity"]) for row in equity_curve], dtype=float)
        max_drawdown_pct = float(((equity_series / equity_series.cummax()) - 1.0).min() * 100.0)
        daily_returns = equity_series.pct_change().fillna(0.0)
        sharpe_like = 0.0
        if daily_returns.std() > 0:
            sharpe_like = float((daily_returns.mean() / daily_returns.std()) * math.sqrt(252))
    else:
        max_drawdown_pct = 0.0
        sharpe_like = 0.0
    if trades_df.empty:
        win_rate_pct = 0.0
        avg_net_return_pct = 0.0
        median_net_return_pct = 0.0
        max_net_return_pct = 0.0
        min_net_return_pct = 0.0
        avg_holding_days = 0.0
        gross_profit = 0.0
        gross_loss = 0.0
        expectancy_pct = 0.0
    else:
        net_returns = trades_df["net_return_pct"].astype(float)
        win_rate_pct = float((net_returns > 0).mean() * 100.0)
        avg_net_return_pct = float(net_returns.mean())
        median_net_return_pct = float(net_returns.median())
        max_net_return_pct = float(net_returns.max())
        min_net_return_pct = float(net_returns.min())
        avg_holding_days = float(trades_df["holding_days"].astype(float).mean())
        gross_profit = float(trades_df.loc[trades_df["pnl_cash"] > 0, "pnl_cash"].sum())
        gross_loss = float(trades_df.loc[trades_df["pnl_cash"] < 0, "pnl_cash"].sum())
        expectancy_pct = avg_net_return_pct
    return {
        "initial_budget": round(initial_budget, 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / initial_budget - 1.0) * 100.0, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "trade_count": int(len(trades)),
        "win_rate_pct": round(win_rate_pct, 2),
        "avg_net_return_pct": round(avg_net_return_pct, 2),
        "median_net_return_pct": round(median_net_return_pct, 2),
        "max_net_return_pct": round(max_net_return_pct, 2),
        "min_net_return_pct": round(min_net_return_pct, 2),
        "avg_holding_days": round(avg_holding_days, 2),
        "gross_profit_cash": round(gross_profit, 2),
        "gross_loss_cash": round(gross_loss, 2),
        "profit_factor": round(_profit_factor(trades_df), 3),
        "expectancy_pct": round(expectancy_pct, 2),
        "planned_entries": int(planned_entries),
        "filled_entries": int(filled_entries),
        "entry_fill_rate_pct": round((filled_entries / planned_entries) * 100.0, 2) if planned_entries else 0.0,
        "sharpe_like": round(sharpe_like, 3),
    }


def _close_position(
    positions: Dict[str, Dict[str, Any]],
    trades: List[Dict[str, Any]],
    symbol: str,
    trade_date: str,
    gross_exit_price: float,
    exit_reason: str,
    cash_holder: Dict[str, float],
    window_label: str,
    variant: ExecutionVariant,
) -> None:
    pos = positions[symbol]
    sell_price = _apply_sell_costs(gross_exit_price, SelectionV2Params())
    proceeds = _float(pos["shares"]) * sell_price
    cash_holder["cash"] += proceeds
    pos["realized_cash"] = _float(pos.get("realized_cash")) + proceeds
    invested_cash = _float(pos["invested_cash"])
    realized_cash = _float(pos["realized_cash"])
    pnl_cash = realized_cash - invested_cash
    net_return_pct = (realized_cash / invested_cash - 1.0) * 100.0 if invested_cash else 0.0
    trades.append(
        {
            "window": window_label,
            "variant": variant.name,
            "variant_label": variant.label,
            "symbol": symbol,
            "name": pos.get("name") or symbol,
            "signal_date": pos["signal_date"],
            "entry_date": pos["entry_date"],
            "exit_date": trade_date,
            "gross_entry_price": round(_float(pos["gross_entry_price"]), 4),
            "gross_exit_price": round(gross_exit_price, 4),
            "invested_cash": round(invested_cash, 2),
            "realized_cash": round(realized_cash, 2),
            "pnl_cash": round(pnl_cash, 2),
            "net_return_pct": round(net_return_pct, 2),
            "holding_days": int(pos.get("holding_days") or 0),
            "max_runup_pct": round(_float(pos.get("max_runup_pct")), 2),
            "max_drawdown_pct": round(_float(pos.get("max_drawdown_pct")), 2),
            "score": round(_float(pos.get("score")), 2),
            "signal_market_label": pos.get("signal_market_label"),
            "signal_market_score": round(_float(pos.get("signal_market_score")), 2),
            "candidate_types": ",".join(pos.get("candidate_types") or []),
            "scaleout_flags": ",".join(pos.get("scaleout_flags") or []),
            "entry_reason": pos.get("entry_reason"),
            "exit_reason": exit_reason,
        }
    )
    del positions[symbol]


def backtest_variant_window(
    variant: ExecutionVariant,
    start_date: str,
    end_date: str,
    metrics: pd.DataFrame,
    db_path: str,
    budget: float = INITIAL_BUDGET,
    top_n: int = BASE_TOP_N,
) -> Dict[str, Any]:
    row_map = _row_by_symbol_date(metrics)
    simulation_dates = [d for d in sorted(metrics["trade_date"].unique()) if start_date <= d <= end_date]
    signal_dates = list(simulation_dates)
    pending_entries: Dict[str, List[Dict[str, Any]]] = {}
    planned_entries = 0
    screen_log: List[Dict[str, Any]] = []

    base_params = Aggressive10cmParams(initial_budget=budget)

    for signal_date in signal_dates:
        screen = screen_candidates(metrics, signal_date, params=base_params, limit=top_n)
        market = screen["market_regime"]
        regime = _regime_of_market(market)
        entry_date = _next_trade_date(simulation_dates, signal_date)
        kept = 0
        filtered = 0
        for candidate in screen["items"]:
            signal_row = row_map.get((str(candidate["symbol"]), signal_date))
            if signal_row is None:
                filtered += 1
                continue
            ok, reason = _signal_entry_filter(candidate, signal_row, market, variant)
            if not ok:
                filtered += 1
                continue
            if entry_date:
                pending_entries.setdefault(entry_date, []).append(
                    {
                        **candidate,
                        "signal_market_regime": market,
                        "signal_filter_reason": reason,
                        "signal_regime_label": regime,
                    }
                )
                planned_entries += 1
                kept += 1
        screen_log.append(
            {
                "signal_date": signal_date,
                "entry_date": entry_date,
                "candidate_count": len(screen["items"]),
                "kept_after_execution_filter": kept,
                "filtered_before_entry": filtered,
                "market_regime": market,
            }
        )

    cash_holder = {"cash": float(budget)}
    positions: Dict[str, Dict[str, Any]] = {}
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    filled_entries = 0
    window_label = f"{start_date}_{end_date}"

    for trade_date in simulation_dates:
        for symbol, pos in list(positions.items()):
            row = row_map.get((symbol, trade_date))
            if row is None:
                continue
            if pos.get("pending_exit_reason"):
                if _is_limit_down_day(row, SelectionV2Params()):
                    continue
                _close_position(
                    positions,
                    trades,
                    symbol,
                    trade_date,
                    _float(row.get("open")),
                    str(pos["pending_exit_reason"]),
                    cash_holder,
                    window_label,
                    variant,
                )

        for symbol, pos in list(positions.items()):
            row = row_map.get((symbol, trade_date))
            if row is None or symbol not in positions:
                continue
            pos["holding_days"] = int(pos.get("holding_days") or 0) + 1
            entry_price = _float(pos["gross_entry_price"])
            high = _float(row.get("high"))
            low = _float(row.get("low"))
            close = _float(row.get("close"))
            pos["peak_price"] = max(_float(pos.get("peak_price"), entry_price), high)
            pos["max_runup_pct"] = max(_float(pos.get("max_runup_pct")), ((high / entry_price) - 1.0) * 100.0 if entry_price else 0.0)
            pos["max_drawdown_pct"] = min(_float(pos.get("max_drawdown_pct")), ((low / entry_price) - 1.0) * 100.0 if entry_price else 0.0)
            pos["cum_super"] = _float(pos.get("cum_super")) + _float(row.get("l2_super_net_amount"))
            pos["cum_super_peak"] = max(_float(pos.get("cum_super_peak")), _float(pos["cum_super"]))

            if low <= entry_price * (1.0 + variant.hard_stop_pct / 100.0):
                if _is_limit_down_day(row, SelectionV2Params()):
                    pos["pending_exit_reason"] = "stop_blocked_limit_down"
                    continue
                stop_price = entry_price * (1.0 + variant.hard_stop_pct / 100.0)
                if _float(row.get("open")) < stop_price:
                    stop_price = _float(row.get("open"))
                _close_position(
                    positions,
                    trades,
                    symbol,
                    trade_date,
                    stop_price,
                    "hard_stop",
                    cash_holder,
                    window_label,
                    variant,
                )
                continue

            for level in variant.take_profit_levels:
                if level.label in pos["tp_done"]:
                    continue
                if high < entry_price * (1.0 + level.trigger_pct / 100.0):
                    continue
                sell_shares = min(_float(pos["initial_shares"]) * level.fraction_of_initial, _float(pos["shares"]))
                if sell_shares <= 0:
                    pos["tp_done"].add(level.label)
                    continue
                proceeds = sell_shares * _apply_sell_costs(entry_price * (1.0 + level.trigger_pct / 100.0), SelectionV2Params())
                cash_holder["cash"] += proceeds
                pos["shares"] = _float(pos["shares"]) - sell_shares
                pos["realized_cash"] = _float(pos.get("realized_cash")) + proceeds
                pos["tp_done"].add(level.label)
                pos["scaleout_flags"].append(level.label)
                if _float(pos["shares"]) <= 1e-8:
                    _close_position(
                        positions,
                        trades,
                        symbol,
                        trade_date,
                        entry_price * (1.0 + level.trigger_pct / 100.0),
                        f"scaleout_{level.label}",
                        cash_holder,
                        window_label,
                        variant,
                    )
                    break
            if symbol not in positions:
                continue

            peak_return = ((_float(pos["peak_price"]) / entry_price) - 1.0) * 100.0 if entry_price else 0.0
            close_from_peak_pct = ((close / _float(pos["peak_price"])) - 1.0) * 100.0 if _float(pos["peak_price"]) else 0.0
            close_return = ((close / entry_price) - 1.0) * 100.0 if entry_price else 0.0
            cum_super_peak = _float(pos.get("cum_super_peak"))
            cum_super = _float(pos.get("cum_super"))
            intent = _compute_intent_profile(row, SelectionV2Params())
            distribution_score = _float(intent.get("distribution_score"))
            l2_main_ratio = _float(row.get("l2_main_net_ratio"))

            if peak_return >= variant.trailing_activate_pct and close_from_peak_pct <= variant.trailing_drawdown_pct:
                pos["pending_exit_reason"] = "trailing_exit_next_open"
            elif variant.cum_super_peak_drawdown_pct is not None and cum_super_peak > 0:
                super_peak_dd = ((cum_super_peak - cum_super) / cum_super_peak) * 100.0
                if super_peak_dd >= variant.cum_super_peak_drawdown_pct and close_return >= 0:
                    pos["pending_exit_reason"] = "cum_super_drawdown_next_open"
            elif distribution_score >= variant.distribution_exit_score and l2_main_ratio <= variant.distribution_l2_main_ratio_max:
                pos["pending_exit_reason"] = "distribution_exit_next_open"
            elif variant.weak_close_after_days is not None and int(pos["holding_days"]) >= variant.weak_close_after_days:
                if variant.weak_close_floor_pct is not None and close_return <= variant.weak_close_floor_pct:
                    pos["pending_exit_reason"] = "weak_close_exit_next_open"
            elif int(pos["holding_days"]) >= variant.max_holding_days:
                pos["pending_exit_reason"] = "max_holding_exit_next_open"

        entries = sorted(pending_entries.get(trade_date, []), key=lambda x: (-_float(x.get("score")), str(x.get("symbol"))))
        opened_today = 0
        for candidate in entries:
            symbol = str(candidate["symbol"])
            if symbol in positions:
                continue
            if len(positions) >= variant.max_positions:
                continue
            if opened_today >= variant.max_new_positions_per_day:
                continue
            signal_row = row_map.get((symbol, str(candidate["signal_date"])))
            entry_row = row_map.get((symbol, trade_date))
            if signal_row is None or entry_row is None:
                continue
            market = candidate["signal_market_regime"]
            regime = _regime_of_market(market)
            exposure_cap = budget * variant.max_total_exposure_pct_by_regime.get(regime, variant.max_total_exposure_pct_by_regime["unknown"])
            current_cost_exposure = sum(_float(pos["invested_cash"]) for pos in positions.values())
            available_exposure = max(0.0, exposure_cap - current_cost_exposure)
            per_position_pct = variant.per_position_pct_by_regime.get(regime, variant.per_position_pct_by_regime["unknown"])
            target_cash = budget * per_position_pct * _score_multiplier(_float(candidate.get("score")), variant)
            target_cash = min(target_cash, available_exposure, cash_holder["cash"])
            if target_cash <= 5_000:
                continue
            ok, gross_entry, meta = _confirm_entry_variant(candidate, signal_row, entry_row, variant, db_path)
            if not ok or gross_entry <= 0:
                continue
            effective_entry = _apply_buy_costs(gross_entry, SelectionV2Params())
            shares = target_cash / effective_entry
            if shares <= 0:
                continue
            cash_holder["cash"] -= target_cash
            positions[symbol] = {
                "symbol": symbol,
                "name": candidate.get("name") or symbol,
                "signal_date": candidate["signal_date"],
                "entry_date": trade_date,
                "gross_entry_price": gross_entry,
                "effective_entry_price": effective_entry,
                "shares": shares,
                "initial_shares": shares,
                "invested_cash": target_cash,
                "realized_cash": 0.0,
                "score": candidate.get("score"),
                "candidate_types": candidate.get("candidate_types", []),
                "holding_days": 0,
                "peak_price": gross_entry,
                "max_runup_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "cum_super": 0.0,
                "cum_super_peak": 0.0,
                "pending_exit_reason": None,
                "scaleout_flags": [],
                "tp_done": set(),
                "entry_reason": meta.get("reason"),
                "signal_market_label": regime,
                "signal_market_score": _float(market.get("score")),
            }
            filled_entries += 1
            opened_today += 1

        equity_curve.append(
            {
                "trade_date": trade_date,
                "cash": round(cash_holder["cash"], 2),
                "equity": round(_compute_equity(cash_holder["cash"], positions, trade_date, row_map), 2),
                "open_positions": len(positions),
            }
        )

    if simulation_dates:
        final_date = simulation_dates[-1]
        for symbol in list(positions.keys()):
            row = row_map.get((symbol, final_date))
            final_close = _float(row.get("close")) if row is not None else _float(positions[symbol]["gross_entry_price"])
            _close_position(
                positions,
                trades,
                symbol,
                final_date,
                final_close,
                "window_end_mark",
                cash_holder,
                window_label,
                variant,
            )
        equity_curve[-1]["cash"] = round(cash_holder["cash"], 2)
        equity_curve[-1]["equity"] = round(cash_holder["cash"], 2)
        equity_curve[-1]["open_positions"] = 0

    summary = _make_summary(trades, equity_curve, budget, filled_entries, planned_entries)
    return {
        "variant": variant.name,
        "variant_label": variant.label,
        "window": window_label,
        "start_date": start_date,
        "end_date": end_date,
        "summary": summary,
        "screen_log": screen_log,
        "equity_curve": equity_curve,
        "trades": trades,
    }


def _variant_rank_frame(results: Sequence[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for item in results:
        summary = item["summary"]
        rows.append(
            {
                "window": item["window"],
                "variant": item["variant"],
                "variant_label": item["variant_label"],
                "total_return_pct": summary["total_return_pct"],
                "max_drawdown_pct": summary["max_drawdown_pct"],
                "trade_count": summary["trade_count"],
                "win_rate_pct": summary["win_rate_pct"],
                "profit_factor": summary["profit_factor"],
                "avg_holding_days": summary["avg_holding_days"],
                "entry_fill_rate_pct": summary["entry_fill_rate_pct"],
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["score"] = (
        df["total_return_pct"] * 1.0
        - df["max_drawdown_pct"].abs() * 0.35
        + df["win_rate_pct"] * 0.02
        + df["profit_factor"].clip(upper=5.0) * 0.5
    )
    return df.sort_values(["window", "score", "total_return_pct"], ascending=[True, False, False]).reset_index(drop=True)


def _pick_best_variant(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    rank_df = _variant_rank_frame(results)
    if rank_df.empty:
        return {}
    agg = (
        rank_df.groupby(["variant", "variant_label"], as_index=False)
        .agg(
            mean_return_pct=("total_return_pct", "mean"),
            min_return_pct=("total_return_pct", "min"),
            mean_drawdown_pct=("max_drawdown_pct", "mean"),
            max_drawdown_pct=("max_drawdown_pct", "max"),
            mean_score=("score", "mean"),
            mean_profit_factor=("profit_factor", "mean"),
        )
        .sort_values(["mean_score", "min_return_pct", "mean_return_pct"], ascending=[False, False, False])
        .reset_index(drop=True)
    )
    return agg.iloc[0].to_dict()


def _render_readme(summary_payload: Dict[str, Any]) -> str:
    best = summary_payload.get("best_variant") or {}
    lines = [
        "# aggressive_10cm execution agent",
        "",
        "只复用现有 aggressive_10cm 候选池，不改候选生成；差异只在执行过滤、仓位和卖出。",
        "",
        "## 规则组合",
        "",
    ]
    for variant in summary_payload["variants"]:
        lines.extend(
            [
                f"### {variant['label']} `{variant['name']}`",
                "",
                f"- 思路：{variant['thesis']}",
                f"- 进场：高开上限 {variant['max_open_gap_up_pct']}%，低开下限 {variant['max_open_gap_down_pct']}%，首15分钟价格阈值 {variant['first_15m_price_floor_pct']}%",
                f"- 仓位：`{variant['per_position_pct_by_regime']}`，总仓位上限 `{variant['max_total_exposure_pct_by_regime']}`",
                f"- 卖出：止损 {variant['hard_stop_pct']}%，跟踪止盈激活 {variant['trailing_activate_pct']}%，回撤阈值 {variant['trailing_drawdown_pct']}%，最长持有 {variant['max_holding_days']} 天",
                "",
            ]
        )

    lines.extend(
        [
            "## 结果",
            "",
            "| 区间 | 规则 | 总收益 | 最大回撤 | 交易数 | 胜率 | PF | 填单率 |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in summary_payload["results"]:
        s = item["summary"]
        lines.append(
            f"| {item['window']} | {item['variant_label']} | {s['total_return_pct']}% | {s['max_drawdown_pct']}% | "
            f"{s['trade_count']} | {s['win_rate_pct']}% | {s['profit_factor']} | {s['entry_fill_rate_pct']}% |"
        )
    if best:
        lines.extend(
            [
                "",
                "## 最优规则",
                "",
                f"- `{best['variant']}` / {best['variant_label']}",
                f"- 平均收益：{round(best['mean_return_pct'], 2)}%",
                f"- 最差区间收益：{round(best['min_return_pct'], 2)}%",
                f"- 平均最大回撤：{round(best['mean_drawdown_pct'], 2)}%",
            ]
        )
    lines.extend(
        [
            "",
            "## 无未来函数",
            "",
            "- 候选池只用 signal_date 收盘及以前可见字段，由现有 `screen_candidates` 生成。",
            "- 买入只在下一交易日，用开盘价和 09:45 前三个 5 分钟桶确认，不用当日收盘后信息回填进场。",
            "- 止损/止盈只使用当日可成交的阈值价；收盘派发、拖尾、超大单走弱只在收盘后生成，下一交易日开盘执行。",
            "- 评估窗口末日仅做 mark-to-market 强平，便于区间比较，不参与下一日收益。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run_research(data_out: Path, doc_out: Path) -> Dict[str, Any]:
    db_path = os.getenv(
        "ATOMIC_MAINBOARD_DB_PATH",
        "/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_compact_current.db",
    )
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"atomic db not found: {db_path}")

    earliest_metrics_start = min(_selection_start(start) for start, _ in WINDOWS)
    latest_end = max(end for _, end in WINDOWS)
    metrics = prepare_metrics(
        earliest_metrics_start,
        latest_end,
        db_path=db_path,
        selection_db_path="/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db",
        fine_heat_db_path="/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily_v2.db",
    )
    if metrics.empty:
        raise RuntimeError("prepare_metrics returned empty result")

    results: List[Dict[str, Any]] = []
    all_trades: List[Dict[str, Any]] = []
    for start_date, end_date in WINDOWS:
        window_metrics = metrics[(metrics["trade_date"] >= earliest_metrics_start) & (metrics["trade_date"] <= end_date)].copy()
        for variant in VARIANTS:
            payload = backtest_variant_window(variant, start_date, end_date, window_metrics, db_path)
            results.append(
                {
                    "window": payload["window"],
                    "variant": payload["variant"],
                    "variant_label": payload["variant_label"],
                    "summary": payload["summary"],
                }
            )
            all_trades.extend(payload["trades"])

    best_variant = _pick_best_variant(results)
    summary_payload = {
        "budget": INITIAL_BUDGET,
        "base_candidate_pool": {
            "source": "backend.app.services.aggressive_10cm_strategy.screen_candidates",
            "top_n": BASE_TOP_N,
            "candidate_logic_changed": False,
        },
        "data_sources": {
            "atomic_db": db_path,
            "selection_db": "/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db",
            "fine_heat_db": "/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily_v2.db",
        },
        "windows": [{"start_date": s, "end_date": e} for s, e in WINDOWS],
        "variants": [asdict(v) for v in VARIANTS],
        "results": results,
        "best_variant": best_variant,
        "no_lookahead_note": "signal_date only for candidate generation; entry uses next trade date open/09:45; close-based exits execute next open.",
    }

    data_out.mkdir(parents=True, exist_ok=True)
    doc_out.mkdir(parents=True, exist_ok=True)
    (data_out / "summary.json").write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(all_trades).sort_values(["window", "variant", "entry_date", "symbol"]).to_csv(data_out / "trades.csv", index=False)
    (doc_out / "README.md").write_text(_render_readme(summary_payload), encoding="utf-8")
    return summary_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-out", default=str(DEFAULT_DATA_OUT))
    parser.add_argument("--doc-out", default=str(DEFAULT_DOC_OUT))
    args = parser.parse_args()
    payload = run_research(Path(args.data_out), Path(args.doc_out))
    print(json.dumps({"best_variant": payload.get("best_variant"), "results": payload.get("results")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
