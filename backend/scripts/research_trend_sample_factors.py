from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window

START = "2026-03-02"
END = "2026-04-24"
LOOKBACK = "2026-01-01"
OUT = Path("docs/strategy-rework/experiments/20260426-trend-factor-research")
OUT.mkdir(parents=True, exist_ok=True)


def safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b and abs(float(b)) > 1e-9 else 0.0


def pct(a: float, b: float) -> float:
    return ((b / a) - 1.0) * 100.0 if a and a > 0 else 0.0


def max_drawdown(values: List[float]) -> float:
    peak = None
    mdd = 0.0
    for v in values:
        if peak is None or v > peak:
            peak = v
        if peak and peak > 0:
            mdd = min(mdd, (v / peak - 1.0) * 100.0)
    return mdd


def max_runup_after(g: pd.DataFrame, i: int, min_days: int = 5, max_days: int = 40) -> Tuple[float, int]:
    anchor_close = float(g.loc[i, "close"])
    if anchor_close <= 0 or i + min_days >= len(g):
        return 0.0, i
    future = g.iloc[i + 1 : min(len(g), i + max_days + 1)]
    if future.empty:
        return 0.0, i
    idx = int((future.high.astype(float) / anchor_close).idxmax())
    return pct(anchor_close, float(g.loc[idx, "high"])), idx


def return_after(g: pd.DataFrame, i: int, days: int) -> float:
    j = min(len(g) - 1, i + days)
    return pct(float(g.loc[i, "close"]), float(g.loc[j, "close"]))


def first_pullback(g: pd.DataFrame, anchor_i: int, peak_i: int) -> Dict[str, Any]:
    # 找启动后第一次 >=8% 回撤；没有则取 anchor 后到 peak 前最低点。
    segment = g.iloc[anchor_i : max(anchor_i + 1, peak_i + 1)].copy()
    if len(segment) <= 1:
        return {"pullback_start_date": None, "pullback_low_date": None, "pullback_pct": 0.0, "pullback_days": 0}
    running_high = -1.0
    high_idx = anchor_i
    best = {"dd": 0.0, "hi": anchor_i, "lo": anchor_i}
    for idx in range(anchor_i, peak_i + 1):
        high = float(g.loc[idx, "high"])
        low = float(g.loc[idx, "low"])
        if high > running_high:
            running_high = high
            high_idx = idx
        dd = pct(running_high, low)
        if dd < best["dd"]:
            best = {"dd": dd, "hi": high_idx, "lo": idx}
            if dd <= -8.0:
                break
    return {
        "pullback_start_date": str(g.loc[best["hi"], "trade_date"]),
        "pullback_low_date": str(g.loc[best["lo"], "trade_date"]),
        "pullback_pct": round(float(best["dd"]), 2),
        "pullback_days": int(best["lo"] - best["hi"]),
    }


