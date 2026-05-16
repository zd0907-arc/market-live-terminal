from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.research_aggressive_10cm_hot_theme_agent import (  # noqa: E402
    ATOMIC_DB,
    HEAT_DB,
    INITIAL_CAPITAL,
    SELL_COST_RATE,
    BUY_COST_RATE,
    THEME_RESONANCE,
    build_daily_symbol_summary,
    build_maps,
    load_atomic_panel,
    load_hot_theme_panel,
    max_drawdown_from_curve,
    next_trade_date,
    safe_float,
    theme_resonance_candidates,
    trade_dates_between,
)


OUT_DIR = ROOT / "data/selection/evolution_lab/two_stage_joint_objective"
REPORT_PATH = ROOT / "data/selection/evolution_lab/two_stage_joint_objective_report.json"


@dataclass(frozen=True)
class HoldingPolicy:
    name: str
    max_positions: int = 3
    per_position_pct: float = 0.30
    max_gap_up_pct: float = 0.055
    max_gap_down_pct: float = -0.035
    hard_stop_pct: float = -0.07
    trailing_activate_pct: float = 0.18
    trailing_drawdown_pct: float = -0.10
    max_holding_days: int = 18
    theme_decay_rank: int = 28
    min_hold_theme_hits: int = 2
    fade_exit_return_floor_pct: float = -2.0
    selector_top_n_per_day: int = 3
    selector_max_price_position_20d: float = 0.85


def _entry_ok(row: Dict[str, Any], policy: HoldingPolicy) -> Tuple[bool, str]:
    open_price = safe_float(row.get("open"))
    prev_close = safe_float(row.get("prev_close"))
    up_limit_price = safe_float(row.get("up_limit_price"))
    if open_price <= 0 or prev_close <= 0:
        return False, "bad_price"
    gap = open_price / prev_close - 1.0
    if gap > policy.max_gap_up_pct:
        return False, "gap_up_too_high"
    if gap < policy.max_gap_down_pct:
        return False, "gap_down_too_low"
    if up_limit_price > 0 and open_price >= up_limit_price * 0.997:
        return False, "open_near_limit_up"
    return True, "ok"


def _summary(
    trades: Sequence[Dict[str, Any]],
    equity_curve: Sequence[Dict[str, Any]],
    initial_budget: float = INITIAL_CAPITAL,
) -> Dict[str, Any]:
    final_equity = safe_float(equity_curve[-1]["equity"]) if equity_curve else initial_budget
    returns = [safe_float(item.get("net_return_pct")) for item in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    pnl = [safe_float(item.get("pnl_cash")) for item in trades]
    gross_profit = sum(v for v in pnl if v > 0)
    gross_loss = sum(v for v in pnl if v < 0)
    profit_factor = 999.0 if gross_loss == 0 and gross_profit > 0 else (gross_profit / abs(gross_loss) if gross_loss < 0 else 0.0)
    return {
        "initial_budget": round(initial_budget, 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / initial_budget - 1.0) * 100.0, 2),
        "max_drawdown_pct": max_drawdown_from_curve([safe_float(item["equity"]) for item in equity_curve]),
        "trade_count": int(len(trades)),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
        "avg_net_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
        "median_net_return_pct": round(float(pd.Series(returns).median()), 2) if returns else 0.0,
        "max_net_return_pct": round(max(returns), 2) if returns else 0.0,
        "min_net_return_pct": round(min(returns), 2) if returns else 0.0,
        "avg_holding_days": round(sum(int(item.get("holding_days") or 0) for item in trades) / len(trades), 2) if trades else 0.0,
        "profit_factor": round(float(profit_factor), 3),
        "gross_profit_cash": round(gross_profit, 2),
        "gross_loss_cash": round(gross_loss, 2),
    }


