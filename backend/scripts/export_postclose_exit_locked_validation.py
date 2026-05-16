#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/selection/opportunity_discovery/postclose_exit_v0_2"
OUT = ROOT / "data/selection/opportunity_discovery/postclose_exit_locked_validation_v0_1"


LOCKED: List[Tuple[str, str, str]] = [
    ("aggressive", "top1_top2_conditional", "pc_model_th6_stop12"),
    ("robust", "top1", "pc_model_th6_guard12_stop12"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(SRC / "postclose_exit_strategy_summary.csv")
    trades = pd.read_csv(SRC / "postclose_exit_trades.csv")
    curves = pd.read_csv(SRC / "postclose_exit_equity_curves.csv")

    locked_summary_parts = []
    locked_trade_parts = []
    locked_curve_parts = []
    concentration_rows: List[Dict[str, object]] = []
    monthly_realized_rows: List[Dict[str, object]] = []

    for label, strategy, policy in LOCKED:
        sm = summary[(summary["strategy"].eq(strategy)) & (summary["exit_policy"].eq(policy))].copy()
        sm.insert(0, "locked_label", label)
        locked_summary_parts.append(sm)

        scope = f"continuous:{strategy}:{policy}"
        tr = trades[trades["scope"].eq(scope)].copy()
        tr.insert(0, "locked_label", label)
        locked_trade_parts.append(tr)

        cv = curves[curves["scope"].eq(scope)].copy()
        cv.insert(0, "locked_label", label)
        locked_curve_parts.append(cv)

        if not tr.empty:
            total_pnl = float(tr["pnl_cash"].sum())
            top_pnl = tr.sort_values("pnl_cash", ascending=False).head(5).copy()
            concentration_rows.append(
                {
                    "locked_label": label,
                    "strategy": strategy,
                    "exit_policy": policy,
                    "trades": int(len(tr)),
                    "total_pnl_cash": round(total_pnl, 2),
                    "top1_pnl_cash": round(float(top_pnl["pnl_cash"].head(1).sum()), 2),
                    "top3_pnl_cash": round(float(top_pnl["pnl_cash"].head(3).sum()), 2),
                    "top5_pnl_cash": round(float(top_pnl["pnl_cash"].sum()), 2),
                    "top1_pnl_share": round(float(top_pnl["pnl_cash"].head(1).sum() / total_pnl), 4) if total_pnl else 0.0,
                    "top3_pnl_share": round(float(top_pnl["pnl_cash"].head(3).sum() / total_pnl), 4) if total_pnl else 0.0,
                    "top5_pnl_share": round(float(top_pnl["pnl_cash"].sum() / total_pnl), 4) if total_pnl else 0.0,
                }
            )
            month = (
                tr.assign(exit_month=tr["exit_date"].astype(str).str[:7])
                .groupby("exit_month", as_index=False)
                .agg(
                    trades=("symbol", "count"),
                    pnl_cash=("pnl_cash", "sum"),
                    avg_net_return_pct=("net_return_pct", "mean"),
                    win_rate=("net_return_pct", lambda s: float((s > 0).mean())),
                    sold_fly_after_exit_rate=("sold_fly_after_exit", "mean"),
                    avg_post_exit_missed_pp=("post_exit_missed_pp", "mean"),
                )
            )
            month.insert(0, "locked_label", label)
            month.insert(1, "strategy", strategy)
            month.insert(2, "exit_policy", policy)
            monthly_realized_rows.extend(month.to_dict(orient="records"))

    locked_summary = pd.concat(locked_summary_parts, ignore_index=True, sort=False)
    locked_trades = pd.concat(locked_trade_parts, ignore_index=True, sort=False)
    locked_curves = pd.concat(locked_curve_parts, ignore_index=True, sort=False)
    concentration = pd.DataFrame(concentration_rows)
    monthly_realized = pd.DataFrame(monthly_realized_rows)

    locked_summary.to_csv(OUT / "locked_strategy_summary.csv", index=False)
    locked_trades.to_csv(OUT / "locked_strategy_trades.csv", index=False)
    locked_curves.to_csv(OUT / "locked_strategy_equity_curves.csv", index=False)
    concentration.to_csv(OUT / "locked_strategy_pnl_concentration.csv", index=False)
    monthly_realized.to_csv(OUT / "locked_strategy_monthly_realized.csv", index=False)

    payload = {
        "source": str(SRC),
        "locked": [
            {"label": label, "strategy": strategy, "exit_policy": policy}
            for label, strategy, policy in LOCKED
        ],
        "files": {
            "summary": str(OUT / "locked_strategy_summary.csv"),
            "trades": str(OUT / "locked_strategy_trades.csv"),
            "curves": str(OUT / "locked_strategy_equity_curves.csv"),
            "pnl_concentration": str(OUT / "locked_strategy_pnl_concentration.csv"),
            "monthly_realized": str(OUT / "locked_strategy_monthly_realized.csv"),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(locked_summary[locked_summary["window"].eq("continuous")].to_string(index=False))
    print()
    print(concentration.to_string(index=False))


if __name__ == "__main__":
    main()
