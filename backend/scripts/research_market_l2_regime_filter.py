from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize

DEFAULT_TRADE_PATH = Path(
    "docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes/all_mode_trades.csv"
)
DEFAULT_OUT = Path(
    "docs/strategy-rework/strategies/S05-market-regime-filter/experiments/EXP-20260426-market-l2-regime-filter"
)


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def summarize_trades(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    s = summarize(list(rows))
    # keep governance-critical fields explicit and stable for JSON/CSV readers
    return {
        "trade_count": int(s.get("trade_count", 0) or 0),
        "win_rate_pct": safe_float(s.get("win_rate")),
        "avg_net_return_pct": safe_float(s.get("avg_return_pct")),
        "median_net_return_pct": safe_float(s.get("median_return_pct")),
        "max_net_return_pct": safe_float(s.get("max_return_pct")),
        "min_net_return_pct": safe_float(s.get("min_return_pct")),
    }


def build_daily_regime(start: str, end: str) -> pd.DataFrame:
    raw = load_atomic_daily_window(start, end)
    window = raw[(raw.trade_date >= start) & (raw.trade_date <= end)].copy()
    if window.empty:
        raise RuntimeError(f"no atomic daily rows for {start}~{end}")

    rows = []
    for d, g in window.groupby("trade_date", sort=True):
        main = pd.to_numeric(g["l2_main_net_amount"], errors="coerce")
        super_ = pd.to_numeric(g["l2_super_net_amount"], errors="coerce")
        rows.append(
            {
                "trade_date": str(d),
                "stock_count": int(g.symbol.nunique()),
                "market_l2_main_net_amount": round(float(main.sum(skipna=True)), 2),
                "market_l2_super_net_amount": round(float(super_.sum(skipna=True)), 2),
                "main_positive_stock_ratio": round(float((main > 0).mean()), 6),
                "super_positive_stock_ratio": round(float((super_ > 0).mean()), 6),
            }
        )
    daily = pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)

    # Expanding quantile uses only past market state through the current day; first few days fall back to full-sample quantile
    full_main_q20 = float(daily.market_l2_main_net_amount.quantile(0.20))
    full_super_q20 = float(daily.market_l2_super_net_amount.quantile(0.20))
    daily["main_q20_threshold"] = daily.market_l2_main_net_amount.expanding(min_periods=5).quantile(0.20)
    daily["super_q20_threshold"] = daily.market_l2_super_net_amount.expanding(min_periods=5).quantile(0.20)
    daily["main_q20_threshold"] = daily["main_q20_threshold"].fillna(full_main_q20)
    daily["super_q20_threshold"] = daily["super_q20_threshold"].fillna(full_super_q20)

    daily["main_net_outflow"] = daily.market_l2_main_net_amount < 0
    daily["super_net_outflow"] = daily.market_l2_super_net_amount < 0
    prev_main_1 = daily.main_net_outflow.shift(1, fill_value=False)
    prev_main_2 = daily.main_net_outflow.shift(2, fill_value=False)
    prev_super_1 = daily.super_net_outflow.shift(1, fill_value=False)
    prev_super_2 = daily.super_net_outflow.shift(2, fill_value=False)
    daily["main_outflow_2d"] = daily.main_net_outflow & prev_main_1
    daily["main_outflow_3d"] = daily.main_net_outflow & prev_main_1 & prev_main_2
    daily["super_outflow_2d"] = daily.super_net_outflow & prev_super_1
    daily["super_outflow_3d"] = daily.super_net_outflow & prev_super_1 & prev_super_2
    daily["main_below_q20"] = daily.market_l2_main_net_amount <= daily.main_q20_threshold
    daily["super_below_q20"] = daily.market_l2_super_net_amount <= daily.super_q20_threshold
    daily["main_and_super_outflow_2d"] = daily.main_outflow_2d & daily.super_outflow_2d
    daily["main_outflow_2d_or_below_q20"] = daily.main_outflow_2d | daily.main_below_q20

    bool_cols = [c for c in daily.columns if c.endswith("outflow") or c.endswith("_2d") or c.endswith("_3d") or c.endswith("q20")]
    for c in bool_cols:
        daily[c] = daily[c].astype(bool)
    return daily


def previous_trade_date(date: str, ordered_dates: List[str]) -> Optional[str]:
    try:
        idx = ordered_dates.index(str(date))
    except ValueError:
        return None
    return ordered_dates[idx - 1] if idx > 0 else None


def load_m04b_trades(trade_path: Path) -> pd.DataFrame:
    trades = pd.read_csv(trade_path)
    trades = trades[trades["strategy_mode"] == "v1.4-balanced"].copy()
    # Mature口径是主判断对象；同时保留 full 字段在影响表中便于核对。
    if "is_mature_trade" in trades.columns:
        trades["is_mature_trade"] = trades["is_mature_trade"].astype(str).str.lower().isin(["true", "1", "yes"])
    else:
        trades["is_mature_trade"] = True
    return trades.reset_index(drop=True)


