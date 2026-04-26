from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window

START = "2026-03-02"
END = "2026-04-24"
OUT = Path("docs/strategy-rework/experiments/20260426-cumulative-l2-flow")
OUT.mkdir(parents=True, exist_ok=True)


def pct(a: float, b: float) -> float:
    return ((b / a) - 1.0) * 100.0 if a and a > 0 else 0.0


def max_drawdown_from_series(values: List[float]) -> float:
    peak = None
    mdd = 0.0
    for v in values:
        if peak is None or v > peak:
            peak = v
        if peak and peak > 0:
            mdd = min(mdd, (v / peak - 1.0) * 100.0)
    return mdd

raw = load_atomic_daily_window("2026-01-01", END)
metrics = compute_v2_metrics(raw)
window = metrics[(metrics.trade_date >= START) & (metrics.trade_date <= END)].copy()

samples: List[Dict[str, Any]] = []
anchor_rows: List[Dict[str, Any]] = []
for sym, g0 in window.groupby("symbol", sort=False):
    g = g0.sort_values("trade_date").reset_index(drop=True)
    if len(g) < 20:
        continue
    closes = g.close.astype(float).tolist()
    lows = g.low.astype(float).tolist()
    highs = g.high.astype(float).tolist()
    amounts = g.total_amount.astype(float).tolist()
    best = None
    # 任意锚点后 8~40 个交易日内最大涨幅，提取趋势样本，不要求从3月2日开始。
    for i in range(0, len(g) - 8):
        anchor_close = float(g.loc[i, "close"])
        future = g.iloc[i + 1 : min(len(g), i + 41)].copy()
        if future.empty or anchor_close <= 0:
            continue
        j_rel = int((future.high.astype(float) / anchor_close).idxmax())
        peak_row = g.loc[j_rel]
        runup = pct(anchor_close, float(peak_row.high))
        if best is None or runup > best["max_runup_pct"]:
            segment = g.iloc[i : j_rel + 1]
            best = {
                "symbol": sym,
                "anchor_date": str(g.loc[i, "trade_date"]),
                "anchor_close": round(anchor_close, 3),
                "peak_date": str(peak_row.trade_date),
                "peak_high": round(float(peak_row.high), 3),
                "days_to_peak": int(j_rel - i),
                "max_runup_pct": round(runup, 2),
                "end_close_return_pct": round(pct(anchor_close, float(g.close.iloc[-1])), 2),
                "segment_mdd_pct": round(max_drawdown_from_series(segment.close.astype(float).tolist()), 2),
                "avg_amount": round(float(segment.total_amount.mean()), 2),
                "cum_l2_main_net": round(float(segment.l2_main_net_amount.sum()), 2),
                "cum_l2_super_net": round(float(segment.l2_super_net_amount.sum()), 2),
                "cum_amount": round(float(segment.total_amount.sum()), 2),
                "cum_l2_main_net_ratio": round(float(segment.l2_main_net_amount.sum() / max(segment.total_amount.sum(), 1)), 5),
                "cum_l2_super_net_ratio": round(float(segment.l2_super_net_amount.sum() / max(segment.total_amount.sum(), 1)), 5),
                "positive_super_day_ratio": round(float((segment.l2_super_net_amount > 0).mean()), 4),
                "positive_main_day_ratio": round(float((segment.l2_main_net_amount > 0).mean()), 4),
                "max_daily_super_outflow_ratio": round(float((segment.l2_super_net_amount / segment.total_amount.replace(0, pd.NA)).min()), 5),
                "max_daily_main_outflow_ratio": round(float((segment.l2_main_net_amount / segment.total_amount.replace(0, pd.NA)).min()), 5),
                "return_20d_at_anchor": round(float(g.loc[i].get("return_20d_pct") or 0), 2),
                "l2_super_net_ratio_at_anchor": round(float(g.loc[i].get("l2_super_net_ratio") or 0), 5),
                "l2_main_net_ratio_at_anchor": round(float(g.loc[i].get("l2_main_net_ratio") or 0), 5),
                "amount_anomaly_at_anchor": round(float(g.loc[i].get("amount_anomaly_20d") or 0), 3),
            }
    if best and best["max_runup_pct"] >= 50 and best["days_to_peak"] >= 5 and best["avg_amount"] >= 300_000_000:
        samples.append(best)

