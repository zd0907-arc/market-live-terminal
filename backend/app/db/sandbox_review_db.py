import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def get_sandbox_review_db_path() -> str:
    root_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    default_path = os.path.join(root_dir, "data", "sandbox_review.db")
    db_path = os.getenv("SANDBOX_REVIEW_DB_PATH", default_path)
    normalized = os.path.abspath(db_path)
    if os.path.basename(normalized) == "market_data.db":
        raise ValueError("SANDBOX_REVIEW_DB_PATH 不能指向 market_data.db")
    return normalized


def _ensure_parent_dir(db_path: str) -> None:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def get_sandbox_review_connection() -> sqlite3.Connection:
    db_path = get_sandbox_review_db_path()
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    return conn


def ensure_sandbox_review_schema() -> None:
    conn = get_sandbox_review_connection()
    try:
        cursor = conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_5m_bars (
                symbol TEXT NOT NULL,
                datetime TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                total_amount REAL NOT NULL DEFAULT 0,
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
                source_date TEXT NOT NULL,
                PRIMARY KEY(symbol, datetime)
            );

            CREATE INDEX IF NOT EXISTS idx_review_5m_symbol_datetime
            ON review_5m_bars(symbol, datetime);
            """
        )
        # 兼容旧库：补齐 total_amount 列
        cursor.execute("PRAGMA table_info(review_5m_bars)")
        columns = [row[1] for row in cursor.fetchall()]
        if "total_amount" not in columns:
            cursor.execute(
                "ALTER TABLE review_5m_bars ADD COLUMN total_amount REAL NOT NULL DEFAULT 0"
            )
        conn.commit()
    finally:
        conn.close()


def _normalize_date_boundary(date_text: str, end: bool = False) -> str:
    if end:
        dt = datetime.strptime(date_text, "%Y-%m-%d") + timedelta(days=1)
        return dt.strftime("%Y-%m-%d 00:00:00")
    return f"{date_text} 00:00:00"


def get_review_5m_bars(symbol: str, start_date: str, end_date: str) -> List[Dict]:
    ensure_sandbox_review_schema()
    conn = get_sandbox_review_connection()
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                symbol, datetime, open, high, low, close,
                total_amount,
                l1_main_buy, l1_main_sell, l1_main_net,
                l1_super_buy, l1_super_sell, l1_super_net,
                l2_main_buy, l2_main_sell, l2_main_net,
                l2_super_buy, l2_super_sell, l2_super_net,
                source_date
            FROM review_5m_bars
            WHERE symbol = ?
              AND datetime >= ?
              AND datetime < ?
            ORDER BY datetime ASC
            """,
            (symbol, _normalize_date_boundary(start_date), _normalize_date_boundary(end_date, end=True)),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
