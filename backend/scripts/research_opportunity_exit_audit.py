#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import research_opportunity_discovery_model as base


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WALK_FORWARD_DIR = ROOT / "data/selection/opportunity_discovery/walk_forward_old_v0_1"
OUT_DIR = ROOT / "data/selection/opportunity_discovery/exit_audit_v0_1"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        if np.isnan(x) or np.isinf(x):
            return default
        return x
    except Exception:
        return default


def _net_return_from_exit(gross_exit: float, net_entry: float, config: base.OpportunityConfig) -> float:
    if gross_exit <= 0 or net_entry <= 0:
        return 0.0
    net_exit = base._apply_sell_cost(gross_exit, config)
    return (net_exit / net_entry - 1.0) * 100.0


def _best_row(rows: pd.DataFrame) -> Dict[str, Any]:
    if rows.empty:
        return {}
    return rows.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).iloc[0].to_dict()


def _load_month_specs(walk_forward_dir: Path) -> List[Dict[str, Any]]:
    summary_path = walk_forward_dir / "walk_forward_summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)
    summary = pd.read_csv(summary_path)
    specs: List[Dict[str, Any]] = []
    for _, row in summary.iterrows():
        window = str(row["window"])
        specs.append(
            {
                "window": window,
                "dir": walk_forward_dir / window,
                "best_mode": str(row["best_mode"]),
                "best_policy": str(row["best_policy"]),
            }
        )
    return specs


def _audit_trade(row: pd.Series, future: pd.DataFrame, config: base.OpportunityConfig) -> Dict[str, Any]:
    symbol = str(row["symbol"])
    signal_date = str(row["trade_date"])
    entry_date = str(row["entry_date"])
    exit_date = str(row["exit_date"])
    gross_entry = _to_float(row.get("gross_entry_price"))
    net_entry = _to_float(row.get("net_entry_price"))
    actual_net_return = _to_float(row.get("net_return_pct"))
    actual_gross_return = _to_float(row.get("gross_return_pct"))
    position_cash = _to_float(row.get("position_cash"))

    path = future.sort_values("trade_date").copy().reset_index(drop=True)
    path["trade_date"] = path["trade_date"].astype(str)
    path["holding_day"] = np.arange(1, len(path) + 1)

    full_high_idx = int(pd.to_numeric(path["high"], errors="coerce").idxmax())
    full_high = _to_float(path.loc[full_high_idx, "high"])
    full_high_date = str(path.loc[full_high_idx, "trade_date"])
    full_mfe_net = _net_return_from_exit(full_high, net_entry, config)

    close22 = _to_float(path.iloc[-1].get("atomic_close", path.iloc[-1].get("close", 0.0)))
    close22_date = str(path.iloc[-1]["trade_date"])
    close22_net_return = _net_return_from_exit(close22, net_entry, config)

    remaining = path[path["trade_date"] > exit_date].copy()
    if remaining.empty:
        best_after_exit_high = 0.0
        best_after_exit_date = ""
        best_after_exit_net = actual_net_return
    else:
        best_after_idx = int(pd.to_numeric(remaining["high"], errors="coerce").idxmax())
        best_after_exit_high = _to_float(path.loc[best_after_idx, "high"])
        best_after_exit_date = str(path.loc[best_after_idx, "trade_date"])
        best_after_exit_net = _net_return_from_exit(best_after_exit_high, net_entry, config)

    post_exit_missed_pp = max(0.0, best_after_exit_net - actual_net_return)
    full_mfe_gap_pp = max(0.0, full_mfe_net - actual_net_return)
    hold22_delta_pp = close22_net_return - actual_net_return

    return {
        "window": row.get("window", ""),
        "mode": row.get("mode", ""),
        "policy": row.get("policy", ""),
        "symbol": symbol,
        "signal_date": signal_date,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "exit_reason": row.get("exit_reason", ""),
        "holding_days": int(_to_float(row.get("holding_days"))),
        "gross_entry_price": round(gross_entry, 4),
        "gross_exit_price": round(_to_float(row.get("gross_exit_price")), 4),
        "actual_net_return_pct": round(actual_net_return, 4),
        "actual_gross_return_pct": round(actual_gross_return, 4),
        "full_mfe_net_return_pct": round(full_mfe_net, 4),
        "full_mfe_date": full_high_date,
        "full_mfe_gap_pp": round(full_mfe_gap_pp, 4),
        "best_after_exit_net_return_pct": round(best_after_exit_net, 4),
        "best_after_exit_date": best_after_exit_date,
        "post_exit_missed_pp": round(post_exit_missed_pp, 4),
        "close22_net_return_pct": round(close22_net_return, 4),
        "close22_date": close22_date,
        "hold22_delta_pp": round(hold22_delta_pp, 4),
        "sold_fly_after_exit": int(post_exit_missed_pp >= 3.0),
        "severe_sold_fly_after_exit": int(post_exit_missed_pp >= 10.0),
        "hold22_better": int(hold22_delta_pp >= 3.0),
        "position_cash": round(position_cash, 2),
        "missed_cash_upper_bound": round(position_cash * post_exit_missed_pp / 100.0, 2),
        "full_mfe_gap_cash_upper_bound": round(position_cash * full_mfe_gap_pp / 100.0, 2),
    }