def simulate_policy(
    policy: HoldingPolicy,
    *,
    signal_start: str,
    signal_end: str,
    replay_end: str,
    trade_dates: Sequence[str],
    atomic_map: Dict[Tuple[str, str], Dict[str, Any]],
    summary_map: Dict[Tuple[str, str], Dict[str, Any]],
    theme_panel: pd.DataFrame,
    summary_panel: pd.DataFrame,
) -> Dict[str, Any]:
    selector_cfg = replace(
        THEME_RESONANCE,
        top_n_per_day=int(policy.selector_top_n_per_day),
        max_positions=int(policy.max_positions),
        per_position_pct=float(policy.per_position_pct),
        max_gap_up_pct=float(policy.max_gap_up_pct),
        max_gap_down_pct=float(policy.max_gap_down_pct),
        hard_stop_pct=float(policy.hard_stop_pct),
        trailing_activate_pct=float(policy.trailing_activate_pct),
        trailing_drawdown_pct=float(policy.trailing_drawdown_pct),
        max_holding_days=int(policy.max_holding_days),
        theme_decay_rank=int(policy.theme_decay_rank),
        max_price_position_20d=float(policy.selector_max_price_position_20d),
    )
    signal_dates = [d for d in trade_dates if signal_start <= d <= signal_end]
    simulation_dates = [d for d in trade_dates if signal_start <= d <= replay_end]
    pending_entries: Dict[str, List[Dict[str, Any]]] = {}
    daily_signals: List[Dict[str, Any]] = []

    for signal_date in signal_dates:
        picks = theme_resonance_candidates(signal_date, selector_cfg, summary_panel, atomic_map)
        entry_date = next_trade_date(simulation_dates, signal_date)
        daily_signals.append(
            {
                "signal_date": signal_date,
                "entry_date": entry_date,
                "candidate_count": len(picks),
                "symbols": [str(item["symbol"]) for item in picks],
            }
        )
        if not entry_date:
            continue
        for item in picks:
            pending_entries.setdefault(entry_date, []).append(item)

    cash = INITIAL_CAPITAL
    positions: Dict[str, Dict[str, Any]] = {}
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []

    def close_position(pos: Dict[str, Any], trade_date: str, gross_exit_price: float, reason: str) -> None:
        nonlocal cash
        shares = safe_float(pos["shares"])
        proceeds = shares * gross_exit_price * (1.0 - SELL_COST_RATE)
        cash += proceeds
        invested_cash = safe_float(pos["invested_cash"])
        pnl_cash = proceeds - invested_cash
        trades.append(
            {
                "symbol": pos["symbol"],
                "name": pos["name"],
                "signal_date": pos["signal_date"],
                "entry_bucket": f"{pos['entry_date']} 09:30:00",
                "entry_date": pos["entry_date"],
                "exit_bucket": f"{trade_date} 09:30:00",
                "exit_date": trade_date,
                "gross_entry_price": round(safe_float(pos["entry_price"]), 4),
                "gross_exit_price": round(gross_exit_price, 4),
                "sold_fraction": 1.0,
                "cost_cash": round(invested_cash, 2),
                "realized_cash": round(proceeds, 2),
                "pnl_cash": round(pnl_cash, 2),
                "net_return_pct": round((proceeds / invested_cash - 1.0) * 100.0, 4) if invested_cash else 0.0,
                "holding_days": int(pos["holding_days"]),
                "max_runup_pct": round(safe_float(pos["max_runup_pct"]), 2),
                "max_drawdown_pct": round(safe_float(pos["max_drawdown_pct"]), 2),
                "exit_reason": reason,
                "entry_reason": pos["signal_reason"],
                "theme_names": pos["theme_names"],
                "theme_hits": int(pos["theme_hits"]),
                "best_rank": int(pos["best_rank"]),
                "selection_score": round(safe_float(pos["signal_score"]), 2),
            }
        )
        positions.pop(pos["symbol"], None)

    for trade_date in simulation_dates:
        for symbol, pos in list(positions.items()):
            if pos.get("pending_exit_reason"):
                row = atomic_map.get((symbol, trade_date))
                exit_price = safe_float(row.get("open")) if row else safe_float(pos["entry_price"])
                close_position(pos, trade_date, exit_price, str(pos["pending_exit_reason"]))

        for symbol, pos in list(positions.items()):
            row = atomic_map.get((symbol, trade_date))
            if not row:
                continue
            entry_price = safe_float(pos["entry_price"])
            high = safe_float(row.get("high"))
            low = safe_float(row.get("low"))
            close_price = safe_float(row.get("close"))
            open_price = safe_float(row.get("open"))
            pos["holding_days"] = int(pos.get("holding_days") or 0) + 1
            pos["peak_price"] = max(safe_float(pos.get("peak_price"), entry_price), high)
            pos["max_runup_pct"] = max(safe_float(pos.get("max_runup_pct")), (high / entry_price - 1.0) * 100.0 if entry_price else 0.0)
            pos["max_drawdown_pct"] = min(safe_float(pos.get("max_drawdown_pct")), (low / entry_price - 1.0) * 100.0 if entry_price else 0.0)

            stop_price = entry_price * (1.0 + policy.hard_stop_pct)
            if low <= stop_price:
                close_position(pos, trade_date, min(open_price, stop_price) if open_price < stop_price else stop_price, "hard_stop")
                continue

            peak_return = safe_float(pos["peak_price"]) / entry_price - 1.0 if entry_price else 0.0
            pullback = close_price / safe_float(pos["peak_price"]) - 1.0 if safe_float(pos["peak_price"]) else 0.0
            if peak_return >= policy.trailing_activate_pct and pullback <= policy.trailing_drawdown_pct:
                pos["pending_exit_reason"] = "trailing_exit_next_open"

            day_summary = summary_map.get((symbol, trade_date), {})
            theme_hits = int(safe_float(day_summary.get("theme_hits"), 0.0))
            best_rank = safe_float(day_summary.get("best_rank"), 999.0)
            close_return_pct = (close_price / entry_price - 1.0) * 100.0 if entry_price else 0.0
            if (
                theme_hits < policy.min_hold_theme_hits
                and best_rank > policy.theme_decay_rank
                and close_return_pct <= policy.fade_exit_return_floor_pct
            ):
                pos["pending_exit_reason"] = "resonance_fade_next_open"
            if int(pos["holding_days"]) >= int(policy.max_holding_days):
                pos["pending_exit_reason"] = "time_exit_next_open"

        entries = sorted(
            pending_entries.get(trade_date, []),
            key=lambda item: (-safe_float(item.get("score")), str(item.get("symbol"))),
        )
        for item in entries:
            symbol = str(item["symbol"])
            if symbol in positions:
                continue
            if len(positions) >= int(policy.max_positions):
                break
            row = atomic_map.get((symbol, trade_date))
            if not row:
                continue
            ok, _ = _entry_ok(row, policy)
            if not ok:
                continue
            position_cash = min(cash, INITIAL_CAPITAL * float(policy.per_position_pct))
            if position_cash < 50_000:
                continue
            gross_open = safe_float(row["open"])
            entry_price = gross_open * (1.0 + BUY_COST_RATE)
            shares = position_cash / entry_price
            if shares <= 0:
                continue
            cash -= position_cash
            positions[symbol] = {
                "symbol": symbol,
                "name": str(item.get("name") or symbol),
                "signal_date": str(item["trade_date"]),
                "entry_date": trade_date,
                "entry_price": entry_price,
                "shares": shares,
                "invested_cash": position_cash,
                "signal_score": safe_float(item.get("score")),
                "signal_reason": str(item.get("signal_reason") or ""),
                "theme_names": str(item.get("theme_names") or ""),
                "theme_hits": int(safe_float(item.get("theme_hits"), 1.0)),
                "best_rank": int(safe_float(item.get("best_rank"), 999.0)),
                "holding_days": 0,
                "peak_price": entry_price,
                "max_runup_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "pending_exit_reason": None,
            }

        equity = cash
        for symbol, pos in positions.items():
            row = atomic_map.get((symbol, trade_date))
            mark_price = safe_float(row.get("close")) if row else safe_float(pos["entry_price"])
            equity += safe_float(pos["shares"]) * mark_price
        equity_curve.append(
            {
                "bucket_start": f"{trade_date} 15:00:00",
                "trade_date": trade_date,
                "cash": round(cash, 2),
                "equity": round(equity, 2),
                "open_positions": len(positions),
            }
        )

    if simulation_dates:
        last_date = simulation_dates[-1]
        for symbol, pos in list(positions.items()):
            row = atomic_map.get((symbol, last_date))
            close_position(pos, last_date, safe_float(row.get("close")) if row else safe_float(pos["entry_price"]), "window_end_mark")
        if equity_curve:
            equity_curve[-1]["cash"] = round(cash, 2)
            equity_curve[-1]["equity"] = round(cash, 2)
            equity_curve[-1]["open_positions"] = 0

    summary = _summary(trades, equity_curve)
    score = (
        safe_float(summary["total_return_pct"])
        - abs(safe_float(summary["max_drawdown_pct"])) * 0.18
        + min(safe_float(summary["profit_factor"]), 5.0) * 0.2
    )
    return {
        "policy": asdict(policy),
        "summary": summary,
        "score": round(score, 6),
        "daily_signals": daily_signals,
        "trades": sorted(trades, key=lambda item: (item["entry_date"], item["symbol"])),
        "equity_curve": equity_curve,
    }


