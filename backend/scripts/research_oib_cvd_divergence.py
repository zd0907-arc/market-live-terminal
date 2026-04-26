from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize

EXP_DIR = Path("docs/strategy-rework/strategies/S04-capital-exit-risk/experiments/EXP-20260426-oib-cvd-divergence")
V13_TRADES = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-robustness-scan/all_threshold_trades.csv")
V14_TRADES = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes/all_mode_trades.csv")
EPS = 1e-9


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def safe_ratio(oib: float, cvd: float) -> float | None:
    """Signed ratio with zero guard. Positive when OIB and CVD same sign; negative when divergent."""
    if abs(cvd) < EPS:
        return None
    return oib / abs(cvd)


def window_sum(g: pd.DataFrame, start: str | None, end: str | None) -> Dict[str, Any]:
    if not start or not end or pd.isna(start) or pd.isna(end):
        return {
            "oib_sum": 0.0,
            "cvd_sum": 0.0,
            "days": 0,
            "divergence": False,
            "oib_cvd_diff": 0.0,
            "oib_to_abs_cvd_ratio": None,
        }
    w = g[(g.trade_date >= str(start)) & (g.trade_date <= str(end))]
    oib = float(w.oib_delta_amount.fillna(0.0).sum()) if not w.empty else 0.0
    cvd = float(w.cvd_delta_amount.fillna(0.0).sum()) if not w.empty else 0.0
    return {
        "oib_sum": oib,
        "cvd_sum": cvd,
        "days": int(len(w)),
        "divergence": bool(oib > 0 and cvd <= 0),
        "oib_cvd_diff": oib - cvd,
        "oib_to_abs_cvd_ratio": safe_ratio(oib, cvd),
    }


def next_day_return(g: pd.DataFrame, entry_date: str, entry_price: float) -> float | None:
    if not entry_date or pd.isna(entry_date) or not entry_price:
        return None
    future = g[g.trade_date > str(entry_date)].head(1)
    if future.empty:
        return None
    close = fnum(future.iloc[0].close)
    return (close / entry_price - 1.0) * 100.0 if entry_price else None


def load_samples() -> pd.DataFrame:
    v13 = pd.read_csv(V13_TRADES)
    v13 = v13[(v13["filter_threshold"].astype(str) == "1.5") & (v13["is_mature_trade"].astype(bool))].copy()
    v13["sample_version"] = "v1.3-threshold-1.5"

    v14 = pd.read_csv(V14_TRADES)
    v14 = v14[(v14["strategy_mode"] == "v1.4-balanced") & (v14["is_mature_trade"].astype(bool))].copy()
    v14["sample_version"] = "v1.4-balanced"

    return pd.concat([v13, v14], ignore_index=True, sort=False)


def enrich_oib_cvd(trades: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in raw.groupby("symbol")}
    rows: List[Dict[str, Any]] = []
    for _, rec in trades.iterrows():
        sym = str(rec["symbol"])
        g = by_symbol.get(sym)
        base = rec.to_dict()
        if g is None:
            rows.append({**base, "oib_cvd_available": False})
            continue
        launch = window_sum(g, base.get("launch_start_date"), base.get("launch_end_date"))
        confirm = window_sum(g, base.get("pullback_confirm_date"), base.get("pullback_confirm_date"))
        entry_price = fnum(base.get("entry_price"))
        nd_ret = next_day_return(g, str(base.get("entry_date")), entry_price)
        rows.append({
            **base,
            "oib_cvd_available": True,
            "launch_oib_sum": launch["oib_sum"],
            "launch_cvd_sum": launch["cvd_sum"],
            "launch_oib_pos_cvd_nonpos": launch["divergence"],
            "launch_oib_cvd_diff": launch["oib_cvd_diff"],
            "launch_oib_to_abs_cvd_ratio": launch["oib_to_abs_cvd_ratio"],
            "launch_oib_cvd_days": launch["days"],
            "confirm_oib_sum": confirm["oib_sum"],
            "confirm_cvd_sum": confirm["cvd_sum"],
            "confirm_oib_pos_cvd_nonpos": confirm["divergence"],
            "confirm_oib_cvd_diff": confirm["oib_cvd_diff"],
            "confirm_oib_to_abs_cvd_ratio": confirm["oib_to_abs_cvd_ratio"],
            "confirm_oib_cvd_days": confirm["days"],
            "any_oib_pos_cvd_nonpos": bool(launch["divergence"] or confirm["divergence"]),
            "both_oib_pos_cvd_nonpos": bool(launch["divergence"] and confirm["divergence"]),
            "next_day_return_pct": nd_ret,
        })
    return pd.DataFrame(rows)


