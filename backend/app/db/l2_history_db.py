import os
import sqlite3
from datetime import datetime, time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.core.config import DB_FILE
from backend.app.core.time_buckets import map_to_30m_bucket_start


History5mRow = Tuple[
    str,  # symbol
    str,  # datetime
    str,  # source_date
    float,  # open
    float,  # high
    float,  # low
    float,  # close
    float,  # total_amount
    float,  # l1_main_buy
    float,  # l1_main_sell
    float,  # l1_super_buy
    float,  # l1_super_sell
    float,  # l2_main_buy
    float,  # l2_main_sell
    float,  # l2_super_buy
    float,  # l2_super_sell
    Optional[str],  # quality_info
]

HistoryDailyRow = Tuple[
    str,  # symbol
    str,  # date
    float,  # open
    float,  # high
    float,  # low
    float,  # close
    float,  # total_amount
    float,  # l1_main_buy
    float,  # l1_main_sell
    float,  # l1_main_net
    float,  # l1_super_buy
    float,  # l1_super_sell
    float,  # l1_super_net
    float,  # l2_main_buy
    float,  # l2_main_sell
    float,  # l2_main_net
    float,  # l2_super_buy
    float,  # l2_super_sell
    float,  # l2_super_net
    float,  # l1_activity_ratio
    float,  # l1_super_ratio
    float,  # l2_activity_ratio
    float,  # l2_super_ratio
    float,  # l1_buy_ratio
    float,  # l1_sell_ratio
    float,  # l2_buy_ratio
    float,  # l2_sell_ratio
    Optional[str],  # quality_info
]


def get_l2_history_connection() -> sqlite3.Connection:
    db_path = os.getenv("DB_PATH", DB_FILE)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_l2_history_schema() -> None:
    conn = get_l2_history_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS history_5m_l2 (
                symbol TEXT NOT NULL,
                datetime TEXT NOT NULL,
                source_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL,
                l1_main_buy REAL NOT NULL,
                l1_main_sell REAL NOT NULL,
                l1_super_buy REAL NOT NULL,
                l1_super_sell REAL NOT NULL,
                l2_main_buy REAL NOT NULL,
                l2_main_sell REAL NOT NULL,
                l2_super_buy REAL NOT NULL,
                l2_super_sell REAL NOT NULL,
                quality_info TEXT NULL,
                PRIMARY KEY(symbol, datetime)
            );
            CREATE INDEX IF NOT EXISTS idx_history_5m_l2_symbol_date
            ON history_5m_l2(symbol, source_date);

            CREATE TABLE IF NOT EXISTS history_daily_l2 (
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
                l2_main_buy REAL NOT NULL,
                l2_main_sell REAL NOT NULL,
                l2_main_net REAL NOT NULL,
                l2_super_buy REAL NOT NULL,
                l2_super_sell REAL NOT NULL,
                l2_super_net REAL NOT NULL,
                l1_activity_ratio REAL NOT NULL,
                l1_super_ratio REAL NOT NULL,
                l2_activity_ratio REAL NOT NULL,
                l2_super_ratio REAL NOT NULL,
                l1_buy_ratio REAL NOT NULL,
                l1_sell_ratio REAL NOT NULL,
                l2_buy_ratio REAL NOT NULL,
                l2_sell_ratio REAL NOT NULL,
                quality_info TEXT NULL,
                PRIMARY KEY(symbol, date)
            );
            CREATE INDEX IF NOT EXISTS idx_history_daily_l2_date
            ON history_daily_l2(date);

            CREATE TABLE IF NOT EXISTS l2_daily_ingest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                source_root TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'manual',
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                symbol_count INTEGER NOT NULL DEFAULT 0,
                rows_5m INTEGER NOT NULL DEFAULT 0,
                rows_daily INTEGER NOT NULL DEFAULT 0,
                message TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_l2_daily_ingest_runs_trade_date
            ON l2_daily_ingest_runs(trade_date, started_at DESC);

            CREATE TABLE IF NOT EXISTS l2_daily_ingest_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                source_file TEXT NOT NULL,
                error_message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_l2_daily_ingest_failures_run
            ON l2_daily_ingest_failures(run_id);
            """
        )
        _ensure_column(conn, "history_5m_l2", "quality_info", "TEXT NULL")
        _ensure_column(conn, "history_daily_l2", "quality_info", "TEXT NULL")
        conn.commit()
    finally:
        conn.close()


def replace_history_5m_l2_rows(symbol: str, source_date: str, rows: Sequence[History5mRow]) -> int:
    ensure_l2_history_schema()
    conn = get_l2_history_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM history_5m_l2 WHERE symbol=? AND source_date=?",
                (symbol, source_date),
            )
            if rows:
                normalized_rows = [
                    tuple(row) if len(tuple(row)) >= 17 else tuple(list(row) + [None])
                    for row in rows
                ]
                conn.executemany(
                    """
                    INSERT INTO history_5m_l2 (
                        symbol, datetime, source_date,
                        open, high, low, close, total_amount,
                        l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
                        l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell,
                        quality_info
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    normalized_rows,
                )
        return len(rows)
    finally:
        conn.close()


