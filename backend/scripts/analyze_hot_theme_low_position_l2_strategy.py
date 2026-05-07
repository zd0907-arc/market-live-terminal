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
    is_st_name,
    is_unbuyable_limit_up,
    load_extra_names,
    load_price_and_limit_rows,
    safe_float,
    summarize,
)
from backend.scripts.analyze_strategy_theme_lifecycle import build_rank_history
from backend.scripts.analyze_strategy_theme_resonance import (
    DEFAULT_SELECTION_DB,
    compute_market_returns,
    first_indexes,
    is_valid_tradeable,
    load_or_build_heat_snapshots,
)


def pct_change(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def prior_avg_amount(rows: Dict[str, sqlite3.Row], trade_dates: Sequence[str], i: int, lookback: int = 10) -> Optional[float]:
    vals = []
    for d in trade_dates[max(0, i - lookback):i]:
        row = rows.get(d)
        if row:
            amount = safe_float(row["total_amount"])
            if amount > 0:
                vals.append(amount)
    if len(vals) < max(5, lookback // 2):
        return None
    return sum(vals) / len(vals)


def amount_bin(ratio: float) -> str:
    if ratio < 0.8:
        return "shrink_<0.8"
    if ratio <= 1.2:
        return "normal_0.8_1.2"
    return "expand_>1.2"


def position_20d(rows: Dict[str, sqlite3.Row], trade_dates: Sequence[str], i: int, lookback: int = 20) -> Optional[float]:
    vals = []
    for d in trade_dates[max(0, i - lookback + 1):i + 1]:
        row = rows.get(d)
        if row:
            vals.append(safe_float(row["close"]))
    if len(vals) < max(8, lookback // 2):
        return None
    lo, hi = min(vals), max(vals)
    close = safe_float(rows[trade_dates[i]]["close"])
    if hi <= lo:
        return 0.5
    return (close - lo) / (hi - lo)


def load_selection_flags(selection_db: Path, start_date: str, end_date: str) -> Dict[Tuple[str, str], Dict[str, int]]:
    if not selection_db.exists():
        return {}
    with sqlite3.connect(str(selection_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT symbol, trade_date, max(stealth_signal) AS stealth_signal, max(confirm_signal) AS breakout_signal
            FROM selection_signal_daily
            WHERE trade_date >= ? AND trade_date <= ?
            GROUP BY symbol, trade_date
            """,
            (start_date, end_date),
        ).fetchall()
    return {(str(r["symbol"]).lower(), str(r["trade_date"])): {"stealth": int(r["stealth_signal"] or 0), "breakout": int(r["breakout_signal"] or 0)} for r in rows}


def active_hot_themes(
    d: str,
    heat_dates: Sequence[str],
    heat_pos: Dict[str, int],
    rank_history: Dict[str, Dict[str, int]],
    snapshots: Dict[str, Dict[str, Any]],
    active_top_k: int,
    lookback: int,
    min_hits: int,
    max_hits: int,
) -> List[Dict[str, Any]]:
    idx = heat_pos[d]
    stage_dates = heat_dates[max(0, idx - lookback + 1):idx + 1]
    out = []
    for rank, item in enumerate(snapshots.get(d, {}).get("hot_top", [])[:active_top_k], start=1):
        tid = str(item.get("id"))
        hits = sum(1 for x in stage_dates if rank_history.get(x, {}).get(tid, 10**9) <= active_top_k)
        if min_hits <= hits <= max_hits:
            out.append({"id": tid, "name": item.get("name") or tid, "rank": rank, "hot_score": safe_float(item.get("hot_score")), "recent_hits": hits})
    return out


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 热点内低位 L2 潜伏验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 热点状态：过去 {meta['hot_lookback']} 日内 {meta['hot_min_hits']}~{meta['hot_max_hits']} 日进入 Top{meta['active_top_k']}。",
        f"- 个股：5日涨幅 {meta['min_5d_return']}%~{meta['max_5d_return']}%，20日位置 <= {meta['max_20d_position']}，D/D-1 L2 连续净流入。",
        f"- 量能防呆：D 日成交额 / D-10~D-1 平均成交额 分组。",
        "",
    ]
    for hkey, groups in report["summary"].items():
        market = report["market"].get(hkey, {})
        lines += [f"## D+{hkey}", "", f"市场均值：{market.get('avg', 0):.2f}%，市场胜率：{market.get('win_rate', 0):.1%}", "", "| 组别 | 样本 | 均值 | Alpha | 胜率 |", "|---|---:|---:|---:|---:|"]
        for group, stat in groups.items():
            lines.append(f"| {group} | {stat['n']} | {stat['avg']:.2f}% | {stat['alpha']:.2f}% | {stat['win_rate']:.1%} |")
        lines.append("")
    if report.get("top_themes"):
        lines += ["## D+3 样本最多主题", ""]
        for name, count in report["top_themes"][:15]:
            lines.append(f"- {name}: {count}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate low-position L2 accumulation inside continuing hot fine themes.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--horizons", default="1,3,5")
    parser.add_argument("--active-top-k", type=int, default=10)
    parser.add_argument("--hot-lookback", type=int, default=5)
    parser.add_argument("--hot-min-hits", type=int, default=2)
    parser.add_argument("--hot-max-hits", type=int, default=3)
    parser.add_argument("--min-5d-return", type=float, default=-8.0)
    parser.add_argument("--max-5d-return", type=float, default=5.0)
    parser.add_argument("--max-20d-position", type=float, default=0.65)
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--min-member-count", type=int, default=5)
    parser.add_argument("--max-member-count", type=int, default=80)
    parser.add_argument("--include-unbuyable", action="store_true")
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--selection-db", default=str(DEFAULT_SELECTION_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--no-heat-cache", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    all_dates = _trade_dates(end_date, args.days + args.min_history_days + max(horizons) + 45)
    analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], end_date)
    date_index = {d: idx for idx, d in enumerate(trade_dates)}
    first_idx = first_indexes(price_rows, date_index)

    rules = load_json(Path(args.fine_rules))
    themes, theme_members, _symbol_themes, name_map = load_fine_sector_themes(Path(args.tradable_theme_db), rules, args.min_member_count, args.max_member_count)
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})
    selection_flags = load_selection_flags(Path(args.selection_db), analysis_dates[0], analysis_dates[-1])

    heat_dates = [d for d in all_dates if d <= analysis_dates[-1]]
    snapshots = load_or_build_heat_snapshots(heat_dates, themes, args.active_top_k, args.min_member_count, args.max_member_count, MARKET_HEAT_DIR / "cache", use_cache=not args.no_heat_cache)
    rank_history = build_rank_history(snapshots, heat_dates, args.active_top_k)
    heat_pos = {d: idx for idx, d in enumerate(heat_dates)}
    market = compute_market_returns(analysis_dates, trade_dates, price_rows, limit_rows, name_map, horizons, args.min_amount, args.min_history_days, exclude_unbuyable=not args.include_unbuyable)

    returns: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    theme_counts: Dict[str, int] = defaultdict(int)
    seen_by_h: Dict[str, set] = defaultdict(set)

    for d in analysis_dates:
        i = date_index.get(d)
        if i is None or i + 1 >= len(trade_dates) or d not in heat_pos:
            continue
        active = active_hot_themes(d, heat_dates, heat_pos, rank_history, snapshots, args.active_top_k, args.hot_lookback, args.hot_min_hits, args.hot_max_hits)
        best_by_symbol: Dict[str, Dict[str, Any]] = {}
        for theme in active:
            for symbol in theme_members.get(theme["id"], set()):
                rows = price_rows.get(symbol, {})
                if d not in rows:
                    continue
                entry_date = trade_dates[i + 1]
                if not is_valid_tradeable(symbol, d, entry_date, i, rows, first_idx, limit_rows, name_map, args.min_amount, args.min_history_days, not args.include_unbuyable):
                    continue
                if i < 10 or trade_dates[i - 1] not in rows or trade_dates[i - 5] not in rows:
                    continue
                d_row = rows[d]
                y_row = rows.get(trade_dates[i - 1])
                ret5 = pct_change(safe_float(d_row["close"]), safe_float(rows[trade_dates[i - 5]]["close"]))
                if ret5 is None or ret5 < args.min_5d_return or ret5 >= args.max_5d_return:
                    continue
                pos20 = position_20d(rows, trade_dates, i)
                if pos20 is None or pos20 > args.max_20d_position:
                    continue
                if safe_float(d_row["l2_main_net_amount"]) <= 0 or safe_float(y_row["l2_main_net_amount"]) <= 0:
                    continue
                avg10 = prior_avg_amount(rows, trade_dates, i, 10)
                if not avg10 or avg10 <= 0:
                    continue
                ratio = safe_float(d_row["total_amount"]) / avg10
                rec = {
                    "symbol": symbol,
                    "theme_name": theme["name"],
                    "theme_rank": theme["rank"],
                    "ret5": ret5,
                    "pos20": pos20,
                    "amount_ratio": ratio,
                    "amount_bin": amount_bin(ratio),
                    "l2_2d": safe_float(d_row["l2_main_net_amount"]) + safe_float(y_row["l2_main_net_amount"]),
                }
                old = best_by_symbol.get(symbol)
                if old is None or (rec["theme_rank"], -rec["l2_2d"]) < (old["theme_rank"], -old["l2_2d"]):
                    best_by_symbol[symbol] = rec
        for symbol, rec in best_by_symbol.items():
            rows = price_rows.get(symbol, {})
            entry_date = trade_dates[i + 1]
            flags = selection_flags.get((symbol, d), {})
            for h in horizons:
                if i + h >= len(trade_dates):
                    continue
                exit_date = trade_dates[i + h]
                if entry_date not in rows or exit_date not in rows:
                    continue
                ret = forward_return(rows[entry_date], rows[exit_date])
                if ret is None:
                    continue
                hkey = str(h)
                key = (d, symbol)
                if key in seen_by_h[hkey]:
                    continue
                seen_by_h[hkey].add(key)
                returns[hkey]["all_low_l2"].append(ret)
                returns[hkey][rec["amount_bin"]].append(ret)
                if rec["amount_bin"] != "expand_>1.2":
                    returns[hkey]["shrink_or_normal"].append(ret)
                if flags.get("stealth"):
                    returns[hkey]["overlap_stealth"].append(ret)
                else:
                    returns[hkey]["not_stealth"].append(ret)
                if h == 3:
                    theme_counts[str(rec["theme_name"])] += 1

    summary: Dict[str, Dict[str, Any]] = {}
    order = ["all_low_l2", "shrink_<0.8", "normal_0.8_1.2", "expand_>1.2", "shrink_or_normal", "overlap_stealth", "not_stealth"]
    for hkey, groups in returns.items():
        summary[hkey] = {}
        for group in order:
            stat = summarize(groups.get(group, []))
            stat["alpha"] = round(stat["avg"] - market[hkey]["avg"], 4)
            summary[hkey][group] = stat

    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "analysis_days": len(analysis_dates),
            "active_top_k": args.active_top_k,
            "hot_lookback": args.hot_lookback,
            "hot_min_hits": args.hot_min_hits,
            "hot_max_hits": args.hot_max_hits,
            "min_5d_return": args.min_5d_return,
            "max_5d_return": args.max_5d_return,
            "max_20d_position": args.max_20d_position,
        },
        "market": market,
        "summary": summary,
        "top_themes": sorted(theme_counts.items(), key=lambda x: x[1], reverse=True),
    }
    ensure_market_heat_dir()
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"hot_theme_low_position_l2_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
