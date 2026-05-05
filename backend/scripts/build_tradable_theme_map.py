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
from typing import Any, Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR, ROOT_DIR
from backend.app.services.market_heat import MARKET_HEAT_DIR, ensure_market_heat_dir

DEFAULT_SOURCE_DB = Path(os.getenv("STOCK_SECTOR_MAP_DB", os.path.join(DATA_DIR, "market_heat", "stock_sector_map.db")))
DEFAULT_OUTPUT_DB = Path(os.getenv("TRADABLE_THEME_MAP_DB", os.path.join(DATA_DIR, "market_heat", "tradable_theme_map.db")))
DEFAULT_CLEAN_RULES = Path(ROOT_DIR) / "data" / "market_heat" / "sector_clean_rules.json"
DEFAULT_THEME_RULES = Path(ROOT_DIR) / "data" / "market_heat" / "tradable_theme_rules.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def keyword_match(text: str, keywords: Sequence[str]) -> bool:
    return any(str(k) and str(k) in text for k in keywords)


def is_excluded(sector_name: str, clean_rules: Dict[str, Any]) -> bool:
    keep = set(clean_rules.get("keep_exact") or [])
    if sector_name in keep:
        return False
    if sector_name in set(clean_rules.get("exclude_exact") or []):
        return True
    return keyword_match(sector_name, clean_rules.get("exclude_keywords") or [])


def is_downranked(sector_name: str, clean_rules: Dict[str, Any]) -> bool:
    return keyword_match(sector_name, clean_rules.get("downrank_keywords") or [])