# 生成全部候选中按涨幅排序的正样本。
samples_df = pd.DataFrame(samples).sort_values(["max_runup_pct", "cum_l2_super_net_ratio"], ascending=[False, False])
samples_df.to_csv(OUT / "trend_positive_samples.csv", index=False)

# 对趋势样本，从 anchor 开始逐日累计资金，方便看资金是否跑掉。
positive_symbols = set(samples_df.head(120).symbol.tolist())
for _, sample in samples_df.head(120).iterrows():
    sym = sample.symbol
    anchor = sample.anchor_date
    g = window[(window.symbol == sym) & (window.trade_date >= anchor)].sort_values("trade_date").copy()
    if g.empty:
        continue
    anchor_close = float(g.close.iloc[0])
    g["cum_l2_super_net"] = g.l2_super_net_amount.cumsum()
    g["cum_l2_main_net"] = g.l2_main_net_amount.cumsum()
    g["cum_amount"] = g.total_amount.cumsum()
    g["cum_l2_super_net_ratio"] = g["cum_l2_super_net"] / g["cum_amount"].replace(0, pd.NA)
    g["cum_l2_main_net_ratio"] = g["cum_l2_main_net"] / g["cum_amount"].replace(0, pd.NA)
    g["return_from_anchor_pct"] = (g.close / anchor_close - 1.0) * 100.0
    peak_close_so_far = g.close.cummax()
    g["drawdown_from_peak_pct"] = (g.close / peak_close_so_far - 1.0) * 100.0
    for _, r in g.iterrows():
        anchor_rows.append({
            "symbol": sym,
            "anchor_date": anchor,
            "trade_date": str(r.trade_date),
            "return_from_anchor_pct": round(float(r.return_from_anchor_pct), 2),
            "drawdown_from_peak_pct": round(float(r.drawdown_from_peak_pct), 2),
            "l2_super_net_ratio": round(float(r.l2_super_net_ratio or 0), 5),
            "l2_main_net_ratio": round(float(r.l2_main_net_ratio or 0), 5),
            "cum_l2_super_net_ratio": round(float(r.cum_l2_super_net_ratio or 0), 5),
            "cum_l2_main_net_ratio": round(float(r.cum_l2_main_net_ratio or 0), 5),
            "cum_l2_super_net": round(float(r.cum_l2_super_net or 0), 2),
            "cum_l2_main_net": round(float(r.cum_l2_main_net or 0), 2),
        })
pd.DataFrame(anchor_rows).to_csv(OUT / "trend_sample_anchor_cumulative_flows.csv", index=False)