def slice_stats(g: pd.DataFrame, start_i: int, end_i: int, prefix: str) -> Dict[str, Any]:
    start_i = max(0, int(start_i))
    end_i = min(len(g) - 1, int(end_i))
    if end_i < start_i:
        return {f"{prefix}_empty": 1}
    s = g.iloc[start_i : end_i + 1].copy()
    amount = float(s.total_amount.sum())
    close_ret = pct(float(s.close.iloc[0]), float(s.close.iloc[-1])) if len(s) > 1 else 0.0
    # order fields are 0 before 2026-03-02 when unavailable; for pre-window interpret cautiously.
    out = {
        f"{prefix}_days": int(len(s)),
        f"{prefix}_return_pct": round(close_ret, 2),
        f"{prefix}_max_drawdown_pct": round(max_drawdown(s.close.astype(float).tolist()), 2),
        f"{prefix}_amount_sum": round(amount, 2),
        f"{prefix}_amount_avg": round(float(s.total_amount.mean()), 2),
        f"{prefix}_amount_anomaly_avg": round(float(s.amount_anomaly_20d.mean()), 4),
        f"{prefix}_super_net_ratio": round(safe_div(float(s.l2_super_net_amount.sum()), amount), 5),
        f"{prefix}_main_net_ratio": round(safe_div(float(s.l2_main_net_amount.sum()), amount), 5),
        f"{prefix}_super_positive_day_ratio": round(float((s.l2_super_net_amount > 0).mean()), 4),
        f"{prefix}_main_positive_day_ratio": round(float((s.l2_main_net_amount > 0).mean()), 4),
        f"{prefix}_max_daily_super_outflow_ratio": round(float((s.l2_super_net_amount / s.total_amount.replace(0, pd.NA)).min()), 5),
        f"{prefix}_max_daily_main_outflow_ratio": round(float((s.l2_main_net_amount / s.total_amount.replace(0, pd.NA)).min()), 5),
        f"{prefix}_active_buy_strength_avg": round(float(s.active_buy_strength.mean()), 4),
        f"{prefix}_positive_l2_bar_ratio_avg": round(float(s.positive_l2_bar_ratio.mean()), 4),
        f"{prefix}_support_spread_avg": round(float(s.support_pressure_spread.mean()), 5),
        f"{prefix}_buy_support_avg": round(float(s.buy_support_ratio.mean()), 5),
        f"{prefix}_sell_pressure_avg": round(float(s.sell_pressure_ratio.mean()), 5),
        f"{prefix}_oib_ratio": round(safe_div(float(s.oib_delta_amount.sum()), amount), 5),
        f"{prefix}_cvd_ratio": round(safe_div(float(s.cvd_delta_amount.sum()), amount), 5),
        f"{prefix}_add_buy_ratio": round(safe_div(float(s.add_buy_amount.sum()), amount), 5),
        f"{prefix}_add_sell_ratio": round(safe_div(float(s.add_sell_amount.sum()), amount), 5),
        f"{prefix}_cancel_buy_ratio": round(safe_div(float(s.cancel_buy_amount.sum()), amount), 5),
        f"{prefix}_cancel_sell_ratio": round(safe_div(float(s.cancel_sell_amount.sum()), amount), 5),
        f"{prefix}_order_event_count_sum": round(float(s.order_event_count.sum()), 2),
        f"{prefix}_order_available_ratio": round(float((s.order_event_count > 0).mean()), 4),
    }
    out[f"{prefix}_super_price_divergence"] = round(out[f"{prefix}_super_net_ratio"] - (out[f"{prefix}_return_pct"] / 100.0), 5)
    out[f"{prefix}_main_price_divergence"] = round(out[f"{prefix}_main_net_ratio"] - (out[f"{prefix}_return_pct"] / 100.0), 5)
    return out


