#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR
from backend.app.services.market_heat import MARKET_HEAT_DIR, _symbol_norm, build_market_heat_snapshot, render_markdown, write_snapshot


DEFAULT_TRADABLE_THEME_DB = Path(os.getenv("TRADABLE_THEME_MAP_DB", os.path.join(DATA_DIR, "market_heat", "tradable_theme_map.db")))


def load_tradable_themes(db_path: Path) -> List[Dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT theme_id, theme_name, symbol, name
            FROM tradable_theme_memberships
            ORDER BY theme_id, symbol
            """
        ).fetchall()
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        theme_id = str(row["theme_id"])
        if theme_id not in grouped:
            grouped[theme_id] = {
                "id": theme_id,
                "name": row["theme_name"],
                "type": "tradable_theme",
                "description": f"tradable theme from {db_path.name}",
                "symbols": [],
            }
        grouped[theme_id]["symbols"].append({"symbol": _symbol_norm(row["symbol"]), "name": str(row["name"] or row["symbol"])})
    return list(grouped.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump market hot sectors from local atomic data and curated themes.")
    parser.add_argument("--date", dest="trade_date", default=None, help="交易日 YYYY-MM-DD，默认最新 atomic_trade_daily 日期")
    parser.add_argument("--theme-source", choices=["custom", "tradable-theme"], default="custom", help="custom=手工主题篮子；tradable-theme=清洗合并后的交易主题")
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB), help="tradable_theme_map.db 路径")
    parser.add_argument("--json", action="store_true", help="打印 JSON")
    parser.add_argument("--no-write", action="store_true", help="只打印，不写入 data/market_heat")
    args = parser.parse_args()

    themes = load_tradable_themes(Path(args.tradable_theme_db)) if args.theme_source == "tradable-theme" else None
    snapshot = build_market_heat_snapshot(args.trade_date, themes_override=themes)
    if args.theme_source == "tradable-theme":
        snapshot["meta"]["version"] = "market_heat_v1_tradable_theme"
        snapshot["meta"]["source"] = "local atomic_trade_daily + tradable_theme_map"
        snapshot["meta"]["tradable_theme_db"] = str(Path(args.tradable_theme_db))
    if not args.no_write:
        json_path, md_path = write_snapshot(snapshot)
        print(f"wrote {json_path}")
        print(f"wrote {md_path}")
    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(snapshot))


if __name__ == "__main__":
    main()
