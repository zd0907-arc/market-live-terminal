#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from statistics import mean
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR, ROOT_DIR, candidate_atomic_db_paths
from backend.app.services.market_heat import (
    _load_fine_theme_members_cached,
    _symbol_norm,
    _trade_dates,
    build_market_heat_snapshot,
    ensure_market_heat_dir,
    latest_trade_date,
)
from backend.scripts.analyze_hot_sector_granularity import DEFAULT_FINE_RULES, load_fine_sector_themes, load_json
from backend.scripts.build_fine_theme_heat_daily import lifecycle_for
from backend.app.services import market_heat


DEFAULT_TRADABLE_THEME_DB = Path(os.getenv("TRADABLE_THEME_MAP_DB", os.path.join(DATA_DIR, "market_heat", "tradable_theme_map.db")))
def resolve_default_atomic_db() -> Path:
    explicit = os.getenv("MARKET_HEAT_ATOMIC_DB", "").strip()
    if explicit:
        return Path(explicit)
    for path in candidate_atomic_db_paths():
        candidate = Path(path)
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    compact = Path(DATA_DIR) / "atomic_facts" / "shadow" / "market_atomic_mainboard_compact_current.db"
    if compact.exists() and compact.stat().st_size > 0:
        return compact
    return Path(DATA_DIR) / "atomic_facts" / "market_atomic_mainboard_full_reverse.db"


DEFAULT_ATOMIC_DB = resolve_default_atomic_db()
DEFAULT_OUT_DB = Path(os.getenv("FINE_THEME_HEAT_V2_DB", os.path.join(DATA_DIR, "market_heat", "fine_theme_heat_daily_v2.db")))
DEFAULT_REPORT_DIR = Path(os.getenv("MARKET_HEAT_DIR", os.path.join(DATA_DIR, "market_heat")))


