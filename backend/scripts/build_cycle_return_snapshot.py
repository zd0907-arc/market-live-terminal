#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import statistics
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "selection" / "selection_research.db"
EASTMONEY_QUOTE_API = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE_API = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


@dataclass(frozen=True)
class StockRef:
    symbol: str
    code: str
    name: str
    secid: str


def fetch_json(url: str, params: Dict[str, Any], *, timeout: int = 20, retries: int = 3) -> Dict[str, Any]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(
        f"{url}?{query}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    last_exc: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {last_exc}")


def as_float(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct(now: Optional[float], base: Optional[float]) -> Optional[float]:
    if now is None or base in (None, 0):
        return None
    return (now / base - 1.0) * 100.0


def market_symbol(code: str, market: Any) -> Tuple[str, str]:
    market_id = int(market)
    prefix = "sh" if market_id == 1 else "sz"
    return f"{prefix}{code}", f"{market_id}.{code}"


def fetch_stock_refs(page_size: int = 500, *, include_bj: bool = False) -> List[StockRef]:
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    if include_bj:
        fs += ",m:0+t:81"
    params = {
        "pn": 1,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": fs,
        "fields": "f12,f13,f14",
    }
    first = fetch_json(EASTMONEY_QUOTE_API, params)
    data = first.get("data") or {}
    rows = list(data.get("diff") or [])
    total = int(data.get("total") or 0)
    actual_page_size = len(rows) or page_size
    pages = max(1, math.ceil(total / actual_page_size))
    for page in range(2, pages + 1):
        page_json = fetch_json(EASTMONEY_QUOTE_API, {**params, "pn": page})
        rows.extend((page_json.get("data") or {}).get("diff") or [])
        time.sleep(0.03)
    refs: List[StockRef] = []
    for row in rows:
        code = str(row.get("f12") or "")
        if not code:
            continue
        symbol, secid = market_symbol(code, row.get("f13"))
        if not include_bj and code.startswith(("8", "4")):
            continue
        refs.append(StockRef(symbol=symbol, code=code, name=str(row.get("f14") or code), secid=secid))
    return refs


def parse_kline(line: str) -> Optional[Dict[str, Any]]:
    parts = line.split(",")
    if len(parts) < 11:
        return None
    return {
        "date": parts[0],
        "open": as_float(parts[1]),
        "close": as_float(parts[2]),
        "high": as_float(parts[3]),
        "low": as_float(parts[4]),
        "volume": as_float(parts[5]),
        "amount": as_float(parts[6]),
        "change_pct": as_float(parts[8]),
    }


def fetch_kline(ref: StockRef, begin: str, end: str, *, fqt: int) -> List[Dict[str, Any]]:
    data = fetch_json(
        EASTMONEY_KLINE_API,
        {
            "secid": ref.secid,
            "klt": "101",
            "fqt": fqt,
            "beg": begin,
            "end": end,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        },
    ).get("data") or {}
    return [row for line in (data.get("klines") or []) if (row := parse_kline(line))]


def close_on_or_before(rows: Sequence[Dict[str, Any]], date: str) -> Tuple[Optional[str], Optional[float]]:
    candidates = [row for row in rows if row["date"] <= date and row.get("close") is not None]
    if not candidates:
        return None, None
    row = candidates[-1]
    return row["date"], row["close"]


def close_on(rows: Sequence[Dict[str, Any]], date: str) -> Optional[float]:
    for row in rows:
        if row["date"] == date:
            return row.get("close")
    return None


def first_close_in_year(rows: Sequence[Dict[str, Any]], year: str, as_of_date: str) -> Tuple[Optional[str], Optional[float]]:
    for row in rows:
        if row["date"].startswith(year) and row["date"] <= as_of_date and row.get("close") is not None:
            return row["date"], row["close"]
    return None, None


def build_one(
    ref: StockRef,
    *,
    begin: str,
    end: str,
    as_of_date: str,
    fqt: int,
    cycle_baseline_month: str,
    policy_start_date: str,
    crash_low_date: str,
) -> Dict[str, Any]:
    rows = fetch_kline(ref, begin, end, fqt=fqt)
    if not rows:
        return {
            "symbol": ref.symbol,
            "code": ref.code,
            "name": ref.name,
            "trade_date": as_of_date,
            "requested_as_of_date": as_of_date,
            "data_status": "no_kline",
            "cycle_baseline_month": cycle_baseline_month,
            "policy_start_date": policy_start_date,
            "crash_low_date": crash_low_date,
        }
    actual_date, latest_close = close_on_or_before(rows, as_of_date)
    aug_rows = [
        row for row in rows
        if row["date"].startswith(cycle_baseline_month) and row.get("close") is not None
    ]
    aug_closes = [float(row["close"]) for row in aug_rows]
    aug_avg = statistics.fmean(aug_closes) if aug_closes else None
    aug_median = statistics.median(aug_closes) if aug_closes else None
    policy_close = close_on(rows, policy_start_date)
    crash_close = close_on(rows, crash_low_date)
    window = [row for row in rows if "2025-04-07" <= row["date"] <= "2025-04-10" and row.get("low") is not None]
    april_low_row = min(window, key=lambda r: float(r["low"])) if window else None
    year_start_date, year_start_close = first_close_in_year(rows, as_of_date[:4], as_of_date)
    since_rows = [row for row in rows if row["date"] >= f"{cycle_baseline_month}-01" and row["date"] <= as_of_date]
    max_close_row = max(
        (row for row in since_rows if row.get("close") is not None),
        key=lambda r: float(r["close"]),
        default=None,
    )
    max_high_row = max(
        (row for row in since_rows if row.get("high") is not None),
        key=lambda r: float(r["high"]),
        default=None,
    )
    status = "ok"
    if actual_date != as_of_date:
        status = "stale"
    if aug_avg is None:
        status = "no_aug_2024_baseline"
    max_close = None if max_close_row is None else float(max_close_row["close"])
    max_high = None if max_high_row is None else float(max_high_row["high"])
    return {
        "symbol": ref.symbol,
        "code": ref.code,
        "name": ref.name,
        "trade_date": actual_date or as_of_date,
        "requested_as_of_date": as_of_date,
        "data_status": status,
        "close": latest_close,
        "cycle_baseline_month": cycle_baseline_month,
        "baseline_avg_close": aug_avg,
        "baseline_median_close": aug_median,
        "baseline_trading_days": len(aug_closes),
        "policy_start_date": policy_start_date,
        "policy_start_close": policy_close,
        "crash_low_date": crash_low_date,
        "crash_low_close": crash_close,
        "april_2025_window_low": None if april_low_row is None else april_low_row.get("low"),
        "april_2025_window_low_date": None if april_low_row is None else april_low_row.get("date"),
        "year_start_date": year_start_date,
        "year_start_close": year_start_close,
        "return_from_baseline_avg_pct": pct(latest_close, aug_avg),
        "return_from_policy_start_pct": pct(latest_close, policy_close),
        "return_from_crash_low_pct": pct(latest_close, crash_close),
        "return_from_april_2025_window_low_pct": pct(latest_close, None if april_low_row is None else april_low_row.get("low")),
        "return_ytd_pct": pct(latest_close, year_start_close),
        "max_close_since_baseline": max_close,
        "max_close_since_baseline_date": None if max_close_row is None else max_close_row.get("date"),
        "max_return_since_baseline_pct": pct(max_close, aug_avg),
        "max_high_since_baseline": max_high,
        "max_high_since_baseline_date": None if max_high_row is None else max_high_row.get("date"),
        "max_high_return_since_baseline_pct": pct(max_high, aug_avg),
        "drawdown_from_cycle_high_pct": pct(latest_close, max_close),
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_cycle_return_daily (
            symbol TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            requested_as_of_date TEXT NOT NULL,
            code TEXT,
            name TEXT,
            data_status TEXT NOT NULL,
            close REAL,
            cycle_baseline_month TEXT NOT NULL,
            baseline_avg_close REAL,
            baseline_median_close REAL,
            baseline_trading_days INTEGER,
            policy_start_date TEXT,
            policy_start_close REAL,
            crash_low_date TEXT,
            crash_low_close REAL,
            april_2025_window_low REAL,
            april_2025_window_low_date TEXT,
            year_start_date TEXT,
            year_start_close REAL,
            return_from_baseline_avg_pct REAL,
            return_from_policy_start_pct REAL,
            return_from_crash_low_pct REAL,
            return_from_april_2025_window_low_pct REAL,
            return_ytd_pct REAL,
            max_close_since_baseline REAL,
            max_close_since_baseline_date TEXT,
            max_return_since_baseline_pct REAL,
            max_high_since_baseline REAL,
            max_high_since_baseline_date TEXT,
            max_high_return_since_baseline_pct REAL,
            drawdown_from_cycle_high_pct REAL,
            market_percentile_from_baseline REAL,
            market_percentile_ytd REAL,
            market_percentile_from_crash_low REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(symbol, requested_as_of_date, cycle_baseline_month)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_stock_cycle_return_daily_asof ON stock_cycle_return_daily(requested_as_of_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_stock_cycle_return_daily_baseline_return ON stock_cycle_return_daily(requested_as_of_date, return_from_baseline_avg_pct)"
    )


def percentile_map(rows: Sequence[Dict[str, Any]], field: str) -> Dict[str, float]:
    valid = sorted(
        ((row["symbol"], row.get(field)) for row in rows if row.get(field) is not None),
        key=lambda item: float(item[1]),
    )
    n = len(valid)
    if n <= 1:
        return {symbol: 100.0 for symbol, _ in valid}
    return {symbol: idx / (n - 1) * 100.0 for idx, (symbol, _) in enumerate(valid)}


def insert_rows(conn: sqlite3.Connection, rows: Sequence[Dict[str, Any]]) -> None:
    base_pct = percentile_map(rows, "return_from_baseline_avg_pct")
    ytd_pct = percentile_map(rows, "return_ytd_pct")
    crash_pct = percentile_map(rows, "return_from_crash_low_pct")
    columns = [
        "symbol", "trade_date", "requested_as_of_date", "code", "name", "data_status",
        "close", "cycle_baseline_month", "baseline_avg_close", "baseline_median_close",
        "baseline_trading_days", "policy_start_date", "policy_start_close",
        "crash_low_date", "crash_low_close", "april_2025_window_low",
        "april_2025_window_low_date", "year_start_date", "year_start_close",
        "return_from_baseline_avg_pct", "return_from_policy_start_pct",
        "return_from_crash_low_pct", "return_from_april_2025_window_low_pct",
        "return_ytd_pct", "max_close_since_baseline", "max_close_since_baseline_date",
        "max_return_since_baseline_pct", "max_high_since_baseline",
        "max_high_since_baseline_date", "max_high_return_since_baseline_pct",
        "drawdown_from_cycle_high_pct", "market_percentile_from_baseline",
        "market_percentile_ytd", "market_percentile_from_crash_low",
    ]
    sql = f"""
        INSERT OR REPLACE INTO stock_cycle_return_daily ({",".join(columns)})
        VALUES ({",".join("?" for _ in columns)})
    """
    for row in rows:
        enriched = dict(row)
        enriched["market_percentile_from_baseline"] = base_pct.get(row["symbol"])
        enriched["market_percentile_ytd"] = ytd_pct.get(row["symbol"])
        enriched["market_percentile_from_crash_low"] = crash_pct.get(row["symbol"])
        conn.execute(sql, [enriched.get(column) for column in columns])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build bull-cycle return waterline snapshot for A-share stocks.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of-date", default="2026-04-30")
    parser.add_argument("--begin", default="20240801")
    parser.add_argument("--baseline-month", default="2024-08")
    parser.add_argument("--policy-start-date", default="2024-09-24")
    parser.add_argument("--crash-low-date", default="2025-04-07")
    parser.add_argument("--fqt", type=int, default=1, help="Eastmoney adjustment: 1=qfq, 2=hfq, 0=raw")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--symbols", default="", help="comma separated symbols, e.g. sz001309,sz301308")
    parser.add_argument("--include-bj", action="store_true")
    args = parser.parse_args()

    refs = fetch_stock_refs(include_bj=args.include_bj)
    if args.symbols:
        wanted = {s.strip().lower() for s in args.symbols.split(",") if s.strip()}
        refs = [ref for ref in refs if ref.symbol.lower() in wanted]
    if args.limit > 0:
        refs = refs[: args.limit]
    if not refs:
        raise SystemExit("no symbols to process")

    end = args.as_of_date.replace("-", "")
    rows: List[Dict[str, Any]] = []
    failures: List[Tuple[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                build_one,
                ref,
                begin=args.begin,
                end=end,
                as_of_date=args.as_of_date,
                fqt=args.fqt,
                cycle_baseline_month=args.baseline_month,
                policy_start_date=args.policy_start_date,
                crash_low_date=args.crash_low_date,
            ): ref
            for ref in refs
        }
        for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            ref = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                failures.append((ref.symbol, repr(exc)))
            if idx % 200 == 0:
                print(f"[cycle-return] processed={idx}/{len(refs)} ok={len(rows)} failures={len(failures)}", flush=True)

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(args.db))
    try:
        ensure_schema(conn)
        insert_rows(conn, rows)
        conn.commit()
    finally:
        conn.close()
    print(
        json.dumps(
            {
                "db": str(args.db),
                "as_of_date": args.as_of_date,
                "baseline_month": args.baseline_month,
                "processed": len(refs),
                "inserted": len(rows),
                "failures": len(failures),
                "failure_samples": failures[:10],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
