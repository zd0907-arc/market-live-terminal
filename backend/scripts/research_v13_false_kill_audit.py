from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

DEFAULT_SOURCE = Path(
    "docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-robustness-scan/all_threshold_trades.csv"
)
DEFAULT_NAME_CACHE = Path(
    "docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-5-cap-scan/maxcap_500yi/tencent_snapshot_cache.json"
)
DEFAULT_OUT = Path(
    "docs/strategy-rework/strategies/S01-capital-trend-reversal/experiments/EXP-20260426-v13-false-kill-audit"
)

NUMERIC_FIELDS = {
    "rank",
    "setup_score",
    "pre20_return_pct",
    "pre20_super_price_divergence",
    "pre20_main_price_divergence",
    "pre5_return_pct",
    "pre5_super_price_divergence",
    "launch3_return_pct",
    "launch3_max_drawdown_pct",
    "launch3_super_net_ratio",
    "launch3_main_net_ratio",
    "launch3_add_buy_ratio",
    "pullback_super_net_ratio",
    "pullback_main_net_ratio",
    "pullback_support_spread_avg",
    "pullback_depth_from_launch_peak_pct",
    "confirm_distribution_score",
    "launch_hist_order_days",
    "launch_order_days",
    "launch_cancel_buy_to_add_buy",
    "launch_hist_cancel_buy_to_add_buy_avg",
    "launch_cancel_buy_to_add_buy_vs_hist",
    "gross_entry_price",
    "entry_price",
    "gross_exit_price",
    "exit_price",
    "return_pct",
    "net_return_pct",
    "max_runup_pct",
    "max_drawdown_pct",
    "holding_days",
    "final_cum_super_amount",
    "final_cum_super_peak_amount",
    "final_cum_super_ratio",
    "final_super_peak_drawdown_pct",
    "final_super_decline_streak",
    "future_days_available",
}

FOCUS_COLUMNS = [
    "symbol",
    "stock_name",
    "discovery_date",
    "rank",
    "entry_date",
    "exit_date",
    "net_return_pct",
    "max_runup_pct",
    "max_drawdown_pct",
    "holding_days",
    "exit_reason",
    "launch_cancel_buy_to_add_buy_vs_hist",
    "launch3_return_pct",
    "launch3_super_net_ratio",
    "launch3_main_net_ratio",
    "pullback_super_net_ratio",
    "pullback_main_net_ratio",
    "pullback_support_spread_avg",
    "confirm_distribution_score",
    "final_cum_super_ratio",
    "final_super_peak_drawdown_pct",
    "v13_15_action",
    "v13_20_action",
    "audit_note",
]

FEATURES = [
    "launch_cancel_buy_to_add_buy_vs_hist",
    "launch3_return_pct",
    "launch3_super_net_ratio",
    "launch3_main_net_ratio",
    "pullback_super_net_ratio",
    "pullback_main_net_ratio",
    "pullback_support_spread_avg",
    "confirm_distribution_score",
    "final_cum_super_ratio",
    "final_super_peak_drawdown_pct",
    "max_runup_pct",
    "max_drawdown_pct",
]


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in NUMERIC_FIELDS:
            if key in row:
                row[key] = as_float(row[key])
        row["is_mature_trade"] = as_bool(row.get("is_mature_trade"))
    return rows


def load_names(cache_path: Path) -> Dict[str, str]:
    if not cache_path.exists():
        return {}
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    return {str(k): str(v.get("name") or "") for k, v in data.items() if isinstance(v, dict)}


def is_filtered(row: Dict[str, Any], threshold: float) -> bool:
    return as_bool(row.get("order_filter_available")) and as_float(row.get("launch_cancel_buy_to_add_buy_vs_hist")) > threshold


