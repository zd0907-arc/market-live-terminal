#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import MARKET_HEAT_DIR, _trade_dates, ensure_market_heat_dir
from backend.scripts.analyze_hot_sector_granularity import DEFAULT_FINE_RULES, load_fine_sector_themes, load_json
from backend.scripts.analyze_hot_theme_funding_cross_validation import load_atomic_extra
from backend.scripts.analyze_hot_theme_low_position_l2_strategy import active_hot_themes, prior_avg_amount
from backend.scripts.analyze_hot_theme_low_position_l2_robustness import ma_distance, position_n, super_condition
from backend.scripts.analyze_hot_theme_winner_lead_lag import (
    DEFAULT_STOCK_SECTOR_DB,
    DEFAULT_TRADABLE_THEME_DB,
    is_st_name,
    is_unbuyable_limit_up,
    load_extra_names,
    load_price_and_limit_rows,
    safe_float,
)
from backend.scripts.analyze_strategy_theme_lifecycle import build_rank_history
from backend.scripts.analyze_strategy_theme_resonance import first_indexes, load_or_build_heat_snapshots


def sf(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def pct(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def stat(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0, "avg": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0, "p90": 0.0, "worst": 0.0, "best": 0.0}
    def q(p: float) -> float:
        return vals[int((len(vals) - 1) * p)]
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 4),
        "median": round(statistics.median(vals), 4),
        "p25": round(q(0.25), 4),
        "p75": round(q(0.75), 4),
        "p90": round(q(0.90), 4),
        "worst": round(vals[0], 4),
        "best": round(vals[-1], 4),
    }


def pct_rate(rows: Sequence[Dict[str, Any]], pred) -> float:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 4) if rows else 0.0


def tradeable(symbol: str, d: str, entry_date: str, i: int, rows: Dict[str, sqlite3.Row], first_idx: Dict[str, int], name_map: Dict[str, str], limit_rows: Dict[str, Dict[str, sqlite3.Row]], min_amount: float, min_history_days: int) -> bool:
    d_row = rows.get(d)
    entry_row = rows.get(entry_date)
    if not d_row or not entry_row:
        return False
    if first_idx.get(symbol, 10**9) > i - min_history_days:
        return False
    if safe_float(d_row["total_amount"]) < min_amount:
        return False
    if is_st_name(name_map.get(symbol, "")):
        return False
    if is_unbuyable_limit_up(symbol, d_row, entry_row, limit_rows, entry_date):
        return False
    return True


