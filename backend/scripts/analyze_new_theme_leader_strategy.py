#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
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
from backend.scripts.analyze_hot_theme_winner_lead_lag import (
    DEFAULT_STOCK_SECTOR_DB,
    DEFAULT_TRADABLE_THEME_DB,
    forward_return,
    load_extra_names,
    load_price_and_limit_rows,
    safe_float,
    summarize,
)
from backend.scripts.analyze_strategy_theme_lifecycle import build_rank_history
from backend.scripts.analyze_strategy_theme_resonance import compute_market_returns, first_indexes, is_valid_tradeable, load_or_build_heat_snapshots


def pct_change(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def open_gap_bin(gap: float) -> str:
    if gap <= 0:
        return "gap_<=0"
    if gap <= 2:
        return "gap_0_2"
    if gap <= 5:
        return "gap_2_5"
    if gap <= 8:
        return "gap_5_8"
    return "gap_>8"


def intraday_fade(row: sqlite3.Row) -> Tuple[bool, float]:
    high = safe_float(row["high"])
    low = safe_float(row["low"])
    close = safe_float(row["close"])
    open_ = safe_float(row["open"])
    ratio = 0.0
    if high > low:
        ratio = (high - close) / (high - low)
    flag = ratio > 0.5 or (high > open_ and close < open_)
    return flag, ratio


def new_hot_themes(
    d: str,
    heat_dates: Sequence[str],
    heat_pos: Dict[str, int],
    rank_history: Dict[str, Dict[str, int]],
    snapshots: Dict[str, Dict[str, Any]],
    new_rank_k: int,
    new_lookback: int,
    new_prev_top_k: int,
) -> List[Dict[str, Any]]:
    idx = heat_pos[d]
    prev_dates = heat_dates[max(0, idx - new_lookback):idx]
    out = []
    for rank, item in enumerate(snapshots.get(d, {}).get("hot_top", [])[:new_rank_k], start=1):
        tid = str(item.get("id"))
        prev_hits = sum(1 for x in prev_dates if rank_history.get(x, {}).get(tid, 10**9) <= new_prev_top_k)
        if prev_hits == 0:
            out.append({"id": tid, "name": item.get("name") or tid, "rank": rank, "hot_score": safe_float(item.get("hot_score"))})
    return out


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 新热点资金龙头验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 新热点：今日进 Top{meta['new_rank_k']}，过去 {meta['new_lookback']} 日未进 Top{meta['new_prev_top_k']}。",
        f"- 个股池：D 日上涨、阳线、成交额达标、D+1 非一字涨停。",
        f"- 选股：板块内 L2 金额 / L2占成交额 / 复合强度 Top{meta['leader_top_n']}。",
        f"- 防呆：按 D+1 开盘涨幅分组；冲高回落按 (最高-收盘)/(最高-最低)>0.5 或收绿判定。",
        "",
    ]
    for method, by_h in report["summary"].items():
        lines += [f"## {method}", ""]
        for hkey, groups in by_h.items():
            market = report["market"].get(hkey, {})
            lines += [f"### D+{hkey}，市场均值 {market.get('avg', 0):.2f}%", "", "| 组别 | 样本 | 均值 | Alpha | 胜率 | 冲高回落率 | 平均高开 |", "|---|---:|---:|---:|---:|---:|---:|"]
            for group, stat in groups.items():
                lines.append(f"| {group} | {stat['n']} | {stat['avg']:.2f}% | {stat['alpha']:.2f}% | {stat['win_rate']:.1%} | {stat.get('fade_rate', 0):.1%} | {stat.get('avg_open_gap', 0):.2f}% |")
            lines.append("")
    if report.get("top_themes"):
        lines += ["## D+3 样本最多新热点", ""]
        for name, count in report["top_themes"][:15]:
            lines.append(f"- {name}: {count}")
    return "\n".join(lines)


