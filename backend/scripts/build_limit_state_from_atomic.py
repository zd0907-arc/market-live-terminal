#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATOMIC_DB = REPO_ROOT / "data" / "atomic_facts" / "market_atomic.db"
LIMIT_STATE_SCHEMA = REPO_ROOT / "backend" / "scripts" / "sql" / "limit_state_schema.sql"

DEFAULT_RULES = [
    ("sh_main", "normal", 0.10, 0.01, "2000-01-01", None, "SSE main board default"),
    ("sz_main", "normal", 0.10, 0.01, "2000-01-01", None, "SZSE main board default"),
    ("gem", "normal", 0.20, 0.01, "2020-08-24", None, "ChiNext registration-era default"),
    ("star", "normal", 0.20, 0.01, "2019-07-22", None, "STAR board default"),
    ("bse", "normal", 0.30, 0.01, "2021-11-15", None, "BSE default"),
    ("sh_main", "st", 0.05, 0.01, "2000-01-01", None, "SSE ST default"),
    ("sz_main", "st", 0.05, 0.01, "2000-01-01", None, "SZSE ST default"),
]


@dataclass(frozen=True)
class LimitRule:
    board_type: str
    risk_flag_type: str
    limit_pct: float
    tick_size: float
    effective_from: str
    effective_to: Optional[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build atomic limit state tables from atomic trade tables.")
    parser.add_argument("--atomic-db", type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument("--symbols", default="", help="Comma-separated symbols")
    parser.add_argument("--date-from", default="", help="Optional inclusive YYYY-MM-DD")
    parser.add_argument("--date-to", default="", help="Optional inclusive YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(LIMIT_STATE_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


def ensure_default_rules(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO cfg_limit_rule_map (
            board_type, risk_flag_type, limit_pct, tick_size, effective_from, effective_to, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        DEFAULT_RULES,
    )
    conn.commit()


def detect_board_type(symbol: str) -> str:
    s = (symbol or "").lower()
    if s.startswith("sh688"):
        return "star"
    if s.startswith("sz300"):
        return "gem"
    if s.startswith("bj"):
        return "bse"
    if s.startswith("sh"):
        return "sh_main"
    return "sz_main"


def load_rules(conn: sqlite3.Connection) -> Dict[Tuple[str, str], List[LimitRule]]:
    rows = conn.execute(
        """
        SELECT board_type, risk_flag_type, limit_pct, tick_size, effective_from, effective_to
        FROM cfg_limit_rule_map
        ORDER BY board_type, risk_flag_type, effective_from
        """
    ).fetchall()
    out: Dict[Tuple[str, str], List[LimitRule]] = {}
    for row in rows:
        key = (row[0], row[1])
        out.setdefault(key, []).append(
            LimitRule(
                board_type=row[0],
                risk_flag_type=row[1],
                limit_pct=float(row[2]),
                tick_size=float(row[3]),
                effective_from=row[4],
                effective_to=row[5],
            )
        )
    return out


def pick_rule(rules: Dict[Tuple[str, str], List[LimitRule]], board_type: str, risk_flag_type: str, trade_date: str) -> Optional[LimitRule]:
    candidates = rules.get((board_type, risk_flag_type)) or rules.get((board_type, "normal")) or []
    for rule in candidates:
        if rule.effective_from <= trade_date and (rule.effective_to is None or trade_date <= rule.effective_to):
            return rule
    return None


def round_to_tick(value: float, tick_size: float) -> float:
    if value is None:
        return value
    q = Decimal(str(tick_size))
    return float((Decimal(str(value)) / q).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * q)


def calc_limit_prices(prev_close: float, limit_pct: float, tick_size: float) -> Tuple[float, float]:
    up = round_to_tick(prev_close * (1 + limit_pct), tick_size)
    down = round_to_tick(prev_close * (1 - limit_pct), tick_size)
    return up, down


def build_where_clause(symbols: Sequence[str], date_from: str, date_to: str) -> Tuple[str, List[object]]:
    clauses: List[str] = []
    params: List[object] = []
    if symbols:
        clauses.append(f"symbol IN ({','.join('?' for _ in symbols)})")
        params.extend(symbols)
    if date_from:
        clauses.append("trade_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("trade_date <= ?")
        params.append(date_to)
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def classify_label(touch_up: int, touch_down: int, close_up: int, close_down: int) -> str:
    if close_up:
        return "sealed_up"
    if close_down:
        return "sealed_down"
    if touch_up:
        return "broken_up"
    if touch_down:
        return "broken_down"
    return "normal"


def near_ratio(price: float, barrier: Optional[float], prev_close: Optional[float]) -> Optional[float]:
    if barrier is None or prev_close is None or prev_close == barrier:
        return None
    return float(1 - abs(barrier - price) / abs(barrier - prev_close))


def build_limit_state(conn: sqlite3.Connection, symbols: Sequence[str], date_from: str, date_to: str) -> Tuple[List[Tuple], List[Tuple]]:
    where_clause, params = build_where_clause(symbols, date_from, date_to)
    daily = conn.execute(
        f"""
        SELECT symbol, trade_date, open, high, low, close
        FROM atomic_trade_daily
        {where_clause}
        ORDER BY symbol, trade_date
        """,
        params,
    ).fetchall()
    bars = conn.execute(
        f"""
        SELECT symbol, trade_date, bucket_start, open, high, low, close
        FROM atomic_trade_5m
        {where_clause}
        ORDER BY symbol, trade_date, bucket_start
        """,
        params,
    ).fetchall()

    bars_by_day: Dict[Tuple[str, str], List[sqlite3.Row]] = {}
    for row in bars:
        bars_by_day.setdefault((row[0], row[1]), []).append(row)

    rules = load_rules(conn)
    daily_rows: List[Tuple] = []
    rows_5m: List[Tuple] = []
    prev_close_map: Dict[str, float] = {}

    for symbol, trade_date, open_price, high_price, low_price, close_price in daily:
        board_type = detect_board_type(symbol)
        risk_flag_type = "normal"
        prev_close = prev_close_map.get(symbol)
        quality_parts: List[str] = []
        limit_pct = None
        tick_size = None
        up_limit_price = None
        down_limit_price = None
        if prev_close is not None:
            rule = pick_rule(rules, board_type, risk_flag_type, trade_date)
            if rule:
                limit_pct = rule.limit_pct
                tick_size = rule.tick_size
                up_limit_price, down_limit_price = calc_limit_prices(prev_close, rule.limit_pct, rule.tick_size)
            else:
                quality_parts.append("missing_limit_rule")
        else:
            quality_parts.append("missing_prev_close")

        day_bars = bars_by_day.get((symbol, trade_date), [])
        touch_up_count = 0
        touch_down_count = 0
        first_touch_up = last_touch_up = None
        first_touch_down = last_touch_down = None

        for b in day_bars:
            _, _, bucket_start, b_open, b_high, b_low, b_close = b
            if up_limit_price is not None:
                touch_up = int(float(b_high) >= up_limit_price - 0.005)
                close_up = int(abs(float(b_close) - up_limit_price) <= 0.005)
            else:
                touch_up = close_up = 0
            if down_limit_price is not None:
                touch_down = int(float(b_low) <= down_limit_price + 0.005)
                close_down = int(abs(float(b_close) - down_limit_price) <= 0.005)
            else:
                touch_down = close_down = 0

            if touch_up:
                touch_up_count += 1
                first_touch_up = first_touch_up or bucket_start
                last_touch_up = bucket_start
            if touch_down:
                touch_down_count += 1
                first_touch_down = first_touch_down or bucket_start
                last_touch_down = bucket_start

            rows_5m.append(
                (
                    symbol,
                    trade_date,
                    bucket_start,
                    board_type,
                    risk_flag_type,
                    prev_close,
                    up_limit_price,
                    down_limit_price,
                    limit_pct,
                    tick_size,
                    float(b_open),
                    float(b_high),
                    float(b_low),
                    float(b_close),
                    touch_up,
                    touch_down,
                    close_up,
                    close_down,
                    near_ratio(float(b_close), up_limit_price, prev_close),
                    near_ratio(float(b_close), down_limit_price, prev_close),
                    classify_label(touch_up, touch_down, close_up, close_down),
                    "trade_limit_state",
                    "；".join(quality_parts) if quality_parts else None,
                )
            )

        if up_limit_price is not None:
            touch_limit_up = int(float(high_price) >= up_limit_price - 0.005)
            is_limit_up_close = int(abs(float(close_price) - up_limit_price) <= 0.005)
        else:
            touch_limit_up = is_limit_up_close = 0
        if down_limit_price is not None:
            touch_limit_down = int(float(low_price) <= down_limit_price + 0.005)
            is_limit_down_close = int(abs(float(close_price) - down_limit_price) <= 0.005)
        else:
            touch_limit_down = is_limit_down_close = 0

        daily_rows.append(
            (
                symbol,
                trade_date,
                board_type,
                risk_flag_type,
                prev_close,
                up_limit_price,
                down_limit_price,
                limit_pct,
                tick_size,
                float(open_price),
                float(high_price),
                float(low_price),
                float(close_price),
                touch_limit_up,
                touch_limit_down,
                is_limit_up_close,
                is_limit_down_close,
                touch_up_count,
                touch_down_count,
                first_touch_up,
                last_touch_up,
                first_touch_down,
                last_touch_down,
                int(touch_limit_up and not is_limit_up_close),
                int(touch_limit_down and not is_limit_down_close),
                classify_label(touch_limit_up, touch_limit_down, is_limit_up_close, is_limit_down_close),
                "trade_limit_state",
                "；".join(quality_parts) if quality_parts else None,
            )
        )

        prev_close_map[symbol] = float(close_price)
    return rows_5m, daily_rows


def replace_rows(conn: sqlite3.Connection, rows_5m: Sequence[Tuple], daily_rows: Sequence[Tuple], symbols: Sequence[str], date_from: str, date_to: str) -> None:
    where_clause, params = build_where_clause(symbols, date_from, date_to)
    conn.execute(f"DELETE FROM atomic_limit_state_5m {where_clause}", params)
    conn.execute(f"DELETE FROM atomic_limit_state_daily {where_clause}", params)
    if rows_5m:
        conn.executemany(
            """
            INSERT INTO atomic_limit_state_5m (
                symbol, trade_date, bucket_start, board_type, risk_flag_type,
                prev_close, up_limit_price, down_limit_price, limit_pct, tick_size,
                open_price, high_price, low_price, close_price,
                touch_limit_up, touch_limit_down, is_limit_up_close_5m, is_limit_down_close_5m,
                near_limit_up_ratio, near_limit_down_ratio,
                state_label_5m, source_type, quality_info
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows_5m,
        )
    if daily_rows:
        conn.executemany(
            """
            INSERT INTO atomic_limit_state_daily (
                symbol, trade_date, board_type, risk_flag_type,
                prev_close, up_limit_price, down_limit_price, limit_pct, tick_size,
                open_price, high_price, low_price, close_price,
                touch_limit_up, touch_limit_down, is_limit_up_close, is_limit_down_close,
                touch_limit_up_count_5m, touch_limit_down_count_5m,
                first_touch_limit_up_time, last_touch_limit_up_time,
                first_touch_limit_down_time, last_touch_limit_down_time,
                broken_limit_up, broken_limit_down, limit_state_label,
                source_type, quality_info
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            daily_rows,
        )


def main() -> None:
    args = parse_args()
    if not args.atomic_db.exists():
        raise SystemExit(f"Atomic DB not found: {args.atomic_db}")
    symbols = [s.strip().lower() for s in args.symbols.split(",") if s.strip()]
    with sqlite3.connect(args.atomic_db) as conn:
        ensure_schema(conn)
        ensure_default_rules(conn)
        rows_5m, daily_rows = build_limit_state(conn, symbols, args.date_from, args.date_to)
        if not args.dry_run:
            replace_rows(conn, rows_5m, daily_rows, symbols, args.date_from, args.date_to)
            conn.commit()
    print(
        {
            "atomic_db": str(args.atomic_db),
            "symbols": symbols,
            "date_from": args.date_from or None,
            "date_to": args.date_to or None,
            "rows_5m": len(rows_5m),
            "rows_daily": len(daily_rows),
            "dry_run": bool(args.dry_run),
        }
    )


if __name__ == "__main__":
    main()
