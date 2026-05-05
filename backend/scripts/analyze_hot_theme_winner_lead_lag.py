#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import ATOMIC_MAINBOARD_DB_PATH, DATA_DIR
from backend.app.services.market_heat import (
    MARKET_HEAT_DIR,
    _symbol_norm,
    _trade_dates,
    build_market_heat_snapshot,
    ensure_market_heat_dir,
)

DEFAULT_TRADABLE_THEME_DB = Path(os.getenv("TRADABLE_THEME_MAP_DB", os.path.join(DATA_DIR, "market_heat", "tradable_theme_map.db")))
DEFAULT_STOCK_SECTOR_DB = Path(os.getenv("STOCK_SECTOR_MAP_DB", os.path.join(DATA_DIR, "market_heat", "stock_sector_map.db")))
ATOMIC_DB = Path(os.getenv("MARKET_HEAT_ATOMIC_DB", ATOMIC_MAINBOARD_DB_PATH))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def summarize(values: Sequence[float]) -> Dict[str, Any]:
    clean = [safe_float(v) for v in values if v is not None]
    if not clean:
        return {"n": 0, "avg": 0.0, "median": 0.0, "win_rate": 0.0}
    return {
        "n": len(clean),
        "avg": round(sum(clean) / len(clean), 4),
        "median": round(statistics.median(clean), 4),
        "win_rate": round(sum(1 for v in clean if v > 0) / len(clean), 4),
    }


def load_tradable_themes(db_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, set], Dict[str, List[str]], Dict[str, str]]:
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        theme_rows = {str(row["theme_id"]): dict(row) for row in conn.execute("SELECT * FROM tradable_themes")}
        rows = conn.execute(
            """
            SELECT theme_id, theme_name, symbol, name
            FROM tradable_theme_memberships
            ORDER BY theme_id, symbol
            """
        ).fetchall()
    themes: Dict[str, Dict[str, Any]] = {}
    theme_members: Dict[str, set] = defaultdict(set)
    symbol_themes: Dict[str, List[str]] = defaultdict(list)
    name_map: Dict[str, str] = {}
    for row in rows:
        theme_id = str(row["theme_id"])
        symbol = _symbol_norm(row["symbol"])
        if theme_id not in themes:
            meta = theme_rows.get(theme_id, {})
            themes[theme_id] = {
                "id": theme_id,
                "name": str(row["theme_name"]),
                "type": meta.get("theme_type") or "tradable_theme",
                "description": f"tradable theme from {db_path.name}",
                "symbols": [],
            }
        themes[theme_id]["symbols"].append({"symbol": symbol, "name": str(row["name"] or symbol)})
        theme_members[theme_id].add(symbol)
        symbol_themes[symbol].append(theme_id)
        if row["name"]:
            name_map[symbol] = str(row["name"])
    return list(themes.values()), dict(theme_members), dict(symbol_themes), name_map


def load_extra_names(db_path: Path) -> Dict[str, str]:
    if not db_path.exists():
        return {}
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT symbol, name FROM stock_sector_memberships WHERE name IS NOT NULL AND name != ''").fetchall()
        except Exception:
            return {}
    return {_symbol_norm(row["symbol"]): str(row["name"]) for row in rows}


