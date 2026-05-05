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
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR
from backend.app.services.market_heat import MARKET_HEAT_DIR, _symbol_norm, _trade_dates, ensure_market_heat_dir
from backend.scripts.analyze_hot_sector_granularity import (
    DEFAULT_FINE_RULES,
    load_fine_sector_themes,
    load_json,
)
from backend.scripts.analyze_hot_theme_winner_lead_lag import (
    DEFAULT_STOCK_SECTOR_DB,
    DEFAULT_TRADABLE_THEME_DB,
    build_heat_history,
    choose_hot_theme_for_symbol,
    forward_return,
    is_st_name,
    is_unbuyable_limit_up,
    load_extra_names,
    load_price_and_limit_rows,
    safe_float,
    summarize,
)

DEFAULT_SELECTION_DB = Path(os.getenv("SELECTION_DB_PATH", os.path.join(DATA_DIR, "selection", "selection_research.db")))


def _light_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    def keep(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "hot_score": item.get("hot_score"),
            "pct_change": item.get("pct_change"),
        }

    return {
        "hot_top": [keep(x) for x in snapshot.get("hot_top", [])],
        "sectors": [keep(x) for x in snapshot.get("sectors", [])],
    }


def load_or_build_heat_snapshots(
    heat_dates: Sequence[str],
    themes: List[Dict[str, Any]],
    top_k: int,
    min_member_count: int,
    max_member_count: int,
    cache_dir: Path,
    use_cache: bool,
) -> Dict[str, Dict[str, Any]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"fine_heat_snapshots_{heat_dates[0]}_{heat_dates[-1]}_m{min_member_count}_{max_member_count}.json"
    if use_cache and cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        snapshots = payload.get("snapshots", {})
        if all(date in snapshots for date in heat_dates):
            print(f"loaded heat cache {cache_path}", file=sys.stderr)
            return snapshots
    snapshots, _ = build_heat_history(heat_dates, themes, top_k, stage_window=5)
    light = {date: _light_snapshot(snapshot) for date, snapshot in snapshots.items()}
    cache_path.write_text(json.dumps({"snapshots": light}, ensure_ascii=False), encoding="utf-8")
    print(f"wrote heat cache {cache_path}", file=sys.stderr)
    return light


def load_selection_candidates(selection_db: Path, dates: Sequence[str], top_k: int) -> List[Dict[str, Any]]:
    if not selection_db.exists():
        raise FileNotFoundError(str(selection_db))
    start_date, end_date = dates[0], dates[-1]
    with sqlite3.connect(str(selection_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT s.symbol, s.trade_date, s.strategy_version,
                   s.stealth_score, s.stealth_signal,
                   s.breakout_score, s.confirm_signal,
                   f.name
            FROM selection_signal_daily s
            LEFT JOIN selection_feature_daily f
              ON f.symbol = s.symbol
             AND f.trade_date = s.trade_date
             AND f.feature_version = s.feature_version
            WHERE s.trade_date >= ? AND s.trade_date <= ?
              AND (s.stealth_signal = 1 OR s.confirm_signal = 1)
            """,
            (start_date, end_date),
        ).fetchall()
    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = _symbol_norm(row["symbol"])
        if int(row["confirm_signal"] or 0) == 1:
            grouped[(str(row["trade_date"]), "breakout")].append({
                "symbol": symbol,
                "name": row["name"] or symbol,
                "signal_date": str(row["trade_date"]),
                "strategy": "breakout",
                "score": safe_float(row["breakout_score"]),
            })
        if int(row["stealth_signal"] or 0) == 1:
            grouped[(str(row["trade_date"]), "stealth")].append({
                "symbol": symbol,
                "name": row["name"] or symbol,
                "signal_date": str(row["trade_date"]),
                "strategy": "stealth",
                "score": safe_float(row["stealth_score"]),
            })
    out: List[Dict[str, Any]] = []
    for items in grouped.values():
        items.sort(key=lambda x: x["score"], reverse=True)
        out.extend(items[:top_k])
    out.sort(key=lambda x: (x["signal_date"], x["strategy"], -x["score"]))
    return out


def first_indexes(price_rows: Dict[str, Dict[str, sqlite3.Row]], date_index: Dict[str, int]) -> Dict[str, int]:
    out = {}
    for symbol, rows in price_rows.items():
        indexes = [date_index[d] for d in rows.keys() if d in date_index]
        if indexes:
            out[symbol] = min(indexes)
    return out


def is_valid_tradeable(
    symbol: str,
    d: str,
    entry_date: str,
    i: int,
    rows: Dict[str, sqlite3.Row],
    first_idx: Dict[str, int],
    limit_rows: Dict[str, Dict[str, sqlite3.Row]],
    name_map: Dict[str, str],
    min_amount: float,
    min_history_days: int,
    exclude_unbuyable: bool,
) -> bool:
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
    if exclude_unbuyable and is_unbuyable_limit_up(symbol, d_row, entry_row, limit_rows, entry_date):
        return False
    return True


def get_resonance(
    symbol: str,
    rows: Dict[str, sqlite3.Row],
    trade_dates: Sequence[str],
    i: int,
    hot_ids: Sequence[str],
    symbol_themes: Dict[str, List[str]],
    sectors_by_id: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    d = trade_dates[i]
    d_row = rows.get(d)
    if not d_row:
        return None
    prev_row = rows.get(trade_dates[i - 1]) if i > 0 else None
    prev_close = safe_float(prev_row["close"]) if prev_row else safe_float(d_row["open"])
    stock_day_return = (safe_float(d_row["close"]) / prev_close - 1) * 100 if prev_close > 0 else None
    chosen = choose_hot_theme_for_symbol(
        symbol,
        hot_ids,
        symbol_themes,
        sectors_by_id,
        stock_day_return=stock_day_return,
        require_daily_resonance=True,
    )
    if not chosen:
        return None
    theme_id, theme_name, hot_score = chosen
    return {
        "theme_id": theme_id,
        "theme_name": theme_name,
        "hot_score": hot_score,
        "stock_day_return": stock_day_return,
        "theme_pct_change": safe_float(sectors_by_id.get(theme_id, {}).get("pct_change")),
    }


def compute_market_returns(
    analysis_dates: Sequence[str],
    trade_dates: Sequence[str],
    price_rows: Dict[str, Dict[str, sqlite3.Row]],
    limit_rows: Dict[str, Dict[str, sqlite3.Row]],
    name_map: Dict[str, str],
    horizons: Sequence[int],
    min_amount: float,
    min_history_days: int,
    exclude_unbuyable: bool,
) -> Dict[str, Dict[str, Any]]:
    date_index = {d: idx for idx, d in enumerate(trade_dates)}
    first_idx = first_indexes(price_rows, date_index)
    vals: Dict[str, List[float]] = {str(h): [] for h in horizons}
    for d in analysis_dates:
        i = date_index.get(d)
        if i is None:
            continue
        for horizon in horizons:
            if i + horizon >= len(trade_dates) or i + 1 >= len(trade_dates):
                continue
            entry_date = trade_dates[i + 1]
            exit_date = trade_dates[i + horizon]
            for symbol, rows in price_rows.items():
                if not is_valid_tradeable(symbol, d, entry_date, i, rows, first_idx, limit_rows, name_map, min_amount, min_history_days, exclude_unbuyable):
                    continue
                if exit_date not in rows:
                    continue
                ret = forward_return(rows[entry_date], rows[exit_date])
                if ret is not None:
                    vals[str(horizon)].append(ret)
    return {h: summarize(v) for h, v in vals.items()}


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 策略候选 + 细颗粒热点共振 A/B 验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 策略候选：每日每策略 Top{meta['selection_top_k']}。",
        f"- 热点口径：细颗粒热点 Top{meta['hot_top_k']}，成员数 {meta['min_member_count']}~{meta['max_member_count']}，要求股票与板块 D 日同向上涨。",
        f"- 收益口径：D+1 开盘 → D+N 收盘；可交易过滤同前。",
        "",
    ]
    for strategy, groups in report["summary"].items():
        lines += [f"## {strategy}", "", "| Horizon | 组别 | 样本 | 占比 | 均值 | Alpha | 胜率 | 市场均值 | 市场胜率 |", "|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
        for hkey, item in groups.items():
            market = report["market"][hkey]
            total = item["baseline"]["n"] or 1
            for group in ["baseline", "resonance", "non_resonance"]:
                stat = item[group]
                lines.append(
                    f"| {hkey} | {group} | {stat['n']} | {stat['n']/total:.1%} | {stat['avg']:.2f}% | "
                    f"{stat['alpha']:.2f}% | {stat['win_rate']:.1%} | {market['avg']:.2f}% | {market['win_rate']:.1%} |"
                )
        if "5" in groups:
            hits = groups["5"].get("resonance_themes", [])
            if hits:
                lines += ["", "D+5 共振主题分布："]
                for name, count in hits[:12]:
                    lines.append(f"- {name}: {count}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B test selection strategy candidates with fine hot sector resonance.")
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
    parser.add_argument("--selection-db", default=str(DEFAULT_SELECTION_DB))
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--no-heat-cache", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    all_dates = _trade_dates(end_date, args.days + args.min_history_days + max(horizons) + 30)
    analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], end_date)
    date_index = {d: idx for idx, d in enumerate(trade_dates)}
    rules = load_json(Path(args.fine_rules))
    themes, theme_members, symbol_themes, name_map = load_fine_sector_themes(
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
        args.hot_top_k,
        args.min_member_count,
        args.max_member_count,
        MARKET_HEAT_DIR / "cache",
        use_cache=not args.no_heat_cache,
    )
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
    theme_hits: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    sample_counts = defaultdict(int)
    for rec in candidates:
        d = rec["signal_date"]
        i = date_index.get(d)
        symbol = rec["symbol"]
        rows = price_rows.get(symbol, {})
        if i is None or not rows:
            continue
        entry_date = trade_dates[i + 1] if i + 1 < len(trade_dates) else None
        if not entry_date or not is_valid_tradeable(symbol, d, entry_date, i, rows, first_idx, limit_rows, name_map, args.min_amount, args.min_history_days, not args.include_unbuyable):
            continue
        snapshot = snapshots.get(d)
        if not snapshot:
            continue
        hot_ids = [str(x.get("id")) for x in snapshot.get("hot_top", [])[:args.hot_top_k]]
        sectors_by_id = {str(x.get("id")): x for x in snapshot.get("sectors", [])}
        resonance = get_resonance(symbol, rows, trade_dates, i, hot_ids, symbol_themes, sectors_by_id)
        group = "resonance" if resonance else "non_resonance"
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
                returns[strategy][hkey][group].append(ret)
                if resonance and hkey == "5":
                    theme_hits[strategy][resonance["theme_name"]] += 1

    summary: Dict[str, Dict[str, Any]] = {}
    for strategy, by_h in returns.items():
        summary[strategy] = {}
        for hkey, groups in by_h.items():
            summary[strategy][hkey] = {}
            for group in ["baseline", "resonance", "non_resonance"]:
                stat = summarize(groups.get(group, []))
                stat["alpha"] = round(stat["avg"] - market[hkey]["avg"], 4)
                summary[strategy][hkey][group] = stat
            if hkey == "5":
                summary[strategy][hkey]["resonance_themes"] = sorted(theme_hits[strategy].items(), key=lambda x: x[1], reverse=True)

    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "analysis_days": len(analysis_dates),
            "selection_top_k": args.selection_top_k,
            "hot_top_k": args.hot_top_k,
            "min_member_count": args.min_member_count,
            "max_member_count": args.max_member_count,
            "selection_db": str(Path(args.selection_db)),
        },
        "market": market,
        "summary": summary,
    }
    ensure_market_heat_dir()
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"strategy_theme_resonance_top{args.selection_top_k}_hot{args.hot_top_k}_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