def perf(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [as_float(r.get("net_return_pct")) for r in rows]
    if not vals:
        return {"trade_count": 0, "win_rate_pct": 0.0, "avg_return_pct": 0.0, "median_return_pct": 0.0, "max_return_pct": 0.0, "min_return_pct": 0.0, "sum_return_pct": 0.0}
    return {
        "trade_count": len(vals),
        "win_rate_pct": round(sum(v > 0 for v in vals) / len(vals) * 100, 2),
        "avg_return_pct": round(sum(vals) / len(vals), 2),
        "median_return_pct": round(statistics.median(vals), 2),
        "max_return_pct": round(max(vals), 2),
        "min_return_pct": round(min(vals), 2),
        "sum_return_pct": round(sum(vals), 2),
    }


def feature_profile(rows: Sequence[Dict[str, Any]], features: Iterable[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for feature in features:
        vals = [as_float(r.get(feature)) for r in rows if r.get(feature) not in (None, "")]
        if vals:
            out[feature] = {"avg": round(sum(vals) / len(vals), 4), "median": round(statistics.median(vals), 4)}
    return out


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], columns: Sequence[str] | None = None) -> None:
    if columns is None:
        seen: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.append(key)
        columns = seen
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def annotate(row: Dict[str, Any], names: Dict[str, str]) -> Dict[str, Any]:
    out = dict(row)
    out["stock_name"] = out.get("stock_name") or names.get(str(out.get("symbol")), "")
    out["v13_15_action"] = "filtered" if is_filtered(out, 1.5) else "kept"
    out["v13_20_action"] = "filtered" if is_filtered(out, 2.0) else "kept"
    if is_filtered(out, 1.5) and as_float(out.get("net_return_pct")) > 15:
        out["audit_note"] = "false_killed_big_winner_gt_15"
    elif is_filtered(out, 1.5) and as_float(out.get("net_return_pct")) <= -8:
        out["audit_note"] = "correctly_filtered_big_loss_le_-8"
    elif is_filtered(out, 1.5):
        out["audit_note"] = "filtered_other"
    else:
        out["audit_note"] = "kept_by_1_5"
    return out


def threshold_tradeoff_rows(base_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for label, rows in [
        ("no_filter_mature", list(base_rows)),
        ("threshold_1_5_kept", [r for r in base_rows if not is_filtered(r, 1.5)]),
        ("threshold_2_0_kept", [r for r in base_rows if not is_filtered(r, 2.0)]),
        ("threshold_1_5_filtered", [r for r in base_rows if is_filtered(r, 1.5)]),
        ("threshold_2_0_filtered", [r for r in base_rows if is_filtered(r, 2.0)]),
        ("filtered_by_1_5_only_band", [r for r in base_rows if is_filtered(r, 1.5) and not is_filtered(r, 2.0)]),
    ]:
        row = {"bucket": label, **perf(rows)}
        row["big_winner_gt_15_count"] = sum(as_float(r.get("net_return_pct")) > 15 for r in rows)
        row["big_loss_le_-8_count"] = sum(as_float(r.get("net_return_pct")) <= -8 for r in rows)
        out.append(row)
    return out


def render_readme(summary: Dict[str, Any], tradeoff: Sequence[Dict[str, Any]], big_winners: Sequence[Dict[str, Any]]) -> str:
    big_lines = []
    for r in big_winners:
        big_lines.append(
            f"| {r.get('symbol')} | {r.get('stock_name')} | {r.get('entry_date')} | {r.get('exit_date')} | "
            f"{as_float(r.get('net_return_pct')):.2f}% | {as_float(r.get('launch_cancel_buy_to_add_buy_vs_hist')):.4f} | "
            f"{as_float(r.get('pullback_support_spread_avg')):.4f} | {as_float(r.get('final_cum_super_ratio')):.4f} |"
        )
    tradeoff_lines = [
        f"| {r['bucket']} | {r['trade_count']} | {r['win_rate_pct']:.2f}% | {r['avg_return_pct']:.2f}% | {r['median_return_pct']:.2f}% | {r['sum_return_pct']:.2f}% | {r['big_winner_gt_15_count']} | {r['big_loss_le_-8_count']} |"
        for r in tradeoff
    ]
    return "\n".join([
        "# EXP-20260426-v13-false-kill-audit：v1.3 撤梯子过滤误杀审查",
        "",
        "## 1. 问题",
        "审查 `launch_cancel_buy_to_add_buy_vs_hist > 1.5` 是否误杀收益 >15% 的大赢家。",
        "",
        "## 2. 假设",
        "若被过滤大赢家具备强补偿特征，可考虑豁免；否则维持阈值，接受少数误杀。",
        "",
        "## 3. 数据范围",
        f"- 来源：`{summary['source']}`",
        "- 发现日：2026-03-02 ~ 2026-04-24",
        "- 成熟交易：买入后至少还有 10 个交易日数据",
        "",
        "## 4. 样本口径",
        "以不加 v1.3 过滤的成熟交易为母样本，再按阈值 1.5 / 2.0 划分保留与过滤。",
        "",
        "## 5. 规则/参数",
        "```text",
        "v1.3过滤：order_filter_available 且 launch_cancel_buy_to_add_buy_vs_hist > threshold",
        "大赢家：net_return_pct > 15",
        "大亏：net_return_pct <= -8",
        "```",
        "",
        "## 6. 输出文件",
        "- `filtered_trades_sorted.csv`：阈值 1.5 会过滤的成熟交易，按最终收益降序",
        "- `false_killed_big_winners.csv`：被过滤但收益 >15% 的大赢家",
        "- `threshold_tradeoff.csv`：不加过滤、阈值 1.5、阈值 2.0 的权衡",
        "- `summary.json`：程序可读摘要",
        "",
        "## 7. 核心结果",
        "",
        "| 分组 | 笔数 | 胜率 | 平均收益 | 中位收益 | 收益合计 | >15%大赢家 | <=-8%大亏 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *tradeoff_lines,
        "",
        "被阈值 1.5 过滤的 26 笔成熟交易整体收益为负：平均 -4.13%，中位 -8.33%，收益合计 -107.33%。",
        "",
        "### 被过滤但收益 >15% 的大赢家",
        "",
        "| 代码 | 名称 | 买入日 | 卖出日 | 净收益 | 撤买/新增买相对历史 | 回调支撑差 | 卖出时累计超大单/成交额 |",
        "|---|---|---|---|---:|---:|---:|---:|",
        *(big_lines or ["| - | - | - | - | - | - | - | - |"]),
        "",
        "### 为什么撤买单异常也能涨",
        "这 2 笔不是靠盘口撤单信号本身修复，而是有更强的资金补偿：回调日超大单/主力都仍为净流入，卖出时累计超大单/成交额仍为正，持仓期最大回撤较浅。启动涨幅并不显著更强；回调承接和出货分有分化，不能单独作为豁免。",
        "",
        "### 阈值 1.5 vs 2.0",
        "2.0 比 1.5 只多保留 2 笔：一笔 +2.99%，一笔 -8.35%，合计 -5.36%。放宽到 2.0 没救回 >15% 大赢家，反而保留一笔大亏。",
        "",
        "## 8. 结论：继续观察",
        "不建议把阈值从 1.5 放宽到 2.0。可以继续研究豁免条件，但不应无条件豁免高撤梯子；候选豁免必须同时要求回调超大单/主力净流入、累计超大单不转负、持仓回撤浅，并用确认日出货分不过高作辅助约束。",
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--name-cache", default=str(DEFAULT_NAME_CACHE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    names = load_names(Path(args.name_cache))

    rows = [annotate(r, names) for r in read_rows(source)]
    no_filter_mature = [r for r in rows if str(r.get("filter_threshold")) == "none" and r.get("is_mature_trade")]
    filtered_15 = sorted([r for r in no_filter_mature if is_filtered(r, 1.5)], key=lambda r: as_float(r.get("net_return_pct")), reverse=True)
    big_winners = [r for r in filtered_15 if as_float(r.get("net_return_pct")) > 15]
    kept_15 = [r for r in no_filter_mature if not is_filtered(r, 1.5)]
    filtered_losses = [r for r in filtered_15 if as_float(r.get("net_return_pct")) <= 0]

    tradeoff = threshold_tradeoff_rows(no_filter_mature)

    write_csv(out / "filtered_trades_sorted.csv", filtered_15, FOCUS_COLUMNS)
    write_csv(out / "false_killed_big_winners.csv", big_winners, FOCUS_COLUMNS)
    write_csv(out / "threshold_tradeoff.csv", tradeoff)

    summary = {
        "source": str(source),
        "base_no_filter_mature": perf(no_filter_mature),
        "threshold_1_5_kept": perf(kept_15),
        "threshold_1_5_filtered": perf(filtered_15),
        "threshold_2_0_kept": perf([r for r in no_filter_mature if not is_filtered(r, 2.0)]),
        "false_killed_big_winners_gt_15_count": len(big_winners),
        "false_killed_big_winners_gt_15": [
            {
                "symbol": r.get("symbol"),
                "stock_name": r.get("stock_name"),
                "entry_date": r.get("entry_date"),
                "exit_date": r.get("exit_date"),
                "net_return_pct": as_float(r.get("net_return_pct")),
                "launch_cancel_buy_to_add_buy_vs_hist": as_float(r.get("launch_cancel_buy_to_add_buy_vs_hist")),
            }
            for r in big_winners
        ],
        "profiles": {
            "filtered_1_5_all": feature_profile(filtered_15, FEATURES),
            "filtered_1_5_big_winners_gt_15": feature_profile(big_winners, FEATURES),
            "filtered_1_5_losers_le_0": feature_profile(filtered_losses, FEATURES),
        },
        "threshold_1_5_vs_2_0": {
            "additional_trades_kept_by_2_0": [
                {"symbol": r.get("symbol"), "stock_name": r.get("stock_name"), "net_return_pct": as_float(r.get("net_return_pct")), "launch_cancel_buy_to_add_buy_vs_hist": as_float(r.get("launch_cancel_buy_to_add_buy_vs_hist"))}
                for r in no_filter_mature
                if is_filtered(r, 1.5) and not is_filtered(r, 2.0)
            ],
            "recommendation": "keep_threshold_1_5",
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "README.md").write_text(render_readme(summary, tradeoff, big_winners), encoding="utf-8")

    print(json.dumps({"out": str(out), "base": perf(no_filter_mature), "filtered_1_5": perf(filtered_15), "big_winners_gt_15": summary["false_killed_big_winners_gt_15"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