def _candidate_policies(seed: int, limit: int) -> List[HoldingPolicy]:
    rng = random.Random(seed)
    policies = [
        HoldingPolicy(name="baseline_longer_hold"),
        HoldingPolicy(name="trend_runner", trailing_activate_pct=0.22, trailing_drawdown_pct=-0.12, max_holding_days=24, fade_exit_return_floor_pct=-4.0),
        HoldingPolicy(name="loose_fade", theme_decay_rank=35, fade_exit_return_floor_pct=-5.0, max_holding_days=20),
        HoldingPolicy(name="tight_stop_runner", hard_stop_pct=-0.055, trailing_activate_pct=0.18, trailing_drawdown_pct=-0.09, max_holding_days=18),
    ]
    while len(policies) < limit:
        policies.append(
            HoldingPolicy(
                name=f"rand_{len(policies):03d}",
                max_positions=rng.choice([2, 3, 4]),
                per_position_pct=rng.choice([0.22, 0.26, 0.30, 0.34]),
                max_gap_up_pct=rng.choice([0.045, 0.055, 0.065, 0.075]),
                max_gap_down_pct=rng.choice([-0.05, -0.04, -0.035, -0.025]),
                hard_stop_pct=rng.choice([-0.085, -0.075, -0.065, -0.055]),
                trailing_activate_pct=rng.choice([0.14, 0.18, 0.22, 0.28]),
                trailing_drawdown_pct=rng.choice([-0.14, -0.11, -0.09, -0.07]),
                max_holding_days=rng.choice([7, 10, 14, 18, 24, 30]),
                theme_decay_rank=rng.choice([22, 25, 28, 35, 50]),
                min_hold_theme_hits=rng.choice([1, 2, 3]),
                fade_exit_return_floor_pct=rng.choice([-6.0, -4.0, -2.0, 0.0, 1.0]),
                selector_top_n_per_day=rng.choice([2, 3, 4]),
                selector_max_price_position_20d=rng.choice([0.82, 0.85, 0.90, 0.96]),
            )
        )
    return policies[:limit]


