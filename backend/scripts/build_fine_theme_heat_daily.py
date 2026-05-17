#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR, ROOT_DIR, candidate_atomic_db_paths
from backend.app.services import market_heat
from backend.app.services.market_heat import _symbol_norm, _trade_dates, build_market_heat_snapshot, ensure_market_heat_dir
from backend.scripts.analyze_hot_sector_granularity import DEFAULT_FINE_RULES, load_fine_sector_themes, load_json


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
DEFAULT_OUT_DB = Path(os.getenv("FINE_THEME_HEAT_DB", os.path.join(DATA_DIR, "market_heat", "fine_theme_heat_daily.db")))
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


def pct(now: float, base: float) -> Optional[float]:
    if base <= 0:
        return None
    return (now / base - 1.0) * 100.0


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fine_theme_heat_daily (
            trade_date TEXT NOT NULL,
            theme_id TEXT NOT NULL,
            sector_code TEXT,
            sector_name TEXT NOT NULL,
            sector_type TEXT NOT NULL,
            member_count INTEGER NOT NULL,
            hot_rank INTEGER,
            persistence_rank INTEGER,
            hot_score REAL,
            persistence_score REAL,
            avg_return_1d REAL,
            avg_return_5d REAL,
            avg_return_10d REAL,
            avg_return_20d REAL,
            up_ratio REAL,
            strong_count INTEGER,
            limit_up_count INTEGER,
            amount_yi REAL,
            amount_ratio REAL,
            l2_main_net_yi REAL,
            l2_positive_ratio REAL,
            leader_symbol TEXT,
            leader_name TEXT,
            leader_return_1d REAL,
            leader_strength REAL,
            leader_concentration REAL,
            risk_tags_json TEXT,
            readout TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(trade_date, theme_id)
        );

        CREATE TABLE IF NOT EXISTS fine_theme_lifecycle_daily (
            trade_date TEXT NOT NULL,
            theme_id TEXT NOT NULL,
            sector_name TEXT NOT NULL,
            hot_rank INTEGER,
            days_in_top15_5d INTEGER NOT NULL DEFAULT 0,
            days_in_top30_10d INTEGER NOT NULL DEFAULT 0,
            lifecycle_state TEXT NOT NULL,
            is_new_hot INTEGER NOT NULL DEFAULT 0,
            is_continuing_hot INTEGER NOT NULL DEFAULT 0,
            is_climax_hot INTEGER NOT NULL DEFAULT 0,
            is_fading INTEGER NOT NULL DEFAULT 0,
            is_one_day_spike INTEGER NOT NULL DEFAULT 0,
            is_leader_only INTEGER NOT NULL DEFAULT 0,
            is_broad_hot INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(trade_date, theme_id)
        );

        CREATE TABLE IF NOT EXISTS fine_theme_member_daily (
            trade_date TEXT NOT NULL,
            theme_id TEXT NOT NULL,
            sector_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT,
            close REAL,
            return_1d REAL,
            return_3d REAL,
            return_5d REAL,
            return_20d REAL,
            amount_yi REAL,
            amount_ratio_20d REAL,
            l2_main_net_yi REAL,
            l2_super_net_yi REAL,
            price_position_20d REAL,
            dist_ma60_pct REAL,
            role TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(trade_date, theme_id, symbol)
        );

        CREATE TABLE IF NOT EXISTS fine_theme_forward_return (
            trade_date TEXT NOT NULL,
            theme_id TEXT NOT NULL,
            sector_name TEXT NOT NULL,
            hot_rank INTEGER,
            lifecycle_state TEXT,
            forward_3d_avg_return REAL,
            forward_5d_avg_return REAL,
            forward_10d_avg_return REAL,
            forward_3d_win_rate REAL,
            forward_5d_win_rate REAL,
            forward_10d_win_rate REAL,
            future_top15_days_5d INTEGER,
            future_top15_days_10d INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(trade_date, theme_id)
        );

        CREATE INDEX IF NOT EXISTS idx_fine_theme_heat_rank ON fine_theme_heat_daily(trade_date, hot_rank);
        CREATE INDEX IF NOT EXISTS idx_fine_theme_lifecycle_state ON fine_theme_lifecycle_daily(trade_date, lifecycle_state);
        CREATE INDEX IF NOT EXISTS idx_fine_theme_member_symbol ON fine_theme_member_daily(symbol, trade_date);
        """
    )


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def load_atomic_rows(atomic_db: Path, start_date: str, end_date: str) -> Tuple[List[str], Dict[str, Dict[str, Dict[str, Any]]]]:
    uri = f"file:{atomic_db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
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
            rows_by_symbol[_symbol_norm(row["symbol"])][str(row["trade_date"])] = row_to_dict(row)
        return dates, rows_by_symbol
    finally:
        conn.close()


def value_on(rows: Dict[str, Dict[str, Any]], date: str, field: str) -> float:
    return safe_float((rows.get(date) or {}).get(field))


def return_between(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], date: str, days_back: int) -> Optional[float]:
    if date not in dates:
        return None
    i = dates.index(date)
    j = max(0, i - days_back)
    now = value_on(rows, dates[i], "close")
    base = value_on(rows, dates[j], "close")
    return pct(now, base) if now > 0 and base > 0 else None


def daily_return(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], date: str) -> Optional[float]:
    if date not in dates:
        return None
    i = dates.index(date)
    now = value_on(rows, date, "close")
    if i <= 0:
        base = value_on(rows, date, "open")
    else:
        base = value_on(rows, dates[i - 1], "close")
    return pct(now, base) if now > 0 and base > 0 else None


def amount_ratio(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], date: str) -> Optional[float]:
    if date not in dates:
        return None
    i = dates.index(date)
    now = value_on(rows, date, "total_amount")
    prior = [
        value_on(rows, d, "total_amount")
        for d in dates[max(0, i - 20):i]
        if value_on(rows, d, "total_amount") > 0
    ]
    if now <= 0 or not prior:
        return None
    return now / (sum(prior) / len(prior))


def price_position_20d(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], date: str) -> Optional[float]:
    if date not in dates:
        return None
    i = dates.index(date)
    closes = [value_on(rows, d, "close") for d in dates[max(0, i - 19):i + 1] if value_on(rows, d, "close") > 0]
    close = value_on(rows, date, "close")
    if len(closes) < 5 or close <= 0:
        return None
    lo, hi = min(closes), max(closes)
    return 0.5 if hi == lo else (close - lo) / (hi - lo)


def dist_ma(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], date: str, n: int = 60) -> Optional[float]:
    if date not in dates:
        return None
    i = dates.index(date)
    closes = [value_on(rows, d, "close") for d in dates[max(0, i - n + 1):i + 1] if value_on(rows, d, "close") > 0]
    close = value_on(rows, date, "close")
    if len(closes) < max(10, n // 2) or close <= 0:
        return None
    ma = sum(closes) / len(closes)
    return pct(close, ma)


def forward_avg_return(
    theme_id: str,
    theme_members: Dict[str, set],
    rows_by_symbol: Dict[str, Dict[str, Dict[str, Any]]],
    dates: Sequence[str],
    date: str,
    horizon: int,
) -> Tuple[Optional[float], Optional[float]]:
    if date not in dates:
        return None, None
    i = dates.index(date)
    if i + horizon >= len(dates) or i + 1 >= len(dates):
        return None, None
    entry_date = dates[i + 1]
    exit_date = dates[i + horizon]
    vals: List[float] = []
    for symbol in theme_members.get(theme_id, set()):
        rows = rows_by_symbol.get(symbol, {})
        entry = value_on(rows, entry_date, "open")
        exit_close = value_on(rows, exit_date, "close")
        if entry > 0 and exit_close > 0:
            vals.append((exit_close / entry - 1.0) * 100.0)
    if not vals:
        return None, None
    return statistics.fmean(vals), sum(1 for v in vals if v > 0) / len(vals) * 100.0


def theme_member_rows(
    theme: Dict[str, Any],
    rows_by_symbol: Dict[str, Dict[str, Dict[str, Any]]],
    dates: Sequence[str],
    date: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for member in theme.get("symbols", []):
        symbol = _symbol_norm(member.get("symbol"))
        rows = rows_by_symbol.get(symbol, {})
        day = rows.get(date)
        if not day:
            continue
        r1 = daily_return(rows, dates, date)
        r3 = return_between(rows, dates, date, 3)
        r5 = return_between(rows, dates, date, 5)
        r20 = return_between(rows, dates, date, 20)
        out.append({
            "symbol": symbol,
            "name": member.get("name") or symbol,
            "close": safe_float(day.get("close")),
            "return_1d": r1,
            "return_3d": r3,
            "return_5d": r5,
            "return_20d": r20,
            "amount_yi": safe_float(day.get("total_amount")) / 1e8,
            "amount_ratio_20d": amount_ratio(rows, dates, date),
            "l2_main_net_yi": safe_float(day.get("l2_main_net_amount")) / 1e8,
            "l2_super_net_yi": safe_float(day.get("l2_super_net_amount")) / 1e8,
            "price_position_20d": price_position_20d(rows, dates, date),
            "dist_ma60_pct": dist_ma(rows, dates, date, 60),
        })
    if not out:
        return []
    leader_symbol = max(out, key=lambda x: (safe_float(x.get("return_1d")), safe_float(x.get("amount_yi"))))["symbol"]
    volume_symbol = max(out, key=lambda x: safe_float(x.get("amount_yi")))["symbol"]
    low_candidates = sorted(
        [x for x in out if safe_float(x.get("price_position_20d"), 1.0) <= 0.8 and safe_float(x.get("l2_main_net_yi")) > 0],
        key=lambda x: (safe_float(x.get("l2_main_net_yi")), -safe_float(x.get("price_position_20d"), 1.0)),
        reverse=True,
    )
    low_symbol = low_candidates[0]["symbol"] if low_candidates else None
    for item in out:
        role = "member"
        if item["symbol"] == leader_symbol:
            role = "leader"
        if item["symbol"] == volume_symbol:
            role = "volume_core" if role == "member" else f"{role},volume_core"
        if item["symbol"] == low_symbol:
            role = "low_position_candidate" if role == "member" else f"{role},low_position_candidate"
        item["role"] = role
    return out


def lifecycle_for(
    theme_id: str,
    date: str,
    hot_rank_by_date: Dict[str, Dict[str, int]],
    dates: Sequence[str],
) -> Dict[str, Any]:
    i = dates.index(date)
    last5 = dates[max(0, i - 4):i + 1]
    last10 = dates[max(0, i - 9):i + 1]
    hits15 = sum(1 for d in last5 if hot_rank_by_date.get(d, {}).get(theme_id, 9999) <= 15)
    hits30 = sum(1 for d in last10 if hot_rank_by_date.get(d, {}).get(theme_id, 9999) <= 30)
    today_rank = hot_rank_by_date.get(date, {}).get(theme_id)
    yesterday_rank = hot_rank_by_date.get(dates[i - 1], {}).get(theme_id) if i > 0 else None
    is_fading = bool(yesterday_rank and yesterday_rank <= 15 and (today_rank is None or today_rank > 30))
    if today_rank and today_rank <= 15:
        if hits15 <= 1:
            state = "new_hot"
        elif hits15 <= 3:
            state = "continuing_hot"
        else:
            state = "climax_hot"
    elif is_fading:
        state = "fading"
    else:
        state = "normal"
    return {
        "hot_rank": today_rank,
        "days_in_top15_5d": hits15,
        "days_in_top30_10d": hits30,
        "lifecycle_state": state,
        "is_new_hot": int(state == "new_hot"),
        "is_continuing_hot": int(state == "continuing_hot"),
        "is_climax_hot": int(state == "climax_hot"),
        "is_fading": int(state == "fading"),
    }


def render_report(out_db: Path, report_path: Path, start_date: str, end_date: str) -> None:
    conn = sqlite3.connect(str(out_db))
    conn.row_factory = sqlite3.Row
    try:
        top_bull = conn.execute(
            """
            SELECT sector_name, COUNT(*) AS days, MIN(hot_rank) AS best_rank,
                   AVG(hot_score) AS avg_hot, AVG(avg_return_1d) AS avg_ret,
                   SUM(CASE WHEN hot_rank<=15 THEN 1 ELSE 0 END) AS top15_days
            FROM fine_theme_heat_daily
            WHERE trade_date BETWEEN ? AND ? AND hot_rank<=15
            GROUP BY theme_id
            ORDER BY top15_days DESC, avg_hot DESC
            LIMIT 30
            """,
            (start_date, end_date),
        ).fetchall()
        lifecycle = conn.execute(
            """
            SELECT lifecycle_state, COUNT(*) AS n
            FROM fine_theme_lifecycle_daily
            WHERE trade_date BETWEEN ? AND ? AND hot_rank<=15
            GROUP BY lifecycle_state
            ORDER BY n DESC
            """,
            (start_date, end_date),
        ).fetchall()
        wire = conn.execute(
            """
            SELECT h.trade_date, h.hot_rank, h.sector_name, h.hot_score, l.lifecycle_state,
                   h.avg_return_1d, h.avg_return_5d, h.leader_name, h.leader_return_1d
            FROM fine_theme_heat_daily h
            LEFT JOIN fine_theme_lifecycle_daily l
              ON l.trade_date=h.trade_date AND l.theme_id=h.theme_id
            WHERE h.sector_name IN ('通信线缆及配套','CPO概念','光通信模块','光纤概念')
              AND h.trade_date BETWEEN ? AND ?
              AND h.hot_rank<=30
            ORDER BY h.trade_date, h.hot_rank
            """,
            (start_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    lines = [
        f"# 小颗粒热点日表回补 {start_date} ~ {end_date}",
        "",
        f"- 数据库：`{out_db}`",
        "- 口径：清洗后小颗粒行业/概念，成员数 5~80。",
        "- 热度表与牛市水位表分开存储，使用时再关联。",
        "",
        "## Top15 上榜天数最多的小颗粒热点",
        "",
        "| 排名 | 小主题 | Top15天数 | 最好名次 | 平均热度 | 当日均涨 |",
        "| ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(top_bull, 1):
        lines.append(f"| {idx} | {row['sector_name']} | {row['top15_days']} | {row['best_rank']} | {safe_float(row['avg_hot']):.1f} | {safe_float(row['avg_ret']):.2f}% |")
    lines += ["", "## 生命周期分布", "", "| 状态 | 数量 |", "| --- | ---: |"]
    for row in lifecycle:
        lines.append(f"| {row['lifecycle_state']} | {row['n']} |")
    lines += ["", "## 光通信链核验样本（Top30内）", "", "| 日期 | 排名 | 小主题 | 热度 | 阶段 | 当日涨幅 | 5日涨幅 | 代表票 | 代表票涨幅 |", "| --- | ---: | --- | ---: | --- | ---: | ---: | --- | ---: |"]
    for row in wire[:160]:
        lines.append(
            f"| {row['trade_date']} | {row['hot_rank']} | {row['sector_name']} | {safe_float(row['hot_score']):.1f} | "
            f"{row['lifecycle_state'] or ''} | {safe_float(row['avg_return_1d']):.2f}% | {safe_float(row['avg_return_5d']):.2f}% | "
            f"{row['leader_name'] or ''} | {safe_float(row['leader_return_1d']):.2f}% |"
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill fine-grained daily hot theme tables.")
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default="2026-04-30")
    parser.add_argument("--warmup-days", type=int, default=80)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--min-members", type=int, default=5)
    parser.add_argument("--max-members", type=int, default=80)
    parser.add_argument("--rules", type=Path, default=Path(DEFAULT_FINE_RULES))
    parser.add_argument("--theme-db", type=Path, default=DEFAULT_TRADABLE_THEME_DB)
    parser.add_argument("--atomic-db", type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument("--out-db", type=Path, default=DEFAULT_OUT_DB)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    use_atomic_db(args.atomic_db)

    rules = load_json(args.rules)
    themes, theme_members, _, _ = load_fine_sector_themes(args.theme_db, rules, args.min_members, args.max_members)
    if not themes:
        raise RuntimeError("no fine themes loaded")
    all_dates = _trade_dates(args.end_date, 500)
    analysis_dates = [d for d in all_dates if args.start_date <= d <= args.end_date]
    if not analysis_dates:
        raise RuntimeError("no analysis trade dates")
    warmup_start_index = max(0, all_dates.index(analysis_dates[0]) - args.warmup_days)
    calc_dates = [d for d in all_dates[warmup_start_index:] if d <= analysis_dates[-1]]
    # Forward returns need a few future rows if present.
    atomic_dates, rows_by_symbol = load_atomic_rows(args.atomic_db, calc_dates[0], all_dates[min(len(all_dates) - 1, all_dates.index(analysis_dates[-1]) + 12)])

    snapshots: Dict[str, Dict[str, Any]] = {}
    hot_rank_by_date: Dict[str, Dict[str, int]] = {}
    for idx, trade_date in enumerate(calc_dates, 1):
        snapshot = build_market_heat_snapshot(trade_date, themes_override=themes)
        snapshots[trade_date] = snapshot
        hot_rank_by_date[trade_date] = {
            str(item.get("id")): rank
            for rank, item in enumerate(sorted(snapshot.get("sectors", []), key=lambda x: safe_float(x.get("hot_score")), reverse=True), 1)
        }
        if idx % 10 == 0 or trade_date in analysis_dates:
            print(f"[fine-heat] {idx}/{len(calc_dates)} {trade_date}", flush=True)

    args.out_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(args.out_db), timeout=30)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM fine_theme_heat_daily WHERE trade_date BETWEEN ? AND ?", (analysis_dates[0], analysis_dates[-1]))
        conn.execute("DELETE FROM fine_theme_lifecycle_daily WHERE trade_date BETWEEN ? AND ?", (analysis_dates[0], analysis_dates[-1]))
        conn.execute("DELETE FROM fine_theme_member_daily WHERE trade_date BETWEEN ? AND ?", (analysis_dates[0], analysis_dates[-1]))
        conn.execute("DELETE FROM fine_theme_forward_return WHERE trade_date BETWEEN ? AND ?", (analysis_dates[0], analysis_dates[-1]))
        for trade_date in analysis_dates:
            sectors = sorted(snapshots[trade_date].get("sectors", []), key=lambda x: safe_float(x.get("hot_score")), reverse=True)
            persistence_sorted = sorted(snapshots[trade_date].get("sectors", []), key=lambda x: safe_float(x.get("persistence_score")), reverse=True)
            persistence_rank = {str(item.get("id")): idx for idx, item in enumerate(persistence_sorted, 1)}
            sectors_by_id = {str(x.get("id")): x for x in sectors}
            theme_by_id = {str(x.get("id")): x for x in themes}
            for rank, sector in enumerate(sectors, 1):
                theme_id = str(sector.get("id"))
                if rank > args.top_k:
                    continue
                leader = (sector.get("stocks") or [{}])[0]
                stocks = sector.get("stocks") or []
                total_amount = sum(safe_float(x.get("amount")) for x in stocks)
                leader_amount = safe_float(leader.get("amount"))
                leader_conc = leader_amount / total_amount * 100 if total_amount > 0 else None
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fine_theme_heat_daily (
                      trade_date, theme_id, sector_code, sector_name, sector_type, member_count,
                      hot_rank, persistence_rank, hot_score, persistence_score,
                      avg_return_1d, avg_return_5d, avg_return_10d, avg_return_20d,
                      up_ratio, strong_count, limit_up_count, amount_yi, amount_ratio,
                      l2_main_net_yi, l2_positive_ratio, leader_symbol, leader_name,
                      leader_return_1d, leader_strength, leader_concentration, risk_tags_json, readout
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        trade_date, theme_id, sector.get("sector_code"), sector.get("name"), sector.get("sector_type") or sector.get("type"),
                        int(sector.get("member_count") or 0), rank, persistence_rank.get(theme_id), sector.get("hot_score"), sector.get("persistence_score"),
                        sector.get("pct_change"), sector.get("return_5d"), sector.get("return_10d"), sector.get("return_20d"),
                        sector.get("up_ratio"), sector.get("big_up_count"), sector.get("limit_up_count"), sector.get("amount_yi"), sector.get("amount_ratio"),
                        sector.get("l2_net_inflow_yi"), sector.get("l2_positive_ratio"), leader.get("symbol"), leader.get("name"),
                        leader.get("pct_change"), leader.get("strength"), leader_conc, json.dumps(sector.get("risk_tags") or [], ensure_ascii=False), sector.get("readout"),
                    ),
                )
                lc = lifecycle_for(theme_id, trade_date, hot_rank_by_date, calc_dates)
                risk_tags = set(sector.get("risk_tags") or [])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fine_theme_lifecycle_daily (
                      trade_date, theme_id, sector_name, hot_rank, days_in_top15_5d, days_in_top30_10d,
                      lifecycle_state, is_new_hot, is_continuing_hot, is_climax_hot, is_fading,
                      is_one_day_spike, is_leader_only, is_broad_hot
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        trade_date, theme_id, sector.get("name"), rank, lc["days_in_top15_5d"], lc["days_in_top30_10d"],
                        lc["lifecycle_state"], lc["is_new_hot"], lc["is_continuing_hot"], lc["is_climax_hot"], lc["is_fading"],
                        int("one_day_spike" in risk_tags), int("leader_only" in risk_tags),
                        int(safe_float(sector.get("up_ratio")) >= 60 and safe_float(leader.get("pct_change")) >= 5),
                    ),
                )
                f3, w3 = forward_avg_return(theme_id, theme_members, rows_by_symbol, atomic_dates, trade_date, 3)
                f5, w5 = forward_avg_return(theme_id, theme_members, rows_by_symbol, atomic_dates, trade_date, 5)
                f10, w10 = forward_avg_return(theme_id, theme_members, rows_by_symbol, atomic_dates, trade_date, 10)
                i = calc_dates.index(trade_date)
                future5 = calc_dates[i + 1:i + 6]
                future10 = calc_dates[i + 1:i + 11]
                fut5_hits = sum(1 for d in future5 if hot_rank_by_date.get(d, {}).get(theme_id, 9999) <= 15)
                fut10_hits = sum(1 for d in future10 if hot_rank_by_date.get(d, {}).get(theme_id, 9999) <= 15)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fine_theme_forward_return (
                      trade_date, theme_id, sector_name, hot_rank, lifecycle_state,
                      forward_3d_avg_return, forward_5d_avg_return, forward_10d_avg_return,
                      forward_3d_win_rate, forward_5d_win_rate, forward_10d_win_rate,
                      future_top15_days_5d, future_top15_days_10d
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (trade_date, theme_id, sector.get("name"), rank, lc["lifecycle_state"], f3, f5, f10, w3, w5, w10, fut5_hits, fut10_hits),
                )
                if rank <= 15:
                    theme = theme_by_id.get(theme_id)
                    if theme:
                        for member in theme_member_rows(theme, rows_by_symbol, atomic_dates, trade_date):
                            conn.execute(
                                """
                                INSERT OR REPLACE INTO fine_theme_member_daily (
                                  trade_date, theme_id, sector_name, symbol, name, close, return_1d, return_3d,
                                  return_5d, return_20d, amount_yi, amount_ratio_20d, l2_main_net_yi,
                                  l2_super_net_yi, price_position_20d, dist_ma60_pct, role
                                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                """,
                                (
                                    trade_date, theme_id, sector.get("name"), member["symbol"], member["name"], member["close"], member["return_1d"],
                                    member["return_3d"], member["return_5d"], member["return_20d"], member["amount_yi"], member["amount_ratio_20d"],
                                    member["l2_main_net_yi"], member["l2_super_net_yi"], member["price_position_20d"], member["dist_ma60_pct"], member["role"],
                                ),
                            )
        conn.commit()
    finally:
        conn.close()

    report = args.report or (DEFAULT_REPORT_DIR / f"fine_theme_heat_daily_{analysis_dates[0]}_{analysis_dates[-1]}.md")
    render_report(args.out_db, report, analysis_dates[0], analysis_dates[-1])
    print(json.dumps({
        "out_db": str(args.out_db),
        "report": str(report),
        "themes": len(themes),
        "start_date": analysis_dates[0],
        "end_date": analysis_dates[-1],
        "days": len(analysis_dates),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
