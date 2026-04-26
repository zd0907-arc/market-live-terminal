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

EXP = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-2-exit-grid")
TRADES = EXP / "best_trades.csv"
OUT = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-orderbook-attribution")


def safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b and abs(float(b)) > 1e-9 else 0.0


def phase_stats(g: pd.DataFrame, start: str, end: str, prefix: str) -> Dict[str, Any]:
    s = g[(g.trade_date >= start) & (g.trade_date <= end)].copy()
    if s.empty:
        return {f"{prefix}_empty": 1}
    amount = float(s.total_amount.sum())
    add_buy = float(s.add_buy_amount.sum())
    add_sell = float(s.add_sell_amount.sum())
    cancel_buy = float(s.cancel_buy_amount.sum())
    cancel_sell = float(s.cancel_sell_amount.sum())
    oib = float(s.oib_delta_amount.sum())
    cvd = float(s.cvd_delta_amount.sum())
    order_days = s[s.order_event_count > 0]
    return {
        f"{prefix}_days": int(len(s)),
        f"{prefix}_order_available_ratio": round(float((s.order_event_count > 0).mean()), 4),
        f"{prefix}_return_pct": round(safe_div(float(s.close.iloc[-1]), float(s.close.iloc[0])) * 100 - 100, 2) if len(s) > 1 else 0.0,
        f"{prefix}_amount_sum": round(amount, 2),
        f"{prefix}_add_sell_ratio": round(safe_div(add_sell, amount), 5),
        f"{prefix}_add_buy_ratio": round(safe_div(add_buy, amount), 5),
        f"{prefix}_cancel_buy_ratio": round(safe_div(cancel_buy, amount), 5),
        f"{prefix}_cancel_sell_ratio": round(safe_div(cancel_sell, amount), 5),
        f"{prefix}_cancel_buy_to_add_buy": round(safe_div(cancel_buy, add_buy), 5),
        f"{prefix}_oib_ratio": round(safe_div(oib, amount), 5),
        f"{prefix}_cvd_ratio": round(safe_div(cvd, amount), 5),
        f"{prefix}_oib_cvd_gap": round(safe_div(oib, amount) - safe_div(cvd, amount), 5),
        f"{prefix}_buy_support_avg": round(float(order_days.buy_support_ratio.mean()) if not order_days.empty else 0.0, 5),
        f"{prefix}_sell_pressure_avg": round(float(order_days.sell_pressure_ratio.mean()) if not order_days.empty else 0.0, 5),
        f"{prefix}_support_spread_avg": round(float(order_days.support_pressure_spread.mean()) if not order_days.empty else 0.0, 5),
        f"{prefix}_active_buy_strength_avg": round(float(s.active_buy_strength.mean()), 5),
        f"{prefix}_super_net_ratio": round(safe_div(float(s.l2_super_net_amount.sum()), amount), 5),
        f"{prefix}_main_net_ratio": round(safe_div(float(s.l2_main_net_amount.sum()), amount), 5),
    }


def historical_add_sell(g: pd.DataFrame, before_date: str, prefix: str, lookback: int = 20) -> Dict[str, Any]:
    hist = g[g.trade_date < before_date].tail(lookback).copy()
    hist = hist[hist.order_event_count > 0].copy()
    if hist.empty:
        return {
            f"{prefix}_hist_order_days": 0,
            f"{prefix}_hist_add_sell_ratio_avg": 0.0,
            f"{prefix}_hist_cancel_buy_to_add_buy_avg": 0.0,
        }
    daily_add_sell = hist.add_sell_amount / hist.total_amount.replace(0, pd.NA)
    daily_cancel_add = hist.cancel_buy_amount / hist.add_buy_amount.replace(0, pd.NA)
    return {
        f"{prefix}_hist_order_days": int(len(hist)),
        f"{prefix}_hist_add_sell_ratio_avg": round(float(daily_add_sell.dropna().mean()), 5),
        f"{prefix}_hist_cancel_buy_to_add_buy_avg": round(float(daily_cancel_add.dropna().mean()), 5),
    }