def run_search(
    *,
    signal_start: str,
    signal_end: str,
    replay_end: str,
    target_return_pct: float,
    max_trials: int,
    seed: int,
    stop_on_target: bool = False,
) -> Dict[str, Any]:
    trade_dates = trade_dates_between(signal_start, replay_end)
    atomic_panel = load_atomic_panel(signal_start, replay_end)
    theme_panel = load_hot_theme_panel(signal_start, replay_end, rank_limit=20)
    summary_panel = build_daily_symbol_summary(theme_panel)
    atomic_map, summary_map, _ = build_maps(atomic_panel, theme_panel, summary_panel)
    policies = _candidate_policies(seed, max_trials)
    leaderboard: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None
    target_met = False
    for idx, policy in enumerate(policies, start=1):
        result = simulate_policy(
            policy,
            signal_start=signal_start,
            signal_end=signal_end,
            replay_end=replay_end,
            trade_dates=trade_dates,
            atomic_map=atomic_map,
            summary_map=summary_map,
            theme_panel=theme_panel,
            summary_panel=summary_panel,
        )
        row = {
            "trial": idx,
            "policy_name": policy.name,
            "score": result["score"],
            **result["summary"],
            "policy": asdict(policy),
        }
        leaderboard.append(row)
        if best is None or safe_float(result["score"]) > safe_float(best["score"]):
            best = result
        if safe_float(result["summary"]["total_return_pct"]) >= target_return_pct:
            target_met = True
            if stop_on_target:
                best = result
                break
    leaderboard = sorted(leaderboard, key=lambda item: (safe_float(item["score"]), safe_float(item["total_return_pct"])), reverse=True)
    if best is None:
        raise RuntimeError("no policy evaluated")
    payload = {
        "lab_version": "two_stage_joint_objective_v0_1",
        "mode": "fixed_selector_holding_policy_search",
        "range": {"start_date": signal_start, "end_date": signal_end, "replay_end_date": replay_end},
        "target_return_pct": target_return_pct,
        "target_met": target_met,
        "evaluated_trials": int(len(leaderboard)),
        "requested_trials": int(max_trials),
        "stop_on_target": bool(stop_on_target),
        "data": {
            "atomic_db_path": str(ATOMIC_DB),
            "heat_db_path": str(HEAT_DB),
            "trade_dates": trade_dates,
            "symbols": int(len({trade["symbol"] for trade in best["trades"]})),
            "rows": int(len(best["trades"])),
        },
        "selector": {
            "name": THEME_RESONANCE.name,
            "label": THEME_RESONANCE.label,
            "description": THEME_RESONANCE.description,
            "fixed": True,
        },
        "joint_objective": "maximize final portfolio equity over the whole window; drawdown and profit factor only adjust ranking",
        "best": best,
        "leaderboard": leaderboard,
    }
    return payload


