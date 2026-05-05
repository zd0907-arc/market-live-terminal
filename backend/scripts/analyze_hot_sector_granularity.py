#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR, ROOT_DIR
from backend.app.services.market_heat import MARKET_HEAT_DIR, _symbol_norm, _trade_dates, ensure_market_heat_dir
from backend.scripts.analyze_hot_theme_winner_lead_lag import (
    DEFAULT_STOCK_SECTOR_DB,
    aggregate_report,
    build_heat_history,
    load_extra_names,
    load_price_and_limit_rows,
)

DEFAULT_TRADABLE_THEME_DB = Path(os.getenv("TRADABLE_THEME_MAP_DB", os.path.join(DATA_DIR, "market_heat", "tradable_theme_map.db")))
DEFAULT_FINE_RULES = Path(ROOT_DIR) / "data" / "market_heat" / "fine_hotspot_rules.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def keyword_match(text: str, keywords: Sequence[str]) -> bool:
    return any(str(k) and str(k) in text for k in keywords)


def load_fine_sector_themes(
    db_path: Path,
    rules: Dict[str, Any],
    min_member_count: int | None = None,
    max_member_count: int | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, set], Dict[str, List[str]], Dict[str, str]]:
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    sector_types = set(rules.get("sector_types") or ["concept", "industry"])
    min_count = int(min_member_count or rules.get("min_member_count") or 5)
    max_count = int(max_member_count or rules.get("max_member_count") or 80)
    exclude_keywords = list(rules.get("exclude_keywords") or [])
    keep_exact = set(rules.get("keep_exact") or [])
    exclude_downranked = bool(rules.get("exclude_downranked", True))
    dedupe = bool(rules.get("dedupe_identical_members", True))

    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT b.sector_code, b.sector_name, b.sector_type, b.clean_status,
                   m.symbol, m.name
            FROM clean_sector_boards b
            JOIN clean_stock_sector_memberships m
              ON m.sector_code = b.sector_code
             AND m.sector_type = b.sector_type
            WHERE b.clean_status != 'excluded'
            ORDER BY b.sector_type, b.sector_code, m.symbol
            """
        ).fetchall()

    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    name_map: Dict[str, str] = {}
    for row in rows:
        sector_type = str(row["sector_type"] or "")
        sector_name = str(row["sector_name"] or "")
        if sector_type not in sector_types:
            continue
        if exclude_downranked and str(row["clean_status"]) == "downranked" and sector_name not in keep_exact:
            continue
        if sector_name not in keep_exact and keyword_match(sector_name, exclude_keywords):
            continue
        key = (sector_type, str(row["sector_code"]))
        if key not in grouped:
            grouped[key] = {
                "id": f"fine:{sector_type}:{row['sector_code']}",
                "name": sector_name,
                "type": f"fine_{sector_type}",
                "sector_type": sector_type,
                "sector_code": str(row["sector_code"]),
                "symbols": [],
            }
        symbol = _symbol_norm(row["symbol"])
        grouped[key]["symbols"].append({"symbol": symbol, "name": str(row["name"] or symbol)})
        if row["name"]:
            name_map[symbol] = str(row["name"])

    candidates = []
    for item in grouped.values():
        symbols = {x["symbol"] for x in item["symbols"]}
        count = len(symbols)
        if count < min_count or count > max_count:
            continue
        item["member_count"] = count
        candidates.append(item)

    if dedupe:
        by_members: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        for item in candidates:
            key = tuple(sorted({x["symbol"] for x in item["symbols"]}))
            old = by_members.get(key)
            if old is None:
                by_members[key] = item
                continue
            def score(x: Dict[str, Any]) -> Tuple[int, int, int]:
                name = str(x.get("name") or "")
                suffix_penalty = 1 if name.endswith(("Ⅱ", "Ⅲ")) else 0
                type_penalty = 0 if x.get("sector_type") == "concept" else 1
                return (suffix_penalty, type_penalty, len(name))
            if score(item) < score(old):
                by_members[key] = item
        candidates = list(by_members.values())

    theme_members = {item["id"]: {x["symbol"] for x in item["symbols"]} for item in candidates}
    symbol_themes: Dict[str, List[str]] = {}
    for theme_id, members in theme_members.items():
        for symbol in members:
            symbol_themes.setdefault(symbol, []).append(theme_id)
    candidates.sort(key=lambda x: (x["sector_type"], x["name"]))
    return candidates, theme_members, symbol_themes, name_map


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 细颗粒热点板块验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 细板块数量：{meta['fine_sector_count']}，成员数范围：{meta['min_member_count']}~{meta['max_member_count']}。",
        f"- 口径：D 日细颗粒热点 Top{meta['top_k']} → D+1 开盘至 D+N 收盘。",
        f"- 命中约束：{'股票与板块 D 日同向上涨' if meta.get('require_daily_resonance') else '静态板块标签命中'}。",
        "",
        "## 总览",
        "",
        "| Horizon | 样本天数 | Coverage | Recall | Lift | 热门均值 | 市场均值 | Alpha | 热门胜率 | 市场胜率 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for hkey, item in report["summary"].items():
        hot = item["hot_theme_return"]
        market = item["market_return"]
        lines.append(
            f"| {hkey} | {item['analysis_days_used']} | {item['hot_theme_coverage']:.1%} | {item['winner_recall']:.1%} | "
            f"{item['lift']} | {hot['avg']:.2f}% | {market['avg']:.2f}% | {item['hot_theme_alpha']:.2f}% | "
            f"{hot['win_rate']:.1%} | {market['win_rate']:.1%} |"
        )
    hkey = "5" if "5" in report["summary"] else next(iter(report["summary"].keys()), "")
    if hkey:
        lines += ["", f"## Horizon {hkey} 强股命中细板块", ""]
        for name, count in report["summary"][hkey].get("theme_winner_hits", [])[:20]:
            lines.append(f"- {name}: {count}")
        lines += ["", f"## Horizon {hkey} 最近日级样本", ""]
        for row in report["summary"][hkey].get("daily_recent", [])[-10:]:
            lines.append(
                f"- {row['date']}：Coverage {row['coverage']:.1%}，Recall {row['winner_recall']:.1%}，Lift {row['lift']}；热点："
                + "、".join(row["hot_themes"][:5])
            )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate fine-grained hot sectors with lower coverage target.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=63)
    parser.add_argument("--horizons", default="1,3,5,10")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--winner-top-n", type=int, default=20)
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--min-member-count", type=int, default=None)
    parser.add_argument("--max-member-count", type=int, default=None)
    parser.add_argument("--require-daily-resonance", action="store_true")
    parser.add_argument("--include-unbuyable", action="store_true")
    parser.add_argument("--rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    rules = load_json(Path(args.rules))
    min_count = args.min_member_count or int(rules.get("min_member_count") or 5)
    max_count = args.max_member_count or int(rules.get("max_member_count") or 80)
    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    all_dates = _trade_dates(end_date, args.days + args.min_history_days + max(horizons) + 30)
    analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], end_date)
    themes, theme_members, symbol_themes, name_map = load_fine_sector_themes(Path(args.tradable_theme_db), rules, min_count, max_count)
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})
    heat_dates = [d for d in all_dates if d <= analysis_dates[-1]]
    snapshots, stage_by_date_theme = build_heat_history(heat_dates, themes, args.top_k, stage_window=5)
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
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "top_k": args.top_k,
            "fine_sector_count": len(themes),
            "min_member_count": min_count,
            "max_member_count": max_count,
            "require_daily_resonance": bool(args.require_daily_resonance),
            "rules": str(Path(args.rules)),
        },
        "summary": summary,
    }
    ensure_market_heat_dir()
    suffix = "_resonance" if args.require_daily_resonance else ""
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"fine_hotspot_granularity_top{args.top_k}_m{min_count}_{max_count}{suffix}_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
