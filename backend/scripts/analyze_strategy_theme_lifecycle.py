#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR
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
from backend.scripts.analyze_strategy_theme_resonance import (
    DEFAULT_SELECTION_DB,
    compute_market_returns,
    first_indexes,
    get_resonance,
    is_valid_tradeable,
    load_or_build_heat_snapshots,
    load_selection_candidates,
)


def build_rank_history(snapshots: Dict[str, Dict[str, Any]], dates: Sequence[str], max_rank: int) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for d in dates:
        rank_by_id: Dict[str, int] = {}
        for rank, item in enumerate(snapshots.get(d, {}).get("hot_top", [])[:max_rank], start=1):
            rank_by_id[str(item.get("id"))] = rank
        out[d] = rank_by_id
    return out


def classify_stage(
    theme_id: str,
    today: str,
    date_pos: int,
    heat_dates: Sequence[str],
    rank_history: Dict[str, Dict[str, int]],
    today_rank: int,
    new_rank_k: int,
    new_lookback: int,
    new_prev_top_k: int,
    climax_lookback: int,
    climax_top_k: int,
    climax_min_hits: int,
) -> Dict[str, Any]:
    prev_dates_new = heat_dates[max(0, date_pos - new_lookback):date_pos]
    prev_top_hits = sum(1 for d in prev_dates_new if rank_history.get(d, {}).get(theme_id, 10**9) <= new_prev_top_k)

    stage_dates = heat_dates[max(0, date_pos - climax_lookback + 1):date_pos + 1]
    recent_hits = sum(1 for d in stage_dates if rank_history.get(d, {}).get(theme_id, 10**9) <= climax_top_k)

    if today_rank <= new_rank_k and prev_top_hits == 0:
        stage = "new_hot"
    elif recent_hits >= climax_min_hits:
        stage = "climax_hot"
    else:
        stage = "continuing_hot"
    return {
        "stage": stage,
        "today_rank": today_rank,
        "prev_top_hits": prev_top_hits,
        "recent_hits": recent_hits,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 策略候选 + 热点生命周期分层验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 策略候选：每日每策略 Top{meta['selection_top_k']}。",
        f"- 共振口径：细颗粒热点 Top{meta['hot_top_k']} + 股票/板块 D 日同向上涨。",
        f"- new_hot：今日排名 <= Top{meta['new_rank_k']}，且过去 {meta['new_lookback']} 日未进 Top{meta['new_prev_top_k']}。",
        f"- climax_hot：过去 {meta['climax_lookback']} 日内至少 {meta['climax_min_hits']} 日进 Top{meta['climax_top_k']}。",
        "",
    ]
    groups_order = ["baseline", "non_resonance", "new_hot", "continuing_hot", "climax_hot"]
    for strategy, by_h in report["summary"].items():
        lines += [f"## {strategy}", "", "| Horizon | 组别 | 样本 | 占比 | 均值 | Alpha | 胜率 |", "|---:|---|---:|---:|---:|---:|---:|"]
        for hkey, groups in by_h.items():
            total = groups["baseline"]["n"] or 1
            for group in groups_order:
                stat = groups.get(group, {"n": 0, "avg": 0, "alpha": 0, "win_rate": 0})
                lines.append(
                    f"| {hkey} | {group} | {stat['n']} | {stat['n']/total:.1%} | {stat['avg']:.2f}% | {stat['alpha']:.2f}% | {stat['win_rate']:.1%} |"
                )
        if report.get("stage_themes", {}).get(strategy):
            lines += ["", "D+5 生命周期主题分布："]
            for stage, items in report["stage_themes"][strategy].items():
                if items:
                    top = "、".join([f"{name}({count})" for name, count in items[:8]])
                    lines.append(f"- {stage}: {top}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate strategy candidates by hot sector lifecycle stage.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--horizons", default="1,3,5,10")
    parser.add_argument("--selection-top-k", type=int, default=20)
    parser.add_argument("--hot-top-k", type=int, default=15)
    parser.add_argument("--min-member-count", type=int, default=5)
    parser.add_argument("--max-member-count", type=int, default=80)
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--include-unbuyable", action="store_true")
    parser.add_argument("--new-rank-k", type=int, default=10)
    parser.add_argument("--new-lookback", type=int, default=10)
    parser.add_argument("--new-prev-top-k", type=int, default=20)
    parser.add_argument("--climax-lookback", type=int, default=5)
    parser.add_argument("--climax-top-k", type=int, default=15)
    parser.add_argument("--climax-min-hits", type=int, default=3)
    parser.add_argument("--selection-db", default=str(DEFAULT_SELECTION_DB))
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

    rules = load_json(Path(args.fine_rules))
    themes, _theme_members, symbol_themes, name_map = load_fine_sector_themes(
        Path(args.tradable_theme_db),
        rules,
        args.min_member_count,
        args.max_member_count,
    )
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})

    heat_dates = [d for d in all_dates if d <= analysis_dates[-1]]
    snapshots = load_or_build_heat_snapshots(
        heat_dates,
        themes,
        max(args.hot_top_k, args.new_prev_top_k, args.climax_top_k),
        args.min_member_count,
        args.max_member_count,
        MARKET_HEAT_DIR / "cache",
        use_cache=not args.no_heat_cache,
    )
    rank_history = build_rank_history(snapshots, heat_dates, max(args.hot_top_k, args.new_prev_top_k, args.climax_top_k))
    heat_pos = {d: idx for idx, d in enumerate(heat_dates)}

    first_idx = first_indexes(price_rows, date_index)
    candidates = load_selection_candidates(Path(args.selection_db), analysis_dates, args.selection_top_k)
    market = compute_market_returns(
        analysis_dates,
        trade_dates,
        price_rows,
        limit_rows,
        name_map,
        horizons,
        args.min_amount,
        args.min_history_days,
        exclude_unbuyable=not args.include_unbuyable,
    )

    returns: Dict[str, Dict[str, Dict[str, List[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    stage_theme_hits: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for rec in candidates:
        d = rec["signal_date"]
        i = date_index.get(d)
        symbol = rec["symbol"]
        rows = price_rows.get(symbol, {})
        if i is None or not rows:
            continue
        if i + 1 >= len(trade_dates):
            continue
        entry_date = trade_dates[i + 1]
        if not is_valid_tradeable(symbol, d, entry_date, i, rows, first_idx, limit_rows, name_map, args.min_amount, args.min_history_days, not args.include_unbuyable):
            continue
        snapshot = snapshots.get(d)
        if not snapshot:
            continue
        hot_items = snapshot.get("hot_top", [])[:args.hot_top_k]
        hot_ids = [str(x.get("id")) for x in hot_items]
        rank_today = {str(x.get("id")): rank for rank, x in enumerate(hot_items, start=1)}
        sectors_by_id = {str(x.get("id")): x for x in snapshot.get("sectors", [])}
        resonance = get_resonance(symbol, rows, trade_dates, i, hot_ids, symbol_themes, sectors_by_id)
        stage = "non_resonance"
        if resonance:
            theme_id = str(resonance["theme_id"])
            lifecycle = classify_stage(
                theme_id,
                d,
                heat_pos[d],
                heat_dates,
                rank_history,
                rank_today.get(theme_id, 10**9),
                args.new_rank_k,
                args.new_lookback,
                args.new_prev_top_k,
                args.climax_lookback,
                args.climax_top_k,
                args.climax_min_hits,
            )
            stage = lifecycle["stage"]
        strategy_keys = [rec["strategy"], "all"]
        for horizon in horizons:
            if i + horizon >= len(trade_dates):
                continue
            exit_date = trade_dates[i + horizon]
            if exit_date not in rows:
                continue
            ret = forward_return(rows[entry_date], rows[exit_date])
            if ret is None:
                continue
            hkey = str(horizon)
            for strategy in strategy_keys:
                returns[strategy][hkey]["baseline"].append(ret)
                returns[strategy][hkey][stage].append(ret)
                if resonance and hkey == "5":
                    stage_theme_hits[strategy][stage][str(resonance["theme_name"])] += 1

    summary: Dict[str, Dict[str, Any]] = {}
    groups_order = ["baseline", "non_resonance", "new_hot", "continuing_hot", "climax_hot"]
    for strategy, by_h in returns.items():
        summary[strategy] = {}
        for hkey, groups in by_h.items():
            summary[strategy][hkey] = {}
            for group in groups_order:
                stat = summarize(groups.get(group, []))
                stat["alpha"] = round(stat["avg"] - market[hkey]["avg"], 4)
                summary[strategy][hkey][group] = stat

    stage_themes = {
        strategy: {
            stage: sorted(items.items(), key=lambda x: x[1], reverse=True)
            for stage, items in by_stage.items()
        }
        for strategy, by_stage in stage_theme_hits.items()
    }
    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "analysis_days": len(analysis_dates),
            "selection_top_k": args.selection_top_k,
            "hot_top_k": args.hot_top_k,
            "new_rank_k": args.new_rank_k,
            "new_lookback": args.new_lookback,
            "new_prev_top_k": args.new_prev_top_k,
            "climax_lookback": args.climax_lookback,
            "climax_top_k": args.climax_top_k,
            "climax_min_hits": args.climax_min_hits,
        },
        "market": market,
        "summary": summary,
        "stage_themes": stage_themes,
    }
    ensure_market_heat_dir()
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / (
        f"strategy_theme_lifecycle_top{args.selection_top_k}_hot{args.hot_top_k}_"
        f"new{args.new_rank_k}lb{args.new_lookback}_climax{args.climax_min_hits}in{args.climax_lookback}_"
        f"{analysis_dates[0]}_{analysis_dates[-1]}.json"
    )
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
