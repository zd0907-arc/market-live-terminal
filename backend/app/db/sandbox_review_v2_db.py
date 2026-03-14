import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


ALLOWED_GRANULARITIES = {"5m", "15m", "30m", "60m", "1d"}


def normalize_review_symbol(symbol: str) -> str:
    raw = (symbol or "").strip().lower()
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8:
        return raw
    if raw.isdigit() and len(raw) == 6:
        return ("sh" if raw.startswith("6") else "sz") + raw
    return raw


def _project_root() -> str:
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )


def get_sandbox_review_v2_root() -> str:
    default_root = os.path.join(_project_root(), "data", "sandbox", "review_v2")
    root = os.path.abspath(os.getenv("SANDBOX_REVIEW_V2_ROOT", default_root))
    if root.endswith("market_data.db"):
        raise ValueError("SANDBOX_REVIEW_V2_ROOT 不能指向 market_data.db")
    return root


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def get_sandbox_meta_db_path() -> str:
    root = get_sandbox_review_v2_root()
    _ensure_dir(root)
    return os.path.join(root, "meta.db")


def get_symbol_db_path(symbol: str) -> str:
    normalized = normalize_review_symbol(symbol)
    if not normalized.startswith(("sh", "sz", "bj")):
        raise ValueError(f"非法股票代码: {symbol}")
    root = get_sandbox_review_v2_root()
    symbols_dir = os.path.join(root, "symbols")
    _ensure_dir(symbols_dir)
    return os.path.join(symbols_dir, f"{normalized}.db")


def get_meta_connection() -> sqlite3.Connection:
    return sqlite3.connect(get_sandbox_meta_db_path())


def get_symbol_connection(symbol: str) -> sqlite3.Connection:
    return sqlite3.connect(get_symbol_db_path(symbol))


def ensure_sandbox_review_v2_schema() -> None:
    conn = get_meta_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sandbox_stock_pool (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                market_cap REAL NOT NULL,
                as_of_date TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_sandbox_pool_market_cap
            ON sandbox_stock_pool(market_cap DESC);

            CREATE TABLE IF NOT EXISTS sandbox_backfill_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                message TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                workers INTEGER NOT NULL,
                symbol_count INTEGER NOT NULL DEFAULT 0,
                total_rows INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sandbox_backfill_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                source_file TEXT NOT NULL,
                error_message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_backfill_failures_run
            ON sandbox_backfill_failures(run_id);

            CREATE TABLE IF NOT EXISTS sandbox_backfill_month_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                message TEXT,
                workers INTEGER NOT NULL,
                trade_day_count INTEGER NOT NULL DEFAULT 0,
                symbol_count INTEGER NOT NULL DEFAULT 0,
                total_rows INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_backfill_month_runs_month
            ON sandbox_backfill_month_runs(month, started_at DESC);
            """
        )
        conn.commit()
    finally:
        conn.close()


def ensure_symbol_review_5m_schema(symbol: str) -> None:
    conn = get_symbol_connection(symbol)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_5m_bars (
                symbol TEXT NOT NULL,
                datetime TEXT NOT NULL,
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
                source_date TEXT NOT NULL,
                PRIMARY KEY(symbol, datetime)
            );
            CREATE INDEX IF NOT EXISTS idx_review_5m_datetime
            ON review_5m_bars(datetime);
            """
        )
        conn.commit()
    finally:
        conn.close()