def replace_history_daily_l2_row(symbol: str, trade_date: str, row: Optional[HistoryDailyRow]) -> int:
    ensure_l2_history_schema()
    conn = get_l2_history_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM history_daily_l2 WHERE symbol=? AND date=?",
                (symbol, trade_date),
            )
            if row:
                normalized_row = tuple(row) if len(tuple(row)) >= 28 else tuple(list(row) + [None])
                conn.execute(
                    """
                    INSERT INTO history_daily_l2 (
                        symbol, date,
                        open, high, low, close, total_amount,
                        l1_main_buy, l1_main_sell, l1_main_net,
                        l1_super_buy, l1_super_sell, l1_super_net,
                        l2_main_buy, l2_main_sell, l2_main_net,
                        l2_super_buy, l2_super_sell, l2_super_net,
                        l1_activity_ratio, l1_super_ratio,
                        l2_activity_ratio, l2_super_ratio,
                        l1_buy_ratio, l1_sell_ratio, l2_buy_ratio, l2_sell_ratio,
                        quality_info
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    normalized_row,
                )
                return 1
        return 0
    finally:
        conn.close()


def create_l2_daily_ingest_run(
    trade_date: str,
    source_root: str,
    mode: str = "manual",
    message: str = "",
) -> int:
    ensure_l2_history_schema()
    conn = get_l2_history_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO l2_daily_ingest_runs (
                trade_date, source_root, mode, status, started_at, message
            ) VALUES (?, ?, ?, 'running', ?, ?)
            """,
            (
                trade_date,
                source_root,
                mode,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                message,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def finish_l2_daily_ingest_run(
    run_id: int,
    status: str,
    symbol_count: int = 0,
    rows_5m: int = 0,
    rows_daily: int = 0,
    message: str = "",
) -> None:
    ensure_l2_history_schema()
    conn = get_l2_history_connection()
    try:
        conn.execute(
            """
            UPDATE l2_daily_ingest_runs
            SET status=?, finished_at=?, symbol_count=?, rows_5m=?, rows_daily=?, message=?
            WHERE id=?
            """,
            (
                status,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                int(symbol_count),
                int(rows_5m),
                int(rows_daily),
                message,
                int(run_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def add_l2_daily_ingest_failures(
    run_id: int,
    failures: Iterable[Tuple[str, str, str, str]],
) -> int:
    """
    failures item format:
    (symbol, trade_date, source_file, error_message)
    """
    ensure_l2_history_schema()
    failure_rows = list(failures)
    if not failure_rows:
        return 0
    conn = get_l2_history_connection()
    try:
        conn.executemany(
            """
            INSERT INTO l2_daily_ingest_failures (
                run_id, symbol, trade_date, source_file, error_message
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (int(run_id), symbol, trade_date, source_file, error_message)
                for symbol, trade_date, source_file, error_message in failure_rows
            ],
        )
        conn.commit()
        return len(failure_rows)
    finally:
        conn.close()


def get_latest_l2_daily_ingest_run(trade_date: Optional[str] = None) -> Optional[dict]:
    ensure_l2_history_schema()
    conn = get_l2_history_connection()
    try:
        conn.row_factory = sqlite3.Row
        if trade_date:
            row = conn.execute(
                """
                SELECT * FROM l2_daily_ingest_runs
                WHERE trade_date=?
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (trade_date,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM l2_daily_ingest_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


ALLOWED_L2_HISTORY_GRANULARITIES = {"5m", "15m", "30m", "1h", "1d"}


def normalize_l2_symbol(symbol: str) -> str:
    return str(symbol or "").strip().lower()


def _bucket_start(dt: datetime, granularity: str) -> Optional[datetime]:
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

    raise ValueError(f"granularity 仅支持: {', '.join(sorted(ALLOWED_L2_HISTORY_GRANULARITIES))}")


def _row_to_history_5m_dict(row: Sequence) -> Dict[str, object]:
    return {
        "symbol": row[0],
        "datetime": row[1],
        "source_date": row[2],
        "open": float(row[3]),
        "high": float(row[4]),
        "low": float(row[5]),
        "close": float(row[6]),
        "total_amount": float(row[7]),
        "l1_main_buy": float(row[8]),
        "l1_main_sell": float(row[9]),
        "l1_super_buy": float(row[10]),
        "l1_super_sell": float(row[11]),
        "l2_main_buy": float(row[12]),
        "l2_main_sell": float(row[13]),
        "l2_super_buy": float(row[14]),
        "l2_super_sell": float(row[15]),
        "quality_info": row[16],
    }


def _to_optional_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def query_l2_history_5m_rows(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit_days: Optional[int] = None,
) -> List[Dict[str, object]]:
    ensure_l2_history_schema()
    normalized = normalize_l2_symbol(symbol)
    conn = get_l2_history_connection()
    try:
        conn.row_factory = sqlite3.Row
        if limit_days is not None:
            dates = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT DISTINCT source_date
                    FROM history_5m_l2
                    WHERE symbol=?
                    ORDER BY source_date DESC
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
            clauses.append("source_date>=?")
            params.append(str(start_date))
        if end_date:
            clauses.append("source_date<=?")
            params.append(str(end_date))

        rows = conn.execute(
            f"""
            SELECT
                symbol, datetime, source_date,
                open, high, low, close, total_amount,
                l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
                l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell,
                quality_info
            FROM history_5m_l2
            WHERE {' AND '.join(clauses)}
            ORDER BY datetime ASC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def query_l2_history_daily_rows(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit_days: Optional[int] = None,
) -> List[Dict[str, object]]:
    ensure_l2_history_schema()
    normalized = normalize_l2_symbol(symbol)
    conn = get_l2_history_connection()
    try:
        conn.row_factory = sqlite3.Row
        clauses = ["symbol=?"]
        params: List[object] = [normalized]
        if start_date:
            clauses.append("date>=?")
            params.append(str(start_date))
        if end_date:
            clauses.append("date<=?")
            params.append(str(end_date))

        limit_sql = ""
        if limit_days is not None:
            limit_sql = f" LIMIT {int(limit_days)}"

        rows = conn.execute(
            f"""
            SELECT
                symbol, date, open, high, low, close, total_amount,
                l1_main_buy, l1_main_sell, l1_main_net,
                l1_super_buy, l1_super_sell, l1_super_net,
                l2_main_buy, l2_main_sell, l2_main_net,
                l2_super_buy, l2_super_sell, l2_super_net,
                l1_activity_ratio, l1_super_ratio,
                l2_activity_ratio, l2_super_ratio,
                l1_buy_ratio, l1_sell_ratio, l2_buy_ratio, l2_sell_ratio,
                quality_info
            FROM history_daily_l2
            WHERE {' AND '.join(clauses)}
            ORDER BY date DESC{limit_sql}
            """,
            params,
        ).fetchall()
        out = [dict(row) for row in reversed(rows)]
        return out
    finally:
        conn.close()


def query_l2_history_daily_row(symbol: str, trade_date: str) -> Optional[Dict[str, object]]:
    rows = query_l2_history_daily_rows(symbol, start_date=trade_date, end_date=trade_date, limit_days=1)
    return rows[0] if rows else None


def aggregate_l2_history_5m_rows(
    rows_5m: Sequence[Dict[str, object]],
    granularity: str = "30m",
) -> List[Dict[str, object]]:
    if granularity not in ALLOWED_L2_HISTORY_GRANULARITIES:
        raise ValueError(f"granularity 仅支持: {', '.join(sorted(ALLOWED_L2_HISTORY_GRANULARITIES))}")
    if not rows_5m:
        return []
    if granularity == "5m":
        return [dict(row) for row in rows_5m]

    aggregated: Dict[str, Dict[str, object]] = {}
    bucket_order: List[str] = []
    for row in rows_5m:
        dt = datetime.strptime(str(row["datetime"]), "%Y-%m-%d %H:%M:%S")
        bucket_dt = _bucket_start(dt, granularity)
        if bucket_dt is None:
            continue
        bucket_key = bucket_dt.strftime("%Y-%m-%d %H:%M:%S")
        if bucket_key not in aggregated:
            aggregated[bucket_key] = {
                "symbol": row["symbol"],
                "datetime": bucket_key,
                "source_date": row["source_date"],
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "total_amount": 0.0,
                "l1_main_buy": 0.0,
                "l1_main_sell": 0.0,
                "l1_super_buy": 0.0,
                "l1_super_sell": 0.0,
                "l2_main_buy": 0.0,
                "l2_main_sell": 0.0,
                "l2_super_buy": 0.0,
                "l2_super_sell": 0.0,
                "quality_info": None,
                "is_placeholder": False,
                "_quality_messages": [],
                "_placeholder_count": 0,
                "_numeric_count": 0,
            }
            bucket_order.append(bucket_key)
        item = aggregated[bucket_key]
        item["source_date"] = str(row["source_date"])
        quality_info = str(row.get("quality_info") or "").strip()
        if quality_info:
            item["_quality_messages"].append(quality_info)
        if bool(row.get("is_placeholder")):
            item["_placeholder_count"] += 1

        open_value = _to_optional_float(row.get("open"))
        high_value = _to_optional_float(row.get("high"))
        low_value = _to_optional_float(row.get("low"))
        close_value = _to_optional_float(row.get("close"))
        if open_value is None or high_value is None or low_value is None or close_value is None:
            continue

        if int(item["_numeric_count"]) == 0:
            item["open"] = open_value
            item["high"] = high_value
            item["low"] = low_value
            item["close"] = close_value
            item["total_amount"] = float(_to_optional_float(row.get("total_amount")) or 0.0)
            item["l1_main_buy"] = float(_to_optional_float(row.get("l1_main_buy")) or 0.0)
            item["l1_main_sell"] = float(_to_optional_float(row.get("l1_main_sell")) or 0.0)
            item["l1_super_buy"] = float(_to_optional_float(row.get("l1_super_buy")) or 0.0)
            item["l1_super_sell"] = float(_to_optional_float(row.get("l1_super_sell")) or 0.0)
            item["l2_main_buy"] = float(_to_optional_float(row.get("l2_main_buy")) or 0.0)
            item["l2_main_sell"] = float(_to_optional_float(row.get("l2_main_sell")) or 0.0)
            item["l2_super_buy"] = float(_to_optional_float(row.get("l2_super_buy")) or 0.0)
            item["l2_super_sell"] = float(_to_optional_float(row.get("l2_super_sell")) or 0.0)
            item["_numeric_count"] = 1
            continue

        item["high"] = max(float(item["high"]), high_value)
        item["low"] = min(float(item["low"]), low_value)
        item["close"] = close_value
        item["total_amount"] = float(item["total_amount"]) + float(_to_optional_float(row.get("total_amount")) or 0.0)
        item["l1_main_buy"] = float(item["l1_main_buy"]) + float(_to_optional_float(row.get("l1_main_buy")) or 0.0)
        item["l1_main_sell"] = float(item["l1_main_sell"]) + float(_to_optional_float(row.get("l1_main_sell")) or 0.0)
        item["l1_super_buy"] = float(item["l1_super_buy"]) + float(_to_optional_float(row.get("l1_super_buy")) or 0.0)
        item["l1_super_sell"] = float(item["l1_super_sell"]) + float(_to_optional_float(row.get("l1_super_sell")) or 0.0)
        item["l2_main_buy"] = float(item["l2_main_buy"]) + float(_to_optional_float(row.get("l2_main_buy")) or 0.0)
        item["l2_main_sell"] = float(item["l2_main_sell"]) + float(_to_optional_float(row.get("l2_main_sell")) or 0.0)
        item["l2_super_buy"] = float(item["l2_super_buy"]) + float(_to_optional_float(row.get("l2_super_buy")) or 0.0)
        item["l2_super_sell"] = float(item["l2_super_sell"]) + float(_to_optional_float(row.get("l2_super_sell")) or 0.0)
        item["_numeric_count"] = int(item["_numeric_count"]) + 1

    result: List[Dict[str, object]] = []
    for key in sorted(bucket_order):
        item = aggregated[key]
        numeric_count = int(item.pop("_numeric_count"))
        placeholder_count = int(item.pop("_placeholder_count"))
        quality_messages = [msg for msg in item.pop("_quality_messages") if msg]
        unique_messages = list(dict.fromkeys(quality_messages))
        if placeholder_count > 0:
            item["quality_info"] = (
                "该区间包含缺失 5m，聚合值可能偏小"
                if numeric_count > 0
                else "该区间缺失正式 5m 数据"
            )
        elif unique_messages:
            item["quality_info"] = (
                unique_messages[0]
                if numeric_count <= 1 and len(unique_messages) == 1
                else "该区间包含异常 5m，聚合值可能偏小"
            )
        else:
            item["quality_info"] = None

        if numeric_count <= 0:
            item["open"] = None
            item["high"] = None
            item["low"] = None
            item["close"] = None
            item["total_amount"] = None
            item["l1_main_buy"] = None
            item["l1_main_sell"] = None
            item["l1_super_buy"] = None
            item["l1_super_sell"] = None
            item["l2_main_buy"] = None
            item["l2_main_sell"] = None
            item["l2_super_buy"] = None
            item["l2_super_sell"] = None
            item["is_placeholder"] = True
        else:
            item["is_placeholder"] = False
        result.append(item)

    return result


def query_l2_history_trend(
    symbol: str,
    limit_days: int = 20,
    granularity: str = "30m",
) -> List[Dict[str, object]]:
    rows_5m = query_l2_history_5m_rows(symbol, limit_days=limit_days)
    aggregated_rows = aggregate_l2_history_5m_rows(rows_5m, granularity=granularity)
    result: List[Dict[str, object]] = []
    for row in aggregated_rows:
        result.append(
            {
                "time": str(row["datetime"]),
                "net_inflow": float(row["l2_main_buy"]) - float(row["l2_main_sell"]),
                "main_buy": float(row["l2_main_buy"]),
                "main_sell": float(row["l2_main_sell"]),
                "super_net": float(row["l2_super_buy"]) - float(row["l2_super_sell"]),
                "super_buy": float(row["l2_super_buy"]),
                "super_sell": float(row["l2_super_sell"]),
                "close": float(row["close"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "total_amount": float(row["total_amount"]),
                "source": "l2_history",
                "is_finalized": True,
                "fallback_used": False,
                "l1_net_inflow": float(row["l1_main_buy"]) - float(row["l1_main_sell"]),
                "l1_main_buy": float(row["l1_main_buy"]),
                "l1_main_sell": float(row["l1_main_sell"]),
                "l1_super_net": float(row["l1_super_buy"]) - float(row["l1_super_sell"]),
                "l1_super_buy": float(row["l1_super_buy"]),
                "l1_super_sell": float(row["l1_super_sell"]),
            }
        )
    return result


def query_l2_history_analysis(symbol: str, limit_days: Optional[int] = None) -> List[Dict[str, object]]:
    rows = query_l2_history_daily_rows(symbol, limit_days=limit_days)
    result: List[Dict[str, object]] = []
    previous_close: Optional[float] = None
    for row in rows:
        close = float(row["close"])
        pct_change = 0.0
        if previous_close and previous_close > 0:
            pct_change = (close - previous_close) / previous_close * 100
        previous_close = close
        result.append(
            {
                "date": str(row["date"]),
                "close": close,
                "pct_change": float(pct_change),
                "change_pct": float(pct_change),
                "total_amount": float(row["total_amount"]),
                "main_buy_amount": float(row["l2_main_buy"]),
                "main_sell_amount": float(row["l2_main_sell"]),
                "net_inflow": float(row["l2_main_net"]),
                "super_large_in": float(row["l2_super_buy"]),
                "super_large_out": float(row["l2_super_sell"]),
                "buyRatio": float(row["l2_buy_ratio"]),
                "sellRatio": float(row["l2_sell_ratio"]),
                "activityRatio": float(row["l2_activity_ratio"]),
                "super_large_ratio": float(row["l2_super_ratio"]),
                "source": "l2_history",
                "is_finalized": True,
                "fallback_used": False,
                "l1_main_buy_amount": float(row["l1_main_buy"]),
                "l1_main_sell_amount": float(row["l1_main_sell"]),
                "l1_net_inflow": float(row["l1_main_net"]),
                "l1_super_large_in": float(row["l1_super_buy"]),
                "l1_super_large_out": float(row["l1_super_sell"]),
                "l1_activityRatio": float(row["l1_activity_ratio"]),
                "l1_buyRatio": float(row["l1_buy_ratio"]),
                "l1_sellRatio": float(row["l1_sell_ratio"]),
                "l1_super_large_ratio": float(row["l1_super_ratio"]),
                "l2_main_buy_amount": float(row["l2_main_buy"]),
                "l2_main_sell_amount": float(row["l2_main_sell"]),
                "l2_net_inflow": float(row["l2_main_net"]),
                "l2_super_large_in": float(row["l2_super_buy"]),
                "l2_super_large_out": float(row["l2_super_sell"]),
                "l2_activityRatio": float(row["l2_activity_ratio"]),
                "l2_buyRatio": float(row["l2_buy_ratio"]),
                "l2_sellRatio": float(row["l2_sell_ratio"]),
                "l2_super_large_ratio": float(row["l2_super_ratio"]),
            }
        )
    return result
