from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window

V13_SRC = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-post-review/threshold_1_5_mature_kept_trades_enriched.csv")
V14_SRC = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes/all_mode_trades.csv")
OUT = Path("docs/strategy-rework/strategies/S04-capital-exit-risk/experiments/EXP-20260426-sell-pressure-attribution")


def safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b and abs(float(b)) > 1e-9 else 0.0


def summarize_perf(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"count": 0, "win_rate": 0.0, "avg_return": 0.0, "median_return": 0.0, "min_return": 0.0, "max_return": 0.0}
    s = pd.to_numeric(df["net_return_pct"], errors="coerce")
    return {
        "count": int(len(df)),
        "win_rate": round(float((s > 0).mean() * 100), 2),
        "avg_return": round(float(s.mean()), 2),
        "median_return": round(float(s.median()), 2),
        "min_return": round(float(s.min()), 2),
        "max_return": round(float(s.max()), 2),
    }


def phase_sell_pressure(g: pd.DataFrame, start: str, end: str, prefix: str, hist_lookback: int = 20) -> Dict[str, Any]:
    phase = g[(g.trade_date >= start) & (g.trade_date <= end)].copy()
    hist = g[g.trade_date < start].tail(hist_lookback).copy()
    hist_order = hist[hist.order_event_count > 0].copy()
    phase_order = phase[phase.order_event_count > 0].copy()

    if phase.empty:
        return {f"{prefix}_days": 0, f"{prefix}_order_days": 0}

    days = max(int(len(phase)), 1)
    phase_add_sell = float(phase.add_sell_amount.sum())
    phase_amount = float(phase.total_amount.sum())
    hist_daily_add_sell_mean = float(hist_order.add_sell_amount.mean()) if not hist_order.empty else 0.0
    hist_daily_add_sell_ratio_mean = float((hist_order.add_sell_amount / hist_order.total_amount.replace(0, pd.NA)).dropna().mean()) if not hist_order.empty else 0.0
    phase_daily_add_sell_ratio_mean = float((phase.add_sell_amount / phase.total_amount.replace(0, pd.NA)).dropna().mean())

    return {
        f"{prefix}_days": days,
        f"{prefix}_order_days": int(len(phase_order)),
        f"{prefix}_order_available_ratio": round(float((phase.order_event_count > 0).mean()), 4),
        f"{prefix}_add_sell_amount": round(phase_add_sell, 2),
        f"{prefix}_add_sell_amount_vs_hist": round(safe_div(phase_add_sell, hist_daily_add_sell_mean * days), 4),
        f"{prefix}_add_sell_ratio": round(safe_div(phase_add_sell, phase_amount), 6),
        f"{prefix}_add_sell_ratio_daily_avg": round(phase_daily_add_sell_ratio_mean, 6),
        f"{prefix}_add_sell_ratio_vs_hist": round(safe_div(phase_daily_add_sell_ratio_mean, hist_daily_add_sell_ratio_mean), 4),
        f"{prefix}_hist_order_days": int(len(hist_order)),
        f"{prefix}_hist_daily_add_sell_mean": round(hist_daily_add_sell_mean, 2),
        f"{prefix}_hist_daily_add_sell_ratio_mean": round(hist_daily_add_sell_ratio_mean, 6),
        f"{prefix}_support_pressure_spread": round(float(phase_order.support_pressure_spread.mean()) if not phase_order.empty else 0.0, 6),
        f"{prefix}_sell_pressure_ratio": round(float(phase_order.sell_pressure_ratio.mean()) if not phase_order.empty else 0.0, 6),
        f"{prefix}_buy_support_ratio": round(float(phase_order.buy_support_ratio.mean()) if not phase_order.empty else 0.0, 6),
        f"{prefix}_total_amount": round(phase_amount, 2),
    }


