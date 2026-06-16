#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parents[2]
FORMAL_MARKET_DATA_ROOT = Path(os.getenv("FORMAL_MARKET_DATA_ROOT", "/Users/dong/ZhangData/market-data"))
DEFAULT_RESEARCH_ROOT = FORMAL_MARKET_DATA_ROOT / "research" / "current"
DEFAULT_DATA_DIR = Path(os.getenv("DATA_DIR", str(DEFAULT_RESEARCH_ROOT if DEFAULT_RESEARCH_ROOT.is_dir() else FORMAL_MARKET_DATA_ROOT)))
DEFAULT_OUT_DB = Path(os.getenv("MODEL_INDEX_DB", str(DEFAULT_DATA_DIR / "selection" / "model_market_index_daily.db")))
EASTMONEY_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


@dataclass(frozen=True)
class IndexMeta:
    index_code: str
    index_name: str
    baostock_code: str
    eastmoney_secid: str


INDEXES: dict[str, IndexMeta] = {
    "000852.SH": IndexMeta("000852.SH", "中证1000", "sh.000852", "1.000852"),
    "000905.SH": IndexMeta("000905.SH", "中证500", "sh.000905", "1.000905"),
    "000300.SH": IndexMeta("000300.SH", "沪深300", "sh.000300", "1.000300"),
    "000001.SH": IndexMeta("000001.SH", "上证指数", "sh.000001", "1.000001"),
    "399006.SZ": IndexMeta("399006.SZ", "创业板指", "sz.399006", "0.399006"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync market index daily bars for model_feature_store.")
    parser.add_argument("--out-db", type=Path, default=DEFAULT_OUT_DB)
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Daily mode: refresh the last N calendar days and write into local cache DB.",
    )
    parser.add_argument("--lookback-days", type=int, default=10)
    parser.add_argument(
        "--index-code",
        action="append",
        default=[],
        help="Index code to sync; repeatable. Defaults to the five P0 market indexes.",
    )
    parser.add_argument(
        "--source",
        choices=["baostock", "eastmoney"],
        default="baostock",
        help="Primary data source. Baostock is the default; Eastmoney is a fallback.",
    )
    parser.add_argument("--sleep", type=float, default=0.35)
    return parser.parse_args()


def normalize_date(raw: str) -> str:
    text = str(raw or "").strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    datetime.strptime(text, "%Y-%m-%d")
    return text


def resolve_window(args: argparse.Namespace) -> tuple[str, str]:
    if args.daily:
        end = normalize_date(args.end_date) if args.end_date else date.today().isoformat()
        start = (datetime.strptime(end, "%Y-%m-%d").date() - timedelta(days=max(args.lookback_days, 1))).isoformat()
        if args.start_date:
            start = normalize_date(args.start_date)
        return start, end
    if not args.start_date or not args.end_date:
        raise SystemExit("非 daily 模式必须提供 --start-date 和 --end-date")
    start = normalize_date(args.start_date)
    end = normalize_date(args.end_date)
    if start > end:
        raise SystemExit("--start-date must be <= --end-date")
    return start, end


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_market_index_daily (
          index_code TEXT NOT NULL,
          index_name TEXT NOT NULL,
          trade_date TEXT NOT NULL,
          open REAL,
          high REAL,
          low REAL,
          close REAL NOT NULL,
          volume REAL,
          amount REAL,
          source TEXT NOT NULL,
          build_run_id TEXT,
          sync_run_id TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (index_code, trade_date)
        )
        """
    )
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(model_market_index_daily)").fetchall()}
    if "build_run_id" not in columns:
        conn.execute("ALTER TABLE model_market_index_daily ADD COLUMN build_run_id TEXT")
    if "sync_run_id" not in columns:
        conn.execute("ALTER TABLE model_market_index_daily ADD COLUMN sync_run_id TEXT")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE model_market_index_daily ADD COLUMN updated_at TEXT")
        conn.execute("UPDATE model_market_index_daily SET updated_at=COALESCE(created_at, CURRENT_TIMESTAMP)")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_market_index_daily_trade_date
        ON model_market_index_daily(trade_date)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_market_index_daily_sync_run_id
        ON model_market_index_daily(sync_run_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_market_index_sync_runs (
          run_id TEXT PRIMARY KEY,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          source TEXT NOT NULL,
          start_date TEXT NOT NULL,
          end_date TEXT NOT NULL,
          index_codes_json TEXT NOT NULL,
          status TEXT NOT NULL,
          rows_written INTEGER NOT NULL DEFAULT 0,
          summary_json TEXT,
          error_message TEXT
        )
        """
    )


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def backfill_row_metadata(conn: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(model_market_index_daily)").fetchall()}
    if "sync_run_id" not in columns:
        return
    if not table_exists(conn, "model_market_index_sync_runs"):
        return
    conn.execute(
        """
        UPDATE model_market_index_daily
        SET build_run_id = COALESCE(
              build_run_id,
              (
                SELECT r.run_id
                FROM model_market_index_sync_runs AS r
                WHERE r.status='success'
                  AND model_market_index_daily.trade_date BETWEEN r.start_date AND r.end_date
                ORDER BY r.started_at DESC
                LIMIT 1
              )
            ),
            sync_run_id = COALESCE(
              sync_run_id,
              build_run_id,
              (
                SELECT r.run_id
                FROM model_market_index_sync_runs AS r
                WHERE r.status='success'
                  AND model_market_index_daily.trade_date BETWEEN r.start_date AND r.end_date
                ORDER BY r.started_at DESC
                LIMIT 1
              )
            ),
            updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
        WHERE sync_run_id IS NULL OR sync_run_id = ''
        """
    )


def fetch_baostock(indexes: Iterable[IndexMeta], start_date: str, end_date: str) -> list[tuple]:
    try:
        import baostock as bs
    except ImportError as exc:
        raise RuntimeError("缺少 baostock，请先安装 backend/requirements.txt 或 pip install baostock") from exc

    login = bs.login()
    if getattr(login, "error_code", "") != "0":
        raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")

    rows: list[tuple] = []
    try:
        for meta in indexes:
            rs = bs.query_history_k_data_plus(
                meta.baostock_code,
                "date,code,open,high,low,close,volume,amount",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3",
            )
            if rs.error_code != "0":
                raise RuntimeError(f"baostock query failed {meta.baostock_code}: {rs.error_code} {rs.error_msg}")
            while rs.next():
                day, _code, open_, high, low, close, volume, amount = rs.get_row_data()
                if not close:
                    continue
                rows.append(
                    (
                        meta.index_code,
                        meta.index_name,
                        day,
                        float(open_) if open_ else None,
                        float(high) if high else None,
                        float(low) if low else None,
                        float(close),
                        float(volume) / 100.0 if volume else None,
                        float(amount) if amount else None,
                        f"baostock:{meta.baostock_code}",
                    )
                )
    finally:
        bs.logout()
    return rows


def fetch_eastmoney(indexes: Iterable[IndexMeta], start_date: str, end_date: str, sleep_seconds: float) -> list[tuple]:
    rows: list[tuple] = []
    beg = start_date.replace("-", "")
    end = end_date.replace("-", "")
    for meta in indexes:
        params = urlencode(
            {
                "secid": meta.eastmoney_secid,
                "klt": "101",
                "fqt": "0",
                "beg": beg,
                "end": end,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            }
        )
        request = Request(
            f"{EASTMONEY_URL}?{params}",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://quote.eastmoney.com/",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, 9):
            try:
                payload = json.loads(urlopen(request, timeout=45).read().decode("utf-8"))
                break
            except (RemoteDisconnected, TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == 8:
                    raise RuntimeError(f"eastmoney fetch failed {meta.index_code}: {last_error}") from exc
                time.sleep(max(sleep_seconds, 0.8) * attempt)
        else:
            raise RuntimeError(f"eastmoney fetch failed {meta.index_code}: {last_error}")
        data = payload.get("data") or {}
        for line in data.get("klines") or []:
            parts = line.split(",")
            if len(parts) < 7:
                continue
            day, open_, close, high, low, volume, amount = parts[:7]
            rows.append(
                (
                    meta.index_code,
                    data.get("name") or meta.index_name,
                    day,
                    float(open_),
                    float(high),
                    float(low),
                    float(close),
                    float(volume),
                    float(amount),
                    f"eastmoney:{meta.eastmoney_secid}",
                )
            )
        time.sleep(max(sleep_seconds, 0.0))
    return rows


def write_rows(conn: sqlite3.Connection, rows: list[tuple], run_id: str) -> int:
    conn.executemany(
        """
        INSERT OR REPLACE INTO model_market_index_daily (
          index_code, index_name, trade_date, open, high, low, close, volume, amount, source,
          build_run_id, sync_run_id, created_at, updated_at
        )
        VALUES (
          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
          ?,
          ?,
          COALESCE((SELECT created_at FROM model_market_index_daily WHERE index_code=? AND trade_date=?), CURRENT_TIMESTAMP),
          CURRENT_TIMESTAMP
        )
        """,
        [
            (
                *row,
                run_id,
                run_id,
                row[0],
                row[2],
            )
            for row in rows
        ],
    )
    return len(rows)


def summarize(conn: sqlite3.Connection, index_codes: list[str], start_date: str, end_date: str) -> dict[str, object]:
    summary: dict[str, object] = {}
    for code in index_codes:
        row = conn.execute(
            """
            SELECT COUNT(*) AS row_count, MIN(trade_date), MAX(trade_date)
            FROM model_market_index_daily
            WHERE index_code=? AND trade_date BETWEEN ? AND ?
            """,
            (code, start_date, end_date),
        ).fetchone()
        summary[code] = {
            "rows": int(row[0] or 0),
            "min_trade_date": row[1],
            "max_trade_date": row[2],
        }
    return summary


def main() -> None:
    args = parse_args()
    start_date, end_date = resolve_window(args)
    index_codes = args.index_code or list(INDEXES)
    unknown = [code for code in index_codes if code not in INDEXES]
    if unknown:
        raise SystemExit(f"unknown index_code: {unknown}; known={sorted(INDEXES)}")
    indexes = [INDEXES[code] for code in index_codes]
    run_id = f"index_sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    args.out_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(args.out_db) as conn:
        ensure_schema(conn)
        backfill_row_metadata(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO model_market_index_sync_runs (
              run_id, started_at, source, start_date, end_date, index_codes_json, status
            )
            VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, 'running')
            """,
            (run_id, args.source, start_date, end_date, json.dumps(index_codes, ensure_ascii=False)),
        )
        try:
            actual_source = args.source
            try:
                if args.source == "baostock":
                    rows = fetch_baostock(indexes, start_date, end_date)
                else:
                    rows = fetch_eastmoney(indexes, start_date, end_date, args.sleep)
            except RuntimeError as exc:
                if args.source == "baostock":
                    print(f"[warn] baostock failed, fallback to eastmoney: {exc}", file=sys.stderr)
                    rows = fetch_eastmoney(indexes, start_date, end_date, args.sleep)
                    actual_source = "eastmoney"
                else:
                    raise
            written = write_rows(conn, rows, run_id)
            report = summarize(conn, index_codes, start_date, end_date)
            conn.execute(
                """
                UPDATE model_market_index_sync_runs
                SET finished_at=CURRENT_TIMESTAMP, status='success', rows_written=?, summary_json=?
                WHERE run_id=?
                """,
                (written, json.dumps(report, ensure_ascii=False, sort_keys=True), run_id),
            )
            conn.execute(
                """
                UPDATE model_market_index_sync_runs
                SET source=?
                WHERE run_id=?
                """,
                (actual_source, run_id),
            )
            conn.commit()
        except Exception as exc:
            conn.execute(
                """
                UPDATE model_market_index_sync_runs
                SET finished_at=CURRENT_TIMESTAMP, status='failed', error_message=?
                WHERE run_id=?
                """,
                (str(exc), run_id),
            )
            conn.commit()
            raise

    print(
        json.dumps(
            {
                "run_id": run_id,
                "out_db": str(args.out_db),
                "source": actual_source,
                "start_date": start_date,
                "end_date": end_date,
                "index_codes": index_codes,
                "summary": report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