# 对上一轮二次确认交易，计算 entry 到 exit 的累计超大单状态。
trade_path = Path("docs/strategy-rework/experiments/20260426-quick-validation/confirmed_trades.csv")
trade_flow_rows = []
if trade_path.exists():
    trades = pd.read_csv(trade_path)
    for _, t in trades.iterrows():
        sym = str(t.symbol)
        entry = str(t.entry_date)
        exit_signal = str(t.exit_signal_date)
        g = window[(window.symbol == sym) & (window.trade_date >= entry) & (window.trade_date <= exit_signal)].sort_values("trade_date")
        if g.empty:
            continue
        cum_amount = float(g.total_amount.sum())
        cum_super = float(g.l2_super_net_amount.sum())
        cum_main = float(g.l2_main_net_amount.sum())
        neg_super_days = int((g.l2_super_net_amount < 0).sum())
        neg_main_days = int((g.l2_main_net_amount < 0).sum())
        trade_flow_rows.append({
            "signal_date": str(t.signal_date),
            "symbol": sym,
            "entry_date": entry,
            "exit_signal_date": exit_signal,
            "net_return_pct": float(t.net_return_pct),
            "exit_reason": str(t.exit_reason),
            "cum_l2_super_net_ratio_entry_to_exit_signal": round(cum_super / max(cum_amount, 1), 5),
            "cum_l2_main_net_ratio_entry_to_exit_signal": round(cum_main / max(cum_amount, 1), 5),
            "cum_l2_super_net_entry_to_exit_signal": round(cum_super, 2),
            "cum_l2_main_net_entry_to_exit_signal": round(cum_main, 2),
            "neg_super_day_ratio": round(neg_super_days / len(g), 4),
            "neg_main_day_ratio": round(neg_main_days / len(g), 4),
            "holding_observed_days": len(g),
        })
trade_flows_df = pd.DataFrame(trade_flow_rows)
trade_flows_df.to_csv(OUT / "confirmed_trade_entry_to_exit_cumulative_flows.csv", index=False)

summary = {
    "range": {"start": START, "end": END},
    "positive_sample_count_runup_ge_50": int(len(samples_df)),
    "top_positive_samples": samples_df.head(30).to_dict(orient="records"),
}
if not trade_flows_df.empty:
    trade_flows_df["super_cum_positive"] = trade_flows_df.cum_l2_super_net_ratio_entry_to_exit_signal > 0
    summary["confirmed_trade_flow_stats"] = {
        "count": int(len(trade_flows_df)),
        "avg_return_when_cum_super_positive": round(float(trade_flows_df[trade_flows_df.super_cum_positive].net_return_pct.mean()), 2),
        "avg_return_when_cum_super_negative": round(float(trade_flows_df[~trade_flows_df.super_cum_positive].net_return_pct.mean()), 2),
        "win_rate_when_cum_super_positive": round(float((trade_flows_df[trade_flows_df.super_cum_positive].net_return_pct > 0).mean() * 100), 2),
        "win_rate_when_cum_super_negative": round(float((trade_flows_df[~trade_flows_df.super_cum_positive].net_return_pct > 0).mean() * 100), 2),
        "exit_signals_with_positive_cum_super": int(trade_flows_df.super_cum_positive.sum()),
        "exit_signals_with_negative_cum_super": int((~trade_flows_df.super_cum_positive).sum()),
    }
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

lines = ["# 累计 L2 资金流探索", "", f"区间：{START} ~ {END}", "", f"大趋势正样本数（任意锚点后5~40日最高涨幅>=50%，成交额>=3亿）：{len(samples_df)}", "", "## Top 20 正样本", ""]
if not samples_df.empty:
    cols = ["symbol", "anchor_date", "peak_date", "days_to_peak", "max_runup_pct", "end_close_return_pct", "cum_l2_super_net_ratio", "cum_l2_main_net_ratio", "positive_super_day_ratio", "max_daily_super_outflow_ratio"]
    lines.append(samples_df.head(20)[cols].to_markdown(index=False))
if not trade_flows_df.empty:
    s = summary["confirmed_trade_flow_stats"]
    lines += ["", "## 当前二次确认交易：从入场到卖出信号的累计超大单", "", f"- 累计超大单仍为正的交易数：{s['exit_signals_with_positive_cum_super']}", f"- 累计超大单转负的交易数：{s['exit_signals_with_negative_cum_super']}", f"- 累计超大单为正时平均收益：{s['avg_return_when_cum_super_positive']}%，胜率：{s['win_rate_when_cum_super_positive']}%", f"- 累计超大单为负时平均收益：{s['avg_return_when_cum_super_negative']}%，胜率：{s['win_rate_when_cum_super_negative']}%"]
(OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2)[:8000])
