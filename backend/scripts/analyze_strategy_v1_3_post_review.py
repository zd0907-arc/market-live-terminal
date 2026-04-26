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
from backend.scripts.analyze_strategy_v1_2_orderbook_attribution import enrich

SRC = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-robustness-scan")
OUT = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-post-review")


def perf(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"count": 0, "win_rate": 0, "avg": 0, "median": 0, "min": 0, "max": 0, "sum": 0}
    s = df.net_return_pct.astype(float)
    return {
        "count": int(len(df)),
        "win_rate": round(float((s > 0).mean() * 100), 2),
        "avg": round(float(s.mean()), 2),
        "median": round(float(s.median()), 2),
        "min": round(float(s.min()), 2),
        "max": round(float(s.max()), 2),
        "sum": round(float(s.sum()), 2),
    }


def rule_mask(df: pd.DataFrame, name: str) -> pd.Series:
    if name == "launch_ret_lt_6":
        return df.launch3_return_pct < 6
    if name == "confirm_dist_gte_50":
        return df.confirm_distribution_score >= 50
    if name == "launch_ret_lt_6_and_confirm_dist_gte_50":
        return (df.launch3_return_pct < 6) & (df.confirm_distribution_score >= 50)
    if name == "launch_ret_lt_6_and_pullback_support_lt_0":
        return (df.launch3_return_pct < 6) & (df.pullback_support_spread_avg < 0)
    if name == "pullback_support_lt_0_and_confirm_dist_gte_45":
        return (df.pullback_support_spread_avg < 0) & (df.confirm_distribution_score >= 45)
    if name == "launch_ret_lt_6_and_pullback_support_lt_0_and_confirm_dist_gte_45":
        return (df.launch3_return_pct < 6) & (df.pullback_support_spread_avg < 0) & (df.confirm_distribution_score >= 45)
    raise ValueError(name)