def build_samples(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for sym, g0 in metrics[(metrics.trade_date >= START) & (metrics.trade_date <= END)].groupby("symbol", sort=False):
        g = g0.sort_values("trade_date").reset_index(drop=True)
        if len(g) < 18:
            continue
        best_pos = None
        best_fail = None
        for i in range(0, len(g) - 8):
            if float(g.loc[i, "total_amount"]) < 300_000_000:
                continue
            runup, peak_i = max_runup_after(g, i)
            r10 = return_after(g, i, 10)
            # 正样本：后续 5~40 日涨幅 >=50，且不是纯一天尖峰。
            if runup >= 50 and peak_i - i >= 5:
                if best_pos is None or runup > best_pos["max_runup_pct"]:
                    best_pos = {"sample_type": "positive_trend", "anchor_i": i, "peak_i": peak_i, "max_runup_pct": runup}
            # 负样本：先有异动，但后续最多只到 10~35%，10日收益转弱/回落。
            # 用于对比假启动/一日游。
            day_r = float(g.loc[i, "return_1d_pct"] or 0)
            amount_anom = float(g.loc[i, "amount_anomaly_20d"] or 0)
            breakout = float(g.loc[i, "breakout_vs_prev20_high_pct"] or 0)
            if (day_r >= 4 or amount_anom >= 1.6 or breakout >= 1.0) and 10 <= runup < 35 and r10 <= 3:
                score = runup - r10
                if best_fail is None or score > best_fail["fail_score"]:
                    best_fail = {"sample_type": "failed_launch", "anchor_i": i, "peak_i": peak_i, "max_runup_pct": runup, "fail_score": score}
        for sample in [best_pos, best_fail]:
            if not sample:
                continue
            i = int(sample["anchor_i"])
            peak_i = int(sample["peak_i"])
            pull = first_pullback(g, i, peak_i)
            row: Dict[str, Any] = {
                "symbol": sym,
                "sample_type": sample["sample_type"],
                "anchor_date": str(g.loc[i, "trade_date"]),
                "anchor_close": round(float(g.loc[i, "close"]), 3),
                "peak_date": str(g.loc[peak_i, "trade_date"]),
                "peak_high": round(float(g.loc[peak_i, "high"]), 3),
                "days_to_peak": int(peak_i - i),
                "max_runup_pct": round(float(sample["max_runup_pct"]), 2),
                "return_10d_pct": round(return_after(g, i, 10), 2),
                "return_20d_at_anchor": round(float(g.loc[i].get("return_20d_pct") or 0), 2),
                "amount_anomaly_at_anchor": round(float(g.loc[i].get("amount_anomaly_20d") or 0), 4),
                "l2_super_net_ratio_at_anchor": round(float(g.loc[i].get("l2_super_net_ratio") or 0), 5),
                "l2_main_net_ratio_at_anchor": round(float(g.loc[i].get("l2_main_net_ratio") or 0), 5),
                "support_spread_at_anchor": round(float(g.loc[i].get("support_pressure_spread") or 0), 5),
                **pull,
            }
            row.update(slice_stats(g, i - 20, i - 1, "pre20"))
            row.update(slice_stats(g, i - 5, i - 1, "pre5"))
            row.update(slice_stats(g, i, min(len(g) - 1, i + 3), "launch3"))
            if pull.get("pullback_start_date") and pull.get("pullback_low_date"):
                hi_dates = g.index[g.trade_date == pull["pullback_start_date"]].tolist()
                lo_dates = g.index[g.trade_date == pull["pullback_low_date"]].tolist()
                if hi_dates and lo_dates:
                    row.update(slice_stats(g, hi_dates[0], lo_dates[0], "pullback"))
            row.update(slice_stats(g, max(i, peak_i - 5), peak_i, "pre_peak5"))
            row.update(slice_stats(g, peak_i, min(len(g) - 1, peak_i + 5), "post_peak5"))
            rows.append(row)
    return pd.DataFrame(rows)


def diff_stats(df: pd.DataFrame) -> pd.DataFrame:
    numeric = df.select_dtypes(include="number").columns.tolist()
    ignore = {"anchor_close", "peak_high", "max_runup_pct", "return_10d_pct", "days_to_peak"}
    rows = []
    pos = df[df.sample_type == "positive_trend"]
    neg = df[df.sample_type == "failed_launch"]
    for col in numeric:
        if col in ignore:
            continue
        if pos[col].notna().sum() < 10 or neg[col].notna().sum() < 10:
            continue
        pos_mean = float(pos[col].mean())
        neg_mean = float(neg[col].mean())
        pos_med = float(pos[col].median())
        neg_med = float(neg[col].median())
        pooled = float(df[col].std())
        effect = (pos_mean - neg_mean) / pooled if pooled else 0.0
        rows.append({
            "feature": col,
            "positive_mean": round(pos_mean, 6),
            "failed_mean": round(neg_mean, 6),
            "diff_mean": round(pos_mean - neg_mean, 6),
            "positive_median": round(pos_med, 6),
            "failed_median": round(neg_med, 6),
            "diff_median": round(pos_med - neg_med, 6),
            "effect_size_rough": round(effect, 4),
        })
    out = pd.DataFrame(rows)
    return out.sort_values("effect_size_rough", key=lambda s: s.abs(), ascending=False)


def main() -> None:
    raw = load_atomic_daily_window(LOOKBACK, END)
    metrics = compute_v2_metrics(raw)
    samples = build_samples(metrics)
    samples.to_csv(OUT / "trend_factor_samples.csv", index=False)
    diff = diff_stats(samples)
    diff.to_csv(OUT / "positive_vs_failed_feature_diff.csv", index=False)
    summary = {
        "range": {"start": START, "end": END, "lookback": LOOKBACK},
        "sample_counts": samples.sample_type.value_counts().to_dict(),
        "top_positive_features": diff.head(40).to_dict(orient="records"),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 大趋势正负样本因子研究", "", f"区间：{START} ~ {END}", "", "## 样本数", "", samples.sample_type.value_counts().to_markdown(), "", "## 正负样本差异 Top 30", "", diff.head(30).to_markdown(index=False), "", "## 文件", "", "- trend_factor_samples.csv", "- positive_vs_failed_feature_diff.csv", "- summary.json", ""]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:10000])


if __name__ == "__main__":
    main()