def enrich(trades: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}
    rows: List[Dict[str, Any]] = []
    for _, t in trades.iterrows():
        sym = str(t.symbol)
        g = by_symbol.get(sym)
        if g is None:
            continue
        launch_start = str(t.launch_start_date)
        launch_end = str(t.launch_end_date)
        pull_date = str(t.pullback_confirm_date)

        rec = t.to_dict()
        rec["sample_type"] = "big_win_ge_10" if float(t.net_return_pct) >= 10 else ("big_loss_le_-8" if float(t.net_return_pct) <= -8 else "middle")
        rec.update(historical_add_sell(g, launch_start, "launch"))
        rec.update(phase_stats(g, launch_start, launch_end, "launch3_ob"))
        rec.update(historical_add_sell(g, pull_date, "pullback"))
        rec.update(phase_stats(g, pull_date, pull_date, "pullback_day_ob"))

        for phase in ["launch3_ob", "pullback_day_ob"]:
            hist_prefix = "launch" if phase == "launch3_ob" else "pullback"
            add_ratio = float(rec.get(f"{phase}_add_sell_ratio", 0.0) or 0.0)
            hist_add = float(rec.get(f"{hist_prefix}_hist_add_sell_ratio_avg", 0.0) or 0.0)
            cancel_add = float(rec.get(f"{phase}_cancel_buy_to_add_buy", 0.0) or 0.0)
            hist_cancel_add = float(rec.get(f"{hist_prefix}_hist_cancel_buy_to_add_buy_avg", 0.0) or 0.0)
            rec[f"{phase}_add_sell_vs_hist"] = round(safe_div(add_ratio, hist_add), 4)
            rec[f"{phase}_cancel_buy_to_add_buy_vs_hist"] = round(safe_div(cancel_add, hist_cancel_add), 4)
            # 三类诱多风险的可解释代理分；只用于归因，不直接作为最终规则。
            rec[f"{phase}_sell_wall_flag"] = int(add_ratio > 0 and rec[f"{phase}_add_sell_vs_hist"] >= 1.35 and float(rec.get(f"{phase}_support_spread_avg", 0.0)) < 0)
            rec[f"{phase}_fake_support_flag"] = int(cancel_add >= 0.85 and float(rec.get(f"{phase}_buy_support_avg", 0.0)) >= 0.35)
            rec[f"{phase}_thunder_no_rain_flag"] = int(float(rec.get(f"{phase}_oib_cvd_gap", 0.0)) >= 0.03 and float(rec.get(f"{phase}_cvd_ratio", 0.0)) <= 0.01)
        rows.append(rec)
    return pd.DataFrame(rows)