def evaluate_path(rows: Dict[str, sqlite3.Row], trade_dates: Sequence[str], i: int, horizon: int) -> Optional[Dict[str, Any]]:
    entry_idx = i + 1
    if entry_idx >= len(trade_dates):
        return None
    entry = rows.get(trade_dates[entry_idx])
    if not entry or sf(entry["close"]) <= 0:
        return None
    entry_price = sf(entry["close"])
    fut = []
    for j in range(i + 2, i + horizon + 2):
        if j >= len(trade_dates):
            return None
        row = rows.get(trade_dates[j])
        if not row:
            return None
        fut.append((trade_dates[j], row))
    highs = [(d, sf(r["high"])) for d, r in fut]
    lows = [(d, sf(r["low"])) for d, r in fut]
    max_date, max_high = max(highs, key=lambda x: x[1])
    min_date, min_low = min(lows, key=lambda x: x[1])
    close_end = sf(fut[-1][1]["close"])
    out: Dict[str, Any] = {
        "entry_date": trade_dates[entry_idx],
        "entry_price": round(entry_price, 4),
        "mfe40": pct(max_high, entry_price),
        "mae40": pct(min_low, entry_price),
        "close40": pct(close_end, entry_price),
        "max_date": max_date,
        "min_date": min_date,
    }
    for target in [10, 20, 30, 50]:
        hit_j: Optional[int] = None
        for offset, (_d, r) in enumerate(fut):
            if pct(sf(r["high"]), entry_price) is not None and pct(sf(r["high"]), entry_price) >= target:
                hit_j = offset
                break
        if hit_j is None:
            out[f"hit{target}"] = False
            out[f"mae_before_hit{target}"] = None
            out[f"days_to_hit{target}"] = None
        else:
            lows_before = [sf(r["low"]) for _d, r in fut[: hit_j + 1]]
            out[f"hit{target}"] = True
            out[f"mae_before_hit{target}"] = pct(min(lows_before), entry_price)
            out[f"days_to_hit{target}"] = hit_j + 1
    return out


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    latest_date = _trade_dates("9999-12-31", 1)[-1]
    raw_dates = _trade_dates(latest_date, args.days + args.min_history_days + args.horizon + 120)
    # Full-window backtest: D+1 entry plus 40 future sessions must exist.
    trade_dates_all, price_rows, limit_rows = load_price_and_limit_rows(raw_dates[0], latest_date)
    date_index = {d: idx for idx, d in enumerate(trade_dates_all)}
    full_end_idx = len(trade_dates_all) - args.horizon - 2
    full_end_date = trade_dates_all[full_end_idx]
    analysis_dates = [d for d in raw_dates if d <= full_end_date][-args.days:]
    first_idx = first_indexes(price_rows, date_index)

    rules = load_json(Path(args.fine_rules))
    themes, theme_members, _symbol_themes, name_map = load_fine_sector_themes(Path(args.tradable_theme_db), rules, args.min_member_count, args.max_member_count)
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})
    heat_dates = [d for d in raw_dates if d <= analysis_dates[-1]]
    snapshots = load_or_build_heat_snapshots(heat_dates, themes, 15, args.min_member_count, args.max_member_count, MARKET_HEAT_DIR / "cache", use_cache=not args.no_heat_cache)
    rank_history = build_rank_history(snapshots, heat_dates, 15)
    heat_pos = {d: idx for idx, d in enumerate(heat_dates)}
    extras = load_atomic_extra(raw_dates[0], analysis_dates[-1])

    candidates: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for d in analysis_dates:
        i = date_index.get(d)
        if i is None or i < args.min_history_days or i + args.horizon + 1 >= len(trade_dates_all) or d not in heat_pos:
            continue
        entry_date = trade_dates_all[i + 1]
        active = active_hot_themes(d, heat_dates, heat_pos, rank_history, snapshots, args.active_top_k, args.hot_lookback, args.hot_min_hits, args.hot_max_hits)
        for theme in active:
            for symbol in theme_members.get(theme["id"], set()):
                rows = price_rows.get(symbol, {})
                if d not in rows or entry_date not in rows or trade_dates_all[i - 1] not in rows or trade_dates_all[i - 5] not in rows:
                    continue
                if not tradeable(symbol, d, entry_date, i, rows, first_idx, name_map, limit_rows, args.min_amount, args.min_history_days):
                    continue
                d_row = rows[d]
                y_row = rows[trade_dates_all[i - 1]]
                ret5 = pct(sf(d_row["close"]), sf(rows[trade_dates_all[i - 5]]["close"]))
                if ret5 is None or ret5 < args.min_5d_return or ret5 >= args.max_5d_return:
                    continue
                if sf(d_row["l2_main_net_amount"]) <= 0 or sf(y_row["l2_main_net_amount"]) <= 0:
                    continue
                pos20 = position_n(rows, trade_dates_all, i, 20)
                if pos20 is None or pos20 > args.max_20d_position:
                    continue
                avg10 = prior_avg_amount(rows, trade_dates_all, i, 10)
                if not avg10 or avg10 <= 0:
                    continue
                path = evaluate_path(rows, trade_dates_all, i, args.horizon)
                if not path:
                    continue
                extra_rows = extras.get(symbol, {})
                rec = {
                    "trade_date": d,
                    "symbol": symbol,
                    "name": name_map.get(symbol, symbol),
                    "theme_id": theme["id"],
                    "theme_name": theme["name"],
                    "theme_rank": theme["rank"],
                    "theme_recent_hits": theme["recent_hits"],
                    "return_5d_pct": ret5,
                    "position_20d": pos20,
                    "amount_ratio_10d": sf(d_row["total_amount"]) / avg10,
                    "ma60_abs_pct": abs(ma_distance(rows, trade_dates_all, i, 60) or 999),
                    "l2_main_2d_yi": (sf(d_row["l2_main_net_amount"]) + sf(y_row["l2_main_net_amount"])) / 100_000_000,
                    "super_3d_sum_positive": super_condition(extra_rows, trade_dates_all, i, "3d_sum_positive"),
                    "super_2of3": super_condition(extra_rows, trade_dates_all, i, "2of3"),
                    "amount_ok": 0.5 <= (sf(d_row["total_amount"]) / avg10) <= 1.2,
                    "ma60_ok": abs(ma_distance(rows, trade_dates_all, i, 60) or 999) <= 8,
                    **path,
                }
                key = (d, symbol)
                old = candidates.get(key)
                if old is None or rec["theme_rank"] < old["theme_rank"]:
                    candidates[key] = rec

    rows = list(candidates.values())
    groups = {
        "core_hot_low_main_l2": rows,
        "plus_amount_0_5_1_2": [r for r in rows if r["amount_ok"]],
        "plus_super_3d_sum_positive": [r for r in rows if r["super_3d_sum_positive"]],
        "plus_amount_and_super_3d": [r for r in rows if r["amount_ok"] and r["super_3d_sum_positive"]],
        "plus_amount_and_super_2of3": [r for r in rows if r["amount_ok"] and r["super_2of3"]],
        "strict_approx": [r for r in rows if r["amount_ok"] and r["super_2of3"] and r["ma60_ok"]],
    }

    def summarize(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "n": len(rs),
            "mfe40": stat([r["mfe40"] for r in rs]),
            "mae40": stat([r["mae40"] for r in rs]),
            "close40": stat([r["close40"] for r in rs]),
            "hit10": pct_rate(rs, lambda r: r["hit10"]),
            "hit20": pct_rate(rs, lambda r: r["hit20"]),
            "hit50": pct_rate(rs, lambda r: r["hit50"]),
            "safe10_mae5": pct_rate(rs, lambda r: r["hit10"] and sf(r.get("mae_before_hit10"), -999) >= -5),
            "safe20_mae8": pct_rate(rs, lambda r: r["hit20"] and sf(r.get("mae_before_hit20"), -999) >= -8),
            "safe20_mae10": pct_rate(rs, lambda r: r["hit20"] and sf(r.get("mae_before_hit20"), -999) >= -10),
            "safe50_mae10": pct_rate(rs, lambda r: r["hit50"] and sf(r.get("mae_before_hit50"), -999) >= -10),
            "no_big_loss_final_win": pct_rate(rs, lambda r: sf(r["mae40"]) >= -10 and sf(r["close40"]) > 0),
            "pain_then_hit20": pct_rate(rs, lambda r: r["hit20"] and sf(r.get("mae_before_hit20"), 0) < -10),
        }

    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "analysis_start": analysis_dates[0],
            "analysis_end_full_window": analysis_dates[-1],
            "latest_price_date": latest_date,
            "horizon_days": args.horizon,
            "entry": "D+1 close; future path uses D+2..D+41 high/low/close, requiring full 40 sessions.",
            "premise": "hot fine theme + low position + two-day main L2 inflow; then layer amount/super/ma60 filters.",
        },
        "groups": {k: summarize(v) for k, v in groups.items()},
        "top_examples": {
            k: [
                {field: r.get(field) for field in ["trade_date", "symbol", "name", "theme_name", "mfe40", "mae40", "close40", "mae_before_hit20", "days_to_hit20", "amount_ratio_10d", "position_20d", "ma60_abs_pct"]}
                for r in sorted(v, key=lambda x: sf(x["mfe40"]), reverse=True)[:12]
            ]
            for k, v in groups.items()
        },
        "rows": rows,
    }
    return report