def enrich_pressure(trades: pd.DataFrame, metrics: pd.DataFrame, sample_version: str) -> pd.DataFrame:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}
    rows: List[Dict[str, Any]] = []
    for _, t in trades.iterrows():
        sym = str(t.symbol).lower()
        g = by_symbol.get(sym)
        if g is None:
            continue
        rec = t.to_dict()
        rec["sample_version"] = sample_version
        rec["net_return_pct"] = float(rec.get("net_return_pct", 0.0) or 0.0)
        rec["sample_group"] = "loss" if rec["net_return_pct"] < 0 else ("big_win_ge_10" if rec["net_return_pct"] >= 10 else "small_win")
        rec.update(phase_sell_pressure(g, str(t.launch_start_date), str(t.launch_end_date), "launch3"))
        rec.update(phase_sell_pressure(g, str(t.pullback_confirm_date), str(t.pullback_confirm_date), "confirm"))
        rows.append(rec)
    return pd.DataFrame(rows)


def diff_table(df: pd.DataFrame, loss_mask: pd.Series, win_mask: pd.Series, features: Iterable[str]) -> pd.DataFrame:
    rows = []
    loss = df[loss_mask]
    win = df[win_mask]
    for f in features:
        if f not in df.columns:
            continue
        rows.append({
            "feature": f,
            "loss_count": int(loss[f].notna().sum()),
            "win_count": int(win[f].notna().sum()),
            "loss_mean": round(float(loss[f].mean()), 6) if not loss.empty else 0.0,
            "loss_median": round(float(loss[f].median()), 6) if not loss.empty else 0.0,
            "win_mean": round(float(win[f].mean()), 6) if not win.empty else 0.0,
            "win_median": round(float(win[f].median()), 6) if not win.empty else 0.0,
            "loss_minus_win_median": round(float(loss[f].median() - win[f].median()), 6) if not loss.empty and not win.empty else 0.0,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.reindex(out.loss_minus_win_median.abs().sort_values(ascending=False).index)


def rule_scan(df: pd.DataFrame, base_name: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    base_losses = df.net_return_pct < 0
    base_big_wins = df.net_return_pct >= 10
    rules: Dict[str, pd.Series] = {}

    for phase in ["launch3", "confirm"]:
        for mult in [1.2, 1.5, 2.0, 3.0]:
            rules[f"{phase}_add_sell_amount_vs_hist>={mult}"] = df[f"{phase}_add_sell_amount_vs_hist"] >= mult
            rules[f"{phase}_add_sell_ratio_vs_hist>={mult}"] = df[f"{phase}_add_sell_ratio_vs_hist"] >= mult
        for spread in [-0.1, -0.05, 0.0]:
            rules[f"{phase}_support_pressure_spread<={spread}"] = df[f"{phase}_support_pressure_spread"] <= spread
        for sell_ratio in [0.45, 0.55, 0.65]:
            rules[f"{phase}_sell_pressure_ratio>={sell_ratio}"] = df[f"{phase}_sell_pressure_ratio"] >= sell_ratio
        for mult in [1.5, 2.0, 3.0]:
            rules[f"{phase}_add_sell_amount_vs_hist>={mult}_and_support<0"] = (df[f"{phase}_add_sell_amount_vs_hist"] >= mult) & (df[f"{phase}_support_pressure_spread"] < 0)
            rules[f"{phase}_add_sell_ratio_vs_hist>={mult}_and_support<0"] = (df[f"{phase}_add_sell_ratio_vs_hist"] >= mult) & (df[f"{phase}_support_pressure_spread"] < 0)

    rules["launch_or_confirm_add_sell_amount_vs_hist>=2_and_support<0"] = (
        ((df.launch3_add_sell_amount_vs_hist >= 2.0) & (df.launch3_support_pressure_spread < 0))
        | ((df.confirm_add_sell_amount_vs_hist >= 2.0) & (df.confirm_support_pressure_spread < 0))
    )
    rules["launch_or_confirm_add_sell_ratio_vs_hist>=2_and_support<0"] = (
        ((df.launch3_add_sell_ratio_vs_hist >= 2.0) & (df.launch3_support_pressure_spread < 0))
        | ((df.confirm_add_sell_ratio_vs_hist >= 2.0) & (df.confirm_support_pressure_spread < 0))
    )

    for name, mask in rules.items():
        hit = df[mask]
        kept = df[~mask]
        rows.append({
            "base": base_name,
            "rule": name,
            "filter_count": int(mask.sum()),
            "filter_loss_count": int((mask & base_losses).sum()),
            "filter_loss_recall_pct": round(float((mask & base_losses).sum() / max(int(base_losses.sum()), 1) * 100), 2),
            "filter_big_win_count": int((mask & base_big_wins).sum()),
            "filter_big_win_hit_pct": round(float((mask & base_big_wins).sum() / max(int(base_big_wins.sum()), 1) * 100), 2),
            "filtered_avg_return": round(float(hit.net_return_pct.mean()) if len(hit) else 0.0, 2),
            "kept_count": int(len(kept)),
            "kept_win_rate": summarize_perf(kept)["win_rate"],
            "kept_avg_return": summarize_perf(kept)["avg_return"],
            "kept_median_return": summarize_perf(kept)["median_return"],
            "kept_min_return": summarize_perf(kept)["min_return"],
        })
    out = pd.DataFrame(rows)
    return out.sort_values(["filter_loss_recall_pct", "filter_big_win_hit_pct", "kept_avg_return"], ascending=[False, True, False])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    raw = load_atomic_daily_window("2026-01-01", "2026-04-24")
    metrics = compute_v2_metrics(raw)

    v13 = pd.read_csv(V13_SRC)
    v13 = v13[v13.get("is_mature_trade", True) == True].copy()
    v13_en = enrich_pressure(v13, metrics, "v1.3_threshold_1.5_mature")

    v14 = pd.read_csv(V14_SRC)
    v14 = v14[v14.get("is_mature_trade", True) == True].copy()
    v14_parts = []
    for mode in ["v1.4-balanced", "v1.4-quality"]:
        part = v14[v14.strategy_mode == mode].copy()
        v14_parts.append(enrich_pressure(part, metrics, mode))
    all_en = pd.concat([v13_en, *v14_parts], ignore_index=True)

    # 主对比：v1.3 阈值 1.5 保留下来的亏损票（前 10） vs v1.3/v1.4 大赚票。
    v13_loss_top10_idx = list(v13_en[v13_en.net_return_pct < 0].sort_values("net_return_pct").head(10).index)
    all_en["is_v13_loss_top10"] = False
    all_en.loc[v13_loss_top10_idx, "is_v13_loss_top10"] = all_en.loc[v13_loss_top10_idx, "sample_version"].eq("v1.3_threshold_1.5_mature")

    features = [
        "launch3_add_sell_amount_vs_hist", "launch3_add_sell_ratio_vs_hist", "launch3_add_sell_ratio",
        "launch3_support_pressure_spread", "launch3_sell_pressure_ratio",
        "confirm_add_sell_amount_vs_hist", "confirm_add_sell_ratio_vs_hist", "confirm_add_sell_ratio",
        "confirm_support_pressure_spread", "confirm_sell_pressure_ratio",
    ]
    loss_mask = (all_en.sample_version == "v1.3_threshold_1.5_mature") & (all_en.net_return_pct < 0)
    win_mask = all_en.net_return_pct >= 10
    diff = diff_table(all_en, loss_mask, win_mask, features)
    diff.to_csv(OUT / "loss_vs_win_sell_pressure_diff.csv", index=False)

    scan = pd.concat([
        rule_scan(v13_en, "v1.3_threshold_1.5_mature"),
        rule_scan(all_en[all_en.sample_version == "v1.4-balanced"].copy(), "v1.4-balanced_mature"),
    ], ignore_index=True)
    scan.to_csv(OUT / "rule_scan.csv", index=False)

    summary = {
        "experiment": "EXP-20260426-sell-pressure-attribution",
        "sources": {"v1.3": str(V13_SRC), "v1.4": str(V14_SRC)},
        "sample_counts": {
            "v1_3_mature": int(len(v13_en)),
            "v1_3_losses": int((v13_en.net_return_pct < 0).sum()),
            "v1_3_loss_top10_used_for_focus": int(min(10, (v13_en.net_return_pct < 0).sum())),
            "all_big_win_ge_10_controls": int((all_en.net_return_pct >= 10).sum()),
            "v1_4_balanced_mature": int((all_en.sample_version == "v1.4-balanced").sum()),
            "v1_4_quality_mature": int((all_en.sample_version == "v1.4-quality").sum()),
        },
        "performance_by_sample_version": {k: summarize_perf(g) for k, g in all_en.groupby("sample_version")},
        "loss_vs_win_median_diff": diff.to_dict(orient="records"),
        "best_rule_scan_rows": scan.head(12).to_dict(orient="records"),
        "conclusion": {
            "can_distinguish_loss_vs_win": False,
            "reason": "新增卖挂单异常、支撑压力差、卖压比例在亏损票与大赚票之间不稳定；高召回规则会明显误杀大赚票，低误杀组合又覆盖亏损不足。",
            "recommendation": "不建议单独纳入 S01 入场过滤；可作为 S04 观察型风险标签继续留档，不升级为硬过滤。",
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = [
        "# EXP-20260426-sell-pressure-attribution：压单出货归因验证",
        "",
        "## 1. 问题",
        "验证 Gemini 提到的“新增卖挂单异常放大 + 支撑压力差严重为负”是否能解释 v1.3 阈值 1.5 后仍保留的亏损票，并区分 v1.3/v1.4 大赚票。",
        "",
        "## 2. 假设",
        "如果是泰山压顶/压单出货，亏损票在启动 3 日或回调确认日应出现：`add_sell_amount` 相对自身历史异常放大、`support_pressure_spread` 明显为负、`sell_pressure_ratio` 偏高。",
        "",
        "## 3. 数据范围",
        "- 发现日：2026-03-02 ~ 2026-04-24",
        "- 回放到：2026-04-24",
        "- 原子数据回看：2026-01-01 ~ 2026-04-24",
        "- 交易结果：v1.3 阈值 1.5、v1.4-balanced、v1.4-quality 的成熟交易。",
        "",
        "## 4. 样本口径",
        f"- v1.3 阈值 1.5 成熟交易：{summary['sample_counts']['v1_3_mature']} 笔。",
        f"- v1.3 保留下来的亏损票：{summary['sample_counts']['v1_3_losses']} 笔，重点看最亏前 10。",
        f"- v1.3/v1.4 大赚对照：净收益 >= 10%，共 {summary['sample_counts']['all_big_win_ge_10_controls']} 行样本（不同模式同票会分别计入）。",
        "",
        "## 5. 规则/参数",
        "每个阶段计算：",
        "- `add_sell_amount_vs_hist`：阶段新增卖挂单金额 / 该股前 20 个有挂单交易日的日均新增卖挂单金额（按阶段天数折算）。",
        "- `add_sell_ratio_vs_hist`：阶段 `add_sell_amount / total_amount` 日均值相对历史日均倍数。",
        "- `support_pressure_spread`：`buy_support_ratio - sell_pressure_ratio` 阶段均值。",
        "- `sell_pressure_ratio`：阶段均值。",
        "",
        "## 6. 输出文件",
        "- `loss_vs_win_sell_pressure_diff.csv`：亏损票 vs 大赚票指标差异。",
        "- `rule_scan.csv`：简单压单规则扫描。",
        "- `summary.json`：程序可读摘要。",
        "",
        "## 7. 核心结果",
        "",
        diff.to_markdown(index=False),
        "",
        "规则扫描前 12：",
        "",
        scan.head(12).to_markdown(index=False),
        "",
        "## 8. 结论：不采纳为硬过滤，继续观察",
        "新增卖挂单异常和支撑压力差不能稳定地区分剩余亏损票与大赚票。单独看卖压会误杀较多赢家；组合 `add_sell_vs_hist + support<0` 后覆盖亏损又不足。当前不建议纳入 S01/S04 的硬规则，只保留为 S04 观察型风险标签。",
        "",
    ]
    (OUT / "README.md").write_text("\n".join(readme), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:6000])


if __name__ == "__main__":
    main()