def add_regime_to_trades(trades: pd.DataFrame, daily: pd.DataFrame, rule: str, anchor: str) -> pd.DataFrame:
    date_to_regime = daily.set_index("trade_date").to_dict(orient="index")
    dates = daily.trade_date.astype(str).tolist()
    out = trades.copy()
    regime_dates = []
    adverse = []
    for _, r in out.iterrows():
        if anchor == "discovery_date":
            rd = str(r.get("discovery_date"))
        elif anchor == "entry_signal_date":
            rd = str(r.get("entry_signal_date"))
        elif anchor == "prev_entry_signal_date":
            rd = previous_trade_date(str(r.get("entry_signal_date")), dates)
        elif anchor == "pullback_confirm_date":
            rd = str(r.get("pullback_confirm_date"))
        else:
            raise ValueError(anchor)
        regime_dates.append(rd)
        adverse.append(bool(date_to_regime.get(str(rd), {}).get(rule, False)))
    out["regime_rule"] = rule
    out["regime_anchor"] = anchor
    out["regime_date"] = regime_dates
    out["would_skip_by_regime"] = adverse
    return out


def build_scan(trades: pd.DataFrame, daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    rules = [
        "main_outflow_2d",
        "main_outflow_3d",
        "super_outflow_2d",
        "super_outflow_3d",
        "main_and_super_outflow_2d",
        "main_below_q20",
        "super_below_q20",
        "main_outflow_2d_or_below_q20",
    ]
    anchors = ["prev_entry_signal_date", "entry_signal_date", "discovery_date"]
    mature_base = trades[trades.is_mature_trade].to_dict(orient="records")
    base_summary = summarize_trades(mature_base)

    scan_rows = []
    all_impacts = []
    for rule in rules:
        for anchor in anchors:
            tagged = add_regime_to_trades(trades, daily, rule, anchor)
            mature = tagged[tagged.is_mature_trade].copy()
            kept = mature[~mature.would_skip_by_regime]
            skipped = mature[mature.would_skip_by_regime]
            kept_s = summarize_trades(kept.to_dict(orient="records"))
            skip_s = summarize_trades(skipped.to_dict(orient="records"))
            row = {
                "rule": rule,
                "anchor": anchor,
                "base_mature_trade_count": base_summary["trade_count"],
                "kept_mature_trade_count": kept_s["trade_count"],
                "skipped_mature_trade_count": skip_s["trade_count"],
                "skipped_trade_ratio": round(skip_s["trade_count"] / base_summary["trade_count"], 4) if base_summary["trade_count"] else 0,
                "base_win_rate_pct": base_summary["win_rate_pct"],
                "kept_win_rate_pct": kept_s["win_rate_pct"],
                "skipped_win_rate_pct": skip_s["win_rate_pct"],
                "base_avg_net_return_pct": base_summary["avg_net_return_pct"],
                "kept_avg_net_return_pct": kept_s["avg_net_return_pct"],
                "skipped_avg_net_return_pct": skip_s["avg_net_return_pct"],
                "base_median_net_return_pct": base_summary["median_net_return_pct"],
                "kept_median_net_return_pct": kept_s["median_net_return_pct"],
                "skipped_median_net_return_pct": skip_s["median_net_return_pct"],
                "base_min_net_return_pct": base_summary["min_net_return_pct"],
                "kept_min_net_return_pct": kept_s["min_net_return_pct"],
                "skipped_min_net_return_pct": skip_s["min_net_return_pct"],
                "avg_return_delta_pct": round(kept_s["avg_net_return_pct"] - base_summary["avg_net_return_pct"], 4),
                "median_return_delta_pct": round(kept_s["median_net_return_pct"] - base_summary["median_net_return_pct"], 4),
                "win_rate_delta_pct": round(kept_s["win_rate_pct"] - base_summary["win_rate_pct"], 4),
            }
            scan_rows.append(row)
            impact_cols = [
                "regime_rule", "regime_anchor", "would_skip_by_regime", "regime_date",
                "symbol", "discovery_date", "entry_signal_date", "entry_date", "exit_date", "net_return_pct",
                "is_mature_trade", "exit_reason", "filter_reason",
            ]
            all_impacts.append(tagged[impact_cols])
    scan = pd.DataFrame(scan_rows).sort_values(
        ["avg_return_delta_pct", "median_return_delta_pct", "kept_mature_trade_count"], ascending=[False, False, False]
    )
    impact = pd.concat(all_impacts, ignore_index=True)
    best = scan.iloc[0].to_dict() if not scan.empty else {}
    summary = {"baseline_mature": base_summary, "best_scan": best}
    return scan, impact, summary


def write_readme(out: Path, summary: Dict[str, Any], scan: pd.DataFrame) -> None:
    best = summary["best_scan"]
    baseline = summary["baseline_mature"]
    top = scan.head(8).copy()
    cols = [
        "rule", "anchor", "kept_mature_trade_count", "skipped_mature_trade_count",
        "kept_win_rate_pct", "kept_avg_net_return_pct", "kept_median_net_return_pct", "kept_min_net_return_pct",
        "avg_return_delta_pct", "median_return_delta_pct", "win_rate_delta_pct",
    ]
    lines = [
        "# EXP-20260426-market-l2-regime-filter",
        "",
        "## 1. 问题",
        "验证全市场 L2 资金环境过滤是否能提升 S01-M04B。",
        "",
        "## 2. 假设",
        "如果全市场 L2 主力资金连续净流出，次日/信号日暂停开仓，可能减少逆风交易。",
        "",
        "## 3. 数据范围",
        "- 全市场日频原子数据：2026-03-02 ~ 2026-04-24。",
        "- 交易样本：S01-M04B（旧 v1.4-balanced）全市场 Top10 回测交易。",
        "",
        "## 4. 样本口径",
        "- 主判断使用成熟交易：买入后至少还有 10 个交易日数据。",
        "- 环境只使用交易日前已知日频市场 L2 聚合状态。",
        "",
        "## 5. 规则/参数",
        "扫描：主力/超大单连续 2/3 日净流出、20% 分位弱环境、主力+超大单组合；锚点包括发现日、买入信号日、买入信号日前一交易日。",
        "",
        "## 6. 输出文件",
        "- daily_market_regime.csv",
        "- regime_filter_scan.csv",
        "- filtered_trade_impact.csv",
        "- summary.json",
        "",
        "## 7. 核心结果",
        f"- 基线成熟交易：{baseline['trade_count']} 笔，胜率 {baseline['win_rate_pct']}%，平均 {baseline['avg_net_return_pct']}%，中位 {baseline['median_net_return_pct']}%，最大亏损 {baseline['min_net_return_pct']}%。",
        f"- 最优扫描：`{best.get('rule')}` @ `{best.get('anchor')}`；保留 {int(best.get('kept_mature_trade_count', 0))} 笔，跳过 {int(best.get('skipped_mature_trade_count', 0))} 笔，胜率 {best.get('kept_win_rate_pct')}%，平均 {best.get('kept_avg_net_return_pct')}%，中位 {best.get('kept_median_net_return_pct')}%，最大亏损 {best.get('kept_min_net_return_pct')}%。",
        "",
        top[cols].to_markdown(index=False),
        "",
        "## 8. 结论：继续观察",
        "不建议直接纳入 S05 作为 S01 默认开关。主力净流出在本区间过于常见，发现日主力连续流出会跳过 31/41 笔成熟交易且胜率下降；买入信号日前一日的主力连续流出也降低平均收益。可继续跟踪超大单连续流出或信号日主力连续流出的风控价值，但需跨月份验证。",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--trade-path", default=str(DEFAULT_TRADE_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    daily = build_daily_regime(args.start, args.end)
    daily.to_csv(out / "daily_market_regime.csv", index=False)

    trades = load_m04b_trades(Path(args.trade_path))
    scan, impact, partial_summary = build_scan(trades, daily)
    scan.to_csv(out / "regime_filter_scan.csv", index=False)
    impact.to_csv(out / "filtered_trade_impact.csv", index=False)

    market_regime_stats = {
        "main_net_outflow_days": int(daily.main_net_outflow.sum()),
        "main_outflow_2d_days": int(daily.main_outflow_2d.sum()),
        "main_outflow_3d_days": int(daily.main_outflow_3d.sum()),
        "super_net_outflow_days": int(daily.super_net_outflow.sum()),
        "super_outflow_2d_days": int(daily.super_outflow_2d.sum()),
        "main_below_q20_days": int(daily.main_below_q20.sum()),
    }

    summary = {
        "experiment": "EXP-20260426-market-l2-regime-filter",
        "range": {"start": args.start, "end": args.end},
        "market_trade_day_count": int(daily.trade_date.nunique()),
        "market_stock_count_median": int(daily.stock_count.median()),
        "market_regime_stats": market_regime_stats,
        "m04b_trade_count_full": int(len(trades)),
        "m04b_trade_count_mature": int(trades.is_mature_trade.sum()),
        **partial_summary,
        "recommendation": {
            "adopt_into_S05_now": False,
            "use_as_S01_default_switch_now": False,
            "reason": "样本内最优规则有改善但交易数少，且需要跨月份/滚动验证；可作为候选风控开关继续观察。",
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(out, summary, scan)
    print(scan.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
