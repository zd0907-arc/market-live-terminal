#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR
from backend.app.services.market_heat import MARKET_HEAT_DIR, _trade_dates, ensure_market_heat_dir
from backend.scripts.analyze_hot_theme_winner_lead_lag import (
    ATOMIC_DB,
    DEFAULT_STOCK_SECTOR_DB,
    DEFAULT_TRADABLE_THEME_DB,
    build_heat_history,
    choose_hot_theme_for_symbol,
    forward_return,
    is_st_name,
    is_unbuyable_limit_up,
    load_extra_names,
    load_price_and_limit_rows,
    load_tradable_themes,
    safe_float,
    summarize,
)
from backend.scripts.analyze_hot_sector_granularity import (
    DEFAULT_FINE_RULES,
    load_fine_sector_themes,
    load_json,
)


def mark_l2_leaders(records: List[Dict[str, Any]], top_pct: float, metric: str = "ratio") -> None:
    """Mark L2 leaders inside each hot theme.

    Fine-grained sectors can have only 5-10 members, so the selected count uses
    max(1, floor(N * top_pct)). We still require positive L2 ratio unless the
    stock is a strict limit-up close, which is handled as an exemption later.
    """
    by_theme: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rec in records:
        if rec.get("chosen"):
            by_theme[str(rec["theme_id"])].append(rec)
        rec["l2_rank_selected"] = False
    top_pct = max(0.001, min(1.0, top_pct))
    for _, items in by_theme.items():
        items.sort(key=lambda x: safe_float(x.get(f"l2_{metric}")), reverse=True)
        keep = max(1, int(len(items) * top_pct))
        for rec in items[:keep]:
            if safe_float(rec.get(f"l2_{metric}")) > 0:
                rec["l2_rank_selected"] = True