def fmt_stat(s: Dict[str, Any]) -> str:
    return f"avg={s['avg']:.2f}% med={s['median']:.2f}% p75={s['p75']:.2f}% p90={s['p90']:.2f}% best={s['best']:.2f}%"


def render(report: Dict[str, Any]) -> str:
    labels = {
        "core_hot_low_main_l2": "核心：热门+低位+主力2日流入",
        "plus_amount_0_5_1_2": "+ 量能0.5~1.2",
        "plus_super_3d_sum_positive": "+ 超大单3日合计为正",
        "plus_amount_and_super_3d": "+ 量能 + 超大单3日为正",
        "plus_amount_and_super_2of3": "+ 量能 + 超大单3天2阳",
        "strict_approx": "严格近似：量能+超大单2/3+60日乖离<=8",
    }
    lines = [
        "# 热门板块低位埋伏：两个月机会/风险重估",
        "",
        "## 结论",
        "",
        "```text",
        "这次不反推全市场赢家，也不只看原87个严格样本。",
        "样本从核心前提出发：热门细分板块 + 个股低位 + 主力资金连续流入；再逐层叠加量能、超大单、60日位置。",
        "评价目标改成：未来40个交易日内的最大涨幅，同时看达到涨幅前是否先出现大回撤。",
        "```",
        "",
        "## 分层结果",
        "",
        "| 样本层 | 样本 | MFE40 | MAE40 | 40日收盘 | hit20 | hit20且达标前回撤不超8% | hit50且达标前回撤不超10% | 不大亏且最终赚钱 |",
        "|---|---:|---|---|---|---:|---:|---:|---:|",
    ]
    for key, item in report["groups"].items():
        lines.append(
            f"| {labels.get(key, key)} | {item['n']} | {fmt_stat(item['mfe40'])} | {fmt_stat(item['mae40'])} | {fmt_stat(item['close40'])} | "
            f"{item['hit20']:.1%} | {item['safe20_mae8']:.1%} | {item['safe50_mae10']:.1%} | {item['no_big_loss_final_win']:.1%} |"
        )
    lines += ["", "## 严格近似样本的代表机会", ""]
    for r in report["top_examples"].get("strict_approx", [])[:10]:
        lines.append(
            f"- {r['trade_date']} {r['name']}（{r['symbol']}，{r['theme_name']}）："
            f"MFE40 {sf(r['mfe40']):.2f}%，MAE40 {sf(r['mae40']):.2f}%，40日收盘 {sf(r['close40']):.2f}%，"
            f"到20%前回撤 {sf(r.get('mae_before_hit20')):.2f}%"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate two-month opportunity/risk for hot-theme low-position L2 premise layers.")
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--horizon", type=int, default=40)
    parser.add_argument("--active-top-k", type=int, default=10)
    parser.add_argument("--hot-lookback", type=int, default=5)
    parser.add_argument("--hot-min-hits", type=int, default=2)
    parser.add_argument("--hot-max-hits", type=int, default=3)
    parser.add_argument("--min-5d-return", type=float, default=-8.0)
    parser.add_argument("--max-5d-return", type=float, default=5.0)
    parser.add_argument("--max-20d-position", type=float, default=0.8)
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--min-member-count", type=int, default=5)
    parser.add_argument("--max-member-count", type=int, default=80)
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--no-heat-cache", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = build_report(args)
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_l2_two_month_opportunity.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render(report), encoding="utf-8")
    print(render(report))
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