def use_atomic_db(atomic_db: Path) -> None:
    market_heat.ATOMIC_DB = Path(atomic_db)


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


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fine_theme_heat_daily_v2 (
            trade_date TEXT NOT NULL,
            theme_id TEXT NOT NULL,
            theme_name TEXT NOT NULL,
            sector_code TEXT,
            sector_type TEXT NOT NULL,
            member_count INTEGER NOT NULL,
            rank_today INTEGER NOT NULL,
            rank_prev INTEGER,
            rank_delta INTEGER,
            hot_score REAL NOT NULL,
            pct_change REAL,
            return_5d REAL,
            return_10d REAL,
            return_20d REAL,
            up_ratio REAL,
            amount_ratio REAL,
            l2_net_inflow_yi REAL,
            l2_positive_ratio REAL,
            strong_count INTEGER,
            limit_up_count INTEGER,
            touch_limit_up_count INTEGER,
            broken_limit_up_count INTEGER,
            rank_improve_3d REAL,
            rank_improve_5d REAL,
            hot_change_3d REAL,
            hot_change_5d REAL,
            top5_hits_5d INTEGER,
            top10_hits_5d INTEGER,
            top15_hits_5d INTEGER,
            top30_hits_5d INTEGER,
            top5_hits_20d INTEGER,
            top10_hits_20d INTEGER,
            top15_hits_20d INTEGER,
            top30_hits_20d INTEGER,
            best_rank_20d INTEGER,
            out_top30_streak INTEGER,
            today_strong INTEGER NOT NULL DEFAULT 0,
            first_hot INTEGER NOT NULL DEFAULT 0,
            mainline_accel INTEGER NOT NULL DEFAULT 0,
            warming INTEGER NOT NULL DEFAULT 0,
            mainline_continue INTEGER NOT NULL DEFAULT 0,
            fading_watch INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(trade_date, theme_id)
        );
        CREATE INDEX IF NOT EXISTS idx_fine_theme_heat_v2_rank ON fine_theme_heat_daily_v2(trade_date, rank_today);
        CREATE INDEX IF NOT EXISTS idx_fine_theme_heat_v2_theme ON fine_theme_heat_daily_v2(theme_id, trade_date);
        CREATE INDEX IF NOT EXISTS idx_fine_theme_heat_v2_lifecycle ON fine_theme_heat_daily_v2(trade_date, today_strong, first_hot, mainline_accel, warming, mainline_continue, fading_watch);
        """
    )


def build_theme_lookup(theme_meta: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for theme_id, meta in theme_meta.items():
        out[theme_id] = {
            "id": theme_id,
            "name": meta.get("name") or theme_id,
            "sector_type": meta.get("sector_type") or "",
            "sector_code": meta.get("sector_code") or "",
            "symbols": sorted(_symbol_norm(str(s)) for s in (meta.get("symbols") or []) if s),
            "symbol_names": meta.get("symbol_names") or {},
        }
    return out


def _daily_rank_history(dates: Sequence[str], snapshots: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    rank_history: Dict[str, Dict[str, int]] = {}
    for d in dates:
        sectors = sorted(snapshots[d].get("sectors", []), key=lambda x: float(x.get("hot_score") or 0), reverse=True)
        rank_history[d] = {str(item.get("id")): rank for rank, item in enumerate(sectors, 1)}
    return rank_history


def _load_atomic_rows(atomic_db: Path, start_date: str, end_date: str) -> Tuple[List[str], Dict[str, Dict[str, Dict[str, Any]]]]:
    conn = sqlite3.connect(str(atomic_db), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        dates = [
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
        rows_by_symbol: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        for row in conn.execute(
            """
            SELECT symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            FROM atomic_trade_daily
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY symbol, trade_date
            """,
            (start_date, end_date),
        ):
            rows_by_symbol[_symbol_norm(row["symbol"])][str(row["trade_date"])] = {k: row[k] for k in row.keys()}
        return dates, rows_by_symbol
    finally:
        conn.close()


def yday_return(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], date: str) -> Optional[float]:
    if date not in dates:
        return None
    i = dates.index(date)
    if i <= 0:
        return None
    now = safe_float((rows.get(date) or {}).get("close"))
    prev = safe_float((rows.get(dates[i - 1]) or {}).get("close"))
    if now <= 0 or prev <= 0:
        return None
    return (now / prev - 1.0) * 100.0


def return_back(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], date: str, days_back: int) -> Optional[float]:
    if date not in dates:
        return None
    i = dates.index(date)
    j = max(0, i - days_back)
    now = safe_float((rows.get(date) or {}).get("close"))
    base = safe_float((rows.get(dates[j]) or {}).get("close"))
    if now <= 0 or base <= 0:
        return None
    return (now / base - 1.0) * 100.0


def build_theme_member_series(theme: Dict[str, Any], rows_by_symbol: Dict[str, Dict[str, Dict[str, Any]]], dates: Sequence[str], date: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for symbol in theme.get("symbols", []):
        rows = rows_by_symbol.get(symbol, {})
        day = rows.get(date)
        if not day:
            continue
        out.append(
            {
                "symbol": symbol,
                "name": theme.get("symbol_names", {}).get(symbol) or symbol,
                "close": safe_float(day.get("close")),
                "return_1d": yday_return(rows, dates, date),
                "return_3d": return_back(rows, dates, date, 3),
                "return_5d": return_back(rows, dates, date, 5),
                "return_20d": return_back(rows, dates, date, 20),
                "amount_yi": safe_float(day.get("total_amount")) / 1e8,
                "l2_main_net_yi": safe_float(day.get("l2_main_net_amount")) / 1e8,
                "l2_super_net_yi": safe_float(day.get("l2_super_net_amount")) / 1e8,
            }
        )
    return out


def compute_lifecycle(
    theme_id: str,
    dates: Sequence[str],
    rank_history: Dict[str, Dict[str, int]],
    pos: int,
) -> Dict[str, Any]:
    date = dates[pos]
    today_rank = rank_history.get(date, {}).get(theme_id, 9999)
    prev_rank = rank_history.get(dates[pos - 1], {}).get(theme_id) if pos > 0 else None
    recent5 = dates[max(0, pos - 4):pos + 1]
    recent20 = dates[max(0, pos - 19):pos + 1]
    prior20 = dates[max(0, pos - 20):pos]
    rank_values = [rank_history.get(d, {}).get(theme_id, 9999) for d in dates[max(0, pos - 19):pos + 1]]
    prev_rank_values = [rank_history.get(d, {}).get(theme_id, 9999) for d in dates[max(0, pos - 20):pos]]
    rank_delta_1d = (prev_rank - today_rank) if prev_rank else 0
    rank_improve_3d = (sum(prev_rank_values[-3:]) / 3 - today_rank) if len(prev_rank_values) >= 3 else 0.0
    rank_improve_5d = (sum(prev_rank_values[-5:]) / 5 - today_rank) if len(prev_rank_values) >= 5 else 0.0
    today_slice = [rank_history.get(date, {}).get(theme_id, 9999)]
    hot_change_3d = 0.0
    hot_change_5d = 0.0
    top5_hits_5d = sum(1 for d in recent5 if rank_history.get(d, {}).get(theme_id, 9999) <= 5)
    top10_hits_5d = sum(1 for d in recent5 if rank_history.get(d, {}).get(theme_id, 9999) <= 10)
    top15_hits_5d = sum(1 for d in recent5 if rank_history.get(d, {}).get(theme_id, 9999) <= 15)
    top30_hits_5d = sum(1 for d in recent5 if rank_history.get(d, {}).get(theme_id, 9999) <= 30)
    top5_hits_20d = sum(1 for d in recent20 if rank_history.get(d, {}).get(theme_id, 9999) <= 5)
    top10_hits_20d = sum(1 for d in recent20 if rank_history.get(d, {}).get(theme_id, 9999) <= 10)
    top15_hits_20d = sum(1 for d in recent20 if rank_history.get(d, {}).get(theme_id, 9999) <= 15)
    top30_hits_20d = sum(1 for d in recent20 if rank_history.get(d, {}).get(theme_id, 9999) <= 30)
    best_rank_20d = min(rank_values) if rank_values else today_rank
    out_top30_streak = 0
    for d in reversed(dates[: pos + 1]):
        if rank_history.get(d, {}).get(theme_id, 9999) > 30:
            out_top30_streak += 1
        else:
            break

    first_hot_band = 15
    today_strong = int(today_rank <= 5)
    first_hot = int(
        today_rank <= first_hot_band
        and sum(1 for d in prior20 if rank_history.get(d, {}).get(theme_id, 9999) <= 15) <= 1
        and sum(1 for d in prior20 if rank_history.get(d, {}).get(theme_id, 9999) <= 5) == 0
        and (rank_delta_1d >= 10 or rank_improve_5d >= 10)
    )
    mainline_accel = int(today_rank <= 10 and (top15_hits_20d >= 3 or top30_hits_20d >= 6 or top5_hits_20d >= 2))
    warming = int(today_rank > 5 and today_rank <= 30 and not mainline_accel and (rank_improve_3d >= 10 or rank_improve_5d >= 15))
    mainline_continue = int(today_rank <= 30 and (top30_hits_20d >= 5 or top15_hits_20d >= 3 or top5_hits_20d >= 2))
    fading_watch = int(
        today_rank > 30
        and (sum(1 for d in prior20 if rank_history.get(d, {}).get(theme_id, 9999) <= 30) >= 3)
        and ((prev_rank is not None and prev_rank <= 30 and prev_rank - today_rank >= -20) or best_rank_20d <= 10 or out_top30_streak <= 3)
    )
    return {
        "rank_today": today_rank,
        "rank_delta_1d": rank_delta_1d,
        "rank_improve_3d": rank_improve_3d,
        "rank_improve_5d": rank_improve_5d,
        "hot_change_3d": hot_change_3d,
        "hot_change_5d": hot_change_5d,
        "top5_hits_5d": top5_hits_5d,
        "top10_hits_5d": top10_hits_5d,
        "top15_hits_5d": top15_hits_5d,
        "top30_hits_5d": top30_hits_5d,
        "top5_hits_20d": top5_hits_20d,
        "top10_hits_20d": top10_hits_20d,
        "top15_hits_20d": top15_hits_20d,
        "top30_hits_20d": top30_hits_20d,
        "best_rank_20d": best_rank_20d,
        "out_top30_streak": out_top30_streak,
        "today_strong": today_strong,
        "first_hot": first_hot,
        "mainline_accel": mainline_accel,
        "warming": warming,
        "mainline_continue": mainline_continue,
        "fading_watch": fading_watch,
    }


def rebuild(end_date: str, days: int, force: bool) -> Dict[str, Any]:
    ensure_market_heat_dir()
    use_atomic_db(DEFAULT_ATOMIC_DB)
    theme_meta = _load_fine_theme_members_cached()
    themes = build_theme_lookup(theme_meta)
    if not themes:
        raise RuntimeError("细颗粒主题池为空")

    dates = _trade_dates(end_date, max(30, days))
    if not dates:
        raise RuntimeError("没有交易日")
    latest = dates[-1]
    if latest != end_date:
        raise RuntimeError(f"最新交易日不匹配，期望 {end_date}，实际 {latest}")

    theme_defs = []
    for theme_id, meta in sorted(theme_meta.items(), key=lambda kv: (str(kv[1].get("sector_type") or ""), str(kv[1].get("name") or ""))):
        symbols = sorted(_symbol_norm(str(symbol)) for symbol in (meta.get("symbols") or []) if symbol)
        theme_defs.append({
            "id": theme_id,
            "name": meta.get("name") or theme_id,
            "type": f"fine_{meta.get('sector_type') or 'theme'}",
            "sector_type": meta.get("sector_type") or "",
            "sector_code": meta.get("sector_code") or "",
            "symbols": [{"symbol": symbol, "name": (meta.get("symbol_names") or {}).get(symbol) or symbol} for symbol in symbols],
        })
    snapshots: Dict[str, Dict[str, Any]] = {}
    for i, d in enumerate(dates, 1):
        snap = build_market_heat_snapshot(d, themes_override=theme_defs)
        sectors = sorted(snap.get("sectors", []), key=lambda x: safe_float(x.get("hot_score")), reverse=True)
        snapshots[d] = snap
        if i % 10 == 0 or d == end_date:
            print(f"[fine-v2] {i}/{len(dates)} {d}", flush=True)
    rank_history = _daily_rank_history(dates, snapshots)
    hot_score_history: Dict[str, Dict[str, float]] = defaultdict(dict)
    for d in dates:
        for sector in snapshots[d].get("sectors", []):
            hot_score_history[str(sector.get("id"))][d] = safe_float(sector.get("hot_score"))

    out_db = DEFAULT_OUT_DB
    if out_db.exists() and force:
        out_db.unlink()
    conn = sqlite3.connect(str(out_db), timeout=60)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM fine_theme_heat_daily_v2 WHERE trade_date BETWEEN ? AND ?", (dates[0], end_date))
        for pos, d in enumerate(dates):
            snap = snapshots[d]
            sectors = sorted(snap.get("sectors", []), key=lambda x: safe_float(x.get("hot_score")), reverse=True)
            for sector in sectors:
                theme_id = str(sector.get("id"))
                if theme_id not in themes:
                    continue
                lc = compute_lifecycle(theme_id, dates, rank_history, pos)
                prev3_dates = dates[max(0, pos - 3):pos]
                prev5_dates = dates[max(0, pos - 5):pos]
                prev3_hot = [hot_score_history.get(theme_id, {}).get(d) for d in prev3_dates if hot_score_history.get(theme_id, {}).get(d) is not None]
                prev5_hot = [hot_score_history.get(theme_id, {}).get(d) for d in prev5_dates if hot_score_history.get(theme_id, {}).get(d) is not None]
                hot_change_3d = 0.0
                hot_change_5d = 0.0
                if prev3_hot:
                    hot_change_3d = safe_float(sector.get("hot_score")) - mean(prev3_hot)
                if prev5_hot:
                    hot_change_5d = safe_float(sector.get("hot_score")) - mean(prev5_hot)
                rank_prev = rank_history.get(dates[pos - 1], {}).get(theme_id) if pos > 0 else None
                sector_code = themes[theme_id].get("sector_code")
                sector_type = themes[theme_id].get("sector_type") or sector.get("sector_type") or "concept"
                theme_name = sector.get("name") or themes[theme_id].get("name") or theme_id
                placeholders = ",".join("?" for _ in range(42))
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fine_theme_heat_daily_v2 (
                      trade_date, theme_id, theme_name, sector_code, sector_type, member_count,
                      rank_today, rank_prev, rank_delta, hot_score, pct_change, return_5d, return_10d, return_20d,
                      up_ratio, amount_ratio, l2_net_inflow_yi, l2_positive_ratio, strong_count,
                      limit_up_count, touch_limit_up_count, broken_limit_up_count,
                      rank_improve_3d, rank_improve_5d, hot_change_3d, hot_change_5d,
                      top5_hits_5d, top10_hits_5d, top15_hits_5d, top30_hits_5d,
                      top5_hits_20d, top10_hits_20d, top15_hits_20d, top30_hits_20d,
                      best_rank_20d, out_top30_streak,
                      today_strong, first_hot, mainline_accel, warming, mainline_continue, fading_watch
                    ) VALUES ({placeholders})
                    """.format(placeholders=placeholders),
                    (
                        d, theme_id, theme_name, sector_code, sector_type, int(sector.get("member_count") or 0),
                        lc["rank_today"], rank_prev, lc["rank_delta_1d"], safe_float(sector.get("hot_score")), safe_float(sector.get("pct_change")),
                        safe_float(sector.get("return_5d")), safe_float(sector.get("return_10d")), safe_float(sector.get("return_20d")),
                        safe_float(sector.get("up_ratio")), safe_float(sector.get("amount_ratio")), safe_float(sector.get("l2_net_inflow_yi")),
                        safe_float(sector.get("l2_positive_ratio")), int(sector.get("big_up_count") or 0),
                        int(sector.get("limit_up_count") or 0), int(sector.get("touch_limit_up_count") or 0), int(sector.get("broken_limit_up_count") or 0),
                        lc["rank_improve_3d"], lc["rank_improve_5d"], hot_change_3d, hot_change_5d,
                        lc["top5_hits_5d"], lc["top10_hits_5d"], lc["top15_hits_5d"], lc["top30_hits_5d"],
                        lc["top5_hits_20d"], lc["top10_hits_20d"], lc["top15_hits_20d"], lc["top30_hits_20d"],
                        lc["best_rank_20d"], lc["out_top30_streak"],
                        lc["today_strong"], lc["first_hot"], lc["mainline_accel"], lc["warming"], lc["mainline_continue"], lc["fading_watch"],
                    ),
                )
        conn.commit()
    finally:
        conn.close()

    return {
        "out_db": str(out_db),
        "start_date": dates[0],
        "end_date": dates[-1],
        "days": len(dates),
        "themes": len(themes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild unified fine theme heat v2 table.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=325)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    end_date = args.end_date or latest_trade_date()
    if not end_date:
        raise RuntimeError("无法确定最新交易日")
    result = rebuild(end_date=end_date, days=args.days, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