def scan_next_rules(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    base_loss = df.net_return_pct <= -8
    base_win = df.net_return_pct >= 10
    for name in [
        "launch_ret_lt_6",
        "confirm_dist_gte_50",
        "launch_ret_lt_6_and_confirm_dist_gte_50",
        "launch_ret_lt_6_and_pullback_support_lt_0",
        "pullback_support_lt_0_and_confirm_dist_gte_45",
        "launch_ret_lt_6_and_pullback_support_lt_0_and_confirm_dist_gte_45",
    ]:
        mask = rule_mask(df, name)
        kept = df[~mask]
        filtered = df[mask]
        p = perf(kept)
        rows.append({
            "rule": name,
            "filtered_count": int(mask.sum()),
            "filtered_loss_le_-8": int((mask & base_loss).sum()),
            "filtered_win_ge_10": int((mask & base_win).sum()),
            "filtered_avg_return": round(float(filtered.net_return_pct.mean()) if len(filtered) else 0.0, 2),
            "kept_count": p["count"],
            "kept_win_rate": p["win_rate"],
            "kept_avg_return": p["avg"],
            "kept_median_return": p["median"],
            "kept_min_return": p["min"],
            "kept_sum_return": p["sum"],
        })
    return pd.DataFrame(rows)


def median_diff(a: pd.DataFrame, b: pd.DataFrame, features: List[str]) -> pd.DataFrame:
    rows = []
    for col in features:
        if col not in a.columns or col not in b.columns:
            continue
        if a[col].dtype.kind not in "if" or b[col].dtype.kind not in "if":
            continue
        rows.append({
            "feature": col,
            "group_a_median": round(float(a[col].median()), 6),
            "group_b_median": round(float(b[col].median()), 6),
            "a_minus_b_median": round(float(a[col].median() - b[col].median()), 6),
            "group_a_mean": round(float(a[col].mean()), 6),
            "group_b_mean": round(float(b[col].mean()), 6),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.reindex(out.a_minus_b_median.abs().sort_values(ascending=False).index)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trades = pd.read_csv(SRC / "all_threshold_trades.csv")
    raw = load_atomic_daily_window("2026-03-02", "2026-04-24")
    metrics = compute_v2_metrics(raw)

    none = trades[trades.filter_threshold.astype(str) == "none"].copy()
    none_en = enrich(none, metrics)
    would_filtered = none_en[none_en.launch3_ob_cancel_buy_to_add_buy_vs_hist > 1.5].copy()
    would_filtered.to_csv(OUT / "threshold_1_5_would_filter_trades.csv", index=False)
    would_filtered_false_wins = would_filtered[would_filtered.net_return_pct >= 10].copy()
    would_filtered_correct_losses = would_filtered[would_filtered.net_return_pct <= -8].copy()
    would_filtered_false_wins.to_csv(OUT / "threshold_1_5_false_killed_winners.csv", index=False)
    would_filtered_correct_losses.to_csv(OUT / "threshold_1_5_correctly_filtered_losses.csv", index=False)

    kept = trades[(trades.filter_threshold.astype(str) == "1.5") & (trades.is_mature_trade == True)].copy()
    kept_en = enrich(kept, metrics)
    kept_en.to_csv(OUT / "threshold_1_5_mature_kept_trades_enriched.csv", index=False)
    remaining_losses = kept_en[kept_en.net_return_pct <= -8].copy()
    kept_winners = kept_en[kept_en.net_return_pct >= 10].copy()
    remaining_losses.to_csv(OUT / "threshold_1_5_remaining_losses.csv", index=False)

    features = [
        "setup_score",
        "launch3_return_pct",
        "launch3_super_net_ratio",
        "launch3_main_net_ratio",
        "launch3_ob_active_buy_strength_avg",
        "launch3_ob_support_spread_avg",
        "launch3_ob_oib_cvd_gap",
        "pullback_super_net_ratio",
        "pullback_main_net_ratio",
        "pullback_support_spread_avg",
        "pullback_day_ob_support_spread_avg",
        "pullback_day_ob_oib_cvd_gap",
        "pullback_day_ob_cvd_ratio",
        "confirm_distribution_score",
        "launch_cancel_buy_to_add_buy_vs_hist",
    ]
    false_kill_diff = median_diff(would_filtered_false_wins, would_filtered_correct_losses, features)
    false_kill_diff.to_csv(OUT / "false_killed_winners_vs_filtered_losses_diff.csv", index=False)
    remaining_diff = median_diff(remaining_losses, kept_winners, features)
    remaining_diff.to_csv(OUT / "remaining_losses_vs_kept_winners_diff.csv", index=False)
    rule_scan = scan_next_rules(kept_en)
    rule_scan.to_csv(OUT / "next_rule_what_if_scan.csv", index=False)

    summary = {
        "source": str(SRC),
        "threshold_1_5_would_filter": {
            "all": perf(would_filtered),
            "false_killed_win_ge_10_count": int(len(would_filtered_false_wins)),
            "correct_filtered_loss_le_-8_count": int(len(would_filtered_correct_losses)),
        },
        "threshold_1_5_mature_kept": {
            "all": perf(kept_en),
            "remaining_loss_le_-8_count": int(len(remaining_losses)),
            "kept_win_ge_10_count": int(len(kept_winners)),
        },
        "next_rule_scan": rule_scan.to_dict(orient="records"),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# v1.3 后复盘：误杀与剩余亏损",
        "",
        "基于全市场稳健性验证结果，重点看两件事：",
        "",
        "1. 阈值 1.5 过滤掉的票里，有没有误杀大牛。",
        "2. 阈值 1.5 保留下来的成熟交易里，剩余大亏票还有什么共同特征。",
        "",
        "## 1. 阈值 1.5 的误杀情况",
        "",
        f"- 被阈值 1.5 过滤且原本会触发交易：{len(would_filtered)} 笔",
        f"- 其中净收益 >= 10%：{len(would_filtered_false_wins)} 笔",
        f"- 其中净收益 <= -8%：{len(would_filtered_correct_losses)} 笔",
        f"- 被过滤交易原始平均收益：{perf(would_filtered)['avg']}%",
        f"- 被过滤交易原始中位收益：{perf(would_filtered)['median']}%",
        "",
        "被误杀的大赚票数量不多，但包含一笔大牛。当前更合理的判断是：先接受这类误杀，因为这批被过滤交易整体收益为负。",
        "",
        "## 2. 剩余大亏票 vs 保留大赚票",
        "",
        remaining_diff.head(12).to_markdown(index=False),
        "",
        "剩余大亏票的明显特征：启动 3 日涨幅偏弱、确认日出货分偏高，部分伴随回调承接为负。",
        "",
        "## 3. 下一条规则 What-if",
        "",
        rule_scan.to_markdown(index=False),
        "",
        "## 初步建议",
        "",
        "不要马上修正 v1.3 的阈值 1.5；它虽然误杀少数赢家，但整体过滤收益为正。",
        "",
        "下一步可以尝试 v1.4：在 v1.3 后增加“弱启动过滤”，优先测试：",
        "",
        "```text",
        "launch3_return_pct < 6",
        "```",
        "",
        "这条规则会显著减少剩余大亏，但也会明显减少交易数，属于更激进的高质量模式。",
        "",
        "## 文件",
        "",
        "- threshold_1_5_would_filter_trades.csv",
        "- threshold_1_5_false_killed_winners.csv",
        "- threshold_1_5_correctly_filtered_losses.csv",
        "- threshold_1_5_mature_kept_trades_enriched.csv",
        "- threshold_1_5_remaining_losses.csv",
        "- false_killed_winners_vs_filtered_losses_diff.csv",
        "- remaining_losses_vs_kept_winners_diff.csv",
        "- next_rule_what_if_scan.csv",
        "- summary.json",
        "",
    ]
    (OUT / "README.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:8000])


if __name__ == "__main__":
    main()
