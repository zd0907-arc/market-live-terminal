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
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.research_trend_sample_factors import slice_stats, pct
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams, simulate_trade_v1_2
from backend.scripts.run_strategy_v1_3_orderbook_filter import launch_cancel_buy_vs_hist
from backend.scripts.run_strategy_v1_4_modes import filter_reason as m04b_filter_reason
from backend.scripts.run_strategy_v1_trend_reversal import add_ma, find_launch, find_pullback_confirm, setup_score
from backend.scripts.research_combined_risk_stack_robustness import enrich_one

DEFAULT_OUT = Path("docs/strategy-rework/strategies/S01-capital-trend-reversal/experiments/EXP-20260427-liquidity-gate-variants")


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def max_runup_local(g: pd.DataFrame) -> Dict[str, Any]:
    best = {"runup_pct": -999.0, "start_i": 0, "end_i": 0}
    min_low = None
    min_i = None
    for i, r in g.iterrows():
        low = float(r.low); high = float(r.high)
        if min_low is None or low < min_low:
            min_low = low; min_i = i
        if min_low and min_low > 0:
            ru = pct(min_low, high)
            if ru > best["runup_pct"]:
                best = {"runup_pct": ru, "start_i": int(min_i), "end_i": int(i)}
    return best


def build_runups(metrics: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    rows = []
    scoped = metrics[(metrics.trade_date >= start) & (metrics.trade_date <= end)].copy()
    for sym, g0 in scoped.groupby("symbol", sort=False):
        g = g0.sort_values("trade_date").reset_index(drop=True)
        if len(g) < 10: continue
        ru = max_runup_local(g); si = ru["start_i"]; ei = ru["end_i"]
        rows.append({
            "symbol": sym,
            "runup_pct": round(float(ru["runup_pct"]), 2),
            "runup_start_date": str(g.loc[si, "trade_date"]),
            "runup_end_date": str(g.loc[ei, "trade_date"]),
            "amount_avg": round(float(g.total_amount.mean()), 2),
        })
    df = pd.DataFrame(rows).sort_values(["runup_pct", "amount_avg"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "runup_rank", range(1, len(df) + 1))
    return df


def amount_features(g: pd.DataFrame, i: int) -> Dict[str, float]:
    cur = float(g.loc[i].total_amount or 0.0)
    hist20 = g.iloc[max(0, i - 20):i]
    hist60 = g.iloc[max(0, i - 60):i]
    avg20 = float(hist20.total_amount.mean()) if not hist20.empty else 0.0
    med20 = float(hist20.total_amount.median()) if not hist20.empty else 0.0
    pct60 = float((hist60.total_amount <= cur).mean()) if not hist60.empty else 0.0
    return {"amount": cur, "amount_avg20": avg20, "amount_med20": med20, "amount_ratio20": cur / max(avg20, 1.0), "amount_ratio20_median": cur / max(med20, 1.0), "amount_percentile60": pct60}


def price_fund_gate(pre20: Dict[str, Any], pre5: Dict[str, Any], score: float) -> bool:
    if score < 50: return False
    if fnum(pre20.get("pre20_return_pct")) > 12: return False
    if fnum(pre5.get("pre5_return_pct")) > 8: return False
    if max(fnum(pre20.get("pre20_super_price_divergence")), fnum(pre20.get("pre20_main_price_divergence")), fnum(pre5.get("pre5_super_price_divergence"))) <= 0.015:
        return False
    return True


def liquidity_gate(mode: str, af: Dict[str, float]) -> bool:
    amount = af["amount"]; ratio = af["amount_ratio20"]; pct60 = af["amount_percentile60"]
    if mode == "current_abs_250m": return amount >= 250_000_000
    if mode == "abs_100m": return amount >= 100_000_000
    if mode == "hybrid_100m_rel": return amount >= 100_000_000 and (ratio >= 1.15 or pct60 >= 0.70 or amount >= 250_000_000)
    if mode == "hybrid_80m_rel_or_abs": return amount >= 80_000_000 and (ratio >= 1.20 or pct60 >= 0.75 or amount >= 250_000_000)
    if mode == "hybrid_60m_strong_rel": return amount >= 60_000_000 and (ratio >= 1.50 or pct60 >= 0.85)
    raise ValueError(mode)


def build_base_rows(metrics: pd.DataFrame, start: str, end: str) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}
    days = sorted(metrics[(metrics.trade_date >= start) & (metrics.trade_date <= end)].trade_date.unique().tolist())
    rows: List[Dict[str, Any]] = []
    for day in days:
        for sym, g in by_symbol.items():
            idxs = g.index[g.trade_date == day].tolist()
            if not idxs: continue
            i = idxs[0]
            if i < 8: continue
            pre20 = slice_stats(g, i - 20, i - 1, "pre20")
            pre5 = slice_stats(g, i - 5, i - 1, "pre5")
            current = g.loc[i]
            sc = setup_score(pre20, pre5, current)
            if not price_fund_gate(pre20, pre5, sc): continue
            af = amount_features(g, i)
            # 只保留可能被任何一个流动性规则选中的行。
            if af["amount"] < 60_000_000: continue
            rel_bonus = min(8.0, max(0.0, (af["amount_ratio20"] - 1.0) * 4.0)) + min(4.0, max(0.0, (af["amount_percentile60"] - 0.6) * 10.0))
            rows.append({
                "discovery_date": day, "symbol": sym, "base_setup_score": sc, "relative_rank_score": round(sc + rel_bonus, 2),
                **af,
                "pre20_return_pct": pre20.get("pre20_return_pct"), "pre20_super_price_divergence": pre20.get("pre20_super_price_divergence"), "pre20_main_price_divergence": pre20.get("pre20_main_price_divergence"),
                "pre5_return_pct": pre5.get("pre5_return_pct"), "pre5_super_price_divergence": pre5.get("pre5_super_price_divergence"),
            })
    return pd.DataFrame(rows), by_symbol


def candidates_for_mode(base_rows: pd.DataFrame, by_symbol: Dict[str, pd.DataFrame], mode: str, top_n: int, cache: Dict[Tuple[str, str], Dict[str, Any]]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    if base_rows.empty: return recs
    work = base_rows[base_rows.apply(lambda r: liquidity_gate(mode, r.to_dict()), axis=1)].copy()
    if work.empty: return recs
    work["setup_score"] = work["base_setup_score"] if mode == "current_abs_250m" else work["relative_rank_score"]
    for day, gday in work.groupby("discovery_date", sort=True):
        top = gday.sort_values(["setup_score", "symbol"], ascending=[False, True]).head(top_n)
        for rank, row in enumerate(top.to_dict("records"), start=1):
            sym = row["symbol"]; key = (sym, str(day))
            if key not in cache:
                g = by_symbol[sym]
                launch_start, launch_end, launch_meta = find_launch(g, str(day))
                pull_date = None; pull_reason = "no_launch"; pull_meta: Dict[str, Any] = {}
                if launch_end:
                    pull_date, pull_reason, pull_meta = find_pullback_confirm(g, launch_start, launch_end)
                extra = {"launch_start_date": launch_start, "launch_end_date": launch_end, "pullback_confirm_date": pull_date, "pullback_confirm_reason": pull_reason}
                extra.update({k: v for k, v in launch_meta.items() if k in ["launch3_return_pct", "launch3_super_net_ratio", "launch3_main_net_ratio", "launch3_max_drawdown_pct", "launch3_add_buy_ratio"]})
                extra.update({k: v for k, v in pull_meta.items() if k in ["pullback_super_net_ratio", "pullback_main_net_ratio", "pullback_support_spread_avg", "pullback_depth_from_launch_peak_pct", "confirm_distribution_score"]})
                if launch_start and launch_end: extra.update(launch_cancel_buy_vs_hist(g, str(launch_start), str(launch_end)))
                else: extra.update({"order_filter_available": False, "orderbook_filter_reason": "no_launch"})
                cache[key] = extra
            recs.append({**row, "strategy_mode": mode, "rank": rank, **cache[key]})
    return recs


def stable_filter_reason(rec: Dict[str, Any], by_symbol: Dict[str, pd.DataFrame]) -> str:
    base = m04b_filter_reason(rec, "v1.4-balanced")
    if base: return base
    if not rec.get("pullback_confirm_date"): return ""
    try:
        enriched = enrich_one(by_symbol[str(rec["symbol"])], pd.Series(rec))
        if int(enriched.get("risk_count_R1_R5") or 0) >= 2: return "combined_risk_ge_2"
    except Exception as exc:
        return f"risk_calc_error:{type(exc).__name__}"
    return ""


def future_days_after_entry(g: pd.DataFrame, entry_date: str) -> int:
    return int((g.trade_date >= entry_date).sum())


def simulate_stable(candidates: List[Dict[str, Any]], by_symbol: Dict[str, pd.DataFrame], min_future_days: int) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    trade_cost_params = SelectionV2Params()
    passed: List[Dict[str, Any]] = []; filtered: List[Dict[str, Any]] = []; trades: List[Dict[str, Any]] = []
    for rec in candidates:
        reason = stable_filter_reason(rec, by_symbol)
        tagged = {**rec, "filter_reason": reason}
        if reason:
            filtered.append(tagged); continue
        passed.append(tagged)
        pull_date = tagged.get("pullback_confirm_date")
        if not pull_date: continue
        trade = simulate_trade_v1_2(by_symbol[str(tagged["symbol"])], str(pull_date), exit_params, trade_cost_params)
        if not trade or trade.get("skipped"): continue
        fdays = future_days_after_entry(by_symbol[str(tagged["symbol"])], str(trade["entry_date"]))
        trades.append({**tagged, **trade, "future_days_available": fdays, "is_mature_trade": fdays >= min_future_days})
    return pd.DataFrame(passed), pd.DataFrame(filtered), pd.DataFrame(trades)


def strong_coverage(trades: pd.DataFrame, candidates: pd.DataFrame, runups: pd.DataFrame, threshold: float) -> Dict[str, Any]:
    strong = runups[runups.runup_pct >= threshold]
    syms = set(str(s) for s in strong.symbol)
    cand_syms = set(str(s) for s in candidates.symbol.unique()) if not candidates.empty else set()
    trade_syms = set(str(s) for s in trades.symbol.unique()) if not trades.empty else set()
    return {"strong_count": int(len(strong)), "candidate_symbol_hit_count": int(len(syms & cand_syms)), "trade_symbol_hit_count": int(len(syms & trade_syms)), "candidate_symbol_hit_rate_pct": round(len(syms & cand_syms) / max(len(syms), 1) * 100, 2), "trade_symbol_hit_rate_pct": round(len(syms & trade_syms) / max(len(syms), 1) * 100, 2)}


def summarize_df(df: pd.DataFrame) -> Dict[str, Any]:
    return summarize(df.to_dict("records") if not df.empty else [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02"); parser.add_argument("--end", default="2026-04-24"); parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10); parser.add_argument("--min-future-days", type=int, default=10); parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    raw = load_atomic_daily_window("2026-01-01", args.replay_end)
    metrics = add_ma(compute_v2_metrics(raw))
    runups = build_runups(metrics, args.start, args.end); runups.to_csv(out / "all_runup_opportunities.csv", index=False)
    base_rows, by_symbol = build_base_rows(metrics, args.start, args.end); base_rows.to_csv(out / "base_candidate_pool.csv", index=False)

    modes = ["current_abs_250m", "abs_100m", "hybrid_100m_rel", "hybrid_80m_rel_or_abs", "hybrid_60m_strong_rel"]
    cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    rows = []; all_c = []; all_f = []; all_t = []
    for mode in modes:
        cands = candidates_for_mode(base_rows, by_symbol, mode, args.top_n, cache)
        passed, filtered, trades = simulate_stable(cands, by_symbol, args.min_future_days)
        cdf = pd.DataFrame(cands); cdf["liquidity_mode"] = mode if not cdf.empty else mode
        if not filtered.empty: filtered["liquidity_mode"] = mode
        if not trades.empty: trades["liquidity_mode"] = mode
        all_c.append(cdf); all_f.append(filtered); all_t.append(trades)
        mature = trades[trades.is_mature_trade.astype(bool)] if not trades.empty else pd.DataFrame()
        row = {"liquidity_mode": mode, "candidate_rows": len(cands), "passed_rows": int(len(passed)), "filtered_rows": int(len(filtered)), "trade_rows": int(len(trades))}
        for prefix, df in [("full", trades), ("mature", mature)]:
            for k, v in summarize_df(df).items(): row[f"{prefix}_{k}"] = v
        for th in [30, 50]:
            for k, v in strong_coverage(trades, cdf, runups, th).items(): row[f"ge{th}_{k}"] = v
        top50 = runups.head(50); row["top50_candidate_symbol_hit_count"] = int(len(set(top50.symbol) & set(cdf.symbol.unique()))) if not cdf.empty else 0; row["top50_trade_symbol_hit_count"] = int(len(set(top50.symbol) & set(trades.symbol.unique()))) if not trades.empty else 0
        rows.append(row)

    pd.DataFrame(rows).to_csv(out / "liquidity_variant_summary.csv", index=False)
    pd.concat(all_c, ignore_index=True).to_csv(out / "all_variant_candidates.csv", index=False)
    pd.concat([x for x in all_f if not x.empty], ignore_index=True).to_csv(out / "all_variant_filtered.csv", index=False)
    pd.concat([x for x in all_t if not x.empty], ignore_index=True).to_csv(out / "all_variant_trades.csv", index=False)
    summary = {"range": {"start": args.start, "end": args.end, "replay_end": args.replay_end, "top_n": args.top_n}, "modes": modes, "rows": rows}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    table = pd.DataFrame(rows)
    cols = ["liquidity_mode", "candidate_rows", "mature_trade_count", "mature_win_rate", "mature_avg_return_pct", "mature_median_return_pct", "mature_min_return_pct", "top50_candidate_symbol_hit_count", "top50_trade_symbol_hit_count", "ge50_candidate_symbol_hit_count", "ge50_trade_symbol_hit_count", "ge30_candidate_symbol_hit_count", "ge30_trade_symbol_hit_count"]
    table_cols = [c for c in cols if c in table.columns]
    readme = f"""# 成交额发现层替代规则实验

## 问题

当前强势样本覆盖面窄，大量股票被 `2.5亿成交额硬门槛` 卡掉。本实验只替换发现层成交额规则，买点、组合风险过滤、出场逻辑保持不变。

## 测试规则

- `current_abs_250m`：当前硬门槛，成交额 >=2.5亿。
- `abs_100m`：简单放宽到 >=1亿。
- `hybrid_100m_rel`：>=1亿，且相对20日均额或60日分位有放大。
- `hybrid_80m_rel_or_abs`：>=8000万，且相对放量/高分位/或绝对达到2.5亿。
- `hybrid_60m_strong_rel`：>=6000万，但要求强相对放量。

## 核心结果

{table[table_cols].to_markdown(index=False)}

## 输出文件

- `liquidity_variant_summary.csv`
- `base_candidate_pool.csv`
- `all_variant_candidates.csv`
- `all_variant_filtered.csv`
- `all_variant_trades.csv`
- `all_runup_opportunities.csv`
- `summary.json`
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    print(table[table_cols].to_string(index=False))


if __name__ == "__main__":
    main()
