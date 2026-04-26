from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window
from backend.scripts.run_strategy_v1_3_orderbook_filter import launch_cancel_buy_vs_hist
from backend.scripts.run_strategy_v1_4_modes import filter_reason as mode_filter_reason
from backend.scripts.run_strategy_v1_trend_reversal import add_ma, candidate_ok, find_launch, find_pullback_confirm, setup_score
from backend.scripts.research_trend_sample_factors import pct, slice_stats

START = "2026-03-02"
END = "2026-04-24"
LOOKBACK = "2026-01-01"
OUT = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-market-extreme-review")


def max_runup(g: pd.DataFrame) -> Dict[str, Any]:
    best = {"runup_pct": -999.0, "start_i": 0, "end_i": 0}
    min_low = None
    min_i = None
    for i, r in g.iterrows():
        low = float(r.low)
        high = float(r.high)
        if min_low is None or low < min_low:
            min_low = low
            min_i = i
        if min_low and min_low > 0:
            ru = pct(min_low, high)
            if ru > best["runup_pct"]:
                best = {"runup_pct": ru, "start_i": int(min_i), "end_i": int(i)}
    return best


def max_drawdown(g: pd.DataFrame) -> Dict[str, Any]:
    worst = {"drawdown_pct": 999.0, "start_i": 0, "end_i": 0}
    max_high = None
    max_i = None
    for i, r in g.iterrows():
        high = float(r.high)
        low = float(r.low)
        if max_high is None or high > max_high:
            max_high = high
            max_i = i
        if max_high and max_high > 0:
            dd = pct(max_high, low)
            if dd < worst["drawdown_pct"]:
                worst = {"drawdown_pct": dd, "start_i": int(max_i), "end_i": int(i)}
    return worst


