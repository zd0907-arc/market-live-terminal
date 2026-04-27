from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import score_linear, summarize
from backend.scripts.research_trend_sample_factors import slice_stats, pct, max_drawdown
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams, simulate_trade_v1_2
from backend.scripts.run_strategy_v1_trend_reversal import add_ma
from backend.scripts.research_strong_runup_opportunity_audit import build_all_runups

OUT = Path("docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-prototype")
STABLE_TRADES = Path("docs/strategy-rework/strategies/S01-capital-trend-reversal/experiments/EXP-20260426-S01-M05-conservative-combined-risk/s01_m05_trades.csv")


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v): return default
        return float(v)
    except Exception:
        return default


def future_days_after_entry(g: pd.DataFrame, entry_date: str) -> int:
    return int((g.trade_date >= entry_date).sum())


def trend_continuation_score(g: pd.DataFrame, i: int) -> Tuple[float, Dict[str, Any], List[str]]:
    row = g.loc[i]
    if i < 20:
        return 0.0, {}, ["lookback不足"]
    pre20 = slice_stats(g, i - 20, i - 1, "pre20")
    pre10 = slice_stats(g, i - 10, i - 1, "pre10")
    pre5 = slice_stats(g, i - 5, i - 1, "pre5")
    recent = g.iloc[max(0, i - 10): i + 1].copy()
    pre20_ret = fnum(pre20.get("pre20_return_pct"))
    pre10_ret = fnum(pre10.get("pre10_return_pct"))
    pre5_ret = fnum(pre5.get("pre5_return_pct"))
    amount = fnum(row.get("total_amount"))
    amount_anom = fnum(row.get("amount_anomaly_20d"))
    close = fnum(row.get("close"))
    ma5 = fnum(row.get("close_ma5"))
    ma10 = fnum(row.get("close_ma10"))
    high20 = float(g.iloc[i - 20:i].high.max())
    low10 = float(recent.low.min()) if not recent.empty else close
    dd_from_20h = pct(high20, low10) if high20 > 0 else 0.0
    close_vs_20h = pct(high20, close) if high20 > 0 else 0.0
    day_ret = fnum(row.get("return_1d_pct"))
    active = fnum(row.get("active_buy_strength"))
    support = fnum(row.get("support_pressure_spread"))
    pre20_super = fnum(pre20.get("pre20_super_net_ratio"))
    pre20_main = fnum(pre20.get("pre20_main_net_ratio"))
    pre10_super = fnum(pre10.get("pre10_super_net_ratio"))
    pre10_main = fnum(pre10.get("pre10_main_net_ratio"))
    pre20_super_pos = fnum(pre20.get("pre20_super_positive_day_ratio"))
    pre20_main_pos = fnum(pre20.get("pre20_main_positive_day_ratio"))
    order_avail = fnum(pre5.get("pre5_order_available_ratio"))

    reasons: List[str] = []
    if amount < 180_000_000:
        reasons.append("成交额<1.8亿")
    if not (10 <= pre20_ret <= 65):
        reasons.append("前20日涨幅不在10~65")
    if pre5_ret > 18:
        reasons.append("近5日过热")
    if pre10_ret < -18:
        reasons.append("近10日走弱过深")
    if close < ma10 * 0.965 if ma10 > 0 else False:
        reasons.append("跌破10日线过多")
    if dd_from_20h < -22:
        reasons.append("阶段回撤过深")
    if close_vs_20h < -18:
        reasons.append("离20日高点太远")
    if max(pre20_super, pre20_main, pre10_super, pre10_main) < 0.002 and max(pre20_super_pos, pre20_main_pos) < 0.48:
        reasons.append("资金未留场")
    if day_ret < -4:
        reasons.append("信号日下跌过大")

    trend_score = 0.45 * score_linear(pre20_ret, 10, 45) + 0.25 * score_linear(pre10_ret, -8, 20) + 0.30 * score_linear(close_vs_20h, -18, -2)
    fund_score = 0.35 * score_linear(max(pre20_super, pre10_super), -0.005, 0.035) + 0.35 * score_linear(max(pre20_main, pre10_main), -0.005, 0.035) + 0.30 * score_linear(max(pre20_super_pos, pre20_main_pos), 0.35, 0.70)
    repair_score = 0.35 * score_linear(dd_from_20h, -22, -5) + 0.25 * score_linear(day_ret, -2, 6) + 0.20 * score_linear(active, -0.05, 0.12) + 0.20 * score_linear(support, -0.08, 0.08)
    liquidity_score = 0.6 * score_linear(amount, 180_000_000, 1_000_000_000) + 0.4 * score_linear(amount_anom, 0.8, 2.0)
    score = round(max(0, min(100, 0.30 * trend_score + 0.35 * fund_score + 0.25 * repair_score + 0.10 * liquidity_score)), 2)

    meta = {
        "pre20_return_pct": pre20_ret,
        "pre10_return_pct": pre10_ret,
        "pre5_return_pct": pre5_ret,
        "drawdown_from_20d_high_pct": round(dd_from_20h, 2),
        "close_vs_20d_high_pct": round(close_vs_20h, 2),
        "amount": amount,
        "amount_anomaly_20d": amount_anom,
        "signal_return_1d_pct": day_ret,
        "active_buy_strength": active,
        "support_pressure_spread": support,
        "pre20_super_net_ratio": pre20_super,
        "pre20_main_net_ratio": pre20_main,
        "pre10_super_net_ratio": pre10_super,
        "pre10_main_net_ratio": pre10_main,
        "pre20_super_positive_day_ratio": pre20_super_pos,
        "pre20_main_positive_day_ratio": pre20_main_pos,
        "pre5_order_available_ratio": order_avail,
        "trend_score": round(trend_score, 2),
        "fund_score": round(fund_score, 2),
        "repair_score": round(repair_score, 2),
        "liquidity_score": round(liquidity_score, 2),
    }
    return score, meta, reasons