def diff_table(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    loss = df[df.sample_type == "big_loss_le_-8"]
    win = df[df.sample_type == "big_win_ge_10"]
    rows = []
    for col in cols:
        if col not in df.columns:
            continue
        rows.append({
            "feature": col,
            "loss_mean": round(float(loss[col].mean()), 6),
            "loss_median": round(float(loss[col].median()), 6),
            "win_mean": round(float(win[col].mean()), 6),
            "win_median": round(float(win[col].median()), 6),
            "loss_minus_win_median": round(float(loss[col].median() - win[col].median()), 6),
        })
    return pd.DataFrame(rows)


def scan_simple_rules(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base_loss = df[df.sample_type == "big_loss_le_-8"]
    base_win = df[df.sample_type == "big_win_ge_10"]
    rules = {
        "pullback_cancel_buy_to_add_buy>=0.85": df["pullback_day_ob_cancel_buy_to_add_buy"] >= 0.85,
        "pullback_cancel_buy_to_add_buy>=1.0": df["pullback_day_ob_cancel_buy_to_add_buy"] >= 1.0,
        "pullback_support_spread<0": df["pullback_day_ob_support_spread_avg"] < 0,
        "pullback_add_sell_vs_hist>=1.35": df["pullback_day_ob_add_sell_vs_hist"] >= 1.35,
        "pullback_oib_cvd_gap>=0.03_and_cvd<=0.01": (df["pullback_day_ob_oib_cvd_gap"] >= 0.03) & (df["pullback_day_ob_cvd_ratio"] <= 0.01),
        "launch_add_sell_vs_hist>=1.35_and_support<0": (df["launch3_ob_add_sell_vs_hist"] >= 1.35) & (df["launch3_ob_support_spread_avg"] < 0),
        "launch_cancel_buy_to_add_buy>=0.85": df["launch3_ob_cancel_buy_to_add_buy"] >= 0.85,
    }
    for name, mask in rules.items():
        hit = df[mask]
        loss_hit = base_loss[mask.loc[base_loss.index]]
        win_hit = base_win[mask.loc[base_win.index]]
        rows.append({
            "rule": name,
            "hit_all": int(len(hit)),
            "hit_loss": int(len(loss_hit)),
            "hit_loss_rate_in_losses": round(100 * len(loss_hit) / max(len(base_loss), 1), 2),
            "hit_win": int(len(win_hit)),
            "hit_win_rate_in_winners": round(100 * len(win_hit) / max(len(base_win), 1), 2),
            "hit_avg_return": round(float(hit.net_return_pct.mean()) if len(hit) else 0.0, 4),
        })
    return pd.DataFrame(rows).sort_values(["hit_loss_rate_in_losses", "hit_win_rate_in_winners"], ascending=[False, True])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trades = pd.read_csv(TRADES)
    raw = load_atomic_daily_window("2026-03-02", "2026-04-24")
    metrics = compute_v2_metrics(raw)
    enriched = enrich(trades, metrics)
    enriched.to_csv(OUT / "v1_2_trades_orderbook_enriched.csv", index=False)

    cols = [
        "launch3_ob_add_sell_vs_hist",
        "launch3_ob_cancel_buy_to_add_buy",
        "launch3_ob_cancel_buy_to_add_buy_vs_hist",
        "launch3_ob_oib_ratio",
        "launch3_ob_cvd_ratio",
        "launch3_ob_oib_cvd_gap",
        "launch3_ob_buy_support_avg",
        "launch3_ob_support_spread_avg",
        "pullback_day_ob_add_sell_vs_hist",
        "pullback_day_ob_cancel_buy_to_add_buy",
        "pullback_day_ob_cancel_buy_to_add_buy_vs_hist",
        "pullback_day_ob_oib_ratio",
        "pullback_day_ob_cvd_ratio",
        "pullback_day_ob_oib_cvd_gap",
        "pullback_day_ob_buy_support_avg",
        "pullback_day_ob_support_spread_avg",
        "pullback_day_ob_super_net_ratio",
        "pullback_day_ob_main_net_ratio",
    ]
    diff = diff_table(enriched[enriched.sample_type != "middle"], cols)
    diff.to_csv(OUT / "big_loss_vs_big_win_orderbook_diff.csv", index=False)
    rules = scan_simple_rules(enriched)
    rules.to_csv(OUT / "simple_rule_scan.csv", index=False)

    loss_focus = enriched[enriched.net_return_pct <= -8].sort_values("net_return_pct")
    loss_focus.to_csv(OUT / "loss_trades_focus.csv", index=False)

    summary = {
        "source": str(TRADES),
        "counts": enriched.sample_type.value_counts().to_dict(),
        "loss_le_-8_count": int((enriched.net_return_pct <= -8).sum()),
        "win_ge_10_count": int((enriched.net_return_pct >= 10).sum()),
        "top_diff_by_median": diff.reindex(diff.loss_minus_win_median.abs().sort_values(ascending=False).index).head(12).to_dict(orient="records"),
        "simple_rule_scan": rules.head(10).to_dict(orient="records"),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# v1.3 挂单归因分析：大亏票 vs 大赚票",
        "",
        "基于 v1.2 最优参数的交易结果，暂不改策略，只对 `净收益 <= -8%` 与 `净收益 >= 10%` 做 L2 挂单对比。",
        "",
        "## 样本数",
        "",
        f"- 大亏样本：{summary['loss_le_-8_count']}",
        f"- 大赚样本：{summary['win_ge_10_count']}",
        "",
        "## 关键差异",
        "",
        diff.reindex(diff.loss_minus_win_median.abs().sort_values(ascending=False).index).head(12).to_markdown(index=False),
        "",
        "## 简单规则扫描",
        "",
        rules.head(10).to_markdown(index=False),
        "",
        "## 初步结论",
        "",
        "1. 这一步只做归因，不直接固化规则。",
        "2. 优先寻找“能覆盖较多大亏、但少误杀大赚”的过滤条件。",
        "3. 如果单一挂单条件误杀严重，v1.3 应使用组合规则，而不是一票否决。",
        "",
        "## 文件",
        "",
        "- v1_2_trades_orderbook_enriched.csv",
        "- big_loss_vs_big_win_orderbook_diff.csv",
        "- simple_rule_scan.csv",
        "- loss_trades_focus.csv",
        "- summary.json",
        "",
    ]
    (OUT / "README.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:8000])


if __name__ == "__main__":
    main()