def is_limit_up_close(symbol: str, date: str, limit_rows: Dict[str, Dict[str, sqlite3.Row]]) -> bool:
    row = limit_rows.get(symbol, {}).get(date)
    if not row:
        return False
    try:
        return int(row["is_limit_up_close"]) == 1
    except Exception:
        label = str(row["limit_state_label"] or "")
        return "limit_up" in label


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 热门热点 + L2 龙头过滤验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 口径：{meta.get('theme_source')} Top{meta['top_k']}；在热点内按 L2 {meta.get('l2_metric')} 保留 Top {meta['l2_top_pct']:.0%}，收盘封死涨停豁免。",
        f"- 可交易过滤：D 日成交额 >= {meta['min_amount'] / 1e8:.2f} 亿，历史 >= {meta['min_history_days']} 个交易日，剔除 ST，剔除 D+1 一字涨停开盘。",
        f"- 细板块参数：成员数 {meta.get('min_member_count', '-') }~{meta.get('max_member_count', '-')}；L2 小样本保底 max(1, floor(N*pct))。",
        "",
        "## 总览",
        "",
        "| Horizon | 池子 | Coverage | Recall | Lift | 均值 | 市场均值 | Alpha | 胜率 | 市场胜率 | 样本 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for hkey, groups in report["summary"].items():
        market = groups["market_return"]
        for group_key in ["hot_all", "l2_filtered"]:
            item = groups[group_key]
            stat = item["return"]
            lines.append(
                f"| {hkey} | {group_key} | {item['coverage']:.1%} | {item['winner_recall']:.1%} | {item['lift']} | "
                f"{stat['avg']:.2f}% | {market['avg']:.2f}% | {item['alpha']:.2f}% | "
                f"{stat['win_rate']:.1%} | {market['win_rate']:.1%} | {stat['n']} |"
            )
    hkey = "5" if "5" in report["summary"] else next(iter(report["summary"].keys()), "")
    if hkey:
        lines += ["", f"## Horizon {hkey} L2 过滤命中主题", ""]
        for name, count in report["summary"][hkey]["l2_filtered"].get("theme_winner_hits", [])[:15]:
            lines.append(f"- {name}: {count}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate hot theme + L2 leader filter with limit-up exemption.")
    parser.add_argument("--theme-source", choices=["tradable-theme", "fine-sector"], default="tradable-theme")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=63)
    parser.add_argument("--horizons", default="1,3,5,10")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--winner-top-n", type=int, default=20)
    parser.add_argument("--l2-top-pct", type=float, default=0.2)
    parser.add_argument("--l2-metric", choices=["ratio", "amount"], default="ratio", help="ratio=净流入/成交额；amount=净流入金额")
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--require-daily-resonance", action="store_true")
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--min-member-count", type=int, default=None)
    parser.add_argument("--max-member-count", type=int, default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    all_dates = _trade_dates(end_date, args.days + args.min_history_days + max(horizons) + 30)
    analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], end_date)
    date_index = {d: i for i, d in enumerate(trade_dates)}
    if args.theme_source == "fine-sector":
        fine_rules = load_json(Path(args.fine_rules))
        min_member_count = args.min_member_count or int(fine_rules.get("min_member_count") or 5)
        max_member_count = args.max_member_count or int(fine_rules.get("max_member_count") or 80)
        themes, theme_members, symbol_themes, name_map = load_fine_sector_themes(
            Path(args.tradable_theme_db),
            fine_rules,
            min_member_count,
            max_member_count,
        )
    else:
        min_member_count = None
        max_member_count = None
        themes, theme_members, symbol_themes, name_map = load_tradable_themes(Path(args.tradable_theme_db))
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})
    heat_dates = [d for d in all_dates if d <= analysis_dates[-1]]
    snapshots, _ = build_heat_history(heat_dates, themes, args.top_k, stage_window=5)

    first_index: Dict[str, int] = {}
    for symbol, rows in price_rows.items():
        indexes = [date_index[d] for d in rows.keys() if d in date_index]
        if indexes:
            first_index[symbol] = min(indexes)

    summary: Dict[str, Any] = {}
    for horizon in horizons:
        hkey = str(horizon)
        market_returns: List[float] = []
        group_returns = {"hot_all": [], "l2_filtered": []}
        counts = {"pool": 0, "hot_all": 0, "l2_filtered": 0, "winners": 0, "hot_all_winners": 0, "l2_filtered_winners": 0}
        theme_hits = {"hot_all": Counter(), "l2_filtered": Counter()}

        for d in analysis_dates:
            i = date_index.get(d)
            if i is None or i + horizon >= len(trade_dates) or i + 1 >= len(trade_dates):
                continue
            entry_date = trade_dates[i + 1]
            exit_date = trade_dates[i + horizon]
            snapshot = snapshots[d]
            hot_ids = [str(x.get("id")) for x in snapshot.get("hot_top", [])[:args.top_k]]
            sectors_by_id = {str(x.get("id")): x for x in snapshot.get("sectors", [])}
            day_records = []

            for symbol, rows in price_rows.items():
                d_row, entry_row, exit_row = rows.get(d), rows.get(entry_date), rows.get(exit_date)
                if not d_row or not entry_row or not exit_row:
                    continue
                if first_index.get(symbol, 10**9) > i - args.min_history_days:
                    continue
                if safe_float(d_row["total_amount"]) < args.min_amount:
                    continue
                if is_st_name(name_map.get(symbol, "")):
                    continue
                if is_unbuyable_limit_up(symbol, d_row, entry_row, limit_rows, entry_date):
                    continue
                ret = forward_return(entry_row, exit_row)
                if ret is None:
                    continue
                prev_row = rows.get(trade_dates[i - 1]) if i > 0 else None
                prev_close = safe_float(prev_row["close"]) if prev_row else safe_float(d_row["open"])
                stock_day_return = (safe_float(d_row["close"]) / prev_close - 1) * 100 if prev_close > 0 else None
                chosen = choose_hot_theme_for_symbol(
                    symbol,
                    hot_ids,
                    symbol_themes,
                    sectors_by_id,
                    stock_day_return=stock_day_return,
                    require_daily_resonance=args.require_daily_resonance,
                )
                l2_ratio = safe_float(d_row["l2_main_net_amount"]) / safe_float(d_row["total_amount"], 1.0)
                l2_amount = safe_float(d_row["l2_main_net_amount"])
                rec = {
                    "symbol": symbol,
                    "name": name_map.get(symbol, symbol),
                    "return": ret,
                    "chosen": chosen,
                    "theme_id": chosen[0] if chosen else None,
                    "theme_name": chosen[1] if chosen else None,
                    "l2_ratio": l2_ratio,
                    "l2_amount": l2_amount,
                    "limit_up_close": is_limit_up_close(symbol, d, limit_rows),
                }
                day_records.append(rec)

            mark_l2_leaders(day_records, args.l2_top_pct, metric=args.l2_metric)
            for rec in day_records:
                rec["hot_all"] = rec["chosen"] is not None
                rec["l2_filtered"] = bool(
                    rec["chosen"]
                    and (
                        rec["limit_up_close"]
                        or rec.get("l2_rank_selected")
                    )
                )
            winners = sorted(day_records, key=lambda x: x["return"], reverse=True)[:args.winner_top_n]
            counts["pool"] += len(day_records)
            counts["winners"] += len(winners)
            market_returns.extend([r["return"] for r in day_records])
            for group in ["hot_all", "l2_filtered"]:
                selected = [r for r in day_records if r[group]]
                hit_winners = [r for r in winners if r[group]]
                counts[group] += len(selected)
                counts[f"{group}_winners"] += len(hit_winners)
                group_returns[group].extend([r["return"] for r in selected])
                for r in hit_winners:
                    theme_hits[group][str(r.get("theme_name") or "unknown")] += 1

        market_stat = summarize(market_returns)
        summary[hkey] = {"market_return": market_stat}
        for group in ["hot_all", "l2_filtered"]:
            coverage = counts[group] / counts["pool"] if counts["pool"] else 0.0
            recall = counts[f"{group}_winners"] / counts["winners"] if counts["winners"] else 0.0
            stat = summarize(group_returns[group])
            summary[hkey][group] = {
                "coverage": round(coverage, 4),
                "winner_recall": round(recall, 4),
                "lift": round(recall / coverage, 4) if coverage > 0 else None,
                "return": stat,
                "alpha": round(stat["avg"] - market_stat["avg"], 4),
                "theme_winner_hits": theme_hits[group].most_common(20),
            }

    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "top_k": args.top_k,
            "theme_source": args.theme_source,
            "l2_top_pct": args.l2_top_pct,
            "l2_metric": args.l2_metric,
            "min_member_count": min_member_count,
            "max_member_count": max_member_count,
            "winner_top_n": args.winner_top_n,
            "min_amount": args.min_amount,
            "min_history_days": args.min_history_days,
            "require_daily_resonance": bool(args.require_daily_resonance),
            "atomic_db": str(ATOMIC_DB),
        },
        "summary": summary,
    }
    ensure_market_heat_dir()
    suffix = "_resonance" if args.require_daily_resonance else ""
    source_slug = args.theme_source.replace("-", "_")
    member_suffix = f"_m{min_member_count}_{max_member_count}" if args.theme_source == "fine-sector" else ""
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"hot_{source_slug}_l2_{args.l2_metric}_leader_filter_top{args.top_k}{member_suffix}_l2top{int(args.l2_top_pct*100)}{suffix}_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
