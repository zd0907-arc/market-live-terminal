#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from http.client import RemoteDisconnected
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_OUT_DB = Path("/Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db")
EASTMONEY_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
INDEX_SOURCES = {
    "000852.SH": {"secid": "1.000852", "name": "中证1000"},
    "000905.SH": {"secid": "1.000905", "name": "中证500"},
    "000300.SH": {"secid": "1.000300", "name": "沪深300"},
    "000001.SH": {"secid": "1.000001", "name": "上证指数"},
    "399006.SZ": {"secid": "0.399006", "name": "创业板指"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync model index daily bars into a small SQLite index DB.")
    parser.add_argument("--out-db", type=Path, default=DEFAULT_OUT_DB)
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--index-code",
        action="append",
        default=[],
        help="Index code to sync; repeatable. Defaults to all P0 indexes.",
    )
    parser.add_argument("--sleep", type=float, default=0.2)
    return parser.parse_args()


def compact_date(date_text: str) -> str:
    return date_text.replace("-", "")


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
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (index_code, trade_date)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_market_index_daily_trade_date
        ON model_market_index_daily(trade_date)
        """
    )


def fetch_index(index_code: str, start_date: str, end_date: str) -> list[tuple]:
    meta = INDEX_SOURCES[index_code]
    params = urlencode(
        {
            "secid": meta["secid"],
            "klt": "101",
            "fqt": "0",
            "beg": compact_date(start_date),
            "end": compact_date(end_date),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        }
    )
    request = Request(f"{EASTMONEY_URL}?{params}", headers={"User-Agent": "Mozilla/5.0"})
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            payload = json.loads(urlopen(request, timeout=30).read().decode("utf-8"))
            break
        except (RemoteDisconnected, TimeoutError, URLError) as exc:
            last_error = exc
            if attempt == 3:
                raise
            time.sleep(0.8 * attempt)
    else:
        raise RuntimeError(f"failed to fetch {index_code}: {last_error}")
    data = payload.get("data") or {}
    name = data.get("name") or meta["name"]
    rows = []
    for line in data.get("klines") or []:
        parts = line.split(",")
        if len(parts) < 7:
            continue
        trade_date, open_, close, high, low, volume, amount = parts[:7]
        rows.append(
            (
                index_code,
                name,
                trade_date,
                float(open_),
                float(high),
                float(low),
                float(close),
                float(volume),
                float(amount),
                f"eastmoney:{meta['secid']}",
            )
        )
    return rows


def main() -> None:
    args = parse_args()
    index_codes = args.index_code or list(INDEX_SOURCES)
    unknown = [code for code in index_codes if code not in INDEX_SOURCES]
    if unknown:
        raise SystemExit(f"unknown index_code: {unknown}; known={sorted(INDEX_SOURCES)}")
    args.out_db.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with sqlite3.connect(args.out_db) as conn:
        ensure_schema(conn)
        for code in index_codes:
            rows = fetch_index(code, args.start_date, args.end_date)
            conn.executemany(
                """
                INSERT OR REPLACE INTO model_market_index_daily (
                  index_code, index_name, trade_date, open, high, low, close, volume, amount, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            total += len(rows)
            time.sleep(args.sleep)
    print(json.dumps({"out_db": str(args.out_db), "rows": total, "index_codes": index_codes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
