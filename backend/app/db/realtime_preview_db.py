import os
import sqlite3
from datetime import datetime, time
from typing import Dict, List, Optional, Sequence, Tuple

from backend.app.core.config import DB_FILE
from backend.app.core.time_buckets import map_to_30m_bucket_start


Realtime5mPreviewRow = Tuple[
    str,   # symbol
    str,   # datetime
    str,   # trade_date
    float, # open
    float, # high
    float, # low
    float, # close
    float, # total_amount
    float, # l1_main_buy
    float, # l1_main_sell
    float, # l1_super_buy
    float, # l1_super_sell
    str,   # source
    str,   # preview_level
    str,   # updated_at
]

RealtimeDailyPreviewRow = Tuple[
    str,   # symbol
    str,   # date
    float, # open
    float, # high
    float, # low
    float, # close
    float, # total_amount
    float, # l1_main_buy
    float, # l1_main_sell
    float, # l1_main_net
    float, # l1_super_buy
    float, # l1_super_sell
    float, # l1_super_net
    str,   # source
    str,   # preview_level
    str,   # updated_at
]


ALLOWED_PREVIEW_GRANULARITIES = {"5m", "15m", "30m", "1h", "1d"}


def get_realtime_preview_connection() -> sqlite3.Connection:
    db_path = os.getenv("DB_PATH", DB_FILE)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path)