def replace_stock_pool(
    rows: Sequence[Tuple[str, str, float]],
    as_of_date: str,
    source: str = "akshare_spot_em",
) -> int:
    ensure_sandbox_review_v2_schema()
    conn = get_meta_connection()
    try:
        conn.execute("DELETE FROM sandbox_stock_pool")
        conn.executemany(
            """
            INSERT INTO sandbox_stock_pool (
                symbol, name, market_cap, as_of_date, source
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    normalize_review_symbol(symbol),
                    str(name),
                    float(market_cap),
                    as_of_date,
                    source,
                )
                for symbol, name, market_cap in rows
            ],
        )
        conn.commit()
        return conn.execute("SELECT count(*) FROM sandbox_stock_pool").fetchone()[0]
    finally:
        conn.close()


def get_stock_pool(
    keyword: str = "",
    limit: Optional[int] = None,
) -> Dict[str, object]:
    ensure_sandbox_review_v2_schema()
    conn = get_meta_connection()
    try:
        conn.row_factory = sqlite3.Row
        where = ""
        args: List[object] = []
        if keyword:
            where = "WHERE symbol LIKE ? OR name LIKE ?"
            args.extend([f"%{keyword.lower()}%", f"%{keyword}%"])

        count_sql = f"SELECT count(*) FROM sandbox_stock_pool {where}"
        total = conn.execute(count_sql, args).fetchone()[0]

        sql = f"""
            SELECT symbol, name, market_cap, as_of_date, source, updated_at
            FROM sandbox_stock_pool
            {where}
            ORDER BY market_cap DESC, symbol ASC
        """
        if limit and limit > 0:
            sql += " LIMIT ?"
            args.append(int(limit))

        rows = [dict(row) for row in conn.execute(sql, args).fetchall()]
        as_of_date = rows[0]["as_of_date"] if rows else ""
        return {"total": total, "as_of_date": as_of_date, "items": rows}
    finally:
        conn.close()


def create_backfill_run(
    start_date: str,
    end_date: str,
    workers: int,
    symbol_count: int,
    message: str = "",
) -> int:
    ensure_sandbox_review_v2_schema()
    conn = get_meta_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO sandbox_backfill_runs (
                started_at, status, message, start_date, end_date, workers, symbol_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "running",
                message,
                start_date,
                end_date,
                int(workers),
                int(symbol_count),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def finish_backfill_run(
    run_id: int,
    status: str,
    total_rows: int,
    failed_count: int,
    message: str = "",
) -> None:
    ensure_sandbox_review_v2_schema()
    conn = get_meta_connection()
    try:
        conn.execute(
            """
            UPDATE sandbox_backfill_runs
            SET finished_at = ?, status = ?, total_rows = ?, failed_count = ?, message = ?
            WHERE id = ?
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status,
                int(total_rows),
                int(failed_count),
                message,
                int(run_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def create_month_run(
    month: str,
    workers: int,
    trade_day_count: int,
    symbol_count: int,
    message: str = "",
) -> int:
    ensure_sandbox_review_v2_schema()
    conn = get_meta_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO sandbox_backfill_month_runs (
                month, started_at, status, message, workers, trade_day_count, symbol_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                month,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "running",
                message,
                int(workers),
                int(trade_day_count),
                int(symbol_count),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def finish_month_run(
    month_run_id: int,
    status: str,
    total_rows: int,
    failed_count: int,
    message: str = "",
) -> None:
    ensure_sandbox_review_v2_schema()
    conn = get_meta_connection()
    try:
        conn.execute(
            """
            UPDATE sandbox_backfill_month_runs
            SET finished_at = ?, status = ?, total_rows = ?, failed_count = ?, message = ?
            WHERE id = ?
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status,
                int(total_rows),
                int(failed_count),
                message,
                int(month_run_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_month_run(month: str) -> Optional[Dict[str, object]]:
    ensure_sandbox_review_v2_schema()
    conn = get_meta_connection()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, month, started_at, finished_at, status, message,
                   workers, trade_day_count, symbol_count, total_rows, failed_count
            FROM sandbox_backfill_month_runs
            WHERE month = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(month),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def record_backfill_failures(
    run_id: int,
    failures: Sequence[Tuple[str, str, str, str]],
) -> None:
    if not failures:
        return
    ensure_sandbox_review_v2_schema()
    conn = get_meta_connection()
    try:
        conn.executemany(
            """
            INSERT INTO sandbox_backfill_failures (
                run_id, symbol, trade_date, source_file, error_message
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    int(run_id),
                    normalize_review_symbol(symbol),
                    trade_date,
                    source_file,
                    error_message,
                )
                for symbol, trade_date, source_file, error_message in failures
            ],
        )
        conn.commit()
    finally:
        conn.close()


def clear_symbol_review_rows(symbol: str) -> None:
    ensure_symbol_review_5m_schema(symbol)
    conn = get_symbol_connection(symbol)
    try:
        conn.execute(
            "DELETE FROM review_5m_bars WHERE symbol = ?",
            (normalize_review_symbol(symbol),),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_symbol_review_rows(symbol: str, rows: Sequence[Tuple]) -> int:
    if not rows:
        return 0
    normalized = normalize_review_symbol(symbol)
    ensure_symbol_review_5m_schema(normalized)
    conn = get_symbol_connection(normalized)
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO review_5m_bars (
                symbol, datetime, open, high, low, close, total_amount,
                l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
                l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell, source_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def symbol_has_review_rows(
    symbol: str,
    start_date: str,
    end_date: str,
) -> bool:
    normalized = normalize_review_symbol(symbol)
    db_path = get_symbol_db_path(normalized)
    if not os.path.exists(db_path):
        return False
    ensure_symbol_review_5m_schema(normalized)
    conn = get_symbol_connection(normalized)
    try:
        row = conn.execute(
            """
            SELECT count(*) FROM review_5m_bars
            WHERE symbol = ?
              AND datetime >= ?
              AND datetime < ?
            """,
            (
                normalized,
                _normalize_date_boundary(start_date),
                _normalize_date_boundary(end_date, end=True),
            ),
        ).fetchone()
        return bool(row and int(row[0]) > 0)
    finally:
        conn.close()


def symbol_has_review_date_rows(symbol: str, trade_date: str) -> bool:
    normalized = normalize_review_symbol(symbol)
    db_path = get_symbol_db_path(normalized)
    if not os.path.exists(db_path):
        return False
    ensure_symbol_review_5m_schema(normalized)
    conn = get_symbol_connection(normalized)
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM review_5m_bars
            WHERE symbol = ?
              AND source_date = ?
            LIMIT 1
            """,
            (normalized, trade_date),
        ).fetchone()
        return bool(row)
    finally:
        conn.close()


def get_symbol_review_dates(
    symbol: str,
    start_date: str,
    end_date: str,
) -> set[str]:
    normalized = normalize_review_symbol(symbol)
    db_path = get_symbol_db_path(normalized)
    if not os.path.exists(db_path):
        return set()
    ensure_symbol_review_5m_schema(normalized)
    conn = get_symbol_connection(normalized)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT source_date
            FROM review_5m_bars
            WHERE symbol = ?
              AND source_date >= ?
              AND source_date <= ?
            """,
            (normalized, start_date, end_date),
        ).fetchall()
        return {str(row[0]) for row in rows if row and row[0]}
    finally:
        conn.close()


def _normalize_date_boundary(date_text: str, end: bool = False) -> str:
    dt = datetime.strptime(date_text, "%Y-%m-%d")
    if end:
        dt = dt + timedelta(days=1)
    return dt.strftime("%Y-%m-%d 00:00:00")


def _fetch_symbol_5m_rows(symbol: str, start_date: str, end_date: str) -> List[Dict]:
    normalized = normalize_review_symbol(symbol)
    db_path = get_symbol_db_path(normalized)
    if not os.path.exists(db_path):
        return []
    ensure_symbol_review_5m_schema(normalized)
    conn = get_symbol_connection(normalized)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                symbol, datetime, open, high, low, close,
                total_amount,
                l1_main_buy, l1_main_sell,
                l1_super_buy, l1_super_sell,
                l2_main_buy, l2_main_sell,
                l2_super_buy, l2_super_sell,
                source_date
            FROM review_5m_bars
            WHERE symbol = ?
              AND datetime >= ?
              AND datetime < ?
            ORDER BY datetime ASC
            """,
            (
                normalized,
                _normalize_date_boundary(start_date),
                _normalize_date_boundary(end_date, end=True),
            ),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _finalize_rows(rows: Iterable[Dict], granularity: str) -> List[Dict]:
    out: List[Dict] = []
    for row in rows:
        item = dict(row)
        item["l1_main_net"] = float(item["l1_main_buy"]) - float(item["l1_main_sell"])
        item["l1_super_net"] = float(item["l1_super_buy"]) - float(item["l1_super_sell"])
        item["l2_main_net"] = float(item["l2_main_buy"]) - float(item["l2_main_sell"])
        item["l2_super_net"] = float(item["l2_super_buy"]) - float(item["l2_super_sell"])
        item["bucket_granularity"] = granularity
        out.append(item)
    return out


def query_review_bars(
    symbol: str,
    start_date: str,
    end_date: str,
    granularity: str = "5m",
) -> List[Dict]:
    normalized = normalize_review_symbol(symbol)
    if granularity not in ALLOWED_GRANULARITIES:
        raise ValueError(f"granularity 仅支持: {', '.join(sorted(ALLOWED_GRANULARITIES))}")

    rows = _fetch_symbol_5m_rows(normalized, start_date, end_date)
    if not rows:
        return []

    if granularity == "5m":
        return _finalize_rows(rows, "5m")

    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).sort_values("datetime")
    if df.empty:
        return []

    if granularity == "1d":
        df["bucket"] = pd.to_datetime(df["source_date"], errors="coerce")
    else:
        freq_map = {
            "15m": "15min",
            "30m": "30min",
            "60m": "60min",
        }
        df["bucket"] = df["datetime"].dt.floor(freq_map[granularity])

    grouped = (
        df.groupby("bucket", dropna=True)
        .agg(
            symbol=("symbol", "last"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            total_amount=("total_amount", "sum"),
            l1_main_buy=("l1_main_buy", "sum"),
            l1_main_sell=("l1_main_sell", "sum"),
            l1_super_buy=("l1_super_buy", "sum"),
            l1_super_sell=("l1_super_sell", "sum"),
            l2_main_buy=("l2_main_buy", "sum"),
            l2_main_sell=("l2_main_sell", "sum"),
            l2_super_buy=("l2_super_buy", "sum"),
            l2_super_sell=("l2_super_sell", "sum"),
            source_date=("source_date", "last"),
        )
        .reset_index()
        .sort_values("bucket")
    )

    if granularity == "1d":
        grouped["datetime"] = grouped["bucket"].dt.strftime("%Y-%m-%d") + " 15:00:00"
    else:
        grouped["datetime"] = grouped["bucket"].dt.strftime("%Y-%m-%d %H:%M:%S")

    merged_rows = grouped[
        [
            "symbol",
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "total_amount",
            "l1_main_buy",
            "l1_main_sell",
            "l1_super_buy",
            "l1_super_sell",
            "l2_main_buy",
            "l2_main_sell",
            "l2_super_buy",
            "l2_super_sell",
            "source_date",
        ]
    ].to_dict(orient="records")
    return _finalize_rows(merged_rows, granularity)
