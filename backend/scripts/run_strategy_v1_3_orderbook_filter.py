from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.run_strategy_v1_2_exit_grid import (
    V12ExitParams,
    build_v1_candidates,
    simulate_trade_v1_2,
)


def safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b and abs(float(b)) > 1e-9 else 0.0


def launch_cancel_buy_vs_hist(g: pd.DataFrame, launch_start: str, launch_end: str, lookback: int = 20) -> Dict[str, Any]:
    """启动期撤买单/新增买单相对历史倍数。

    业务解释：
    - 不是看撤买单绝对值高不高；
    - 而是看启动 3 日内 “撤买单/新增买单” 是否相对该股过去盘口行为突然放大。
    - 放大过多时，更像启动时撤梯子诱多。
    """
    hist = g[g.trade_date < launch_start].tail(lookback).copy()
    hist = hist[hist.order_event_count > 0].copy()
    launch = g[(g.trade_date >= launch_start) & (g.trade_date <= launch_end)].copy()
    launch = launch[launch.order_event_count > 0].copy()
    if hist.empty or launch.empty:
        return {
            "order_filter_available": False,
            "launch_hist_order_days": int(len(hist)),
            "launch_order_days": int(len(launch)),
            "launch_cancel_buy_to_add_buy": 0.0,
            "launch_hist_cancel_buy_to_add_buy_avg": 0.0,
            "launch_cancel_buy_to_add_buy_vs_hist": 0.0,
            "orderbook_filter_reason": "insufficient_order_history",
        }

    hist_daily = hist.cancel_buy_amount / hist.add_buy_amount.replace(0, pd.NA)
    hist_avg = float(hist_daily.dropna().mean()) if hist_daily.dropna().size else 0.0
    launch_ratio = safe_div(float(launch.cancel_buy_amount.sum()), float(launch.add_buy_amount.sum()))
    vs_hist = safe_div(launch_ratio, hist_avg)
    return {
        "order_filter_available": True,
        "launch_hist_order_days": int(len(hist)),
        "launch_order_days": int(len(launch)),
        "launch_cancel_buy_to_add_buy": round(launch_ratio, 5),
        "launch_hist_cancel_buy_to_add_buy_avg": round(hist_avg, 5),
        "launch_cancel_buy_to_add_buy_vs_hist": round(vs_hist, 4),
        "orderbook_filter_reason": "launch_cancel_buy_to_add_buy_vs_hist_gt_2" if vs_hist > 2 else "",
    }


def run_v1_3(start: str, end: str, replay_end: str, top_n: int, out_dir: Path) -> Dict[str, Any]:
    raw = load_atomic_daily_window("2026-01-01", replay_end)
    metrics = compute_v2_metrics(raw)
    # v1 候选逻辑依赖 MA 字段；复用 v1.2 里的候选构造。
    from backend.scripts.run_strategy_v1_trend_reversal import add_ma

    metrics = add_ma(metrics)
    candidates, by_symbol = build_v1_candidates(metrics, start, end, top_n)

    exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    from backend.app.services.selection_strategy_v2 import SelectionV2Params

    trade_cost_params = SelectionV2Params()
    passed_candidates: List[Dict[str, Any]] = []
    filtered_candidates: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []

    for rec in candidates:
        if not rec.get("launch_start_date") or not rec.get("launch_end_date"):
            passed_candidates.append(rec)
            continue

        g = by_symbol[str(rec["symbol"])]
        ob = launch_cancel_buy_vs_hist(g, str(rec["launch_start_date"]), str(rec["launch_end_date"]))
        enriched = {**rec, **ob}

        if ob.get("order_filter_available") and float(ob.get("launch_cancel_buy_to_add_buy_vs_hist", 0.0)) > 2.0:
            filtered_candidates.append(enriched)
            continue

        passed_candidates.append(enriched)
        pull_date = enriched.get("pullback_confirm_date")
        if not pull_date:
            continue
        trade = simulate_trade_v1_2(g, str(pull_date), exit_params, trade_cost_params)
        if trade and not trade.get("skipped"):
            trades.append({**enriched, **trade})

    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(candidates).to_csv(out_dir / "raw_candidates.csv", index=False)
    pd.DataFrame(passed_candidates).to_csv(out_dir / "passed_candidates.csv", index=False)
    pd.DataFrame(filtered_candidates).to_csv(out_dir / "filtered_candidates.csv", index=False)
    pd.DataFrame(trades).to_csv(out_dir / "v1_3_trades.csv", index=False)

    s = summarize(trades)
    summary = {
        "range": {"start": start, "end": end, "replay_end": replay_end, "top_n": top_n},
        "entry": "v1 入场候选 + v1 回调确认",
        "exit": "v1.2 最优：-8% 止损 + 累计超大单峰值回撤 20% 且连续下降 3 天",
        "orderbook_filter": {
            "rule": "launch_cancel_buy_to_add_buy_vs_hist > 2",
            "meaning": "启动期 撤买单/新增买单 相对该股历史均值放大超过 2 倍，视为撤梯子诱多风险",
            "raw_candidate_count": len(candidates),
            "filtered_candidate_count": len(filtered_candidates),
            "passed_candidate_count": len(passed_candidates),
        },
        "summary": s,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    comparison_rows = [
        {"strategy": "v1", "trade_count": 82, "win_rate": 52.44, "avg_return_pct": 2.11, "median_return_pct": 0.97, "max_return_pct": 59.71, "min_return_pct": -18.38, "avg_holding_days": 7.68},
        {"strategy": "v1.2", "trade_count": 82, "win_rate": 59.76, "avg_return_pct": 3.21, "median_return_pct": 2.75, "max_return_pct": 62.30, "min_return_pct": -18.38, "avg_holding_days": 8.39},
        {"strategy": "v1.3", **s},
    ]
    cmp_df = pd.DataFrame(comparison_rows)
    cmp_df.to_csv(out_dir / "strategy_comparison.csv", index=False)

    md = [
        "# v1.3 挂单过滤回测",
        "",
        "本版在 v1.2 基础上，只增加一条启动期挂单诱多过滤。",
        "",
        "## 过滤规则",
        "",
        "```text",
        "launch_cancel_buy_to_add_buy_vs_hist > 2",
        "```",
        "",
        "含义：启动期 `撤买单 / 新增买单` 相对该股历史均值放大超过 2 倍，认为有“撤梯子诱多”风险。",
        "",
        "## 策略对比",
        "",
        cmp_df.to_markdown(index=False),
        "",
        "## 候选过滤",
        "",
        f"- 原始候选：{len(candidates)}",
        f"- 过滤候选：{len(filtered_candidates)}",
        f"- 保留候选：{len(passed_candidates)}",
        "",
        "## 文件",
        "",
        "- raw_candidates.csv",
        "- filtered_candidates.csv",
        "- passed_candidates.csv",
        "- v1_3_trades.csv",
        "- strategy_comparison.csv",
        "- summary.json",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(md), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--out", default="docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-orderbook-filter")
    args = parser.parse_args()
    summary = run_v1_3(args.start, args.end, args.replay_end, args.top_n, Path(args.out))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