def _summarize(group: pd.DataFrame, *, scope: str, window: str = "", mode: str = "", policy: str = "") -> Dict[str, Any]:
    if group.empty:
        return {"scope": scope, "window": window, "mode": mode, "policy": policy, "trades": 0}
    actual = pd.to_numeric(group["actual_net_return_pct"], errors="coerce").fillna(0.0)
    post_gap = pd.to_numeric(group["post_exit_missed_pp"], errors="coerce").fillna(0.0)
    full_gap = pd.to_numeric(group["full_mfe_gap_pp"], errors="coerce").fillna(0.0)
    hold22_delta = pd.to_numeric(group["hold22_delta_pp"], errors="coerce").fillna(0.0)
    missed_cash = pd.to_numeric(group["missed_cash_upper_bound"], errors="coerce").fillna(0.0)
    full_gap_cash = pd.to_numeric(group["full_mfe_gap_cash_upper_bound"], errors="coerce").fillna(0.0)
    return {
        "scope": scope,
        "window": window,
        "mode": mode,
        "policy": policy,
        "trades": int(len(group)),
        "actual_avg_net_return_pct": round(float(actual.mean()), 4),
        "actual_median_net_return_pct": round(float(actual.median()), 4),
        "sold_fly_after_exit_rate": round(float(group["sold_fly_after_exit"].mean()), 4),
        "severe_sold_fly_after_exit_rate": round(float(group["severe_sold_fly_after_exit"].mean()), 4),
        "avg_post_exit_missed_pp": round(float(post_gap.mean()), 4),
        "median_post_exit_missed_pp": round(float(post_gap.median()), 4),
        "total_post_exit_missed_cash_upper_bound": round(float(missed_cash.sum()), 2),
        "missed_cash_vs_1m_pct": round(float(missed_cash.sum() / 1_000_000.0 * 100.0), 4),
        "avg_full_mfe_gap_pp": round(float(full_gap.mean()), 4),
        "total_full_mfe_gap_cash_upper_bound": round(float(full_gap_cash.sum()), 2),
        "hold22_better_rate": round(float(group["hold22_better"].mean()), 4),
        "avg_hold22_delta_pp": round(float(hold22_delta.mean()), 4),
        "exit_reason_counts": json.dumps(group["exit_reason"].value_counts().to_dict(), ensure_ascii=False),
    }


def run_command(args: argparse.Namespace) -> None:
    walk_forward_dir = Path(args.walk_forward_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = base.OpportunityConfig(start_date=args.start_date, end_date=args.end_date, horizon_days=int(args.horizon_days))

    atomic = base.add_atomic_features(base.load_atomic_daily(config.start_date, config.end_date, Path(args.atomic_db)))
    specs = _load_month_specs(walk_forward_dir)

    rows: List[Dict[str, Any]] = []
    for spec in specs:
        trades_path = spec["dir"] / "holding_model_portfolio_trades.csv"
        if not trades_path.exists():
            continue
        trades = pd.read_csv(trades_path)
        if trades.empty:
            continue
        trades["window"] = spec["window"]
        keys = [(str(r["symbol"]), str(r["trade_date"])) for _, r in trades.iterrows()]
        path_map = base._future_path_map(atomic, config, keys=keys)
        for _, row in trades.iterrows():
            future = path_map.get((str(row["symbol"]), str(row["trade_date"])))
            if future is None or future.empty:
                continue
            rows.append(_audit_trade(row, future, config))

    audit = pd.DataFrame(rows)
    if audit.empty:
        raise RuntimeError("No trades were audited")
    audit.to_csv(out_dir / "exit_audit_trades_all_policies.csv", index=False)

    best_rows = []
    for spec in specs:
        month = audit[
            audit["window"].eq(spec["window"])
            & audit["mode"].eq(spec["best_mode"])
            & audit["policy"].eq(spec["best_policy"])
        ].copy()
        best_rows.append(month)
    best_audit = pd.concat(best_rows, ignore_index=True) if best_rows else pd.DataFrame()
    best_audit.to_csv(out_dir / "exit_audit_trades_monthly_best.csv", index=False)

    summary_rows: List[Dict[str, Any]] = []
    for window, group in best_audit.groupby("window", sort=True):
        mode = str(group["mode"].iloc[0])
        policy = str(group["policy"].iloc[0])
        summary_rows.append(_summarize(group, scope="monthly_best", window=str(window), mode=mode, policy=policy))
    summary_rows.append(_summarize(best_audit, scope="monthly_best_all", window="ALL"))

    for (window, mode, policy), group in audit.groupby(["window", "mode", "policy"], sort=True):
        summary_rows.append(_summarize(group, scope="all_policy", window=str(window), mode=str(mode), policy=str(policy)))
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out_dir / "exit_audit_summary.csv", index=False)

    payload = {
        "model_version": "exit_audit_v0_1",
        "source": str(walk_forward_dir),
        "notes": [
            "post_exit_missed_pp uses the highest daily high strictly after the actual exit date within the original 22-trading-day path.",
            "full_mfe_gap_pp is an upper bound versus the full 22-day maximum high and may include prices before the actual exit.",
            "cash upper bounds assume the original position size and do not model whether the later high was executable intraday.",
        ],
        "files": {
            "summary": str(out_dir / "exit_audit_summary.csv"),
            "monthly_best_trades": str(out_dir / "exit_audit_trades_monthly_best.csv"),
            "all_policy_trades": str(out_dir / "exit_audit_trades_all_policies.csv"),
        },
    }
    base._json_dump(out_dir / "summary.json", payload)
    print(summary[summary["scope"].isin(["monthly_best", "monthly_best_all"])].to_string(index=False))


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Audit exit timing opportunity for opportunity discovery trades")
    parser.add_argument("--atomic-db", default=str(base.DEFAULT_ATOMIC_DB))
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Audit walk-forward exit timing")
    run.add_argument("--start-date", default="2025-01-02")
    run.add_argument("--end-date", default="2026-05-14")
    run.add_argument("--horizon-days", type=int, default=22)
    run.add_argument("--walk-forward-dir", default=str(DEFAULT_WALK_FORWARD_DIR))
    run.add_argument("--out", default=str(OUT_DIR))
    run.set_defaults(func=run_command)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