def write_outputs(payload: Dict[str, Any]) -> Dict[str, str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    leaderboard_path = OUT_DIR / "leaderboard.csv"
    pd.DataFrame(payload["leaderboard"]).drop(columns=["policy"], errors="ignore").to_csv(leaderboard_path, index=False)
    trades_path = OUT_DIR / "best_trades.csv"
    pd.DataFrame(payload["best"]["trades"]).to_csv(trades_path, index=False)
    report = {
        "lab_version": payload["lab_version"],
        "mode": payload["mode"],
        "range": payload["range"],
        "data": payload["data"],
        "training": {
            "target_return_pct": payload["target_return_pct"],
            "target_met": payload["target_met"],
            "evaluated_trials": payload["evaluated_trials"],
            "requested_trials": payload["requested_trials"],
            "stop_on_target": payload["stop_on_target"],
            "assessment": "full_candidate_search" if not payload["stop_on_target"] else "smoke_target_run",
        },
        "summary": {
            **payload["best"]["summary"],
            "open_positions": 0,
            "cash": payload["best"]["summary"]["final_equity"],
        },
        "policy_note": "Fixed theme_resonance selector plus holding-policy search. The ranking objective is full-window final equity, not stock-pick hit rate or single-trade return. The 5% target is a pass/fail marker, not the optimization ceiling.",
        "feature_names": ["theme_hits", "best_rank", "selection_score", "current_return", "peak_drawdown", "holding_days"],
        "selector": payload["selector"],
        "holding_policy": payload["best"]["policy"],
        "trades": payload["best"]["trades"],
        "actions": [],
        "equity_curve": payload["best"]["equity_curve"],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary_json": str(summary_path), "leaderboard_csv": str(leaderboard_path), "trades_csv": str(trades_path), "report_json": str(REPORT_PATH)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal-start", default="2026-03-15")
    parser.add_argument("--signal-end", default="2026-04-15")
    parser.add_argument("--replay-end", default="2026-04-15")
    parser.add_argument("--target-return-pct", type=float, default=5.0)
    parser.add_argument("--max-trials", type=int, default=240)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--stop-on-target", action="store_true", help="Stop early once target return is reached. Default is to complete all trials.")
    args = parser.parse_args()
    payload = run_search(
        signal_start=args.signal_start,
        signal_end=args.signal_end,
        replay_end=args.replay_end,
        target_return_pct=float(args.target_return_pct),
        max_trials=int(args.max_trials),
        seed=int(args.seed),
        stop_on_target=bool(args.stop_on_target),
    )
    written = write_outputs(payload)
    print(json.dumps({"target_met": payload["target_met"], "best_summary": payload["best"]["summary"], "best_policy": payload["best"]["policy"], "written": written}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