def init_output_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS clean_sector_boards (
                sector_code TEXT NOT NULL,
                sector_name TEXT NOT NULL,
                sector_type TEXT NOT NULL,
                clean_status TEXT NOT NULL,
                clean_reason TEXT,
                weight REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                PRIMARY KEY (sector_code, sector_type)
            );
            CREATE TABLE IF NOT EXISTS clean_stock_sector_memberships (
                symbol TEXT NOT NULL,
                name TEXT,
                sector_code TEXT NOT NULL,
                sector_name TEXT NOT NULL,
                sector_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                PRIMARY KEY (symbol, sector_code, sector_type)
            );
            CREATE TABLE IF NOT EXISTS tradable_themes (
                theme_id TEXT PRIMARY KEY,
                theme_name TEXT NOT NULL,
                theme_type TEXT NOT NULL,
                rule_source TEXT,
                member_count INTEGER NOT NULL DEFAULT 0,
                source_sector_count INTEGER NOT NULL DEFAULT 0,
                generated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tradable_theme_memberships (
                theme_id TEXT NOT NULL,
                theme_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT,
                source_sectors TEXT NOT NULL,
                match_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                generated_at TEXT NOT NULL,
                PRIMARY KEY (theme_id, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_clean_members_symbol ON clean_stock_sector_memberships(symbol);
            CREATE INDEX IF NOT EXISTS idx_theme_members_symbol ON tradable_theme_memberships(symbol);
            """
        )
        conn.commit()


def load_raw(source_db: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not source_db.exists():
        raise FileNotFoundError(str(source_db))
    with sqlite3.connect(str(source_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        boards = [dict(row) for row in conn.execute("SELECT * FROM sector_boards")]
        memberships = [dict(row) for row in conn.execute("SELECT * FROM stock_sector_memberships")]
    return boards, memberships


def build_clean(
    boards: List[Dict[str, Any]],
    memberships: List[Dict[str, Any]],
    clean_rules: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    clean_boards = []
    allowed_keys = set()
    for board in boards:
        name = str(board.get("sector_name") or "")
        excluded = is_excluded(name, clean_rules)
        downrank = is_downranked(name, clean_rules)
        status = "excluded" if excluded else ("downranked" if downrank else "active")
        weight = 0.0 if excluded else (0.5 if downrank else 1.0)
        clean_boards.append({
            "sector_code": board.get("sector_code"),
            "sector_name": name,
            "sector_type": board.get("sector_type"),
            "clean_status": status,
            "clean_reason": status,
            "weight": weight,
            "source": "stock_sector_map",
        })
        if not excluded:
            allowed_keys.add((board.get("sector_code"), board.get("sector_type")))
    clean_memberships = []
    for item in memberships:
        key = (item.get("sector_code"), item.get("sector_type"))
        if key not in allowed_keys:
            continue
        name = str(item.get("sector_name") or "")
        clean_memberships.append({
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "sector_code": item.get("sector_code"),
            "sector_name": name,
            "sector_type": item.get("sector_type"),
            "weight": 0.5 if is_downranked(name, clean_rules) else 1.0,
            "source": "stock_sector_map.clean",
        })
    return clean_boards, clean_memberships


def build_rule_themes(clean_memberships: List[Dict[str, Any]], theme_rules: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_symbol_theme: Dict[Tuple[str, str], Dict[str, Any]] = {}
    theme_defs = []
    themes = theme_rules.get("themes") or []
    for theme in themes:
        theme_id = str(theme["id"])
        theme_name = str(theme["name"])
        include = theme.get("include_keywords") or []
        exclude = theme.get("exclude_keywords") or []
        source_sector_names = set()
        for item in clean_memberships:
            sector_name = str(item.get("sector_name") or "")
            if not keyword_match(sector_name, include):
                continue
            if exclude and keyword_match(sector_name, exclude):
                continue
            key = (theme_id, str(item["symbol"]))
            rec = by_symbol_theme.setdefault(
                key,
                {
                    "theme_id": theme_id,
                    "theme_name": theme_name,
                    "symbol": item["symbol"],
                    "name": item.get("name"),
                    "source_sectors": [],
                    "match_type": "rule",
                    "weight": 0.0,
                },
            )
            rec["source_sectors"].append(sector_name)
            rec["weight"] = max(float(rec["weight"]), float(item.get("weight") or 1.0))
            source_sector_names.add(sector_name)
        theme_defs.append({
            "theme_id": theme_id,
            "theme_name": theme_name,
            "theme_type": "rule",
            "rule_source": ",".join(include),
            "member_count": 0,
            "source_sector_count": len(source_sector_names),
        })
    memberships = list(by_symbol_theme.values())
    counts = defaultdict(int)
    for item in memberships:
        counts[item["theme_id"]] += 1
        item["source_sectors"] = json.dumps(sorted(set(item["source_sectors"])), ensure_ascii=False)
    for theme in theme_defs:
        theme["member_count"] = counts.get(theme["theme_id"], 0)
    return theme_defs, memberships


def build_fallback_industry_themes(
    clean_memberships: List[Dict[str, Any]],
    existing_memberships: List[Dict[str, Any]],
    min_member_count: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    existing = {(m["theme_id"], m["symbol"]) for m in existing_memberships}
    by_sector: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for item in clean_memberships:
        if item.get("sector_type") == "industry":
            by_sector[(str(item["sector_code"]), str(item["sector_name"]))].append(item)
    theme_defs = []
    memberships = []
    for (sector_code, sector_name), items in by_sector.items():
        if len(items) < min_member_count:
            continue
        theme_id = f"industry_{sector_code.lower()}"
        theme_defs.append({
            "theme_id": theme_id,
            "theme_name": sector_name,
            "theme_type": "fallback_industry",
            "rule_source": sector_code,
            "member_count": len(items),
            "source_sector_count": 1,
        })
        for item in items:
            key = (theme_id, item["symbol"])
            if key in existing:
                continue
            memberships.append({
                "theme_id": theme_id,
                "theme_name": sector_name,
                "symbol": item["symbol"],
                "name": item.get("name"),
                "source_sectors": json.dumps([sector_name], ensure_ascii=False),
                "match_type": "fallback_industry",
                "weight": item.get("weight") or 1.0,
            })
    return theme_defs, memberships


def cap_themes_per_stock(memberships: List[Dict[str, Any]], max_themes: int) -> List[Dict[str, Any]]:
    if max_themes <= 0:
        return memberships
    priority = {"rule": 0, "fallback_industry": 1}
    by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in memberships:
        by_symbol[str(item["symbol"])].append(item)
    out = []
    for _, items in by_symbol.items():
        items.sort(key=lambda x: (priority.get(str(x.get("match_type")), 9), -float(x.get("weight") or 0), x["theme_name"]))
        out.extend(items[:max_themes])
    return out


def write_output(
    output_db: Path,
    clean_boards: List[Dict[str, Any]],
    clean_memberships: List[Dict[str, Any]],
    themes: List[Dict[str, Any]],
    theme_memberships: List[Dict[str, Any]],
    generated_at: str,
) -> None:
    init_output_db(output_db)
    with sqlite3.connect(str(output_db), timeout=30) as conn:
        conn.execute("DELETE FROM clean_sector_boards")
        conn.execute("DELETE FROM clean_stock_sector_memberships")
        conn.execute("DELETE FROM tradable_themes")
        conn.execute("DELETE FROM tradable_theme_memberships")
        conn.executemany(
            """
            INSERT OR REPLACE INTO clean_sector_boards
            (sector_code, sector_name, sector_type, clean_status, clean_reason, weight, source, generated_at)
            VALUES (:sector_code, :sector_name, :sector_type, :clean_status, :clean_reason, :weight, :source, :generated_at)
            """,
            [{**x, "generated_at": generated_at} for x in clean_boards],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO clean_stock_sector_memberships
            (symbol, name, sector_code, sector_name, sector_type, weight, source, generated_at)
            VALUES (:symbol, :name, :sector_code, :sector_name, :sector_type, :weight, :source, :generated_at)
            """,
            [{**x, "generated_at": generated_at} for x in clean_memberships],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO tradable_themes
            (theme_id, theme_name, theme_type, rule_source, member_count, source_sector_count, generated_at)
            VALUES (:theme_id, :theme_name, :theme_type, :rule_source, :member_count, :source_sector_count, :generated_at)
            """,
            [{**x, "generated_at": generated_at} for x in themes],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO tradable_theme_memberships
            (theme_id, theme_name, symbol, name, source_sectors, match_type, weight, generated_at)
            VALUES (:theme_id, :theme_name, :symbol, :name, :source_sectors, :match_type, :weight, :generated_at)
            """,
            [{**x, "generated_at": generated_at} for x in theme_memberships],
        )
        conn.commit()


def write_json(output_db: Path, themes: List[Dict[str, Any]], memberships: List[Dict[str, Any]], generated_at: str) -> None:
    ensure_market_heat_dir()
    by_theme = defaultdict(list)
    for item in memberships:
        by_theme[item["theme_id"]].append({
            "symbol": item["symbol"],
            "name": item.get("name"),
            "source_sectors": json.loads(item.get("source_sectors") or "[]"),
            "match_type": item.get("match_type"),
        })
    payload = {
        "meta": {
            "generated_at": generated_at,
            "output_db": str(output_db),
            "theme_count": len(themes),
            "membership_count": len(memberships),
            "stock_count": len({m["symbol"] for m in memberships}),
        },
        "themes": [
            {**theme, "members": by_theme.get(theme["theme_id"], [])[:30]}
            for theme in sorted(themes, key=lambda x: (-int(x.get("member_count") or 0), x["theme_name"]))
        ],
    }
    (MARKET_HEAT_DIR / "tradable_theme_map_latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cleaned tradable theme map from raw stock-sector memberships.")
    parser.add_argument("--source-db", default=str(DEFAULT_SOURCE_DB))
    parser.add_argument("--output-db", default=str(DEFAULT_OUTPUT_DB))
    parser.add_argument("--clean-rules", default=str(DEFAULT_CLEAN_RULES))
    parser.add_argument("--theme-rules", default=str(DEFAULT_THEME_RULES))
    args = parser.parse_args()

    generated_at = datetime.now().isoformat(timespec="seconds")
    clean_rules = load_json(Path(args.clean_rules))
    theme_rules = load_json(Path(args.theme_rules))
    boards, raw_memberships = load_raw(Path(args.source_db))
    clean_boards, clean_memberships = build_clean(boards, raw_memberships, clean_rules)
    rule_themes, rule_memberships = build_rule_themes(clean_memberships, theme_rules)
    fallback_conf = theme_rules.get("fallback") or {}
    fallback_themes, fallback_memberships = ([], [])
    if fallback_conf.get("industry_as_theme", True):
        fallback_themes, fallback_memberships = build_fallback_industry_themes(
            clean_memberships,
            rule_memberships,
            int(fallback_conf.get("min_member_count") or 3),
        )
    all_themes = rule_themes + fallback_themes
    all_memberships = cap_themes_per_stock(rule_memberships + fallback_memberships, int(fallback_conf.get("max_themes_per_stock") or 8))
    # Recount after cap.
    counts = defaultdict(int)
    for item in all_memberships:
        counts[item["theme_id"]] += 1
    for theme in all_themes:
        theme["member_count"] = counts.get(theme["theme_id"], 0)
    all_themes = [t for t in all_themes if int(t.get("member_count") or 0) > 0]

    output_db = Path(args.output_db)
    write_output(output_db, clean_boards, clean_memberships, all_themes, all_memberships, generated_at)
    write_json(output_db, all_themes, all_memberships, generated_at)
    print(f"wrote {output_db}")
    print(f"wrote {MARKET_HEAT_DIR / 'tradable_theme_map_latest.json'}")
    print(
        "summary: "
        f"raw_boards={len(boards)} clean_active_boards={sum(1 for b in clean_boards if b['clean_status'] != 'excluded')} "
        f"clean_memberships={len(clean_memberships)} themes={len(all_themes)} "
        f"theme_memberships={len(all_memberships)} stocks={len({m['symbol'] for m in all_memberships})}"
    )


if __name__ == "__main__":
    main()