def ensure_realtime_preview_schema() -> None:
    conn = get_realtime_preview_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS realtime_5m_preview (
                symbol TEXT NOT NULL,
                datetime TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                l1_main_buy REAL NOT NULL,
                l1_main_sell REAL NOT NULL,
                l1_super_buy REAL NOT NULL,
                l1_super_sell REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'realtime_ticks',
                preview_level TEXT NOT NULL DEFAULT 'l1_only',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(symbol, datetime)
            );
            CREATE INDEX IF NOT EXISTS idx_realtime_5m_preview_symbol_date
            ON realtime_5m_preview(symbol, trade_date);

            CREATE TABLE IF NOT EXISTS realtime_daily_preview (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                l1_main_buy REAL NOT NULL,
                l1_main_sell REAL NOT NULL,
                l1_main_net REAL NOT NULL,
                l1_super_buy REAL NOT NULL,
                l1_super_sell REAL NOT NULL,
                l1_super_net REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'realtime_ticks',
                preview_level TEXT NOT NULL DEFAULT 'l1_only',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(symbol, date)
            );
            CREATE INDEX IF NOT EXISTS idx_realtime_daily_preview_date
            ON realtime_daily_preview(date);
            """
        )
        conn.commit()
    finally:
        conn.close()


def normalize_preview_symbol(symbol: str) -> str:
    return str(symbol or "").strip().lower()


def replace_realtime_5m_preview_rows(symbol: str, trade_date: str, rows: Sequence[Realtime5mPreviewRow]) -> int:
    ensure_realtime_preview_schema()
    normalized = normalize_preview_symbol(symbol)
    conn = get_realtime_preview_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM realtime_5m_preview WHERE symbol=? AND trade_date=?",
                (normalized, str(trade_date)),
            )
            if rows:
                conn.executemany(
                    """
                    INSERT INTO realtime_5m_preview (
                        symbol, datetime, trade_date,
                        open, high, low, close, total_amount,
                        l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
                        source, preview_level, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        return len(rows)
    finally:
        conn.close()


def replace_realtime_daily_preview_row(
    symbol: str,
    trade_date: str,
    row: Optional[RealtimeDailyPreviewRow],
) -> int:
    ensure_realtime_preview_schema()
    normalized = normalize_preview_symbol(symbol)
    conn = get_realtime_preview_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM realtime_daily_preview WHERE symbol=? AND date=?",
                (normalized, str(trade_date)),
            )
            if row:
                conn.execute(
                    """
                    INSERT INTO realtime_daily_preview (
                        symbol, date,
                        open, high, low, close, total_amount,
                        l1_main_buy, l1_main_sell, l1_main_net,
                        l1_super_buy, l1_super_sell, l1_super_net,
                        source, preview_level, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
                return 1
        return 0
    finally:
        conn.close()


def query_realtime_5m_preview_rows(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit_days: Optional[int] = None,
) -> List[Dict[str, object]]:
    ensure_realtime_preview_schema()
    normalized = normalize_preview_symbol(symbol)
    conn = get_realtime_preview_connection()
    try:
        conn.row_factory = sqlite3.Row
        if limit_days is not None:
            dates = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT DISTINCT trade_date
                    FROM realtime_5m_preview
                    WHERE symbol=?
                    ORDER BY trade_date DESC
                    LIMIT ?
                    """,
                    (normalized, int(limit_days)),
                ).fetchall()
            ]
            if not dates:
                return []
            start_date = min(dates)

        clauses = ["symbol=?"]
        params: List[object] = [normalized]
        if start_date:
            clauses.append("trade_date>=?")
            params.append(str(start_date))
        if end_date:
            clauses.append("trade_date<=?")
            params.append(str(end_date))

        rows = conn.execute(
            f"""
            SELECT
                symbol, datetime, trade_date,
                open, high, low, close, total_amount,
                l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
                source, preview_level, updated_at
            FROM realtime_5m_preview
            WHERE {' AND '.join(clauses)}
            ORDER BY datetime ASC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def query_realtime_daily_preview_row(symbol: str, trade_date: str) -> Optional[Dict[str, object]]:
    ensure_realtime_preview_schema()
    normalized = normalize_preview_symbol(symbol)
    conn = get_realtime_preview_connection()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                symbol, date, open, high, low, close, total_amount,
                l1_main_buy, l1_main_sell, l1_main_net,
                l1_super_buy, l1_super_sell, l1_super_net,
                source, preview_level, updated_at
            FROM realtime_daily_preview
            WHERE symbol=? AND date=?
            LIMIT 1
            """,
            (normalized, str(trade_date)),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _preview_bucket_start(dt: datetime, granularity: str) -> Optional[datetime]:
    if granularity == "5m":
        minute = (dt.minute // 5) * 5
        return dt.replace(minute=minute, second=0, microsecond=0)

    if granularity == "15m":
        minute = (dt.minute // 15) * 15
        return dt.replace(minute=minute, second=0, microsecond=0)

    if granularity == "30m":
        return map_to_30m_bucket_start(dt)

    if granularity == "1h":
        current_time = dt.time()
        if time(9, 30) <= current_time < time(10, 30):
            return dt.replace(hour=9, minute=30, second=0, microsecond=0)
        if time(10, 30) <= current_time < time(11, 30):
            return dt.replace(hour=10, minute=30, second=0, microsecond=0)
        if time(13, 0) <= current_time < time(14, 0):
            return dt.replace(hour=13, minute=0, second=0, microsecond=0)
        if time(14, 0) <= current_time <= time(15, 0):
            return dt.replace(hour=14, minute=0, second=0, microsecond=0)
        return None

    if granularity == "1d":
        return dt.replace(hour=15, minute=0, second=0, microsecond=0)

    raise ValueError(f"granularity 仅支持: {', '.join(sorted(ALLOWED_PREVIEW_GRANULARITIES))}")


def aggregate_realtime_5m_preview_rows(
    rows_5m: Sequence[Dict[str, object]],
    granularity: str = "30m",
) -> List[Dict[str, object]]:
    if granularity not in ALLOWED_PREVIEW_GRANULARITIES:
        raise ValueError(f"granularity 仅支持: {', '.join(sorted(ALLOWED_PREVIEW_GRANULARITIES))}")
    if not rows_5m:
        return []
    if granularity == "5m":
        return [dict(row) for row in rows_5m]

    aggregated: Dict[str, Dict[str, object]] = {}
    bucket_order: List[str] = []
    for row in rows_5m:
        dt = datetime.strptime(str(row["datetime"]), "%Y-%m-%d %H:%M:%S")
        bucket_dt = _preview_bucket_start(dt, granularity)
        if bucket_dt is None:
            continue
        bucket_key = bucket_dt.strftime("%Y-%m-%d %H:%M:%S")
        if bucket_key not in aggregated:
            aggregated[bucket_key] = {
                "symbol": row["symbol"],
                "datetime": bucket_key,
                "trade_date": row["trade_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "total_amount": float(row["total_amount"]),
                "l1_main_buy": float(row["l1_main_buy"]),
                "l1_main_sell": float(row["l1_main_sell"]),
                "l1_super_buy": float(row["l1_super_buy"]),
                "l1_super_sell": float(row["l1_super_sell"]),
                "source": str(row["source"]),
                "preview_level": str(row["preview_level"]),
                "updated_at": str(row["updated_at"]),
            }
            bucket_order.append(bucket_key)
            continue

        item = aggregated[bucket_key]
        item["high"] = max(float(item["high"]), float(row["high"]))
        item["low"] = min(float(item["low"]), float(row["low"]))
        item["close"] = float(row["close"])
        item["total_amount"] = float(item["total_amount"]) + float(row["total_amount"])
        item["l1_main_buy"] = float(item["l1_main_buy"]) + float(row["l1_main_buy"])
        item["l1_main_sell"] = float(item["l1_main_sell"]) + float(row["l1_main_sell"])
        item["l1_super_buy"] = float(item["l1_super_buy"]) + float(row["l1_super_buy"])
        item["l1_super_sell"] = float(item["l1_super_sell"]) + float(row["l1_super_sell"])
        item["trade_date"] = str(row["trade_date"])
        item["updated_at"] = str(row["updated_at"])

    return [aggregated[key] for key in sorted(bucket_order)]