def fetch_names(symbols: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i in range(0, len(symbols), 80):
        batch = ",".join(symbols[i : i + 80])
        url = "https://hq.sinajs.cn/list=" + batch
        try:
            req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"})
            text = urllib.request.urlopen(req, timeout=20).read().decode("gbk", "ignore")
            for sym, body in re.findall(r"var hq_str_(\w+)=\"([^\"]*)\";", text):
                name = body.split(",")[0].strip()
                if name:
                    out[sym] = name
        except Exception:
            pass
    return out


def build_extremes(metrics: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    scoped = metrics[(metrics.trade_date >= START) & (metrics.trade_date <= END)].copy()
    for sym, g0 in scoped.groupby("symbol", sort=False):
        g = g0.sort_values("trade_date").reset_index(drop=True)
        if len(g) < 10:
            continue
        ru = max_runup(g)
        dd = max_drawdown(g)
        rows.append({
            "symbol": sym,
            "runup_pct": round(float(ru["runup_pct"]), 2),
            "runup_start_date": str(g.loc[ru["start_i"], "trade_date"]),
            "runup_end_date": str(g.loc[ru["end_i"], "trade_date"]),
            "runup_start_price": round(float(g.loc[ru["start_i"], "low"]), 3),
            "runup_end_price": round(float(g.loc[ru["end_i"], "high"]), 3),
            "drawdown_pct": round(float(dd["drawdown_pct"]), 2),
            "drawdown_start_date": str(g.loc[dd["start_i"], "trade_date"]),
            "drawdown_end_date": str(g.loc[dd["end_i"], "trade_date"]),
            "drawdown_start_price": round(float(g.loc[dd["start_i"], "high"]), 3),
            "drawdown_end_price": round(float(g.loc[dd["end_i"], "low"]), 3),
            "period_return_pct": round(pct(float(g.close.iloc[0]), float(g.close.iloc[-1])), 2),
            "amount_avg": round(float(g.total_amount.mean()), 2),
        })
    df = pd.DataFrame(rows)
    top = df.sort_values(["runup_pct", "amount_avg"], ascending=[False, False]).head(30).copy()
    bottom = df.sort_values(["drawdown_pct", "amount_avg"], ascending=[True, False]).head(30).copy()
    names = fetch_names(sorted(set(top.symbol.tolist() + bottom.symbol.tolist())))
    top["name"] = top.symbol.map(names).fillna("")
    bottom["name"] = bottom.symbol.map(names).fillna("")
    return top, bottom


def nearest_candidate_analysis(sym: str, anchor_date: str, by_symbol: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    g = by_symbol.get(sym)
    if g is None or g.empty:
        return {"stage": "no_data"}
    idxs = g.index[g.trade_date <= anchor_date].tolist()
    if not idxs:
        return {"stage": "no_prior_data"}
    i = idxs[-1]
    if i < 8:
        return {"stage": "insufficient_lookback", "nearest_date": str(g.loc[i, "trade_date"])}
    pre20 = slice_stats(g, i - 20, i - 1, "pre20")
    pre5 = slice_stats(g, i - 5, i - 1, "pre5")
    current = g.loc[i]
    sc = setup_score(pre20, pre5, current)
    ok = candidate_ok(pre20, pre5, current, sc)
    launch_start, launch_end, launch_meta = find_launch(g, str(g.loc[i, "trade_date"]))
    pull_date = None
    pull_reason = "no_launch"
    pull_meta: Dict[str, Any] = {}
    if launch_end:
        pull_date, pull_reason, pull_meta = find_pullback_confirm(g, launch_start, launch_end)
    rec = {
        "nearest_date": str(g.loc[i, "trade_date"]),
        "setup_score_at_anchor": sc,
        "candidate_ok_at_anchor": bool(ok),
        "anchor_pre20_return_pct": pre20.get("pre20_return_pct"),
        "anchor_pre20_super_price_divergence": pre20.get("pre20_super_price_divergence"),
        "anchor_pre20_main_price_divergence": pre20.get("pre20_main_price_divergence"),
        "anchor_pre5_return_pct": pre5.get("pre5_return_pct"),
        "anchor_pre5_super_price_divergence": pre5.get("pre5_super_price_divergence"),
        "anchor_total_amount": float(current.total_amount),
        "anchor_launch_start": launch_start,
        "anchor_launch_end": launch_end,
        "anchor_pullback_confirm_date": pull_date,
        "anchor_pullback_reason": pull_reason,
        **{f"anchor_{k}": v for k, v in launch_meta.items() if k in ["launch3_return_pct", "launch3_super_net_ratio", "launch3_main_net_ratio", "launch3_max_drawdown_pct"]},
        **{f"anchor_{k}": v for k, v in pull_meta.items() if k in ["pullback_super_net_ratio", "pullback_main_net_ratio", "pullback_support_spread_avg", "confirm_distribution_score"]},
    }
    if not ok:
        reason = []
        if float(current.total_amount or 0) < 250_000_000:
            reason.append("成交额<2.5亿")
        if sc < 50:
            reason.append("setup_score<50")
        if float(pre20.get("pre20_return_pct", 0) or 0) > 12:
            reason.append("前20日涨幅>12")
        if float(pre5.get("pre5_return_pct", 0) or 0) > 8:
            reason.append("前5日涨幅>8")
        if max(float(pre20.get("pre20_super_price_divergence", 0) or 0), float(pre20.get("pre20_main_price_divergence", 0) or 0), float(pre5.get("pre5_super_price_divergence", 0) or 0)) <= 0.015:
            reason.append("资金价格背离不足")
        rec["primary_miss_reason_at_anchor"] = ";".join(reason)
    elif not launch_start:
        rec["primary_miss_reason_at_anchor"] = "候选通过但未找到启动3日"
    elif not pull_date:
        rec["primary_miss_reason_at_anchor"] = "启动通过但未等到回调承接"
    else:
        rec["primary_miss_reason_at_anchor"] = "锚点附近链路可通过"
    return rec


def match_strategy(extreme: pd.DataFrame, kind: str, candidates: pd.DataFrame, trades: pd.DataFrame, by_symbol: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for _, r in extreme.iterrows():
        sym = str(r.symbol)
        anchor_date = str(r.runup_start_date if kind == "top" else r.drawdown_start_date)
        c = candidates[candidates.symbol == sym].copy()
        t = trades[trades.symbol == sym].copy()
        v13 = t[t.strategy_mode == "v1.3"] if "strategy_mode" in t.columns else pd.DataFrame()
        v14b = t[t.strategy_mode == "v1.4-balanced"] if "strategy_mode" in t.columns else pd.DataFrame()
        v14q = t[t.strategy_mode == "v1.4-quality"] if "strategy_mode" in t.columns else pd.DataFrame()

        filter_reasons = []
        if not c.empty:
            for _, cr in c.iterrows():
                reason = mode_filter_reason(cr.to_dict(), "v1.4-balanced")
                if reason:
                    filter_reasons.append(f"{cr.get('discovery_date')}:{reason}")
        analysis = nearest_candidate_analysis(sym, anchor_date, by_symbol)
        rows.append({
            **r.to_dict(),
            "strategy_candidate_count": int(len(c)),
            "candidate_dates": ",".join(c.discovery_date.astype(str).head(8).tolist()) if not c.empty else "",
            "has_pullback_confirm_candidate": bool((c.pullback_confirm_date.notna()).any()) if not c.empty else False,
            "v1_3_trade_count": int(len(v13)),
            "v1_3_best_return": round(float(v13.net_return_pct.max()), 2) if not v13.empty else None,
            "v1_3_entry_dates": ",".join(v13.entry_date.astype(str).head(5).tolist()) if not v13.empty else "",
            "v1_4_balanced_trade_count": int(len(v14b)),
            "v1_4_balanced_best_return": round(float(v14b.net_return_pct.max()), 2) if not v14b.empty else None,
            "v1_4_quality_trade_count": int(len(v14q)),
            "v1_4_quality_best_return": round(float(v14q.net_return_pct.max()), 2) if not v14q.empty else None,
            "balanced_filter_reasons": "|".join(filter_reasons[:6]),
            **analysis,
        })
    return pd.DataFrame(rows)


def summarize_matches(top_match: pd.DataFrame, bottom_match: pd.DataFrame) -> Dict[str, Any]:
    def s(df: pd.DataFrame) -> Dict[str, Any]:
        return {
            "count": int(len(df)),
            "candidate_hit": int((df.strategy_candidate_count > 0).sum()),
            "v1_3_trade_hit": int((df.v1_3_trade_count > 0).sum()),
            "v1_4_balanced_trade_hit": int((df.v1_4_balanced_trade_count > 0).sum()),
            "v1_4_quality_trade_hit": int((df.v1_4_quality_trade_count > 0).sum()),
            "anchor_candidate_ok": int((df.candidate_ok_at_anchor == True).sum()) if "candidate_ok_at_anchor" in df else 0,
            "top_miss_reasons": df.get("primary_miss_reason_at_anchor", pd.Series(dtype=str)).value_counts().head(10).to_dict(),
        }
    return {"top30": s(top_match), "bottom30": s(bottom_match)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = load_atomic_daily_window(LOOKBACK, END)
    metrics = add_ma(compute_v2_metrics(raw))
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}
    top, bottom = build_extremes(metrics)
    top.to_csv(OUT / "market_top30_runup.csv", index=False)
    bottom.to_csv(OUT / "market_bottom30_drawdown.csv", index=False)

    cand_path = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes/enriched_candidates.csv")
    trades_path = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes/all_mode_trades.csv")
    candidates = pd.read_csv(cand_path)
    trades = pd.read_csv(trades_path)
    top_match = match_strategy(top, "top", candidates, trades, by_symbol)
    bottom_match = match_strategy(bottom, "bottom", candidates, trades, by_symbol)
    top_match.to_csv(OUT / "top30_strategy_match.csv", index=False)
    bottom_match.to_csv(OUT / "bottom30_strategy_match.csv", index=False)
    summary = summarize_matches(top_match, bottom_match)
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 市场极端样本反推：最强30 / 最弱30 与策略匹配",
        "",
        "## 样本定义",
        "",
        "- 最强30：2026-03-02 ~ 2026-04-24 区间内，任意低点到后续高点的最大波段涨幅 Top30。",
        "- 最弱30：同区间内，任意高点到后续低点的最大回撤 Top30。",
        "",
        "## 命中概览",
        "",
        pd.DataFrame([
            {"sample": "top30", **summary["top30"]},
            {"sample": "bottom30", **summary["bottom30"]},
        ]).drop(columns=["top_miss_reasons"]).to_markdown(index=False),
        "",
        "## 最强30 未命中/卡点原因 Top",
        "",
        pd.Series(summary["top30"]["top_miss_reasons"]).to_frame("count").to_markdown(),
        "",
        "## 最弱30 卡点原因 Top",
        "",
        pd.Series(summary["bottom30"]["top_miss_reasons"]).to_frame("count").to_markdown(),
        "",
        "## 最强30 摘要",
        "",
        top_match[["symbol", "name", "runup_pct", "runup_start_date", "runup_end_date", "strategy_candidate_count", "v1_3_trade_count", "v1_4_balanced_trade_count", "primary_miss_reason_at_anchor"]].to_markdown(index=False),
        "",
        "## 文件",
        "",
        "- market_top30_runup.csv",
        "- market_bottom30_drawdown.csv",
        "- top30_strategy_match.csv",
        "- bottom30_strategy_match.csv",
        "- summary.json",
        "",
    ]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
