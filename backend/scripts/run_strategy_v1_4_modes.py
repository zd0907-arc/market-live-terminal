from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams, build_v1_candidates, simulate_trade_v1_2
from backend.scripts.run_strategy_v1_3_orderbook_filter import launch_cancel_buy_vs_hist
from backend.scripts.run_strategy_v1_trend_reversal import add_ma


def future_days_after_entry(g: pd.DataFrame, entry_date: str) -> int:
    return int((g.trade_date >= entry_date).sum())


def enrich_candidates(candidates: List[Dict[str, Any]], by_symbol: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rec in candidates:
        if not rec.get("launch_start_date") or not rec.get("launch_end_date"):
            out.append({**rec, "order_filter_available": False, "orderbook_filter_reason": "no_launch"})
            continue
        g = by_symbol[str(rec["symbol"])]
        ob = launch_cancel_buy_vs_hist(g, str(rec["launch_start_date"]), str(rec["launch_end_date"]))
        out.append({**rec, **ob})
    return out


def filter_reason(rec: Dict[str, Any], mode: str) -> str:
    """Return empty string if candidate passes."""
    # v1.3 base filter: 启动期撤买单/新增买单相对历史放大，视为撤梯子诱多。
    if bool(rec.get("order_filter_available")) and float(rec.get("launch_cancel_buy_to_add_buy_vs_hist") or 0.0) > 1.5:
        return "v1_3_ladder_pull_filter"

    launch_ret = float(rec.get("launch3_return_pct") or 0.0)
    support = float(rec.get("pullback_support_spread_avg") or 0.0)
    dist = float(rec.get("confirm_distribution_score") or 0.0)

    if mode == "v1.3":
        return ""
    if mode == "v1.4-quality":
        # 高质量模式：启动 3 日不够强，直接不做。
        if launch_ret < 6.0:
            return "weak_launch_lt_6"
        return ""
    if mode == "v1.4-balanced":
        # 均衡模式：弱启动本身不杀；只有弱启动 + 回调承接弱 + 出货分偏高，才过滤。
        if launch_ret < 6.0 and support < 0.0 and dist >= 45.0:
            return "weak_launch_with_bad_pullback_and_distribution"
        return ""
    raise ValueError(f"unknown mode: {mode}")


def run_mode(
    mode: str,
    candidates: List[Dict[str, Any]],
    by_symbol: Dict[str, pd.DataFrame],
    min_future_days: int,
) -> Dict[str, Any]:
    exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    trade_cost_params = SelectionV2Params()
    passed: List[Dict[str, Any]] = []
    filtered: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []

    for rec in candidates:
        reason = filter_reason(rec, mode)
        tagged = {**rec, "strategy_mode": mode, "filter_reason": reason}
        if reason:
            filtered.append(tagged)
            continue
        passed.append(tagged)
        pull_date = tagged.get("pullback_confirm_date")
        if not pull_date:
            continue
        sym = str(tagged["symbol"])
        g = by_symbol[sym]
        trade = simulate_trade_v1_2(g, str(pull_date), exit_params, trade_cost_params)
        if not trade or trade.get("skipped"):
            continue
        fdays = future_days_after_entry(g, str(trade["entry_date"]))
        trades.append({
            **tagged,
            **trade,
            "future_days_available": fdays,
            "is_mature_trade": fdays >= min_future_days,
        })

    mature = [t for t in trades if t.get("is_mature_trade")]
    return {
        "mode": mode,
        "passed_candidates": passed,
        "filtered_candidates": filtered,
        "trades": trades,
        "full_summary": summarize(trades),
        "mature_summary": summarize(mature),
    }


def write_outputs(out: Path, results: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    rows = []
    all_trades: List[Dict[str, Any]] = []
    all_filtered: List[Dict[str, Any]] = []
    for r in results:
        row = {
            "mode": r["mode"],
            "passed_candidate_count": len(r["passed_candidates"]),
            "filtered_candidate_count": len(r["filtered_candidates"]),
        }
        for prefix, s in [("full", r["full_summary"]), ("mature", r["mature_summary"])]:
            for k, v in s.items():
                row[f"{prefix}_{k}"] = v
        rows.append(row)
        all_trades.extend(r["trades"])
        all_filtered.extend(r["filtered_candidates"])

    comparison = pd.DataFrame(rows)
    comparison.to_csv(out / "mode_comparison.csv", index=False)
    pd.DataFrame(all_trades).to_csv(out / "all_mode_trades.csv", index=False)
    pd.DataFrame(all_filtered).to_csv(out / "all_mode_filtered_candidates.csv", index=False)

    summary["mode_comparison"] = rows
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# v1.4 双模式回测",
        "",
        "基于 v1.3 阈值 1.5，再测试弱启动过滤的两个模式。",
        "",
        "## 模式定义",
        "",
        "```text",
        "v1.3:",
        "  过滤 launch_cancel_buy_to_add_buy_vs_hist > 1.5",
        "",
        "v1.4-quality:",
        "  先执行 v1.3 过滤",
        "  再过滤 launch3_return_pct < 6",
        "",
        "v1.4-balanced:",
        "  先执行 v1.3 过滤",
        "  再过滤 launch3_return_pct < 6",
        "       且 pullback_support_spread < 0",
        "       且 confirm_distribution_score >= 45",
        "```",
        "",
        "## 结果对比",
        "",
        comparison.to_markdown(index=False),
        "",
        "## 口径说明",
        "",
        f"- 发现日：{summary['range']['start']} ~ {summary['range']['end']}",
        f"- 回放到：{summary['range']['replay_end']}",
        f"- 成熟交易：买入后至少还有 {summary['min_future_days']} 个交易日数据",
        "- full：包含 4 月下旬未来数据不足的交易。",
        "- mature：只统计成熟交易，更适合判断策略质量。",
        "",
        "## 文件",
        "",
        "- mode_comparison.csv",
        "- all_mode_trades.csv",
        "- all_mode_filtered_candidates.csv",
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
    parser.add_argument("--min-future-days", type=int, default=10)
    parser.add_argument("--out", default="docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes")
    args = parser.parse_args()

    t0 = time.perf_counter()
    raw = load_atomic_daily_window("2026-01-01", args.replay_end)
    metrics = add_ma(compute_v2_metrics(raw))
    candidates, by_symbol = build_v1_candidates(metrics, args.start, args.end, args.top_n)
    enriched = enrich_candidates(candidates, by_symbol)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(enriched).to_csv(out / "enriched_candidates.csv", index=False)

    results = [run_mode(mode, enriched, by_symbol, args.min_future_days) for mode in ["v1.3", "v1.4-quality", "v1.4-balanced"]]
    summary = {
        "range": {"start": args.start, "end": args.end, "replay_end": args.replay_end, "top_n": args.top_n},
        "stock_count": int(metrics.symbol.nunique()),
        "trade_day_count": int(metrics[(metrics.trade_date >= args.start) & (metrics.trade_date <= args.end)].trade_date.nunique()),
        "raw_candidate_count": len(candidates),
        "min_future_days": args.min_future_days,
        "timing_seconds": {"total": round(time.perf_counter() - t0, 2)},
    }
    write_outputs(out, results, summary)
    print(pd.read_csv(out / "mode_comparison.csv").to_string(index=False))


if __name__ == "__main__":
    main()