def build_candidates(metrics: pd.DataFrame, start: str, end: str, top_n: int, min_score: float) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}
    days = sorted(metrics[(metrics.trade_date >= start) & (metrics.trade_date <= end)].trade_date.unique().tolist())
    rows: List[Dict[str, Any]] = []
    rejected_reason_counts: Dict[str, int] = {}
    for day in days:
        ranked = []
        for sym, g in by_symbol.items():
            idxs = g.index[g.trade_date == day].tolist()
            if not idxs:
                continue
            i = idxs[0]
            score, meta, reasons = trend_continuation_score(g, i)
            if reasons or score < min_score:
                for r in reasons[:2]:
                    rejected_reason_counts[r] = rejected_reason_counts.get(r, 0) + 1
                continue
            ranked.append({"symbol": sym, "signal_date": day, "score": score, **meta})
        ranked = sorted(ranked, key=lambda x: (-x["score"], x["symbol"]))[:top_n]
        for rank, rec in enumerate(ranked, start=1):
            rows.append({**rec, "rank": rank, "strategy_name": "趋势中继原型"})
    df = pd.DataFrame(rows)
    if not df.empty:
        df.attrs["rejected_reason_counts"] = rejected_reason_counts
    return df, by_symbol


def simulate_trades(candidates: pd.DataFrame, by_symbol: Dict[str, pd.DataFrame], min_future_days: int) -> pd.DataFrame:
    exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    trade_cost_params = SelectionV2Params()
    rows = []
    for _, rec in candidates.iterrows():
        g = by_symbol[str(rec.symbol)]
        trade = simulate_trade_v1_2(g, str(rec.signal_date), exit_params, trade_cost_params)
        if not trade or trade.get("skipped"):
            continue
        fdays = future_days_after_entry(g, str(trade["entry_date"]))
        rows.append({**rec.to_dict(), **trade, "future_days_available": fdays, "is_mature_trade": fdays >= min_future_days})
    return pd.DataFrame(rows)


