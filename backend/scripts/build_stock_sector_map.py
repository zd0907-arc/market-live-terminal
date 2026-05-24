#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR, candidate_atomic_db_paths
from backend.app.services.market_heat import MARKET_HEAT_DIR, _symbol_norm, ensure_market_heat_dir

EASTMONEY_CLIST_URL = "https://79.push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_PLATE_URL = "https://datacenter.eastmoney.com/securities/api/data/get"
EASTMONEY_UT = "bd1d9ddb04089700cf9c27f6f7426281"
DEFAULT_DB_PATH = MARKET_HEAT_DIR / "stock_sector_map.db"
CACHE_DIR = MARKET_HEAT_DIR / "eastmoney_sector_cache"


def _get_json(params: Dict[str, Any], timeout: int = 15, retries: int = 3) -> Dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    }
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = requests.get(EASTMONEY_CLIST_URL, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("rc") == 0:
                return payload
            raise RuntimeError(f"eastmoney rc={payload.get('rc')} {payload.get('rt')}")
        except Exception as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Eastmoney request failed: {last_error}")


def _get_datacenter_json(params: Dict[str, Any], timeout: int = 15, retries: int = 3) -> Dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://emweb.securities.eastmoney.com/",
    }
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = requests.get(EASTMONEY_PLATE_URL, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("success", True) is not False:
                return payload
            raise RuntimeError(f"eastmoney datacenter success=false")
        except Exception as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Eastmoney datacenter request failed: {last_error}")


def _fetch_pages(fs: str, fields: str, page_size: int = 100) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    page = 1
    total = None
    while True:
        params = {
            "pn": page,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "ut": EASTMONEY_UT,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": fs,
            "fields": fields,
        }
        payload = _get_json(params)
        data = payload.get("data") or {}
        if total is None:
            total = int(data.get("total") or 0)
        diff = data.get("diff") or []
        if not diff:
            break
        out.extend(diff)
        if len(out) >= total:
            break
        page += 1
    return out


def _read_cache(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cache(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_boards(board_type: str, use_cache: bool = True) -> List[Dict[str, Any]]:
    cache_path = CACHE_DIR / f"boards_{board_type}.json"
    if board_type == "concept":
        fs = "m:90+t:3+f:!50"
    elif board_type == "industry":
        fs = "m:90+t:2+f:!50"
    else:
        raise ValueError(board_type)
    try:
        rows = _fetch_pages(fs, "f12,f14,f2,f3,f62")
        _write_cache(cache_path, rows)
    except Exception:
        if use_cache:
            cached = _read_cache(cache_path)
            if cached is not None:
                rows = cached
            else:
                raise
        else:
            raise
    out = []
    for row in rows:
        code = str(row.get("f12") or "").strip()
        name = str(row.get("f14") or "").strip()
        if not code or not name:
            continue
        out.append(
            {
                "sector_code": code,
                "sector_name": name,
                "sector_type": board_type,
                "price": row.get("f2"),
                "change_pct": row.get("f3"),
                "main_net_inflow": row.get("f62"),
            }
        )
    return out


def fetch_board_members(board: Dict[str, Any], page_size: int = 100, use_cache: bool = True) -> List[Dict[str, Any]]:
    cache_path = CACHE_DIR / f"members_{board['sector_type']}_{board['sector_code']}.json"
    try:
        rows = _fetch_pages(f"b:{board['sector_code']}", "f12,f14,f2,f3,f62", page_size=page_size)
        _write_cache(cache_path, rows)
    except Exception:
        if use_cache:
            cached = _read_cache(cache_path)
            if cached is not None:
                rows = cached
            else:
                raise
        else:
            raise
    out = []
    for row in rows:
        raw_code = str(row.get("f12") or "").strip()
        symbol = _symbol_norm(raw_code)
        if not symbol:
            continue
        out.append(
            {
                "symbol": symbol,
                "raw_code": raw_code,
                "name": str(row.get("f14") or "").strip(),
                "sector_code": board["sector_code"],
                "sector_name": board["sector_name"],
                "sector_type": board["sector_type"],
                "price": row.get("f2"),
                "change_pct": row.get("f3"),
                "main_net_inflow": row.get("f62"),
            }
        )
    return out


def _code6(symbol: str) -> str:
    text = str(symbol or "").strip().lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits if len(digits) == 6 else ""


def _secucode(symbol: str) -> str:
    code = _code6(symbol)
    if not code:
        return ""
    if str(symbol).lower().startswith("sh") or code.startswith(("60", "68", "51", "56", "58")):
        return f"{code}.SH"
    if str(symbol).lower().startswith("sz") or code.startswith(("00", "30", "15", "16", "18")):
        return f"{code}.SZ"
    if str(symbol).lower().startswith("bj") or code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def _normalize_plate_type(value: Any) -> str:
    text = str(value or "").strip()
    if text == "行业":
        return "industry"
    if text == "概念" or not text:
        return "concept"
    if text in {"板块", "地域", "地域板块"}:
        return "region"
    return text


def fetch_stock_plates(symbol: str, use_cache: bool = True) -> List[Dict[str, Any]]:
    symbol = _symbol_norm(symbol)
    secucode = _secucode(symbol)
    if not secucode:
        return []
    cache_path = CACHE_DIR / f"stock_plate_{symbol}.json"
    try:
        payload = _get_datacenter_json(
            {
                "type": "RPT_F10_CORETHEME_BOARDTYPE",
                "sty": "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_CODE,BOARD_NAME,IS_PRECISE,BOARD_RANK,BOARD_TYPE",
                "filter": f'(SECUCODE="{secucode}")',
                "p": 1,
                "ps": "",
                "sr": 1,
                "st": "BOARD_RANK",
                "source": "HSF10",
                "client": "PC",
                "v": str(int(time.time() * 1000)),
            }
        )
        rows = (payload.get("result") or {}).get("data") or []
        _write_cache(cache_path, rows)
    except Exception:
        if use_cache:
            cached = _read_cache(cache_path)
            if cached is not None:
                rows = cached
            else:
                raise
        else:
            raise
    out: List[Dict[str, Any]] = []
    for row in rows:
        board_code = str(row.get("BOARD_CODE") or "").strip()
        if not board_code:
            continue
        plate_code = "BK" + ("0000" + board_code)[-4:]
        out.append(
            {
                "symbol": symbol,
                "raw_code": _code6(symbol),
                "name": str(row.get("SECURITY_NAME_ABBR") or "").strip(),
                "sector_code": plate_code,
                "sector_name": str(row.get("BOARD_NAME") or plate_code).strip(),
                "sector_type": _normalize_plate_type(row.get("BOARD_TYPE")),
                "price": None,
                "change_pct": None,
                "main_net_inflow": None,
            }
        )
    return out


def load_stock_universe(limit: int = 0) -> List[str]:
    candidates = [Path(os.getenv("SELECTION_DB_PATH", os.path.join(DATA_DIR, "selection", "selection_research.db")))]
    explicit_atomic = str(os.getenv("ATOMIC_MAINBOARD_DB_PATH", "")).strip()
    if explicit_atomic:
        candidates.append(Path(explicit_atomic))
    for raw in candidate_atomic_db_paths():
        path = Path(str(raw))
        if path not in candidates:
            candidates.append(path)
    for db_path in candidates:
        if not db_path.exists():
            continue
        with sqlite3.connect(str(db_path), timeout=30) as conn:
            try:
                table = "selection_feature_daily" if "selection" in str(db_path) else "atomic_trade_daily"
                date_col = "trade_date"
                latest = conn.execute(f"SELECT MAX({date_col}) FROM {table}").fetchone()[0]
                rows = [str(r[0]) for r in conn.execute(f"SELECT DISTINCT symbol FROM {table} WHERE {date_col}=? ORDER BY symbol", (latest,))]
                if rows:
                    return rows[:limit] if limit > 0 else rows
            except Exception:
                continue
    return []


def build_from_stock_plates(symbols: List[str], fetched_at: str, sleep_seconds: float, use_cache: bool, strict: bool) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, str]]]:
    memberships: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for idx, symbol in enumerate(symbols, start=1):
        try:
            items = fetch_stock_plates(symbol, use_cache=use_cache)
            memberships.extend(items)
            print(f"[stock {idx}/{len(symbols)}] {symbol} plates={len(items)}")
        except Exception as exc:
            error = {"symbol": symbol, "error": str(exc)}
            errors.append(error)
            print(f"[ERROR] {error}", file=sys.stderr)
            if strict:
                raise
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    board_map: Dict[tuple[str, str], Dict[str, Any]] = {}
    for item in memberships:
        key = (item["sector_type"], item["sector_code"])
        board_map[key] = {
            "sector_code": item["sector_code"],
            "sector_name": item["sector_name"],
            "sector_type": item["sector_type"],
            "price": None,
            "change_pct": None,
            "main_net_inflow": None,
        }
    return list(board_map.values()), memberships, errors


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sector_boards (
                sector_code TEXT NOT NULL,
                sector_name TEXT NOT NULL,
                sector_type TEXT NOT NULL,
                price REAL,
                change_pct REAL,
                main_net_inflow REAL,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (sector_code, sector_type)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_sector_memberships (
                symbol TEXT NOT NULL,
                raw_code TEXT,
                name TEXT,
                sector_code TEXT NOT NULL,
                sector_name TEXT NOT NULL,
                sector_type TEXT NOT NULL,
                price REAL,
                change_pct REAL,
                main_net_inflow REAL,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (symbol, sector_code, sector_type)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_sector_symbol ON stock_sector_memberships(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_sector_sector ON stock_sector_memberships(sector_code, sector_type)")
        conn.commit()


def write_db(db_path: Path, boards: List[Dict[str, Any]], memberships: List[Dict[str, Any]], fetched_at: str) -> None:
    init_db(db_path)
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("DELETE FROM sector_boards")
        conn.execute("DELETE FROM stock_sector_memberships")
        conn.executemany(
            """
            INSERT OR REPLACE INTO sector_boards
            (sector_code, sector_name, sector_type, price, change_pct, main_net_inflow, source, fetched_at)
            VALUES (:sector_code, :sector_name, :sector_type, :price, :change_pct, :main_net_inflow, :source, :fetched_at)
            """,
            [{**b, "source": "eastmoney.push2", "fetched_at": fetched_at} for b in boards],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO stock_sector_memberships
            (symbol, raw_code, name, sector_code, sector_name, sector_type, price, change_pct, main_net_inflow, source, fetched_at)
            VALUES (:symbol, :raw_code, :name, :sector_code, :sector_name, :sector_type, :price, :change_pct, :main_net_inflow, :source, :fetched_at)
            """,
            [{**m, "source": "eastmoney.push2", "fetched_at": fetched_at} for m in memberships],
        )
        conn.commit()


def load_existing_db(db_path: Path, sector_types: Iterable[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    allowed = set(sector_types)
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        boards = [
            dict(row)
            for row in conn.execute(
                "SELECT sector_code, sector_name, sector_type, price, change_pct, main_net_inflow FROM sector_boards ORDER BY sector_type, sector_code"
            )
            if not allowed or row["sector_type"] in allowed
        ]
        memberships = [
            dict(row)
            for row in conn.execute(
                "SELECT symbol, raw_code, name, sector_code, sector_name, sector_type, price, change_pct, main_net_inflow FROM stock_sector_memberships ORDER BY symbol, sector_type, sector_code"
            )
            if not allowed or row["sector_type"] in allowed
        ]
    return boards, memberships


def write_json(boards: List[Dict[str, Any]], memberships: List[Dict[str, Any]], fetched_at: str) -> None:
    ensure_market_heat_dir()
    stock_map: Dict[str, Dict[str, Any]] = {}
    for item in memberships:
        symbol = item["symbol"]
        if symbol not in stock_map:
            stock_map[symbol] = {
                "symbol": symbol,
                "name": item.get("name"),
                "sectors": [],
            }
        stock_map[symbol]["sectors"].append(
            {
                "sector_code": item["sector_code"],
                "sector_name": item["sector_name"],
                "sector_type": item["sector_type"],
            }
        )
    payload = {
        "meta": {
            "generated_at": fetched_at,
            "source": "eastmoney.push2",
            "stock_count": len(stock_map),
            "membership_count": len(memberships),
            "board_count": len(boards),
        },
        "stocks": dict(sorted(stock_map.items())),
    }
    (MARKET_HEAT_DIR / "stock_sector_map_latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (MARKET_HEAT_DIR / "sector_boards_latest.json").write_text(
        json.dumps(
            {
                "meta": {
                    "generated_at": fetched_at,
                    "source": "eastmoney.push2",
                    "board_count": len(boards),
                },
                "boards": sorted(boards, key=lambda x: (x["sector_type"], x["sector_code"])),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local stock -> sector membership map from Eastmoney public quote APIs.")
    parser.add_argument("--source", choices=["board-members", "stock-plate"], default="stock-plate", help="stock-plate=逐股获取所属板块，更稳；board-members=逐板块获取成分股")
    parser.add_argument("--types", default="concept,industry", help="板块类型，逗号分隔：concept,industry")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="输出 SQLite 路径")
    parser.add_argument("--max-boards-per-type", type=int, default=0, help="调试用：每类最多抓多少个板块，0 表示全部")
    parser.add_argument("--limit-symbols", type=int, default=0, help="调试用：stock-plate 模式最多抓多少只股票，0 表示全部")
    parser.add_argument("--sleep", type=float, default=0.03, help="每个板块请求后的暂停秒数")
    parser.add_argument("--no-cache", action="store_true", help="禁用本地缓存读取/写入")
    parser.add_argument("--strict", action="store_true", help="任一板块失败即退出；默认记录失败并继续")
    parser.add_argument("--from-existing-db", action="store_true", help="不联网，直接从已有 SQLite 重建 JSON")
    args = parser.parse_args()

    fetched_at = datetime.now().isoformat(timespec="seconds")
    board_types = [x.strip() for x in args.types.split(",") if x.strip()]
    all_boards: List[Dict[str, Any]] = []
    all_members: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    if args.from_existing_db:
        all_boards, all_members = load_existing_db(Path(args.db_path), board_types)
        write_json(all_boards, all_members, fetched_at)
        unique_symbols = {m["symbol"] for m in all_members}
        print(f"rebuilt json from {args.db_path}")
        print(f"summary: boards={len(all_boards)} memberships={len(all_members)} stocks={len(unique_symbols)} fetched_at={fetched_at}")
        return
    if args.source == "stock-plate":
        symbols = load_stock_universe(limit=args.limit_symbols)
        if not symbols:
            raise RuntimeError("无法从 selection/atomic 数据库读取股票池")
        all_boards, all_members, errors = build_from_stock_plates(symbols, fetched_at, args.sleep, use_cache=not args.no_cache, strict=args.strict)
        allowed_types = set(board_types)
        if allowed_types:
            all_boards = [b for b in all_boards if b["sector_type"] in allowed_types]
            all_members = [m for m in all_members if m["sector_type"] in allowed_types]
        write_db(Path(args.db_path), all_boards, all_members, fetched_at)
        write_json(all_boards, all_members, fetched_at)
        if errors:
            (MARKET_HEAT_DIR / "stock_sector_map_errors_latest.json").write_text(json.dumps({"generated_at": fetched_at, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        unique_symbols = {m["symbol"] for m in all_members}
        print(f"wrote {args.db_path}")
        print(f"wrote {MARKET_HEAT_DIR / 'stock_sector_map_latest.json'}")
        print(f"wrote {MARKET_HEAT_DIR / 'sector_boards_latest.json'}")
        print(f"summary: source=stock-plate boards={len(all_boards)} memberships={len(all_members)} stocks={len(unique_symbols)} errors={len(errors)} fetched_at={fetched_at}")
        return
    for board_type in board_types:
        try:
            boards = fetch_boards(board_type, use_cache=not args.no_cache)
        except Exception as exc:
            if Path(args.db_path).exists() and not args.strict:
                print(f"[WARN] fetch boards failed for {board_type}; fallback to existing db: {exc}", file=sys.stderr)
                old_boards, old_members = load_existing_db(Path(args.db_path), [board_type])
                all_boards.extend(old_boards)
                all_members.extend(old_members)
                continue
            raise
        if args.max_boards_per_type > 0:
            boards = boards[: args.max_boards_per_type]
        all_boards.extend(boards)
        print(f"{board_type}: boards={len(boards)}")
        for idx, board in enumerate(boards, start=1):
            try:
                members = fetch_board_members(board, use_cache=not args.no_cache)
                all_members.extend(members)
                print(f"[{board_type} {idx}/{len(boards)}] {board['sector_code']} {board['sector_name']} members={len(members)}")
            except Exception as exc:
                error = {"sector_type": board_type, "sector_code": board["sector_code"], "sector_name": board["sector_name"], "error": str(exc)}
                errors.append(error)
                print(f"[ERROR] {error}", file=sys.stderr)
                if args.strict:
                    raise
            if args.sleep > 0:
                time.sleep(args.sleep)

    write_db(Path(args.db_path), all_boards, all_members, fetched_at)
    write_json(all_boards, all_members, fetched_at)
    if errors:
        (MARKET_HEAT_DIR / "stock_sector_map_errors_latest.json").write_text(json.dumps({"generated_at": fetched_at, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    unique_symbols = {m["symbol"] for m in all_members}
    print(f"wrote {args.db_path}")
    print(f"wrote {MARKET_HEAT_DIR / 'stock_sector_map_latest.json'}")
    print(f"wrote {MARKET_HEAT_DIR / 'sector_boards_latest.json'}")
    print(f"summary: boards={len(all_boards)} memberships={len(all_members)} stocks={len(unique_symbols)} errors={len(errors)} fetched_at={fetched_at}")


if __name__ == "__main__":
    main()