def summarize_recs(recs: Sequence[Dict[str, Any]], market_avg: float) -> Dict[str, Any]:
    stat = summarize([x["ret"] for x in recs])
    stat["alpha"] = round(stat["avg"] - market_avg, 4)
    if recs:
        stat["fade_rate"] = round(sum(1 for x in recs if x.get("fade")) / len(recs), 4)
        stat["avg_open_gap"] = round(sum(safe_float(x.get("open_gap")) for x in recs) / len(recs), 4)
        stat["avg_fade_ratio"] = round(sum(safe_float(x.get("fade_ratio")) for x in recs) / len(recs), 4)
    else:
        stat["fade_rate"] = 0.0
        stat["avg_open_gap"] = 0.0
        stat["avg_fade_ratio"] = 0.0
    return stat


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate first-day new hot theme leader strategy with D+1 gap bins.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--horizons", default="1,3")
    parser.add_argument("--new-rank-k", type=int, default=5)
    parser.add_argument("--new-lookback", type=int, default=10)
    parser.add_argument("--new-prev-top-k", type=int, default=20)
    parser.add_argument("--leader-top-n", type=int, default=3)
    parser.add_argument("--min-day-return", type=float, default=0.0)
    parser.add_argument("--require-positive-candle", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--min-member-count", type=int, default=5)
    parser.add_argument("--max-member-count", type=int, default=80)
    parser.add_argument("--include-unbuyable", action="store_true")
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--no-heat-cache", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    all_dates = _trade_dates(end_date, args.days + args.min_history_days + max(horizons) + args.new_lookback + 30)
    analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], end_date)
    date_index = {d: idx for idx, d in enumerate(trade_dates)}
    first_idx = first_indexes(price_rows, date_index)

    rules = load_json(Path(args.fine_rules))
    themes, theme_members, _symbol_themes, name_map = load_fine_sector_themes(Path(args.tradable_theme_db), rules, args.min_member_count, args.max_member_count)
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})

    heat_dates = [d for d in all_dates if d <= analysis_dates[-1]]
    snapshots = load_or_build_heat_snapshots(heat_dates, themes, max(args.new_rank_k, args.new_prev_top_k), args.min_member_count, args.max_member_count, MARKET_HEAT_DIR / "cache", use_cache=not args.no_heat_cache)
    rank_history = build_rank_history(snapshots, heat_dates, max(args.new_rank_k, args.new_prev_top_k))
    heat_pos = {d: idx for idx, d in enumerate(heat_dates)}
    market = compute_market_returns(analysis_dates, trade_dates, price_rows, limit_rows, name_map, horizons, args.min_amount, args.min_history_days, exclude_unbuyable=not args.include_unbuyable)

    methods = ["theme_pool", "l2_amount_top", "l2_ratio_top", "composite_top"]
    recs: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    top_theme_counts: Dict[str, int] = defaultdict(int)
    seen: Dict[Tuple[str, str], set] = defaultdict(set)

    for d in analysis_dates:
        i = date_index.get(d)
        if i is None or i + max(horizons) >= len(trade_dates) or d not in heat_pos:
            continue
        entry_date = trade_dates[i + 1]
        themes_today = new_hot_themes(d, heat_dates, heat_pos, rank_history, snapshots, args.new_rank_k, args.new_lookback, args.new_prev_top_k)
        for theme in themes_today:
            pool = []
            for symbol in theme_members.get(theme["id"], set()):
                rows = price_rows.get(symbol, {})
                if d not in rows or entry_date not in rows or trade_dates[i - 1] not in rows:
                    continue
                if not is_valid_tradeable(symbol, d, entry_date, i, rows, first_idx, limit_rows, name_map, args.min_amount, args.min_history_days, not args.include_unbuyable):
                    continue
                d_row = rows[d]
                prev_row = rows[trade_dates[i - 1]]
                day_ret = pct_change(safe_float(d_row["close"]), safe_float(prev_row["close"]))
                if day_ret is None or day_ret <= args.min_day_return:
                    continue
                if args.require_positive_candle and safe_float(d_row["close"]) < safe_float(d_row["open"]):
                    continue
                amount = safe_float(d_row["total_amount"])
                l2_amt = safe_float(d_row["l2_main_net_amount"])
                l2_ratio = l2_amt / amount if amount > 0 else 0.0
                pool.append({
                    "symbol": symbol,
                    "theme_name": theme["name"],
                    "theme_rank": theme["rank"],
                    "day_ret": day_ret,
                    "l2_amount": l2_amt,
                    "l2_ratio": l2_ratio,
                    "composite": l2_ratio * 100 + day_ret + min(amount / 1e8, 20) * 0.15,
                })
            ranked = {
                "theme_pool": pool,
                "l2_amount_top": sorted(pool, key=lambda x: x["l2_amount"], reverse=True)[:args.leader_top_n],
                "l2_ratio_top": sorted(pool, key=lambda x: x["l2_ratio"], reverse=True)[:args.leader_top_n],
                "composite_top": sorted(pool, key=lambda x: x["composite"], reverse=True)[:args.leader_top_n],
            }
            for method, candidates in ranked.items():
                for cand in candidates:
                    symbol = cand["symbol"]
                    if symbol in seen[(method, d)]:
                        continue
                    seen[(method, d)].add(symbol)
                    rows = price_rows.get(symbol, {})
                    entry_row = rows[entry_date]
                    open_gap = pct_change(safe_float(entry_row["open"]), safe_float(rows[d]["close"])) or 0.0
                    fade, fade_ratio = intraday_fade(entry_row)
                    gap_bin = open_gap_bin(open_gap)
                    for h in horizons:
                        exit_date = trade_dates[i + h]
                        if exit_date not in rows:
                            continue
                        ret = forward_return(entry_row, rows[exit_date])
                        if ret is None:
                            continue
                        hkey = str(h)
                        item = {"ret": ret, "open_gap": open_gap, "fade": fade, "fade_ratio": fade_ratio, "theme_name": cand["theme_name"]}
                        recs[method][hkey].append(item)
                        recs[f"{method}:{gap_bin}"][hkey].append(item)
                        if method != "theme_pool" and h == 3:
                            top_theme_counts[str(cand["theme_name"])] += 1

    summary: Dict[str, Dict[str, Dict[str, Any]]] = {}
    method_order = []
    for m in methods:
        method_order.append(m)
        for b in ["gap_<=0", "gap_0_2", "gap_2_5", "gap_5_8", "gap_>8"]:
            method_order.append(f"{m}:{b}")
    for method in method_order:
        if method not in recs:
            continue
        summary[method] = {}
        for hkey, items in recs[method].items():
            summary[method][hkey] = {"all": summarize_recs(items, market[hkey]["avg"])}

    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "analysis_days": len(analysis_dates),
            "new_rank_k": args.new_rank_k,
            "new_lookback": args.new_lookback,
            "new_prev_top_k": args.new_prev_top_k,
            "leader_top_n": args.leader_top_n,
        },
        "market": market,
        "summary": summary,
        "top_themes": sorted(top_theme_counts.items(), key=lambda x: x[1], reverse=True),
    }
    ensure_market_heat_dir()
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"new_theme_leader_strategy_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