def coverage(trades: pd.DataFrame, candidates: pd.DataFrame, runups: pd.DataFrame, threshold: float, stable_syms: set[str]) -> Dict[str, Any]:
    strong = runups[runups.runup_pct >= threshold].copy()
    syms = set(str(s) for s in strong.symbol)
    cand_syms = set(str(s) for s in candidates.symbol.unique()) if not candidates.empty else set()
    trade_syms = set(str(s) for s in trades.symbol.unique()) if not trades.empty else set()
    return {
        "threshold": threshold,
        "strong_count": int(len(strong)),
        "candidate_hit_count": int(len(syms & cand_syms)),
        "trade_hit_count": int(len(syms & trade_syms)),
        "stable_trade_hit_count": int(len(syms & stable_syms)),
        "combined_trade_hit_count": int(len(syms & (trade_syms | stable_syms))),
        "new_trade_hit_vs_stable": int(len((syms & trade_syms) - stable_syms)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-score", type=float, default=58.0)
    parser.add_argument("--min-future-days", type=int, default=10)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = load_atomic_daily_window("2026-01-01", args.replay_end)
    metrics = add_ma(compute_v2_metrics(raw))
    runups = build_all_runups(metrics, args.start, args.end)
    candidates, by_symbol = build_candidates(metrics, args.start, args.end, args.top_n, args.min_score)
    trades = simulate_trades(candidates, by_symbol, args.min_future_days)
    mature = trades[trades.is_mature_trade.astype(bool)].copy() if not trades.empty else pd.DataFrame()

    stable = pd.read_csv(STABLE_TRADES) if STABLE_TRADES.exists() else pd.DataFrame()
    stable_syms = set(str(s) for s in stable.symbol.unique()) if not stable.empty else set()
    cover_rows = [coverage(trades, candidates, runups, th, stable_syms) for th in [30, 50]]
    top50 = runups.head(50)
    cover_rows.append({
        "threshold": "top50",
        "strong_count": 50,
        "candidate_hit_count": int(len(set(top50.symbol) & set(candidates.symbol.unique()))) if not candidates.empty else 0,
        "trade_hit_count": int(len(set(top50.symbol) & set(trades.symbol.unique()))) if not trades.empty else 0,
        "stable_trade_hit_count": int(len(set(top50.symbol) & stable_syms)),
        "combined_trade_hit_count": int(len(set(top50.symbol) & (set(trades.symbol.unique()) | stable_syms))) if not trades.empty else int(len(set(top50.symbol) & stable_syms)),
        "new_trade_hit_vs_stable": int(len((set(top50.symbol) & set(trades.symbol.unique())) - stable_syms)) if not trades.empty else 0,
    })

    candidates.to_csv(out / "trend_continuation_candidates.csv", index=False)
    trades.to_csv(out / "trend_continuation_trades.csv", index=False)
    mature.to_csv(out / "trend_continuation_mature_trades.csv", index=False)
    runups.to_csv(out / "all_runup_opportunities.csv", index=False)
    coverage_df = pd.DataFrame(cover_rows)
    coverage_df.to_csv(out / "strong_coverage.csv", index=False)

    trade_summary = summarize(trades.to_dict("records") if not trades.empty else [])
    mature_summary = summarize(mature.to_dict("records") if not mature.empty else [])
    summary = {
        "range": {"start": args.start, "end": args.end, "replay_end": args.replay_end, "top_n": args.top_n, "min_score": args.min_score},
        "candidate_count": int(len(candidates)),
        "trade_summary": trade_summary,
        "mature_summary": mature_summary,
        "coverage": cover_rows,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# 趋势中继策略原型实验

## 问题

当前“资金流回调稳健策略”高胜率但覆盖窄。大量强势股属于：

```text
已经涨过一段
资金没有明显撤退
没有标准回调买点
后面继续二波/主升
```

本实验验证“趋势中继原型”能否补充覆盖这类股票。

## 原型逻辑

信号日要求：

```text
前20日已有明显涨幅，但不极端过热
价格仍在20日高点附近
近期有回撤/震荡但未破坏趋势
前20/10日 L2 主力或超大单仍有留场迹象
信号日不能大跌，承接/主动买入不能太差
```

买入：信号日次日开盘。

卖出：暂复用资金流回调稳健策略的累计超大单退出/硬止损。

## 回测结果

- 全部交易：{trade_summary}
- 成熟交易：{mature_summary}

## 强势样本覆盖

{coverage_df.to_markdown(index=False)}

## 初步结论

这是第一版原型，只用于判断方向是否值得继续。重点看它是否能补充当前稳健策略没有抓到的强势股，而不是马上投产。

## 输出文件

- `trend_continuation_candidates.csv`
- `trend_continuation_trades.csv`
- `trend_continuation_mature_trades.csv`
- `strong_coverage.csv`
- `all_runup_opportunities.csv`
- `summary.json`
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