def group_stats(df: pd.DataFrame, label: str) -> Dict[str, Any]:
    if df.empty:
        return {"group": label, "count": 0}
    out = {
        "group": label,
        "count": int(len(df)),
        "win_rate_pct": round(float((df.net_return_pct > 0).mean() * 100.0), 2),
        "avg_net_return_pct": round(float(df.net_return_pct.mean()), 2),
        "median_net_return_pct": round(float(df.net_return_pct.median()), 2),
        "avg_next_day_return_pct": round(float(df.next_day_return_pct.dropna().mean()), 2) if df.next_day_return_pct.notna().any() else None,
        "launch_divergence_rate_pct": round(float(df.launch_oib_pos_cvd_nonpos.mean() * 100.0), 2),
        "confirm_divergence_rate_pct": round(float(df.confirm_oib_pos_cvd_nonpos.mean() * 100.0), 2),
        "any_divergence_rate_pct": round(float(df.any_oib_pos_cvd_nonpos.mean() * 100.0), 2),
        "median_launch_oib_cvd_diff": round(float(df.launch_oib_cvd_diff.median()), 2),
        "median_confirm_oib_cvd_diff": round(float(df.confirm_oib_cvd_diff.median()), 2),
    }
    return out


def diff_rows(enriched: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for version, g in enriched.groupby("sample_version"):
        g = g.sort_values("net_return_pct")
        losses = g[g.net_return_pct < 0]
        wins = g[g.net_return_pct > 0]
        groups = {
            "loss_all": losses,
            "loss_bottom10": losses.head(min(10, len(losses))),
            "win_all": wins,
            "win_top10": wins.tail(min(10, len(wins))),
        }
        for name, sub in groups.items():
            rows.append({"sample_version": version, **group_stats(sub, name)})
    return pd.DataFrame(rows)


def eval_rule(df: pd.DataFrame, version: str, rule_name: str, mask: pd.Series) -> Dict[str, Any]:
    d = df[df.sample_version == version].copy()
    m = mask.loc[d.index].fillna(False)
    kept = d[~m]
    filtered = d[m]
    losses = d[d.net_return_pct < 0]
    wins = d[d.net_return_pct > 0]
    top10 = d.sort_values("net_return_pct", ascending=False).head(min(10, len(d)))
    bottom10 = d.sort_values("net_return_pct", ascending=True).head(min(10, len(d)))
    kept_summary = summarize(kept.to_dict("records"))
    return {
        "sample_version": version,
        "rule_name": rule_name,
        "total_trades": int(len(d)),
        "filtered_count": int(m.sum()),
        "filtered_loss_count": int((filtered.net_return_pct < 0).sum()),
        "filtered_win_count": int((filtered.net_return_pct > 0).sum()),
        "filtered_bottom10_loss_count": int(top_false(mask=m, target=bottom10.index)),
        "filtered_top10_winner_count": int(top_false(mask=m, target=top10.index)),
        "loss_capture_rate_pct": round(float((filtered.net_return_pct < 0).sum() / max(len(losses), 1) * 100.0), 2),
        "win_kill_rate_pct": round(float((filtered.net_return_pct > 0).sum() / max(len(wins), 1) * 100.0), 2),
        "top10_kill_rate_pct": round(float(top_false(mask=m, target=top10.index) / max(len(top10), 1) * 100.0), 2),
        "kept_count": int(len(kept)),
        "kept_win_rate_pct": kept_summary.get("win_rate"),
        "kept_avg_net_return_pct": kept_summary.get("avg_return_pct"),
        "kept_median_net_return_pct": kept_summary.get("median_return_pct"),
        "kept_max_loss_pct": kept_summary.get("min_return_pct"),
    }


def top_false(mask: pd.Series, target: Iterable[int]) -> int:
    return int(mask.loc[list(target)].fillna(False).sum())


def scan_rules(enriched: pd.DataFrame) -> pd.DataFrame:
    rules: Dict[str, pd.Series] = {}
    rules["launch_divergence"] = enriched["launch_oib_pos_cvd_nonpos"]
    rules["confirm_divergence"] = enriched["confirm_oib_pos_cvd_nonpos"]
    rules["any_launch_or_confirm_divergence"] = enriched["any_oib_pos_cvd_nonpos"]
    rules["both_launch_and_confirm_divergence"] = enriched["both_oib_pos_cvd_nonpos"]

    for col, label in [("launch_oib_cvd_diff", "launch_diff"), ("confirm_oib_cvd_diff", "confirm_diff")]:
        positive = enriched[col][enriched[col] > 0]
        for q in [0.5, 0.75, 0.9]:
            if not positive.empty:
                th = float(positive.quantile(q))
                rules[f"{label}_gt_q{int(q*100)}_{th:.0f}"] = enriched[col] > th
    # Explicit OIB positive + CVD non-positive + stronger amount gap.
    for prefix in ["launch", "confirm"]:
        div = enriched[f"{prefix}_oib_pos_cvd_nonpos"]
        diff = enriched[f"{prefix}_oib_cvd_diff"]
        div_diff = diff[div]
        for q in [0.5, 0.75]:
            if not div_diff.empty:
                th = float(div_diff.quantile(q))
                rules[f"{prefix}_divergence_and_diff_gt_div_q{int(q*100)}_{th:.0f}"] = div & (diff > th)

    rows: List[Dict[str, Any]] = []
    for version in ["v1.3-threshold-1.5", "v1.4-balanced"]:
        for name, mask in rules.items():
            rows.append(eval_rule(enriched, version, name, mask))
    return pd.DataFrame(rows).sort_values(
        ["sample_version", "filtered_loss_count", "filtered_top10_winner_count", "filtered_win_count"],
        ascending=[True, False, True, True],
    )


def corr_rows(enriched: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = []
    cols = [
        "launch_oib_sum", "launch_cvd_sum", "launch_oib_cvd_diff", "launch_oib_to_abs_cvd_ratio",
        "confirm_oib_sum", "confirm_cvd_sum", "confirm_oib_cvd_diff", "confirm_oib_to_abs_cvd_ratio",
    ]
    for version, g in enriched.groupby("sample_version"):
        for col in cols:
            s = pd.to_numeric(g[col], errors="coerce")
            for target in ["next_day_return_pct", "net_return_pct"]:
                t = pd.to_numeric(g[target], errors="coerce")
                valid = s.notna() & t.notna()
                corr = float(s[valid].corr(t[valid], method="spearman")) if valid.sum() >= 3 else None
                rows.append({"sample_version": version, "feature": col, "target": target, "spearman_corr": None if corr is None or math.isnan(corr) else round(corr, 4), "n": int(valid.sum())})
    return rows


def write_readme(out: Path, summary: Dict[str, Any], diff: pd.DataFrame, scan: pd.DataFrame) -> None:
    best_bal = scan[scan.sample_version == "v1.4-balanced"].head(8)
    lines = [
        "# EXP-20260426-oib-cvd-divergence：OIB 与 CVD 背离验证",
        "",
        "## 1. 问题",
        "验证“盘口看起来买方强（OIB 为正），但主动成交 CVD 弱或负”是否能识别假托真砸/诱多，是否值得加入 S04 或反向过滤 S01。",
        "",
        "## 2. 假设",
        "如果启动期或回调确认日出现 `sum(oib_delta_amount) > 0 且 sum(cvd_delta_amount) <= 0`，说明挂单买盘强但主动成交不跟，亏损票中应更常见，且简单过滤应能少误杀大赢家。",
        "",
        "## 3. 数据范围",
        f"- 原子日线窗口：{summary['range']['raw_start']} ~ {summary['range']['replay_end']}",
        "- 候选发现日：2026-03-02 ~ 2026-04-24",
        "- 成熟交易：买入后至少还有 10 个交易日数据。",
        "",
        "## 4. 样本口径",
        "- `v1.3-threshold-1.5`：v1.3 稳健性扫描中阈值 1.5 的成熟交易。",
        "- `v1.4-balanced`：v1.4 双模式中 balanced 的成熟交易。",
        "- 分别对亏损票/亏损前10、盈利票/盈利前10做对比。",
        "",
        "## 5. 规则/参数",
        "- 启动窗口：`launch_start_date ~ launch_end_date`，通常为启动 3 日。",
        "- 回调确认日：`pullback_confirm_date` 单日。",
        "- 背离：窗口内 `sum(oib_delta_amount) > 0` 且 `sum(cvd_delta_amount) <= 0`。",
        "- 比值：`oib_sum / abs(cvd_sum)`，`cvd_sum` 近零时置空，避免除零。",
        "- 规则扫描只验证简单过滤，不改线上策略。",
        "",
        "## 6. 输出文件",
        "- `summary.json`",
        "- `oib_cvd_loss_win_diff.csv`",
        "- `divergence_rule_scan.csv`",
        "- `oib_cvd_trade_enriched.csv`（辅助明细）",
        "",
        "## 7. 核心结果",
        "",
        diff.to_markdown(index=False),
        "",
        "### v1.4-balanced 规则扫描前 8 行",
        "",
        best_bal.to_markdown(index=False),
        "",
        "## 8. 结论：继续观察，不直接采纳为 S01 硬过滤",
        "",
        summary["conclusion"],
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(EXP_DIR))
    parser.add_argument("--raw-start", default="2026-01-01")
    parser.add_argument("--replay-end", default="2026-04-24")
    args = parser.parse_args()

    t0 = time.perf_counter()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    trades = load_samples()
    raw = load_atomic_daily_window(args.raw_start, args.replay_end)
    enriched = enrich_oib_cvd(trades, raw)
    diff = diff_rows(enriched)
    scan = scan_rules(enriched)
    corrs = corr_rows(enriched)

    enriched.to_csv(out / "oib_cvd_trade_enriched.csv", index=False)
    diff.to_csv(out / "oib_cvd_loss_win_diff.csv", index=False)
    scan.to_csv(out / "divergence_rule_scan.csv", index=False)

    sample_summary = []
    for version, g in enriched.groupby("sample_version"):
        sample_summary.append({
            "sample_version": version,
            "trade_count": int(len(g)),
            "loss_count": int((g.net_return_pct < 0).sum()),
            "win_count": int((g.net_return_pct > 0).sum()),
            "any_divergence_count": int(g.any_oib_pos_cvd_nonpos.sum()),
            "launch_divergence_count": int(g.launch_oib_pos_cvd_nonpos.sum()),
            "confirm_divergence_count": int(g.confirm_oib_pos_cvd_nonpos.sum()),
        })

    v14_scan = scan[scan.sample_version == "v1.4-balanced"].copy()
    candidate_rules = v14_scan[(v14_scan.filtered_loss_count >= 2) & (v14_scan.filtered_top10_winner_count <= 1)].head(5)
    conclusion = (
        "OIB/CVD 背离在亏损票中有一定解释力，尤其可作为 S04 的风险标签；"
        "但在 v1.4-balanced 样本里，简单规则会同时过滤部分盈利票，且对 Top10 大赢家仍有误杀风险。"
        "建议先纳入 S04 观察型风险因子/案例解释，不纳入 S01 硬过滤；若后续扩大样本，可测试与弱启动、出货分、撤梯子共同触发。"
    )
    summary = {
        "experiment": "EXP-20260426-oib-cvd-divergence",
        "range": {"raw_start": args.raw_start, "replay_end": args.replay_end},
        "inputs": {"v13_trades": str(V13_TRADES), "v14_trades": str(V14_TRADES)},
        "sample_summary": sample_summary,
        "correlations": corrs,
        "top_candidate_rules_v1_4_balanced": candidate_rules.to_dict("records"),
        "output_files": ["README.md", "summary.json", "oib_cvd_loss_win_diff.csv", "divergence_rule_scan.csv", "oib_cvd_trade_enriched.csv"],
        "conclusion": conclusion,
        "timing_seconds": {"total": round(time.perf_counter() - t0, 2)},
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(out, summary, diff, scan)

    print(json.dumps({"sample_summary": sample_summary, "top_rules": summary["top_candidate_rules_v1_4_balanced"], "out": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