def load_price_and_limit_rows(start_date: str, end_date: str) -> Tuple[List[str], Dict[str, Dict[str, sqlite3.Row]], Dict[str, Dict[str, sqlite3.Row]]]:
    with sqlite3.connect(str(ATOMIC_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        trade_dates = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT trade_date
                FROM atomic_trade_daily
                WHERE trade_date >= ? AND trade_date <= ?
                ORDER BY trade_date
                """,
                (start_date, end_date),
            )
        ]
        price: Dict[str, Dict[str, sqlite3.Row]] = defaultdict(dict)
        for row in conn.execute(
            """
            SELECT symbol, trade_date, open, high, low, close, total_amount, l2_main_net_amount, l2_activity_ratio
            FROM atomic_trade_daily
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY symbol, trade_date
            """,
            (start_date, end_date),
        ):
            price[_symbol_norm(row["symbol"])][str(row["trade_date"])] = row
        limit: Dict[str, Dict[str, sqlite3.Row]] = defaultdict(dict)
        for row in conn.execute(
            """
            SELECT symbol, trade_date, up_limit_price, open_price, is_limit_up_close, limit_state_label
            FROM atomic_limit_state_daily
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY symbol, trade_date
            """,
            (start_date, end_date),
        ):
            limit[_symbol_norm(row["symbol"])][str(row["trade_date"])] = row
    return trade_dates, dict(price), dict(limit)


def is_st_name(name: str) -> bool:
    text = str(name or "").upper().strip()
    return text.startswith("ST") or text.startswith("*ST") or text.startswith("S*ST")


def is_unbuyable_limit_up(symbol: str, d_row: sqlite3.Row, entry_row: sqlite3.Row, limit_rows: Dict[str, Dict[str, sqlite3.Row]], entry_date: str) -> bool:
    open_price = safe_float(entry_row["open"])
    limit_row = limit_rows.get(symbol, {}).get(entry_date)
    if limit_row:
        up_limit = safe_float(limit_row["up_limit_price"])
        if up_limit > 0 and open_price >= up_limit - 0.001:
            return True
    prev_close = safe_float(d_row["close"])
    return prev_close > 0 and open_price / prev_close >= 1.095


def forward_return(entry_row: sqlite3.Row, exit_row: sqlite3.Row) -> Optional[float]:
    entry_open = safe_float(entry_row["open"])
    exit_close = safe_float(exit_row["close"])
    if entry_open <= 0:
        return None
    return (exit_close / entry_open - 1) * 100


def build_heat_history(
    dates: Sequence[str],
    themes: List[Dict[str, Any]],
    top_k: int,
    stage_window: int = 5,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Dict[str, Any]]]]:
    snapshots: Dict[str, Dict[str, Any]] = {}
    stage_by_date_theme: Dict[str, Dict[str, Dict[str, Any]]] = {}
    hot_history: Dict[str, List[int]] = defaultdict(list)
    prev_scores: Dict[str, float] = {}
    for idx, date in enumerate(dates, start=1):
        snapshot = build_market_heat_snapshot(date, themes_override=themes)
        snapshots[date] = snapshot
        hot_top = snapshot.get("hot_top", [])[:top_k]
        hot_ids = {str(item.get("id")) for item in hot_top}
        current_scores = {str(item.get("id")): safe_float(item.get("hot_score")) for item in snapshot.get("sectors", [])}
        for theme_id in current_scores:
            hot_history[theme_id].append(1 if theme_id in hot_ids else 0)
        stage_by_date_theme[date] = {}
        for rank, item in enumerate(hot_top, start=1):
            theme_id = str(item.get("id"))
            recent_hits = sum(hot_history.get(theme_id, [])[-max(1, stage_window):])
            stage = "new_hot" if recent_hits <= 1 else ("continuing_hot" if recent_hits <= 3 else "climax_hot")
            stage_by_date_theme[date][theme_id] = {
                "rank": rank,
                "duration": recent_hits,
                "stage": stage,
                "hot_score": safe_float(item.get("hot_score")),
                "acceleration": round(safe_float(item.get("hot_score")) - prev_scores.get(theme_id, 0.0), 4),
            }
        prev_scores = current_scores
        print(f"[heat {idx}/{len(dates)}] {date}", file=sys.stderr)
    return snapshots, stage_by_date_theme


def choose_hot_theme_for_symbol(
    symbol: str,
    hot_theme_ids: Sequence[str],
    symbol_themes: Dict[str, List[str]],
    sectors_by_id: Dict[str, Dict[str, Any]],
    stock_day_return: Optional[float] = None,
    require_daily_resonance: bool = False,
) -> Optional[Tuple[str, str, float]]:
    candidates = [tid for tid in symbol_themes.get(symbol, []) if tid in hot_theme_ids]
    if require_daily_resonance:
        candidates = [
            tid for tid in candidates
            if stock_day_return is not None
            and stock_day_return > 0
            and safe_float(sectors_by_id.get(tid, {}).get("pct_change")) > 0
        ]
    if not candidates:
        return None
    candidates.sort(key=lambda tid: safe_float(sectors_by_id.get(tid, {}).get("hot_score")), reverse=True)
    tid = candidates[0]
    sector = sectors_by_id.get(tid, {})
    return tid, str(sector.get("name") or tid), safe_float(sector.get("hot_score"))


def aggregate_report(
    analysis_dates: Sequence[str],
    trade_dates: Sequence[str],
    price_rows: Dict[str, Dict[str, sqlite3.Row]],
    limit_rows: Dict[str, Dict[str, sqlite3.Row]],
    snapshots: Dict[str, Dict[str, Any]],
    stage_by_date_theme: Dict[str, Dict[str, Dict[str, Any]]],
    theme_members: Dict[str, set],
    symbol_themes: Dict[str, List[str]],
    name_map: Dict[str, str],
    horizons: Sequence[int],
    top_k: int,
    winner_top_n: int,
    min_amount: float,
    min_history_days: int,
    exclude_unbuyable: bool,
    require_daily_resonance: bool,
) -> Dict[str, Any]:
    date_index = {d: i for i, d in enumerate(trade_dates)}
    first_index: Dict[str, int] = {}
    for symbol, rows in price_rows.items():
        indexes = [date_index[d] for d in rows.keys() if d in date_index]
        if indexes:
            first_index[symbol] = min(indexes)

    summaries: Dict[str, Dict[str, Any]] = {}
    daily_rows_by_horizon: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for horizon in horizons:
        hkey = str(horizon)
        market_returns: List[float] = []
        hot_returns: List[float] = []
        stage_returns: Dict[str, List[float]] = defaultdict(list)
        pool_count = hot_pool_count = 0
        winner_count = winner_hit_count = 0
        raw_hot_winner_count = raw_unbuyable_hot_winner_count = 0
        theme_winner_hits: Counter[str] = Counter()
        stage_winner_hits: Counter[str] = Counter()

        for d in analysis_dates:
            i = date_index.get(d)
            if i is None or i + horizon >= len(trade_dates) or i + 1 >= len(trade_dates):
                continue
            entry_date = trade_dates[i + 1]
            exit_date = trade_dates[i + horizon]
            snapshot = snapshots[d]
            hot_top = snapshot.get("hot_top", [])[:top_k]
            hot_theme_ids = [str(item.get("id")) for item in hot_top]
            hot_theme_names = [str(item.get("name")) for item in hot_top]
            hot_member_union = set()
            for tid in hot_theme_ids:
                hot_member_union.update(theme_members.get(tid, set()))
            sectors_by_id = {str(item.get("id")): item for item in snapshot.get("sectors", [])}

            raw_records = []
            exec_records = []
            for symbol, rows in price_rows.items():
                d_row = rows.get(d)
                entry_row = rows.get(entry_date)
                exit_row = rows.get(exit_date)
                if not d_row or not entry_row or not exit_row:
                    continue
                if first_index.get(symbol, 10**9) > i - min_history_days:
                    continue
                if safe_float(d_row["total_amount"]) < min_amount:
                    continue
                if is_st_name(name_map.get(symbol, "")):
                    continue
                ret = forward_return(entry_row, exit_row)
                if ret is None:
                    continue
                prev_row = rows.get(trade_dates[i - 1]) if i > 0 else None
                prev_close = safe_float(prev_row["close"]) if prev_row else safe_float(d_row["open"])
                stock_day_return = (safe_float(d_row["close"]) / prev_close - 1) * 100 if prev_close > 0 else None
                chosen = choose_hot_theme_for_symbol(
                    symbol,
                    hot_theme_ids,
                    symbol_themes,
                    sectors_by_id,
                    stock_day_return=stock_day_return,
                    require_daily_resonance=require_daily_resonance,
                )
                is_hot = chosen is not None
                stage = None
                theme_name = None
                if chosen:
                    tid, theme_name, _ = chosen
                    stage = stage_by_date_theme.get(d, {}).get(tid, {}).get("stage")
                unbuyable = is_unbuyable_limit_up(symbol, d_row, entry_row, limit_rows, entry_date)
                rec = {
                    "symbol": symbol,
                    "name": name_map.get(symbol, symbol),
                    "return": ret,
                    "is_hot": is_hot,
                    "theme_name": theme_name,
                    "stage": stage,
                    "unbuyable": unbuyable,
                }
                raw_records.append(rec)
                if exclude_unbuyable and unbuyable:
                    continue
                exec_records.append(rec)

            if not exec_records:
                continue
            day_pool_count = len(exec_records)
            day_hot_records = [r for r in exec_records if r["is_hot"]]
            day_hot_count = len(day_hot_records)
            pool_count += day_pool_count
            hot_pool_count += day_hot_count
            market_returns.extend([r["return"] for r in exec_records])
            hot_returns.extend([r["return"] for r in day_hot_records])
            for r in day_hot_records:
                stage_returns[str(r.get("stage") or "unknown")].append(r["return"])

            winners = sorted(exec_records, key=lambda r: r["return"], reverse=True)[:winner_top_n]
            winner_count += len(winners)
            hit_winners = [r for r in winners if r["is_hot"]]
            winner_hit_count += len(hit_winners)
            for r in hit_winners:
                theme_winner_hits[str(r.get("theme_name") or "unknown")] += 1
                stage_winner_hits[str(r.get("stage") or "unknown")] += 1

            raw_winners = sorted(raw_records, key=lambda r: r["return"], reverse=True)[:winner_top_n]
            raw_hot_winners = [r for r in raw_winners if r["is_hot"]]
            raw_hot_winner_count += len(raw_hot_winners)
            raw_unbuyable_hot_winner_count += sum(1 for r in raw_hot_winners if r["unbuyable"])

            daily_coverage = day_hot_count / day_pool_count if day_pool_count else 0.0
            daily_recall = len(hit_winners) / len(winners) if winners else 0.0
            daily_rows_by_horizon[hkey].append({
                "date": d,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "hot_themes": hot_theme_names,
                "pool_count": day_pool_count,
                "hot_pool_count": day_hot_count,
                "coverage": round(daily_coverage, 4),
                "winner_count": len(winners),
                "winner_hit_count": len(hit_winners),
                "winner_recall": round(daily_recall, 4),
                "lift": round(daily_recall / daily_coverage, 4) if daily_coverage > 0 else None,
                "top_winners": [
                    {
                        "symbol": r["symbol"],
                        "name": r["name"],
                        "return": round(r["return"], 2),
                        "hot_theme": r.get("theme_name"),
                    }
                    for r in winners[:10]
                ],
            })

        coverage = hot_pool_count / pool_count if pool_count else 0.0
        recall = winner_hit_count / winner_count if winner_count else 0.0
        market = summarize(market_returns)
        hot = summarize(hot_returns)
        summaries[hkey] = {
            "horizon": horizon,
            "analysis_days_used": len(daily_rows_by_horizon[hkey]),
            "pool_count": pool_count,
            "hot_pool_count": hot_pool_count,
            "hot_theme_coverage": round(coverage, 4),
            "winner_count": winner_count,
            "winner_hit_count": winner_hit_count,
            "winner_recall": round(recall, 4),
            "lift": round(recall / coverage, 4) if coverage > 0 else None,
            "market_return": market,
            "hot_theme_return": hot,
            "hot_theme_alpha": round(hot["avg"] - market["avg"], 4),
            "win_rate_alpha": round(hot["win_rate"] - market["win_rate"], 4),
            "unbuyable_limit_up_ratio": round(raw_unbuyable_hot_winner_count / raw_hot_winner_count, 4) if raw_hot_winner_count else 0.0,
            "stage_returns": {stage: summarize(vals) for stage, vals in sorted(stage_returns.items())},
            "stage_winner_hits": dict(stage_winner_hits.most_common()),
            "theme_winner_hits": theme_winner_hits.most_common(20),
            "daily_recent": daily_rows_by_horizon[hkey][-10:],
        }
    return summaries


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 热门主题领先性验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 口径：D 日热门交易主题 Top{meta['top_k']} → D+1 开盘至 D+N 收盘。",
        f"- 可交易过滤：D 日成交额 >= {meta['min_amount'] / 1e8:.2f} 亿，历史 >= {meta['min_history_days']} 个交易日，剔除 ST，剔除 D+1 一字涨停开盘。",
        f"- 命中约束：{'要求股票与热门主题 D 日同向上涨' if meta.get('require_daily_resonance') else '静态主题标签命中'}；生命周期窗口：过去 {meta.get('stage_window', 5)} 个交易日。",
        "",
        "## 总览",
        "",
        "| Horizon | 样本天数 | Coverage | Recall | Lift | 热门均值 | 市场均值 | Alpha | 热门胜率 | 市场胜率 | 一字不可买占比 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for hkey, item in report["summary"].items():
        hot = item["hot_theme_return"]
        market = item["market_return"]
        lines.append(
            f"| {hkey} | {item['analysis_days_used']} | {item['hot_theme_coverage']:.1%} | {item['winner_recall']:.1%} | "
            f"{item['lift']} | {hot['avg']:.2f}% | {market['avg']:.2f}% | {item['hot_theme_alpha']:.2f}% | "
            f"{hot['win_rate']:.1%} | {market['win_rate']:.1%} | {item['unbuyable_limit_up_ratio']:.1%} |"
        )
    lines += ["", "## 热度阶段表现", ""]
    for hkey, item in report["summary"].items():
        lines += [f"### Horizon {hkey}", "", "| 阶段 | 样本 | 均值 | 胜率 | 赢家命中数 |", "|---|---:|---:|---:|---:|"]
        hits = item.get("stage_winner_hits", {})
        for stage in ["new_hot", "continuing_hot", "climax_hot", "unknown"]:
            stat = item.get("stage_returns", {}).get(stage, {"n": 0, "avg": 0.0, "win_rate": 0.0})
            if stat["n"] == 0 and not hits.get(stage):
                continue
            lines.append(f"| {stage} | {stat['n']} | {stat['avg']:.2f}% | {stat['win_rate']:.1%} | {hits.get(stage, 0)} |")
        lines.append("")
    preferred_h = "5" if "5" in report["summary"] else next(iter(report["summary"].keys()), "")
    if preferred_h:
        item = report["summary"][preferred_h]
        lines += [f"## Horizon {preferred_h} 强股命中主题分布", ""]
        for name, count in item.get("theme_winner_hits", [])[:15]:
            lines.append(f"- {name}: {count}")
        lines += ["", f"## Horizon {preferred_h} 最近日级样本", ""]
        for row in item.get("daily_recent", []):
            lines.append(
                f"- {row['date']}：Coverage {row['coverage']:.1%}，Recall {row['winner_recall']:.1%}，Lift {row['lift']}；热门："
                + "、".join(row["hot_themes"][:5])
            )
    lines += ["", "## 解释", ""]
    lines += [
        "- Coverage 是热门主题覆盖全市场可交易股票的比例。",
        "- Recall 是未来强股命中 D 日热门主题的比例。",
        "- Lift = Recall / Coverage，用来判断是否只是因为热门主题覆盖股票多。",
        "- Alpha 和胜率用于判断热门主题池整体是否值得买，而不是只解释少数牛股。",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate whether D-day hot tradable themes lead future market winners.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--days", type=int, default=63)
    parser.add_argument("--horizons", default="1,3,5,10")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--winner-top-n", type=int, default=20)
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--include-unbuyable", action="store_true", help="不剔除 D+1 一字涨停开盘股票")
    parser.add_argument("--require-daily-resonance", action="store_true", help="命中热门主题时要求股票 D 日上涨且主题 D 日上涨，降低多标签污染")
    parser.add_argument("--stage-window", type=int, default=5, help="热度生命周期使用过去 N 个交易日滑动窗口统计上榜次数")
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    if not horizons:
        raise RuntimeError("horizons is empty")
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    lookback = args.days + args.min_history_days + max(horizons) + 30
    all_dates = _trade_dates(end_date, lookback)
    if args.start_date:
        analysis_dates = [d for d in all_dates if args.start_date <= d <= end_date]
    else:
        analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    if not analysis_dates:
        raise RuntimeError("No analysis dates.")
    start_price_date = all_dates[0]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(start_price_date, end_date)
    themes, theme_members, symbol_themes, name_map = load_tradable_themes(Path(args.tradable_theme_db))
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})

    # Warm up a few dates before the analysis window so new/continuing/climax is less biased at the first day.
    warmup_start_idx = max(0, all_dates.index(analysis_dates[0]) - 20) if analysis_dates[0] in all_dates else 0
    heat_dates = [d for d in all_dates[warmup_start_idx:] if d <= analysis_dates[-1]]
    snapshots, stage_by_date_theme = build_heat_history(heat_dates, themes, args.top_k, stage_window=args.stage_window)
    summary = aggregate_report(
        analysis_dates=analysis_dates,
        trade_dates=trade_dates,
        price_rows=price_rows,
        limit_rows=limit_rows,
        snapshots=snapshots,
        stage_by_date_theme=stage_by_date_theme,
        theme_members=theme_members,
        symbol_themes=symbol_themes,
        name_map=name_map,
        horizons=horizons,
        top_k=args.top_k,
        winner_top_n=args.winner_top_n,
        min_amount=args.min_amount,
        min_history_days=args.min_history_days,
        exclude_unbuyable=not args.include_unbuyable,
        require_daily_resonance=args.require_daily_resonance,
    )
    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "analysis_days": len(analysis_dates),
            "horizons": horizons,
            "top_k": args.top_k,
            "winner_top_n": args.winner_top_n,
            "min_amount": args.min_amount,
            "min_history_days": args.min_history_days,
            "exclude_unbuyable": not args.include_unbuyable,
            "require_daily_resonance": bool(args.require_daily_resonance),
            "stage_window": int(args.stage_window),
            "tradable_theme_db": str(Path(args.tradable_theme_db)),
            "atomic_db": str(ATOMIC_DB),
        },
        "summary": summary,
    }
    ensure_market_heat_dir()
    resonance_suffix = "_resonance" if args.require_daily_resonance else ""
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"hot_theme_winner_lead_lag_top{args.top_k}{resonance_suffix}_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
