from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams, build_v1_candidates, simulate_trade_v1_2
from backend.scripts.run_strategy_v1_3_orderbook_filter import launch_cancel_buy_vs_hist
from backend.scripts.run_strategy_v1_trend_reversal import add_ma


def summarize_trade_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return summarize(rows)


def enrich_candidates(candidates: List[Dict[str, Any]], by_symbol: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for rec in candidates:
        if not rec.get("launch_start_date") or not rec.get("launch_end_date"):
            enriched.append({**rec, "order_filter_available": False, "orderbook_filter_reason": "no_launch"})
            continue
        g = by_symbol[str(rec["symbol"])]
        ob = launch_cancel_buy_vs_hist(g, str(rec["launch_start_date"]), str(rec["launch_end_date"]))
        enriched.append({**rec, **ob})
    return enriched


def future_days_after_entry(g: pd.DataFrame, entry_date: str) -> int:
    return int((g.trade_date >= entry_date).sum())


def run_threshold(
    enriched_candidates: List[Dict[str, Any]],
    by_symbol: Dict[str, pd.DataFrame],
    threshold: Optional[float],
    min_future_days: int,
) -> Dict[str, Any]:
    exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    trade_cost_params = SelectionV2Params()
    trades: List[Dict[str, Any]] = []
    filtered_candidates: List[Dict[str, Any]] = []
    passed_candidates: List[Dict[str, Any]] = []

    for rec in enriched_candidates:
        ratio = float(rec.get("launch_cancel_buy_to_add_buy_vs_hist", 0.0) or 0.0)
        available = bool(rec.get("order_filter_available"))
        if threshold is not None and available and ratio > threshold:
            filtered_candidates.append({**rec, "filter_threshold": threshold})
            continue
        passed_candidates.append({**rec, "filter_threshold": threshold if threshold is not None else "none"})
        pull_date = rec.get("pullback_confirm_date")
        if not pull_date:
            continue
        sym = str(rec["symbol"])
        g = by_symbol[sym]
        trade = simulate_trade_v1_2(g, str(pull_date), exit_params, trade_cost_params)
        if not trade or trade.get("skipped"):
            continue
        fdays = future_days_after_entry(g, str(trade["entry_date"]))
        trades.append({
            **rec,
            **trade,
            "filter_threshold": threshold if threshold is not None else "none",
            "future_days_available": fdays,
            "is_mature_trade": fdays >= min_future_days,
        })

    mature_trades = [t for t in trades if t.get("is_mature_trade")]
    return {
        "threshold": threshold if threshold is not None else "none",
        "filtered_candidate_count": len(filtered_candidates),
        "passed_candidate_count": len(passed_candidates),
        "trades": trades,
        "filtered_candidates": filtered_candidates,
        "full_summary": summarize_trade_rows(trades),
        "mature_summary": summarize_trade_rows(mature_trades),
    }


def write_outputs(out: Path, summary: Dict[str, Any], threshold_results: List[Dict[str, Any]]) -> None:
    rows = []
    for r in threshold_results:
        row = {
            "threshold": r["threshold"],
            "filtered_candidate_count": r["filtered_candidate_count"],
            "passed_candidate_count": r["passed_candidate_count"],
        }
        for prefix, s in [("full", r["full_summary"]), ("mature", r["mature_summary"])]:
            for k, v in s.items():
                row[f"{prefix}_{k}"] = v
        rows.append(row)
    scan_df = pd.DataFrame(rows)
    scan_df.to_csv(out / "threshold_scan_summary.csv", index=False)

    all_trades = []
    all_filtered = []
    for r in threshold_results:
        all_trades.extend(r["trades"])
        all_filtered.extend(r["filtered_candidates"])
    pd.DataFrame(all_trades).to_csv(out / "all_threshold_trades.csv", index=False)
    pd.DataFrame(all_filtered).to_csv(out / "all_threshold_filtered_candidates.csv", index=False)

    summary["threshold_scan"] = rows
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# v1.3 稳健性验证：全市场 3-4 月阈值扫描",
        "",
        "范围内每日 TopN 仍来自全市场逐日扫描，不是固定样本池。",
        "",
        "## 运行范围",
        "",
        f"- 发现日：{summary['range']['start']} ~ {summary['range']['end']}",
        f"- 回放到：{summary['range']['replay_end']}",
        f"- 每日候选：Top{summary['range']['top_n']}",
        f"- 成熟交易定义：买入后至少还有 {summary['min_future_days']} 个交易日数据",
        "",
        "## 阈值扫描结果",
        "",
        scan_df.to_markdown(index=False),
        "",
        "## 口径说明",
        "",
        "- `full_*`：所有触发交易，包含 4 月下旬未来数据不足的交易。",
        "- `mature_*`：只统计买入后至少还有足够未来交易日的交易，更适合评估策略质量。",
        "- `threshold = none`：等价 v1.2 出场逻辑，不加挂单过滤。",
        "",
        "## 输出文件",
        "",
        "- threshold_scan_summary.csv",
        "- all_threshold_trades.csv",
        "- all_threshold_filtered_candidates.csv",
        "- enriched_candidates.csv",
        "- summary.json",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--thresholds", default="1.5,2.0,2.5,3.0")
    parser.add_argument("--min-future-days", type=int, default=10)
    parser.add_argument("--out", default="docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-robustness-scan")
    args = parser.parse_args()

    t0 = time.perf_counter()
    raw = load_atomic_daily_window("2026-01-01", args.replay_end)
    metrics = add_ma(compute_v2_metrics(raw))
    data_seconds = round(time.perf_counter() - t0, 2)

    t1 = time.perf_counter()
    candidates, by_symbol = build_v1_candidates(metrics, args.start, args.end, args.top_n)
    candidate_seconds = round(time.perf_counter() - t1, 2)

    t2 = time.perf_counter()
    enriched_candidates = enrich_candidates(candidates, by_symbol)
    enrich_seconds = round(time.perf_counter() - t2, 2)

    thresholds: List[Optional[float]] = [None] + [float(x.strip()) for x in args.thresholds.split(",") if x.strip()]
    t3 = time.perf_counter()
    threshold_results = [run_threshold(enriched_candidates, by_symbol, th, args.min_future_days) for th in thresholds]
    simulation_seconds = round(time.perf_counter() - t3, 2)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(enriched_candidates).to_csv(out / "enriched_candidates.csv", index=False)

    summary = {
        "range": {"start": args.start, "end": args.end, "replay_end": args.replay_end, "top_n": args.top_n},
        "stock_count": int(metrics.symbol.nunique()),
        "trade_day_count": int(metrics[(metrics.trade_date >= args.start) & (metrics.trade_date <= args.end)].trade_date.nunique()),
        "raw_candidate_count": len(candidates),
        "order_available_candidate_count": int(sum(1 for c in enriched_candidates if c.get("order_filter_available"))),
        "min_future_days": args.min_future_days,
        "timing_seconds": {
            "data_load_and_metrics": data_seconds,
            "candidate_build": candidate_seconds,
            "orderbook_enrich": enrich_seconds,
            "threshold_simulation": simulation_seconds,
            "total": round(time.perf_counter() - t0, 2),
        },
    }
    write_outputs(out, summary, threshold_results)
    print(json.dumps({k: summary[k] for k in ["range", "stock_count", "trade_day_count", "raw_candidate_count", "timing_seconds"]}, ensure_ascii=False, indent=2))
    print(pd.read_csv(out / "threshold_scan_summary.csv").to_string(index=False))


if __name__ == "__main__":
    main()
