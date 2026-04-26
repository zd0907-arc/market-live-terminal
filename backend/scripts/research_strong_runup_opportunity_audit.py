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

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window
from backend.scripts.research_market_extreme_reverse_audit import (
    LOOKBACK,
    fetch_names,
    max_runup,
    pct,
    safe_float,
    stage_analysis,
    mode_filter_counts,
)
from backend.scripts.run_strategy_v1_trend_reversal import add_ma

DEFAULT_OUT = Path("docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-strong-runup-opportunity-audit")
LEGACY_V14_OUT = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes")
STABLE_OUT = Path("docs/strategy-rework/strategies/S01-capital-trend-reversal/experiments/EXP-20260426-S01-M05-conservative-combined-risk")


def build_all_runups(metrics: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    scoped = metrics[(metrics.trade_date >= start) & (metrics.trade_date <= end)].copy()
    for sym, g0 in scoped.groupby("symbol", sort=False):
        g = g0.sort_values("trade_date").reset_index(drop=True)
        if len(g) < 10:
            continue
        ru = max_runup(g)
        si, ei = int(ru["start_i"]), int(ru["end_i"])
        rows.append({
            "symbol": sym,
            "runup_pct": round(float(ru["runup_pct"]), 2),
            "runup_start_date": str(g.loc[si, "trade_date"]),
            "runup_end_date": str(g.loc[ei, "trade_date"]),
            "runup_start_price": round(float(g.loc[si, "low"]), 3),
            "runup_end_price": round(float(g.loc[ei, "high"]), 3),
            "runup_days": int(ei - si + 1),
            "period_return_pct": round(pct(float(g.close.iloc[0]), float(g.close.iloc[-1])), 2),
            "amount_avg": round(float(g.total_amount.mean()), 2),
            "amount_at_start": round(float(g.loc[si, "total_amount"]), 2),
        })
    df = pd.DataFrame(rows).sort_values(["runup_pct", "amount_avg"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "runup_rank", range(1, len(df) + 1))
    names = fetch_names(df.head(200).symbol.tolist())
    df.insert(2, "name", df.symbol.map(names).fillna(""))
    return df


def classify(row: Dict[str, Any]) -> Tuple[str, str, str]:
    """return bucket, owner, action"""
    if int(row.get("stable_trade_count") or 0) > 0:
        return "当前策略已抓到", "资金流回调稳健策略", "保留"
    if int(row.get("base_trade_count") or 0) > 0 and int(row.get("stable_trade_count") or 0) == 0:
        return "被组合风险过滤", "组合风险模块复核", "检查是否误杀真强票"
    if int(row.get("candidate_count") or 0) > 0:
        reasons = str(row.get("candidate_only_filter_reasons") or "")
        if "v1_3_ladder_pull_filter" in reasons:
            return "被撤买单风险过滤", "组合风险模块复核", "研究强资金豁免"
        if not bool(row.get("has_pullback_confirm_candidate")):
            return "有发现但无回调买点", "趋势中继策略", "研究无标准回调的中继买点"
        return "有发现但排序/交易链路未命中", "资金流回调稳健策略", "优化排序容量或工程链路"

    reason = str(row.get("primary_anchor_reason") or "")
    pre20 = safe_float(row.get("anchor_pre20_return_pct"))
    pre5 = safe_float(row.get("anchor_pre5_return_pct"))
    if "成交额<2.5亿" in reason:
        return "成交额硬门槛错过", "资金流回调稳健策略", "改相对成交额/换手/历史分位"
    if pre20 > 12 or pre5 > 8:
        return "启动前已涨过", "趋势中继策略", "研究二波/中继，不强塞回调策略"
    if "资金价格背离不足" in reason:
        return "资金流特征不足", "消息事件重估策略", "需要新闻/公司研究解释"
    if "setup_score<50" in reason:
        return "低位资金结构不达标", "资金流回调稳健策略", "可优化发现层打分"
    if "候选通过但未找到启动3日" in reason:
        return "启动识别缺失", "资金流回调稳健策略", "优化启动识别"
    if "启动通过但未等到回调承接" in reason:
        return "无标准回调承接", "趋势中继策略", "研究趋势中继买点"
    if "锚点附近链路可通过" in reason:
        return "链路可过但未进Top10", "资金流回调稳健策略", "优化排序/每日容量"
    return "其他", "人工复盘", "人工复盘"


def diagnose(strong: pd.DataFrame, candidates: pd.DataFrame, base_trades: pd.DataFrame, stable_trades: pd.DataFrame, by_symbol: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, er in strong.iterrows():
        sym = str(er.symbol)
        c = candidates[candidates.symbol == sym].copy()
        bt = base_trades[base_trades.symbol == sym].copy()
        st = stable_trades[stable_trades.symbol == sym].copy()
        c_filter_counts = mode_filter_counts(c) if not c.empty else {}
        analysis = stage_analysis(sym, str(er.runup_start_date), by_symbol)
        row = {
            **er.to_dict(),
            "candidate_count": int(len(c)),
            "candidate_dates": ",".join(c.discovery_date.astype(str).head(10).tolist()) if not c.empty else "",
            "has_pullback_confirm_candidate": bool((c.pullback_confirm_date.notna()).any()) if not c.empty else False,
            "candidate_only_filter_reasons": ";".join(f"{k}:{v}" for k, v in c_filter_counts.items()),
            "base_trade_count": int(len(bt)),
            "base_entry_dates": ",".join(bt.entry_date.astype(str).head(5).tolist()) if not bt.empty else "",
            "base_best_return_pct": round(float(bt.net_return_pct.max()), 2) if not bt.empty else None,
            "stable_trade_count": int(len(st)),
            "stable_entry_dates": ",".join(st.entry_date.astype(str).head(5).tolist()) if not st.empty else "",
            "stable_best_return_pct": round(float(st.net_return_pct.max()), 2) if not st.empty else None,
            **analysis,
        }
        bucket, owner, action = classify(row)
        row["reason_bucket"] = bucket
        row["recommended_owner"] = owner
        row["next_action"] = action
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_cohort(name: str, df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"cohort": name, "count": 0}
    owner_counts = df.recommended_owner.value_counts().to_dict()
    reason_counts = df.reason_bucket.value_counts().to_dict()
    return {
        "cohort": name,
        "count": int(len(df)),
        "avg_runup_pct": round(float(df.runup_pct.mean()), 2),
        "min_runup_pct": round(float(df.runup_pct.min()), 2),
        "max_runup_pct": round(float(df.runup_pct.max()), 2),
        "candidate_count": int((df.candidate_count > 0).sum()),
        "base_trade_count": int((df.base_trade_count > 0).sum()),
        "stable_trade_count": int((df.stable_trade_count > 0).sum()),
        "owner_counts": owner_counts,
        "reason_counts": reason_counts,
    }


def reason_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (owner, reason), g in df.groupby(["recommended_owner", "reason_bucket"]):
        rows.append({
            "recommended_owner": owner,
            "reason": reason,
            "count": int(len(g)),
            "avg_runup_pct": round(float(g.runup_pct.mean()), 2),
            "symbols": ",".join((g.symbol + ":" + g.name.fillna("")).head(12).tolist()),
            "next_action": g.next_action.mode().iloc[0] if not g.empty else "",
        })
    return pd.DataFrame(rows).sort_values(["count", "avg_runup_pct"], ascending=[False, False])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    raw = load_atomic_daily_window(LOOKBACK, args.end)
    metrics = add_ma(compute_v2_metrics(raw))
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}

    all_runups = build_all_runups(metrics, args.start, args.end)
    candidates = pd.read_csv(LEGACY_V14_OUT / "enriched_candidates.csv")
    all_base = pd.read_csv(LEGACY_V14_OUT / "all_mode_trades.csv")
    base_trades = all_base[all_base.strategy_mode == "v1.4-balanced"].copy()
    stable_trades = pd.read_csv(STABLE_OUT / "s01_m05_trades.csv")

    diagnosed_all = diagnose(all_runups, candidates, base_trades, stable_trades, by_symbol)
    top50 = diagnosed_all.head(50).copy()
    gt50 = diagnosed_all[diagnosed_all.runup_pct >= 50].copy()
    gt30 = diagnosed_all[diagnosed_all.runup_pct >= 30].copy()

    diagnosed_all.to_csv(out / "all_runup_opportunities.csv", index=False)
    top50.to_csv(out / "top50_runup_diagnosis.csv", index=False)
    gt50.to_csv(out / "runup_ge_50_diagnosis.csv", index=False)
    gt30.to_csv(out / "runup_ge_30_diagnosis.csv", index=False)

    reason_top50 = reason_table(top50)
    reason_gt50 = reason_table(gt50)
    reason_gt30 = reason_table(gt30)
    reason_top50.to_csv(out / "top50_reason_summary.csv", index=False)
    reason_gt50.to_csv(out / "runup_ge_50_reason_summary.csv", index=False)
    reason_gt30.to_csv(out / "runup_ge_30_reason_summary.csv", index=False)

    cohorts = [
        summarize_cohort("top50", top50),
        summarize_cohort("runup_ge_50", gt50),
        summarize_cohort("runup_ge_30", gt30),
    ]
    summary = {
        "range": {"start": args.start, "end": args.end},
        "stock_count": int(metrics.symbol.nunique()),
        "cohorts": cohorts,
        "outputs": [
            "all_runup_opportunities.csv",
            "top50_runup_diagnosis.csv",
            "runup_ge_50_diagnosis.csv",
            "runup_ge_30_diagnosis.csv",
            "top50_reason_summary.csv",
            "runup_ge_50_reason_summary.csv",
            "runup_ge_30_reason_summary.csv",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    overview = pd.DataFrame(cohorts)
    readme = f"""# 强势样本机会反推

## 问题

不只看市场最强30，扩展到：

```text
波段涨幅 Top50
波段涨幅 >=50%
波段涨幅 >=30%
```

目标是判断：这些强势机会里，哪些是“资金流回调稳健策略”应该抓的，哪些应该拆给趋势中继或消息事件策略。

## 数据范围

- 区间：{args.start} ~ {args.end}
- 全市场股票数：{int(metrics.symbol.nunique())}
- 波段涨幅：任意低点到后续高点最大涨幅。

## 总览

{overview.to_markdown(index=False)}

## Top50 原因分布

{reason_top50.to_markdown(index=False)}

## 涨幅 >=50% 原因分布

{reason_gt50.to_markdown(index=False)}

## 结论

1. 当前稳健策略只覆盖强势机会的一小部分，原因不是单纯策略失败，而是强势股类型不同。
2. “成交额硬门槛错过”属于当前策略发现层可优化。
3. “启动前已涨过”“无标准回调承接”应拆给趋势中继策略。
4. “资金流特征不足”更可能需要消息事件重估策略解释。
5. “被组合风险/撤买单过滤”的强势票，要做风险模块误杀复核。

## 输出文件

- `all_runup_opportunities.csv`
- `top50_runup_diagnosis.csv`
- `runup_ge_50_diagnosis.csv`
- `runup_ge_30_diagnosis.csv`
- `top50_reason_summary.csv`
- `runup_ge_50_reason_summary.csv`
- `runup_ge_30_reason_summary.csv`
- `summary.json`
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
