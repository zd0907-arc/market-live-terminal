from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import (
    SelectionV2Params,
    _apply_buy_costs,
    _apply_sell_costs,
    _is_limit_up_day,
    compute_v2_metrics,
    load_atomic_daily_window,
)
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.run_strategy_v1_trend_reversal import (
    add_ma,
    candidate_ok,
    find_launch,
    find_pullback_confirm,
    setup_score,
)
from backend.scripts.research_trend_sample_factors import slice_stats


@dataclass(frozen=True)
class V12ExitParams:
    stop_loss_pct: float
    super_peak_drawdown_pct: float
    super_decline_days: int
    daily_super_outflow_cum_amount_ratio: float = 0.025
    max_holding_days: int = 40


def simulate_trade_v1_2(sym_df: pd.DataFrame, signal_date: str, p: V12ExitParams, trade_cost_params: SelectionV2Params) -> Optional[Dict[str, Any]]:
    future_entry = sym_df[sym_df.trade_date > signal_date]
    if future_entry.empty:
        return None
    entry_i = int(future_entry.index[0])
    entry = sym_df.loc[entry_i]
    if _is_limit_up_day(entry, trade_cost_params):
        return {"skipped": True, "skip_reason": "entry_blocked_limit_up", "entry_signal_date": signal_date}
    gross_entry = float(entry.open)
    if gross_entry <= 0:
        return None

    entry_price = _apply_buy_costs(gross_entry, trade_cost_params)
    entry_date = str(entry.trade_date)
    rows = sym_df.loc[entry_i:].copy()

    cum_super = 0.0
    cum_amount = 0.0
    cum_super_peak = 0.0
    previous_cum_super: Optional[float] = None
    decline_streak = 0
    holding_days = 0
    max_runup = -999.0
    max_drawdown = 999.0
    exit_signal_date: Optional[str] = None
    exit_reason = "window_end"

    final_meta: Dict[str, Any] = {}

    for _, row in rows.iterrows():
        holding_days += 1
        high = float(row.high)
        low = float(row.low)
        close = float(row.close)
        amount = float(row.total_amount or 0.0)
        daily_super = float(row.l2_super_net_amount or 0.0)
        cum_amount += amount
        cum_super += daily_super

        if previous_cum_super is not None and cum_super < previous_cum_super:
            decline_streak += 1
        else:
            decline_streak = 0
        previous_cum_super = cum_super

        cum_super_peak = max(cum_super_peak, cum_super)
        peak_drawdown_amount = max(0.0, cum_super_peak - cum_super)
        peak_drawdown_pct = peak_drawdown_amount / cum_super_peak if cum_super_peak > 0 else 0.0
        daily_outflow_cum_amount_ratio = max(0.0, -daily_super) / max(cum_amount, 1.0)

        max_runup = max(max_runup, (high / gross_entry - 1) * 100)
        max_drawdown = min(max_drawdown, (low / gross_entry - 1) * 100)
        close_return = (close / gross_entry - 1) * 100

        final_meta = {
            "final_cum_super_amount": round(cum_super, 2),
            "final_cum_super_peak_amount": round(cum_super_peak, 2),
            "final_cum_super_ratio": round(cum_super / max(cum_amount, 1.0), 5),
            "final_super_peak_drawdown_pct": round(peak_drawdown_pct * 100, 2),
            "final_super_decline_streak": int(decline_streak),
        }

        if close_return <= p.stop_loss_pct:
            exit_signal_date = str(row.trade_date)
            exit_reason = f"hard_stop_{abs(p.stop_loss_pct):g}pct"
            break

        # 核心约束：只把“累计超大单净流入实际下降”视为风险；走平或增速放缓不卖。
        if (
            cum_super_peak > 0
            and decline_streak >= p.super_decline_days
            and peak_drawdown_pct >= p.super_peak_drawdown_pct
        ):
            exit_signal_date = str(row.trade_date)
            exit_reason = f"cum_super_peak_dd_{int(p.super_peak_drawdown_pct * 100)}pct_{p.super_decline_days}d"
            break

        if (
            cum_super_peak > 0
            and daily_super < 0
            and daily_outflow_cum_amount_ratio >= p.daily_super_outflow_cum_amount_ratio
            and peak_drawdown_pct >= min(0.15, p.super_peak_drawdown_pct)
        ):
            exit_signal_date = str(row.trade_date)
            exit_reason = "violent_super_outflow"
            break

        if holding_days >= p.max_holding_days:
            exit_signal_date = str(row.trade_date)
            exit_reason = "max_holding_days"
            break

    if exit_signal_date:
        exit_next = sym_df[sym_df.trade_date > exit_signal_date]
        if exit_next.empty:
            exit_row = sym_df[sym_df.trade_date == exit_signal_date].iloc[0]
            gross_exit = float(exit_row.close)
        else:
            exit_row = exit_next.iloc[0]
            gross_exit = float(exit_row.open)
    else:
        exit_row = rows.iloc[-1]
        gross_exit = float(exit_row.close)
        exit_signal_date = str(exit_row.trade_date)
    exit_date = str(exit_row.trade_date)
    exit_price = _apply_sell_costs(gross_exit, trade_cost_params)

    return {
        "entry_signal_date": signal_date,
        "entry_date": entry_date,
        "gross_entry_price": round(gross_entry, 4),
        "entry_price": round(entry_price, 4),
        "exit_signal_date": exit_signal_date,
        "exit_date": exit_date,
        "gross_exit_price": round(gross_exit, 4),
        "exit_price": round(exit_price, 4),
        "return_pct": round((gross_exit / gross_entry - 1) * 100, 2),
        "net_return_pct": round((exit_price / entry_price - 1) * 100, 2),
        "max_runup_pct": round(max_runup, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "holding_days": int(holding_days),
        "exit_reason": exit_reason,
        **final_meta,
    }


def build_v1_candidates(metrics: pd.DataFrame, start: str, end: str, top_n: int) -> tuple[List[Dict[str, Any]], Dict[str, pd.DataFrame]]:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}
    days = sorted(metrics[(metrics.trade_date >= start) & (metrics.trade_date <= end)].trade_date.unique().tolist())
    candidates: List[Dict[str, Any]] = []

    for day in days:
        ranked = []
        for sym, g in by_symbol.items():
            idxs = g.index[g.trade_date == day].tolist()
            if not idxs:
                continue
            i = idxs[0]
            if i < 8:
                continue
            pre20 = slice_stats(g, i - 20, i - 1, "pre20")
            pre5 = slice_stats(g, i - 5, i - 1, "pre5")
            current = g.loc[i]
            sc = setup_score(pre20, pre5, current)
            if not candidate_ok(pre20, pre5, current, sc):
                continue
            ranked.append({"symbol": sym, "score": sc, "row": current, "pre20": pre20, "pre5": pre5})

        ranked = sorted(ranked, key=lambda x: (-x["score"], x["symbol"]))[:top_n]
        for rank, item in enumerate(ranked, start=1):
            sym = item["symbol"]
            g = by_symbol[sym]
            launch_start, launch_end, launch_meta = find_launch(g, day)
            pull_date = None
            pull_reason = "no_launch"
            pull_meta: Dict[str, Any] = {}
            if launch_end:
                pull_date, pull_reason, pull_meta = find_pullback_confirm(g, launch_start, launch_end)
            rec = {
                "discovery_date": day,
                "symbol": sym,
                "rank": rank,
                "setup_score": item["score"],
                "pre20_return_pct": item["pre20"].get("pre20_return_pct"),
                "pre20_super_price_divergence": item["pre20"].get("pre20_super_price_divergence"),
                "pre20_main_price_divergence": item["pre20"].get("pre20_main_price_divergence"),
                "pre5_return_pct": item["pre5"].get("pre5_return_pct"),
                "pre5_super_price_divergence": item["pre5"].get("pre5_super_price_divergence"),
                "launch_start_date": launch_start,
                "launch_end_date": launch_end,
                "pullback_confirm_date": pull_date,
                "pullback_confirm_reason": pull_reason,
                **{k: v for k, v in launch_meta.items() if k in ["launch3_return_pct", "launch3_super_net_ratio", "launch3_main_net_ratio", "launch3_max_drawdown_pct", "launch3_add_buy_ratio"]},
                **{k: v for k, v in pull_meta.items() if k in ["pullback_super_net_ratio", "pullback_main_net_ratio", "pullback_support_spread_avg", "pullback_depth_from_launch_peak_pct", "confirm_distribution_score"]},
            }
            candidates.append(rec)
    return candidates, by_symbol


