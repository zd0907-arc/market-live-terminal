"""
刷新正式复盘股票元数据表 stock_universe_meta。

优先级：
1. 东方财富全市场快照接口（无 pandas / akshare 依赖）
2. akshare（若本地环境已安装）
3. 本地 selection/live 库兜底（只保证不为空，质量较弱）

用途：为 /api/review/pool 提供 name / market_cap / as_of_date。
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.config import DEFAULT_FORMAL_MARKET_DATA_ROOT, RESEARCH_CURRENT_ROOT
from backend.app.db.l2_history_db import replace_stock_universe_meta

EASTMONEY_QUOTE_API = "https://push2.eastmoney.com/webguest/api/qt/clist/get"
DEFAULT_MARKET_DB = Path(os.getenv("MARKET_DATA_ROOT", DEFAULT_FORMAL_MARKET_DATA_ROOT)) / "live" / "market_data.db"
DEFAULT_SELECTION_DB = Path(os.getenv("RESEARCH_CURRENT_ROOT", RESEARCH_CURRENT_ROOT)) / "selection" / "selection_research.db"


def _pick_col(columns: Sequence[str], keywords: Sequence[str]) -> str:
    for col in columns:
        text = str(col)
        if any(keyword in text for keyword in keywords):
            return text
    raise ValueError(f"未找到列: {keywords}")


def _normalize_code6(raw_code: object) -> str:
    text = str(raw_code or "").strip().lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits if len(digits) == 6 else ""


def _normalize_symbol(code6: str) -> str:
    if not code6:
        return ""
    if code6.startswith(("60", "68")):
        return f"sh{code6}"
    if code6.startswith(("00", "30")):
        return f"sz{code6}"
    if code6.startswith(("4", "8", "9")):
        return f"bj{code6}"
    return ""


def _as_float(value: object) -> float:
    if value in (None, "", "-"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_placeholder_name(symbol: str, name: object) -> bool:
    text = str(name or "").strip()
    return (not text) or text.lower() == str(symbol or "").lower()


def _load_json_payload(text: str) -> Dict[str, object]:
    body = str(text or "").strip()
    if not body:
        raise RuntimeError("empty payload")
    match = re.match(r"^[^(]+\((.*)\)\s*;?\s*$", body, flags=re.S)
    if match:
        body = match.group(1)
    return json.loads(body)


def _fetch_json(url: str, params: Dict[str, object], *, timeout: int = 20, retries: int = 3) -> Dict[str, object]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{url}?{query}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    last_exc: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            with opener.open(req, timeout=timeout) as resp:
                return _load_json_payload(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.RemoteDisconnected) as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            break
    try:
        cmd = [
            "curl",
            "--noproxy",
            "*",
            "-sG",
            "-H",
            "User-Agent: Mozilla/5.0",
            "-H",
            "Referer: https://quote.eastmoney.com/",
            url,
        ]
        for key, value in params.items():
            if value is not None:
                cmd.extend(["--data-urlencode", f"{key}={value}"])
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
        return _load_json_payload(proc.stdout)
    except Exception:
        if last_exc:
            raise last_exc
        raise
    raise RuntimeError(f"fetch failed: {last_exc}")


def fetch_stock_universe_rows_from_eastmoney(
    *,
    page_size: int = 500,
    include_bj: bool = False,
) -> Tuple[str, List[Tuple[str, str, float]], str]:
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    if include_bj:
        fs += ",m:0+t:81"
    params = {
        "pn": 1,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fltt": 1,
        "invt": 2,
        "fid": "f3",
        "fs": fs,
        "fields": "f12,f13,f14,f20",
        "cb": "jQuery1124",
        "dect": 1,
        "wbp2u": "|0|0|0|web",
    }
    first = _fetch_json(EASTMONEY_QUOTE_API, params)
    data = first.get("data") or {}
    rows_json = list(data.get("diff") or [])
    total = int(data.get("total") or 0)
    actual_page_size = len(rows_json) or int(page_size)
    pages = max(1, (total + actual_page_size - 1) // actual_page_size)
    for page in range(2, pages + 1):
        page_json = _fetch_json(EASTMONEY_QUOTE_API, {**params, "pn": page})
        rows_json.extend((page_json.get("data") or {}).get("diff") or [])
        time.sleep(0.03)

    rows: Dict[str, Tuple[str, str, float]] = {}
    for row in rows_json:
        code6 = _normalize_code6(row.get("f12"))
        symbol = _normalize_symbol(code6)
        if not symbol:
            continue
        name = str(row.get("f14") or symbol).strip() or symbol
        rows[symbol] = (symbol, name, _as_float(row.get("f20")))

    if not rows:
        raise RuntimeError("Eastmoney quote API 返回空表")

    as_of_date = datetime.now().strftime("%Y-%m-%d")
    ordered = sorted(rows.values(), key=lambda item: (item[2], item[0]), reverse=True)
    return as_of_date, ordered, "eastmoney.quote_clist"


def fetch_stock_universe_rows_from_akshare() -> Tuple[str, List[Tuple[str, str, float]], str]:
    import akshare as ak
    import pandas as pd

    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("ak.stock_zh_a_spot_em 返回空表")

    cols = [str(c) for c in df.columns]
    code_col = _pick_col(cols, ["代码"])
    name_col = _pick_col(cols, ["名称"])
    cap_col = _pick_col(cols, ["总市值", "市值"])

    codes = df[code_col].map(_normalize_code6)
    names = df[name_col].astype(str).str.strip()
    caps = pd.to_numeric(df[cap_col], errors="coerce")

    rows: Dict[str, Tuple[str, str, float]] = {}
    for code6, name, cap in zip(codes, names, caps):
        symbol = _normalize_symbol(code6)
        if not symbol:
            continue
        rows[symbol] = (symbol, str(name), 0.0 if pd.isna(cap) else float(cap))

    if not rows:
        raise RuntimeError("akshare.stock_zh_a_spot_em 返回空表")

    as_of_date = datetime.now().strftime("%Y-%m-%d")
    ordered = sorted(rows.values(), key=lambda item: (item[2], item[0]), reverse=True)
    return as_of_date, ordered, "akshare.stock_zh_a_spot_em"


def fetch_stock_universe_rows_from_local_snapshot(
    market_db_path: Path = DEFAULT_MARKET_DB,
    selection_db_path: Path = DEFAULT_SELECTION_DB,
) -> Tuple[str, List[Tuple[str, str, float]], str]:
    if not selection_db_path.exists():
        raise RuntimeError(f"selection db 不存在: {selection_db_path}")

    selection_conn = sqlite3.connect(str(selection_db_path))
    selection_conn.row_factory = sqlite3.Row
    market_conn: Optional[sqlite3.Connection] = None
    try:
        if market_db_path.exists():
            market_conn = sqlite3.connect(str(market_db_path))
            market_conn.row_factory = sqlite3.Row

        profile_map: Dict[str, Tuple[str, Optional[str]]] = {}
        if market_conn is not None:
            for row in market_conn.execute(
                """
                SELECT lower(symbol) AS symbol, short_name, company_name
                FROM stock_company_profiles
                """
            ).fetchall():
                profile_map[str(row["symbol"])] = (
                    str(row["short_name"] or "").strip(),
                    str(row["company_name"] or "").strip(),
                )

        latest_rows = selection_conn.execute(
            """
            SELECT f.symbol, f.name, COALESCE(f.market_cap, 0) AS market_cap, f.trade_date
            FROM selection_feature_daily AS f
            INNER JOIN (
                SELECT symbol, MAX(trade_date) AS max_trade_date
                FROM selection_feature_daily
                GROUP BY symbol
            ) AS x
              ON x.symbol = f.symbol
             AND x.max_trade_date = f.trade_date
            ORDER BY f.symbol
            """
        ).fetchall()
        if not latest_rows:
            raise RuntimeError("selection_feature_daily 返回空表")

        rows: List[Tuple[str, str, float]] = []
        as_of_date = ""
        for row in latest_rows:
            symbol = str(row["symbol"] or "").strip().lower()
            if not symbol:
                continue
            short_name, company_name = profile_map.get(symbol, ("", ""))
            selection_name = str(row["name"] or "").strip()
            name = short_name or company_name or selection_name or symbol
            if _is_placeholder_name(symbol, name):
                name = symbol
            rows.append((symbol, name, _as_float(row["market_cap"])))
            as_of_date = max(as_of_date, str(row["trade_date"] or ""))

        if not rows:
            raise RuntimeError("本地兜底未生成有效股票池")
        return as_of_date or datetime.now().strftime("%Y-%m-%d"), rows, "local.selection_feature_daily"
    finally:
        selection_conn.close()
        if market_conn is not None:
            market_conn.close()


def fetch_stock_universe_rows() -> Tuple[str, List[Tuple[str, str, float]], str]:
    errors: List[str] = []
    for loader in (
        fetch_stock_universe_rows_from_eastmoney,
        fetch_stock_universe_rows_from_akshare,
        fetch_stock_universe_rows_from_local_snapshot,
    ):
        try:
            return loader()
        except Exception as exc:
            errors.append(f"{loader.__name__}: {exc}")
    raise RuntimeError(" ; ".join(errors))


def refresh_stock_universe_meta(db_path: Optional[str] = None) -> dict:
    old_db_path = os.environ.get("DB_PATH")
    if db_path:
        os.environ["DB_PATH"] = os.path.abspath(db_path)
    as_of_date, rows, source = fetch_stock_universe_rows()
    try:
        inserted = replace_stock_universe_meta(rows, as_of_date=as_of_date, source=source)
        return {
            "as_of_date": as_of_date,
            "source": source,
            "rows": inserted,
            "db_path": os.getenv("DB_PATH"),
        }
    finally:
        if db_path:
            if old_db_path is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = old_db_path


def main() -> None:
    parser = argparse.ArgumentParser(description="刷新正式复盘股票元数据表 stock_universe_meta")
    parser.add_argument("--db-path", default="", help="可选目标 DB_PATH；默认使用正式 live/market_data.db")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    report = refresh_stock_universe_meta(db_path=args.db_path or None)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(
        f"[stock-universe-meta] as_of_date={report['as_of_date']} "
        f"rows={report['rows']} source={report['source']} db_path={report['db_path']}"
    )


if __name__ == "__main__":
    main()