def run_variant(candidates: List[Dict[str, Any]], by_symbol: Dict[str, pd.DataFrame], p: V12ExitParams) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    trade_cost_params = SelectionV2Params()
    for rec in candidates:
        pull_date = rec.get("pullback_confirm_date")
        if not pull_date:
            continue
        g = by_symbol[str(rec["symbol"])]
        trade = simulate_trade_v1_2(g, str(pull_date), p, trade_cost_params)
        if trade and not trade.get("skipped"):
            trades.append({**rec, **trade, **asdict(p)})
    return trades


def write_markdown(out: Path, summary: Dict[str, Any]) -> None:
    lines = [
        "# v1.2 累计超大单出场参数实验",
        "",
        "入场沿用 v1；本实验只改出场。",
        "",
        "## 出场定义",
        "",
        "- 硬止损：收盘相对买入开盘跌到参数阈值，次日开盘出。",
        "- 累计超大单回撤：从买入日开始累计 `l2_super_net_amount`，记录峰值；只有累计值实际下降且满足连续下降天数与峰值回撤比例才卖。",
        "- 暴烈流出：单日超大单净流出占买入后累计成交额过大，同时累计超大单已从峰值明显回撤。",
        "",
        "## 参数排名 Top 10",
        "",
    ]
    ranked = summary["variant_rankings"][:10]
    if ranked:
        df = pd.DataFrame(ranked)
        lines.append(df.to_markdown(index=False))
    lines.extend([
        "",
        "## 当前建议",
        "",
        summary.get("recommendation", ""),
        "",
        "## 输出文件",
        "",
        "- summary.json",
        "- variant_summary.csv",
        "- best_trades.csv",
        "- candidates.csv",
        "",
    ])
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--out", default="docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-2-exit-grid")
    args = parser.parse_args()

    raw = load_atomic_daily_window("2026-01-01", args.replay_end)
    metrics = add_ma(compute_v2_metrics(raw))
    candidates, by_symbol = build_v1_candidates(metrics, args.start, args.end, args.top_n)

    variants = [
        V12ExitParams(stop, dd, days)
        for stop, dd, days in itertools.product([-8.0, -10.0, -12.0], [0.20, 0.25, 0.30], [2, 3])
    ]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(candidates).to_csv(out / "candidates.csv", index=False)

    rankings: List[Dict[str, Any]] = []
    all_trades_by_key: Dict[str, List[Dict[str, Any]]] = {}
    for p in variants:
        trades = run_variant(candidates, by_symbol, p)
        s = summarize(trades)
        # 排名目标：先保证中位数和平均收益，再看胜率；避免只靠少数大牛拉高平均值。
        objective = (
            float(s.get("median_return_pct", 0.0)) * 0.45
            + float(s.get("avg_return_pct", 0.0)) * 0.35
            + (float(s.get("win_rate", 0.0)) - 50.0) * 0.06
            + float(s.get("min_return_pct", 0.0)) * 0.04
        )
        key = f"stop{int(abs(p.stop_loss_pct))}_dd{int(p.super_peak_drawdown_pct * 100)}_days{p.super_decline_days}"
        all_trades_by_key[key] = trades
        rankings.append({
            "variant": key,
            "objective": round(objective, 4),
            **asdict(p),
            **s,
        })

    rankings = sorted(rankings, key=lambda x: (-float(x["objective"]), -float(x.get("avg_return_pct", 0)), -float(x.get("win_rate", 0))))
    pd.DataFrame(rankings).to_csv(out / "variant_summary.csv", index=False)

    best = rankings[0] if rankings else {}
    best_key = str(best.get("variant", ""))
    best_trades = all_trades_by_key.get(best_key, [])
    pd.DataFrame(best_trades).to_csv(out / "best_trades.csv", index=False)

    summary = {
        "range": {"start": args.start, "end": args.end, "replay_end": args.replay_end, "top_n": args.top_n},
        "candidate_count": len(candidates),
        "pullback_confirmed_count": sum(1 for c in candidates if c.get("pullback_confirm_date")),
        "variant_count": len(variants),
        "best_variant": best,
        "variant_rankings": rankings,
        "recommendation": "优先观察 Top 参数是否提升中位数/最小亏损；如果平均值提升但中位数变差，不能直接替换 v1。",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(out, summary)
    print(json.dumps({"best": best, "top5": rankings[:5]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
