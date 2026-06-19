#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.backfill_atomic_order_from_raw import (
    TRADE_USECOLS,
    _apply_support_ratios,
    _build_order_rows,
    _read_csv,
    _replace_rows as replace_order_rows,
)
from backend.scripts.build_book_state_from_raw import build_book_rows, replace_book_rows
from backend.scripts.build_limit_state_from_atomic import build_limit_state, ensure_default_rules as ensure_limit_rules, ensure_schema as ensure_limit_schema, replace_rows as replace_limit_rows
from backend.scripts.build_open_auction_summaries import _build_l1_summary_from_frames, _build_l2_summary_from_frames, _build_manifest, _build_phase_l1_summary_from_frames, _build_phase_l2_summary_from_frames, _prepare_order_auction_df, _prepare_quote_auction_df, _prepare_trade_auction_df, _upsert as upsert_auction
from backend.app.db.l2_history_db import ensure_l2_history_schema
from backend.scripts.l2_daily_backfill import compute_5m_bars as compute_l2_history_5m_bars, compute_daily_row as compute_l2_history_daily_row
from backend.scripts.merge_l2_day_delta import merge_l2_day_delta
from backend.scripts.run_symbol_atomic_validation import (
    ATOMIC_INIT_SCRIPT,
    BOOK_STATE_SCHEMA,
    OPEN_AUCTION_PHASE_SCHEMA,
    OPEN_AUCTION_SCHEMA,
    WIN_7Z,
    _build_quality_info,
    _build_atomic_trade_5m_rows_from_l2,
    _build_atomic_trade_5m_rows_from_ticks,
    _build_atomic_trade_5m_rows_from_legacy,
    _build_atomic_trade_daily_row,
    _replace_trade_rows,
)
from backend.scripts.sandbox_review_etl import normalize_symbol
from backend.app.core.l2_package_layout import normalize_month_day_root
from backend.scripts.backfill_atomic_trade_from_raw import normalize_symbol_dir_name
from backend.scripts.backfill_atomic_order_from_raw import build_standardized_ticks_from_frames, load_l2_symbol_bundle

SHARD_MERGE_TABLES = [
    "atomic_trade_5m",
    "atomic_trade_daily",
    "atomic_order_5m",
    "atomic_order_daily",
    "atomic_book_state_5m",
    "atomic_book_state_daily",
    "atomic_open_auction_l1_daily",
    "atomic_open_auction_l2_daily",
    "atomic_open_auction_phase_l1_daily",
    "atomic_open_auction_phase_l2_daily",
    "atomic_open_auction_manifest",
]

L2_REQUIRED_FILES = ("行情.csv", "逐笔委托.csv", "逐笔成交.csv")


@dataclass(frozen=True)
class Batch:
    name: str
    kind: str
    date_from: str
    date_to: str


@dataclass(frozen=True)
class PendingTask:
    batch: Batch
    trade_date: str
    archive_path: Path


def daterange(date_from: str, date_to: str) -> List[str]:
    start = datetime.strptime(date_from, "%Y-%m-%d").date()
    end = datetime.strptime(date_to, "%Y-%m-%d").date()
    out: List[str] = []
    cur = start
    while cur <= end:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def to_compact(d: str) -> str:
    return d.replace("-", "")


def elapsed_seconds(started: float) -> float:
    return round(time.perf_counter() - started, 2)


def run_subprocess(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def ensure_atomic_db(atomic_db: Path) -> None:
    atomic_db.parent.mkdir(parents=True, exist_ok=True)
    if not atomic_db.exists():
        run_subprocess([sys.executable, str(ATOMIC_INIT_SCRIPT), "--atomic-db", str(atomic_db)])
    with sqlite3.connect(atomic_db) as conn:
        conn.executescript(OPEN_AUCTION_SCHEMA.read_text(encoding="utf-8"))
        conn.executescript(OPEN_AUCTION_PHASE_SCHEMA.read_text(encoding="utf-8"))
        conn.executescript(BOOK_STATE_SCHEMA.read_text(encoding="utf-8"))
        ensure_limit_schema(conn, include_5m=False)
        ensure_limit_rules(conn)
        conn.commit()


def _configure_sqlite_for_shard(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        conn.execute("PRAGMA journal_mode = MEMORY")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -200000")


def _ensure_l2_artifact_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    previous = os.environ.get("DB_PATH", "")
    os.environ["DB_PATH"] = str(db_path)
    try:
        ensure_l2_history_schema()
    finally:
        if previous:
            os.environ["DB_PATH"] = previous
        else:
            os.environ.pop("DB_PATH", None)


def _replace_l2_history_rows(
    conn: sqlite3.Connection,
    symbol: str,
    trade_date: str,
    rows_5m: Sequence[Tuple],
    daily_row: Optional[Tuple],
) -> Dict[str, int]:
    conn.execute("DELETE FROM history_5m_l2 WHERE symbol=? AND source_date=?", (symbol, trade_date))
    if rows_5m:
        conn.executemany(
            """
            INSERT INTO history_5m_l2 (
                symbol, datetime, source_date,
                open, high, low, close, total_amount, total_volume,
                l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
                l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell,
                l2_add_buy_amount, l2_add_sell_amount,
                l2_cancel_buy_amount, l2_cancel_sell_amount,
                l2_cvd_delta, l2_oib_delta,
                quality_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_5m,
        )
    conn.execute("DELETE FROM history_daily_l2 WHERE symbol=? AND date=?", (symbol, trade_date))
    if daily_row:
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
            daily_row,
        )
    return {"rows_5m": len(rows_5m), "rows_daily": 1 if daily_row else 0}


def _build_postclose_seed_rows(
    prepared,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
) -> Tuple[List[Tuple], Optional[Tuple], Optional[str]]:
    quality_info = _build_quality_info(prepared.diagnostics)
    rows_5m = compute_l2_history_5m_bars(
        prepared.ticks,
        prepared.order_events,
        symbol=prepared.symbol,
        trade_date=trade_date,
        large_threshold=large_threshold,
        super_threshold=super_threshold,
    )
    rows_with_quality = [tuple(list(row) + [quality_info]) for row in rows_5m]
    daily_row = compute_l2_history_daily_row(prepared.symbol, trade_date, rows_with_quality)
    return rows_with_quality, daily_row, quality_info


def _finalize_l2_shard_db(
    db_path: Path,
    trade_date: str,
    source_root: str,
    symbol_count: int,
    rows_5m: int,
    rows_daily: int,
    failures: Sequence[Tuple[str, str, str, str]],
) -> None:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO l2_daily_ingest_runs (
                trade_date, source_root, mode, status, started_at, finished_at, symbol_count, rows_5m, rows_daily, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_date,
                source_root,
                "daily_new_atomic_seed_shard",
                "done" if not failures else "partial_done",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                int(symbol_count),
                int(rows_5m),
                int(rows_daily),
                f"success={symbol_count}, failures={len(failures)}",
            ),
        )
        run_id = int(cursor.lastrowid)
        if failures:
            conn.executemany(
                """
                INSERT INTO l2_daily_ingest_failures (
                    run_id, symbol, trade_date, source_file, error_message
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [(run_id, symbol, trade_date, source_file, error_message) for symbol, trade_date, source_file, error_message in failures],
            )
        conn.commit()


def _write_legacy_rows_to_conn(
    conn: sqlite3.Connection,
    csv_path: Path,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
) -> Dict[str, object]:
    symbol = normalize_symbol(csv_path.name)
    if not symbol:
        raise ValueError(f"invalid legacy symbol file: {csv_path}")
    rows_5m, quality_info, daily_feature = _build_atomic_trade_5m_rows_from_legacy(
        csv_path, symbol, trade_date, large_threshold, super_threshold
    )
    daily = _build_atomic_trade_daily_row(symbol, trade_date, rows_5m, "trade_only", quality_info, daily_feature)
    stats = _replace_trade_rows(conn, rows_5m, daily) if daily else {"rows_5m": 0, "rows_daily": 0}
    return {"symbol": symbol, "rows_5m": len(rows_5m), **stats}


def _write_l2_rows_to_conn(
    conn: sqlite3.Connection,
    symbol_dir: Path,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
    l2_conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, object]:
    prepared = load_l2_symbol_bundle(symbol_dir, trade_date)
    symbol = prepared.symbol
    rows_5m_trade, quality_info, daily_feature = _build_atomic_trade_5m_rows_from_l2(
        symbol_dir, trade_date, large_threshold, super_threshold, prepared=prepared
    )
    daily_trade = _build_atomic_trade_daily_row(symbol, trade_date, rows_5m_trade, "trade_order", quality_info, daily_feature)
    _, rows_5m_order, daily_order, _ = _build_order_rows(symbol_dir, trade_date, prepared=prepared)
    rows_5m_book, daily_book = build_book_rows(symbol_dir, trade_date, quote_df=prepared.quote_raw)
    compact_trade_date = to_compact(trade_date)
    auction_trade_df = _prepare_trade_auction_df(prepared.trade_raw)
    auction_order_df = _prepare_order_auction_df(prepared.order_raw)
    auction_quote_df = _prepare_quote_auction_df(prepared.quote_raw)
    l1_row = _build_l1_summary_from_frames(symbol, compact_trade_date, auction_trade_df, auction_quote_df, prepared.quote_raw)
    l2_row = _build_l2_summary_from_frames(symbol, compact_trade_date, auction_trade_df, auction_order_df)
    phase_l1_row = _build_phase_l1_summary_from_frames(symbol, compact_trade_date, auction_trade_df, auction_quote_df)
    phase_l2_row = _build_phase_l2_summary_from_frames(symbol, compact_trade_date, auction_trade_df, auction_order_df)
    manifest = _build_manifest(l1_row, l2_row)
    trade_stats = _replace_trade_rows(conn, rows_5m_trade, daily_trade) if daily_trade else {"rows_5m": 0, "rows_daily": 0}
    total_amount = float(daily_trade[6]) if daily_trade else None
    daily_order = _apply_support_ratios(daily_order, total_amount)
    replace_order_rows(conn, rows_5m_order, daily_order)
    replace_book_rows(conn, rows_5m_book, daily_book)
    upsert_auction(conn, "atomic_open_auction_l1_daily", l1_row)
    upsert_auction(conn, "atomic_open_auction_l2_daily", l2_row)
    upsert_auction(conn, "atomic_open_auction_phase_l1_daily", phase_l1_row)
    upsert_auction(conn, "atomic_open_auction_phase_l2_daily", phase_l2_row)
    upsert_auction(conn, "atomic_open_auction_manifest", manifest)
    seed_stats: Dict[str, object] = {
        "postclose_seed_rows_5m": 0,
        "postclose_seed_rows_daily": 0,
        "postclose_seed_error": "",
    }
    if l2_conn is not None:
        try:
            l2_rows_5m, l2_daily_row, _ = _build_postclose_seed_rows(
                prepared,
                trade_date,
                large_threshold,
                super_threshold,
            )
            if l2_rows_5m and l2_daily_row is not None:
                l2_stats = _replace_l2_history_rows(l2_conn, symbol, trade_date, l2_rows_5m, l2_daily_row)
                seed_stats["postclose_seed_rows_5m"] = int(l2_stats["rows_5m"])
                seed_stats["postclose_seed_rows_daily"] = int(l2_stats["rows_daily"])
            else:
                seed_stats["postclose_seed_error"] = "no_l2_rows"
        except Exception as exc:
            seed_stats["postclose_seed_error"] = str(exc)
    return {
        "symbol": symbol,
        "rows_5m": len(rows_5m_trade),
        "order_5m_rows": len(rows_5m_order),
        "book_5m_rows": len(rows_5m_book),
        **trade_stats,
        **seed_stats,
    }


def _write_l2_trade_only_rows_to_conn(
    conn: sqlite3.Connection,
    symbol_dir: Path,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
) -> Dict[str, object]:
    trade = _read_csv(symbol_dir / "逐笔成交.csv", usecols=TRADE_USECOLS)
    symbol = normalize_symbol_dir_name(symbol_dir.name)
    import pandas as pd

    ticks = pd.DataFrame()
    time_text = trade["时间"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(9)
    hhmmss = time_text.str[:-3].str.zfill(6)
    ticks["time"] = hhmmss.str[0:2] + ":" + hhmmss.str[2:4] + ":" + hhmmss.str[4:6]
    session_mask = ((ticks["time"] >= "09:30:00") & (ticks["time"] <= "11:30:00")) | (
        (ticks["time"] >= "13:00:00") & (ticks["time"] <= "15:00:00")
    )
    trade = trade.loc[session_mask].reset_index(drop=True)
    ticks = ticks.loc[session_mask].reset_index(drop=True)
    ticks["datetime"] = pd.to_datetime(f"{trade_date} " + ticks["time"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    ticks["price"] = pd.to_numeric(trade["成交价格"], errors="coerce") / 10000
    ticks["volume"] = pd.to_numeric(trade["成交数量"], errors="coerce")
    ticks["side"] = trade["BS标志"].astype(str).str.strip().str.upper().map({"B": "buy", "S": "sell"}).fillna("neutral")
    ticks["amount"] = ticks["price"] * ticks["volume"]
    ticks["buy_order_id"] = 0
    ticks["sell_order_id"] = 0
    ticks = ticks.dropna(subset=["datetime", "price", "volume", "amount"])
    ticks = ticks[(ticks["price"] > 0) & (ticks["volume"] > 0) & (ticks["amount"] > 0)]
    ticks = ticks.sort_values("datetime").reset_index(drop=True)
    diagnostics = {
        "trade_rows": int(len(trade)),
        "ticks_rows": int(len(ticks)),
        "trade_date": trade_date,
        "sample_time_range": [
            ticks["time"].min() if not ticks.empty else None,
            ticks["time"].max() if not ticks.empty else None,
        ],
    }
    rows_5m_trade, daily_feature = _build_atomic_trade_5m_rows_from_ticks(
        ticks=ticks,
        symbol=symbol,
        trade_date=trade_date,
        large_threshold=large_threshold,
        super_threshold=super_threshold,
        source_type="trade_only",
        quality_info="l2_trade_only",
    )
    daily_trade = _build_atomic_trade_daily_row(symbol, trade_date, rows_5m_trade, "trade_only", "l2_trade_only", daily_feature)
    trade_stats = _replace_trade_rows(conn, rows_5m_trade, daily_trade) if daily_trade else {"rows_5m": 0, "rows_daily": 0}
    return {
        "symbol": symbol,
        "rows_5m": len(rows_5m_trade),
        "order_5m_rows": 0,
        "book_5m_rows": 0,
        **trade_stats,
    }


def load_config(path: Path) -> Dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("workers", 6)
    data.setdefault("large_threshold", 200000.0)
    data.setdefault("super_threshold", 1000000.0)
    data.setdefault("include_bj", False)
    data.setdefault("include_star", False)
    data.setdefault("include_gem", True)
    data.setdefault("main_board_only", False)
    data.setdefault("l2_trade_only", False)
    data.setdefault("prefetch_next_day_extract", False)
    data.setdefault("stop_on_failure", True)
    data.setdefault("max_failed_items_per_day", 0)
    data.setdefault("max_failed_item_ratio_per_day", 0.0)
    data.setdefault("cleanup_extracted", True)
    data.setdefault("symbols", [])
    data.setdefault("extract_patterns", [])
    data.setdefault("max_items_per_day", 0)
    data.setdefault("reuse_extracted_day_if_exists", False)
    data.setdefault("force_rerun_completed_days", False)
    data.setdefault("extractor", "auto")
    data.setdefault("selection_db", "")
    data.setdefault("postclose_seed_artifact_db", "")
    data.setdefault("stream_extract_process", False)
    data.setdefault("stream_process_batch_size", 64)
    data.setdefault("stream_poll_seconds", 0.5)
    data.setdefault("stream_ready_stable_seconds", 0.75)
    data.setdefault("state_file", str(path.with_name(path.stem + "_state.json")))
    data.setdefault("report_file", str(path.with_name(path.stem + "_report.json")))
    return data


def parse_batches(raw_batches: Sequence[Dict[str, object]]) -> List[Batch]:
    out: List[Batch] = []
    for item in raw_batches:
        out.append(Batch(name=str(item["name"]), kind=str(item["kind"]), date_from=str(item["date_from"]), date_to=str(item["date_to"])))
    return out


def in_scope(
    symbol: str,
    include_bj: bool,
    include_star: bool,
    include_gem: bool = True,
    main_board_only: bool = False,
) -> bool:
    s = (symbol or "").lower()
    if main_board_only:
        return s.startswith(("sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"))
    if s.startswith("bj"):
        return bool(include_bj)
    if s.startswith("sh688"):
        return bool(include_star)
    if s.startswith("sz300"):
        return bool(include_gem)
    return s.startswith(("sh", "sz"))


def discover_archive(kind: str, market_root: Path, trade_date: str) -> Optional[Path]:
    compact = to_compact(trade_date)
    if kind == "legacy":
        path = market_root / compact[:6] / f"{trade_date}.zip"
    else:
        path = market_root / compact[:6] / f"{compact}.7z"
    return path if path.exists() else None


def _legacy_member_name(symbol: str) -> str:
    return f"{symbol[2:]}.csv"


def _l2_member_prefix(symbol: str, trade_date: str) -> str:
    return f"{to_compact(trade_date)}\\{symbol[2:]}.{symbol[:2].upper()}\\*"


def _l2_member_pattern(pattern: str, trade_date: str) -> str:
    text = str(pattern or "").strip()
    if not text:
        return ""
    if "\\" in text or "/" in text:
        return text
    return f"{to_compact(trade_date)}\\{text}\\*"


def extract_archive(archive_path: Path, out_dir: Path, kind: str, trade_date: str, symbols: Sequence[str], extractor: str = "auto") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    normalized_symbols = [s.lower() for s in symbols if s]
    use_tar = extractor == "tar" or (extractor == "auto" and kind == "l2" and not normalized_symbols)
    if use_tar:
        subprocess.run(["tar", "-xf", str(archive_path), "-C", str(out_dir)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    cmd = [WIN_7Z, "x", "-y", str(archive_path)]
    if normalized_symbols:
        if kind == "legacy":
            cmd.extend([_legacy_member_name(s) for s in normalized_symbols])
        else:
            cmd.extend([_l2_member_prefix(s, trade_date) for s in normalized_symbols])
    cmd.append(f"-o{out_dir}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def extract_archive_with_config(
    archive_path: Path,
    out_dir: Path,
    kind: str,
    trade_date: str,
    config: Dict[str, object],
) -> None:
    patterns = [str(item) for item in config.get("extract_patterns", []) if str(item).strip()]
    if not patterns:
        extract_archive(archive_path, out_dir, kind, trade_date, config.get("symbols", []), str(config.get("extractor", "auto")))
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [WIN_7Z, "x", "-y", str(archive_path)]
    if kind == "legacy":
        cmd.extend(patterns)
    else:
        cmd.extend([item for item in (_l2_member_pattern(pattern, trade_date) for pattern in patterns) if item])
    cmd.append(f"-o{out_dir}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def list_legacy_csvs(
    day_dir: Path,
    include_bj: bool,
    include_star: bool,
    include_gem: bool = True,
    main_board_only: bool = False,
) -> List[Path]:
    result: List[Path] = []
    for child in sorted(day_dir.iterdir()):
        if not child.is_file() or child.suffix.lower() != ".csv":
            continue
        symbol = normalize_symbol(child.name)
        if not symbol or not in_scope(symbol, include_bj, include_star, include_gem, main_board_only):
            continue
        result.append(child)
    return result


def list_l2_symbol_dirs(
    day_dir: Path,
    include_bj: bool,
    include_star: bool,
    include_gem: bool = True,
    main_board_only: bool = False,
) -> List[Path]:
    root, _ = normalize_month_day_root(day_dir)
    result: List[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        symbol = normalize_symbol_dir_name(child.name)
        if not in_scope(symbol, include_bj, include_star, include_gem, main_board_only):
            continue
        result.append(child)
    return result


def apply_symbol_filter(items: Sequence[Path], symbols: Sequence[str], is_legacy: bool) -> List[Path]:
    if not symbols:
        return list(items)
    targets = {s.lower() for s in symbols}
    result: List[Path] = []
    for item in items:
        symbol = normalize_symbol(item.name) if is_legacy else normalize_symbol_dir_name(item.name)
        if symbol in targets:
            result.append(item)
    return result


def process_legacy_symbol(csv_path: Path, trade_date: str, atomic_db: Path, write_lock: threading.Lock, large_threshold: float, super_threshold: float) -> Dict[str, object]:
    with write_lock, sqlite3.connect(atomic_db) as conn:
        stats = _write_legacy_rows_to_conn(conn, csv_path, trade_date, large_threshold, super_threshold)
        conn.commit()
    return stats


def process_l2_symbol(symbol_dir: Path, trade_date: str, atomic_db: Path, write_lock: threading.Lock, large_threshold: float, super_threshold: float) -> Dict[str, object]:
    lock_cm = write_lock if write_lock is not None else threading.Lock()
    with lock_cm, sqlite3.connect(atomic_db) as conn:
        stats = _write_l2_rows_to_conn(conn, symbol_dir, trade_date, large_threshold, super_threshold)
        conn.commit()
    return stats


def _run_process_shard(
    kind: str,
    trade_date: str,
    atomic_db: str,
    item_paths: Sequence[str],
    large_threshold: float,
    super_threshold: float,
    l2_trade_only: bool = False,
    l2_shard_db: str = "",
) -> Dict[str, object]:
    shard_db = Path(atomic_db)
    if shard_db.exists():
        shard_db.unlink()
    ensure_atomic_db(shard_db)
    l2_db_path = Path(l2_shard_db) if l2_shard_db else None
    if l2_db_path is not None:
        if l2_db_path.exists():
            l2_db_path.unlink()
        _ensure_l2_artifact_db(l2_db_path)
    failures: List[Dict[str, str]] = []
    seed_failures: List[Tuple[str, str, str, str]] = []
    success_count = 0
    seed_success_count = 0
    seed_rows_5m_total = 0
    seed_rows_daily_total = 0
    if kind == "legacy":
        worker_fn = _write_legacy_rows_to_conn
    elif l2_trade_only:
        worker_fn = _write_l2_trade_only_rows_to_conn
    else:
        worker_fn = _write_l2_rows_to_conn
    l2_conn_cm = sqlite3.connect(l2_db_path) if l2_db_path is not None else contextlib.nullcontext()
    with sqlite3.connect(shard_db) as conn, l2_conn_cm as l2_conn:
        _configure_sqlite_for_shard(conn)
        if isinstance(l2_conn, sqlite3.Connection):
            _configure_sqlite_for_shard(l2_conn)
        commit_every = 64
        pending_since_commit = 0
        for raw_path in item_paths:
            item = Path(raw_path)
            try:
                result = worker_fn(
                    conn,
                    item,
                    trade_date,
                    large_threshold,
                    super_threshold,
                    l2_conn if worker_fn is _write_l2_rows_to_conn else None,
                ) if worker_fn is _write_l2_rows_to_conn else worker_fn(conn, item, trade_date, large_threshold, super_threshold)
                success_count += 1
                if isinstance(l2_conn, sqlite3.Connection) and worker_fn is _write_l2_rows_to_conn:
                    seed_rows_5m_total += int(result.get("postclose_seed_rows_5m") or 0)
                    seed_rows_daily_total += int(result.get("postclose_seed_rows_daily") or 0)
                    if int(result.get("postclose_seed_rows_daily") or 0) > 0:
                        seed_success_count += 1
                    elif str(result.get("postclose_seed_error") or "").strip():
                        seed_failures.append(
                            (
                                str(result.get("symbol") or normalize_symbol_dir_name(item.name)),
                                trade_date,
                                str(item),
                                str(result.get("postclose_seed_error") or ""),
                            )
                        )
                pending_since_commit += 1
                if pending_since_commit >= commit_every:
                    conn.commit()
                    if isinstance(l2_conn, sqlite3.Connection):
                        l2_conn.commit()
                    pending_since_commit = 0
            except Exception as exc:
                failures.append({"item": str(item), "error": repr(exc)})
        if pending_since_commit > 0:
            conn.commit()
            if isinstance(l2_conn, sqlite3.Connection):
                l2_conn.commit()
    if l2_db_path is not None:
        _finalize_l2_shard_db(
            l2_db_path,
            trade_date,
            source_root=str(shard_db.parent),
            symbol_count=seed_success_count,
            rows_5m=seed_rows_5m_total,
            rows_daily=seed_rows_daily_total,
            failures=seed_failures,
        )
    return {
        "success_count": success_count,
        "failure_count": len(failures),
        "failures": failures[:10],
        "postclose_seed_success_count": seed_success_count,
        "postclose_seed_rows_5m": seed_rows_5m_total,
        "postclose_seed_rows_daily": seed_rows_daily_total,
        "postclose_seed_failure_count": len(seed_failures),
    }


def _failure_policy(config: Dict[str, object], item_count: int, failure_count: int) -> Dict[str, object]:
    max_failed_items = int(config.get("max_failed_items_per_day", 0) or 0)
    max_failed_ratio = float(config.get("max_failed_item_ratio_per_day", 0.0) or 0.0)
    ratio = (failure_count / item_count) if item_count > 0 else 0.0
    checks: List[bool] = []
    if max_failed_items > 0:
        checks.append(failure_count <= max_failed_items)
    if max_failed_ratio > 0:
        checks.append(ratio <= max_failed_ratio)
    tolerated = failure_count > 0 and bool(checks) and all(checks)
    return {
        "max_failed_items_per_day": max_failed_items,
        "max_failed_item_ratio_per_day": max_failed_ratio,
        "failure_ratio": round(ratio, 6),
        "tolerated": tolerated,
    }


def _l2_symbol_dir_signature(symbol_dir: Path) -> Optional[Tuple[Tuple[str, int, int], ...]]:
    signature: List[Tuple[str, int, int]] = []
    for file_name in L2_REQUIRED_FILES:
        path = symbol_dir / file_name
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        if stat.st_size <= 0:
            return None
        signature.append((file_name, int(stat.st_size), int(stat.st_mtime_ns)))
    return tuple(signature)


def _accumulate_shard_result(
    shard_result: Dict[str, object],
    failures: List[Dict[str, str]],
    totals: Dict[str, int],
) -> None:
    totals["success"] += int(shard_result["success_count"])
    failures.extend(shard_result["failures"])
    totals["seed_success"] += int(shard_result.get("postclose_seed_success_count") or 0)
    totals["seed_rows_5m"] += int(shard_result.get("postclose_seed_rows_5m") or 0)
    totals["seed_rows_daily"] += int(shard_result.get("postclose_seed_rows_daily") or 0)
    totals["seed_failures"] += int(shard_result.get("postclose_seed_failure_count") or 0)


def _run_l2_stream_extract_process(
    *,
    batch: Batch,
    trade_date: str,
    archive_path: Path,
    config: Dict[str, object],
    atomic_db: Path,
    extract_root: Path,
    l2_day_root: Path,
    include_bj: bool,
    include_star: bool,
    include_gem: bool,
    main_board_only: bool,
    l2_trade_only: bool,
) -> Dict[str, object]:
    day_started = time.perf_counter()
    workers = max(1, int(config["workers"]))
    batch_size = max(1, int(config.get("stream_process_batch_size", 64) or 64))
    poll_seconds = max(0.1, float(config.get("stream_poll_seconds", 0.5) or 0.5))
    stable_seconds = max(0.0, float(config.get("stream_ready_stable_seconds", 0.75) or 0.75))
    seed_artifact_path = Path(str(config.get("postclose_seed_artifact_db") or "").strip()) if str(config.get("postclose_seed_artifact_db") or "").strip() else None
    shard_root = Path(str(config["extract_root"])) / ".worker_shards" / batch.name / to_compact(trade_date)
    shutil.rmtree(shard_root, ignore_errors=True)
    shard_root.mkdir(parents=True, exist_ok=True)
    if extract_root.exists():
        shutil.rmtree(extract_root, ignore_errors=True)
    extract_root.mkdir(parents=True, exist_ok=True)

    failures: List[Dict[str, str]] = []
    totals = {
        "success": 0,
        "seed_success": 0,
        "seed_rows_5m": 0,
        "seed_rows_daily": 0,
        "seed_failures": 0,
    }
    shard_dbs: List[Path] = []
    l2_shard_dbs: List[Path] = []
    ready_batch: List[Path] = []
    submitted_symbols = set()
    stable_state: Dict[str, Tuple[Tuple[Tuple[str, int, int], ...], float]] = {}
    extract_started = time.perf_counter()
    process_started: Optional[float] = None
    shard_idx = 0
    stderr_lines: List[str] = []

    print(
        f"[atomic-backfill] day={trade_date} batch={batch.name} kind={batch.kind} "
        f"stream_extract_start archive={archive_path} workers={workers} batch_size={batch_size}",
        flush=True,
    )
    proc = subprocess.Popen(
        ["tar", "-xf", str(archive_path), "-C", str(extract_root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def _read_stderr() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            text = line.strip()
            if text and len(stderr_lines) < 50:
                stderr_lines.append(text)

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    def _submit_chunk(executor: ProcessPoolExecutor, future_map: Dict[object, int], chunk: Sequence[Path]) -> None:
        nonlocal shard_idx, process_started
        if not chunk:
            return
        shard_idx += 1
        shard_db = shard_root / f"stream_{shard_idx}.db"
        l2_shard_db = shard_root / f"stream_{shard_idx}.seed_l2.db"
        shard_dbs.append(shard_db)
        use_l2_seed = bool(seed_artifact_path and batch.kind == "l2" and not l2_trade_only)
        if use_l2_seed:
            l2_shard_dbs.append(l2_shard_db)
        if process_started is None:
            process_started = time.perf_counter()
        future_map[
            executor.submit(
                _run_process_shard,
                batch.kind,
                trade_date,
                str(shard_db),
                [str(x) for x in chunk],
                float(config["large_threshold"]),
                float(config["super_threshold"]),
                l2_trade_only,
                str(l2_shard_db) if use_l2_seed else "",
            )
        ] = len(chunk)
        print(
            f"[atomic-backfill] day={trade_date} batch={batch.name} stream_submit "
            f"shard={shard_idx} items={len(chunk)} submitted={len(submitted_symbols)}",
            flush=True,
        )

    def _submit_ready(executor: ProcessPoolExecutor, future_map: Dict[object, int], *, force: bool = False) -> None:
        while len(ready_batch) >= batch_size or (force and ready_batch):
            chunk = ready_batch[:batch_size]
            del ready_batch[:batch_size]
            _submit_chunk(executor, future_map, chunk)

    def _drain_done(future_map: Dict[object, int]) -> None:
        for future in list(future_map):
            if not future.done():
                continue
            shard_result = future.result()
            _accumulate_shard_result(shard_result, failures, totals)
            future_map.pop(future, None)
            print(
                f"[atomic-backfill] day={trade_date} batch={batch.name} shard_done "
                f"success={totals['success']} failure={len(failures)} "
                f"process_sec={elapsed_seconds(process_started or time.perf_counter())}",
                flush=True,
            )

    def _scan_ready_dirs() -> None:
        if not l2_day_root.exists():
            return
        now = time.perf_counter()
        for child in sorted(l2_day_root.iterdir()):
            if not child.is_dir():
                continue
            symbol = normalize_symbol_dir_name(child.name)
            if symbol in submitted_symbols:
                continue
            if not in_scope(symbol, include_bj, include_star, include_gem, main_board_only):
                continue
            signature = _l2_symbol_dir_signature(child)
            if signature is None:
                continue
            previous = stable_state.get(symbol)
            if previous and previous[0] == signature:
                if now - previous[1] >= stable_seconds:
                    ready_batch.append(child)
                    submitted_symbols.add(symbol)
                    stable_state.pop(symbol, None)
            else:
                stable_state[symbol] = (signature, now)

    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_map: Dict[object, int] = {}
            while True:
                _scan_ready_dirs()
                _submit_ready(executor, future_map)
                _drain_done(future_map)
                returncode = proc.poll()
                if returncode is not None:
                    break
                time.sleep(poll_seconds)

            stderr_thread.join(timeout=1.0)
            extract_elapsed = elapsed_seconds(extract_started)
            if returncode != 0:
                raise RuntimeError(
                    "流式解压失败: "
                    + json.dumps({"returncode": returncode, "stderr": stderr_lines[-10:]}, ensure_ascii=False)
                )
            print(
                f"[atomic-backfill] day={trade_date} batch={batch.name} stream_extract_done "
                f"extract_sec={extract_elapsed} submitted={len(submitted_symbols)}",
                flush=True,
            )

            list_started = time.perf_counter()
            final_items = list_l2_symbol_dirs(l2_day_root, include_bj, include_star, include_gem, main_board_only)
            list_elapsed = elapsed_seconds(list_started)
            for item in final_items:
                symbol = normalize_symbol_dir_name(item.name)
                if symbol in submitted_symbols:
                    continue
                ready_batch.append(item)
                submitted_symbols.add(symbol)
            _submit_ready(executor, future_map, force=True)
            while future_map:
                _drain_done(future_map)
                if future_map:
                    time.sleep(0.2)
    except Exception:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        stderr_thread.join(timeout=1.0)
        raise

    process_elapsed = elapsed_seconds(process_started) if process_started is not None else 0.0
    print(f"[atomic-backfill] day={trade_date} batch={batch.name} merge_start shard_db_count={len(shard_dbs)}", flush=True)
    merge_started = time.perf_counter()
    _merge_shard_tables(atomic_db, shard_dbs)
    merge_elapsed = elapsed_seconds(merge_started)
    seed_merge_report = None
    if seed_artifact_path is not None and l2_shard_dbs:
        if seed_artifact_path.exists():
            seed_artifact_path.unlink()
        seed_merge_report = merge_l2_day_delta(
            trade_date=trade_date,
            artifact_paths=[str(path) for path in l2_shard_dbs if path.exists()],
            db_path=str(seed_artifact_path),
            source_root=str(extract_root),
            mode="daily_new_atomic_seed",
            message=f"artifact_count={len(l2_shard_dbs)}",
        )
    total_elapsed = elapsed_seconds(day_started)
    print(f"[atomic-backfill] day={trade_date} batch={batch.name} merge_done merge_sec={merge_elapsed}", flush=True)
    print(
        f"[atomic-backfill] day={trade_date} batch={batch.name} worker_done "
        f"success={totals['success']} failure={len(failures)} total_sec={total_elapsed}",
        flush=True,
    )
    failure_policy = _failure_policy(config, len(final_items), len(failures))
    report = {
        "batch": batch.name,
        "kind": batch.kind,
        "trade_date": trade_date,
        "archive_path": str(archive_path),
        "item_count": len(final_items),
        "success_count": totals["success"],
        "failure_count": len(failures),
        "failures": failures[:20],
        "failure_policy": failure_policy,
        "timing_seconds": {
            "extract": extract_elapsed,
            "list_items": list_elapsed,
            "process_shards": process_elapsed,
            "merge_shards": merge_elapsed,
            "total": total_elapsed,
        },
        "stream_extract_process": True,
        "postclose_seed_artifact": (
            {
                **seed_merge_report,
                "db_path": str(seed_artifact_path),
                "seed_success_count": totals["seed_success"],
                "seed_failure_count": totals["seed_failures"],
            }
            if seed_merge_report is not None and seed_artifact_path is not None
            else None
        ),
    }
    if failures and failure_policy["tolerated"]:
        print(
            f"[atomic-backfill] day={trade_date} batch={batch.name} tolerated_failures="
            f"{len(failures)} ratio={failure_policy['failure_ratio']}",
            flush=True,
        )
    if failures and bool(config.get("stop_on_failure", True)) and not failure_policy["tolerated"]:
        raise RuntimeError(json.dumps(report, ensure_ascii=False))
    return report


def _merge_shard_tables(target_db: Path, shard_dbs: Sequence[Path]) -> None:
    with sqlite3.connect(target_db) as conn:
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        for idx, shard_db in enumerate(shard_dbs, start=1):
            if not shard_db.exists():
                continue
            alias = f"shard_{idx}"
            shard_path = shard_db.resolve().as_posix().replace("'", "''")
            print(f"[atomic-backfill] merge_shard_start target={target_db} shard={shard_path}", flush=True)
            conn.execute(f"ATTACH DATABASE '{shard_path}' AS {alias}")
            try:
                for table in SHARD_MERGE_TABLES:
                    conn.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM {alias}.{table}")
                conn.commit()
            finally:
                conn.execute(f"DETACH DATABASE {alias}")
            print(f"[atomic-backfill] merge_shard_done target={target_db} shard={shard_path}", flush=True)


def _prefetch_extract_root(batch_name: str, trade_date: str, config: Dict[str, object]) -> Path:
    return Path(str(config["extract_root"])) / batch_name / to_compact(trade_date)


def _prefetch_can_reuse(batch: Batch, trade_date: str, config: Dict[str, object]) -> bool:
    extract_root = _prefetch_extract_root(batch.name, trade_date, config)
    l2_day_root = extract_root / to_compact(trade_date)
    return bool(config.get("reuse_extracted_day_if_exists", False)) and (
        (batch.kind == "legacy" and extract_root.exists() and any(extract_root.glob("*.csv")))
        or (batch.kind == "l2" and l2_day_root.exists())
    )


def _prefetch_extract_task(task: PendingTask, config: Dict[str, object]) -> None:
    if _prefetch_can_reuse(task.batch, task.trade_date, config):
        return
    extract_root = _prefetch_extract_root(task.batch.name, task.trade_date, config)
    print(
        f"[atomic-backfill] prefetch_start day={task.trade_date} batch={task.batch.name} archive={task.archive_path}",
        flush=True,
    )
    extract_archive_with_config(task.archive_path, extract_root, task.batch.kind, task.trade_date, config)
    print(f"[atomic-backfill] prefetch_done day={task.trade_date} batch={task.batch.name}", flush=True)


def run_day(
    batch: Batch,
    trade_date: str,
    archive_path: Path,
    config: Dict[str, object],
    atomic_db: Path,
    next_task: Optional[PendingTask] = None,
) -> Tuple[Dict[str, object], Optional[threading.Thread], Optional[str]]:
    day_started = time.perf_counter()
    extract_root = Path(str(config["extract_root"])) / batch.name / to_compact(trade_date)
    cleanup_extracted = bool(config.get("cleanup_extracted", True))
    include_bj = bool(config.get("include_bj", False))
    include_star = bool(config.get("include_star", False))
    include_gem = bool(config.get("include_gem", True))
    main_board_only = bool(config.get("main_board_only", False))
    l2_trade_only = bool(config.get("l2_trade_only", False))
    reuse_extracted = bool(config.get("reuse_extracted_day_if_exists", False))
    l2_day_root = extract_root / to_compact(trade_date)
    configured_symbols = [str(item).strip() for item in config.get("symbols", []) if str(item).strip()]
    configured_patterns = [str(item).strip() for item in config.get("extract_patterns", []) if str(item).strip()]
    max_items = int(config.get("max_items_per_day", 0) or 0)
    can_reuse = reuse_extracted and (
        (batch.kind == "legacy" and extract_root.exists() and any(extract_root.glob("*.csv")))
        or (batch.kind == "l2" and l2_day_root.exists())
    )
    stream_requested = bool(config.get("stream_extract_process", False))
    stream_supported = (
        stream_requested
        and batch.kind == "l2"
        and not can_reuse
        and not configured_symbols
        and not configured_patterns
        and max_items <= 0
        and not bool(config.get("prefetch_next_day_extract", False))
    )
    if stream_requested and not stream_supported:
        print(
            f"[atomic-backfill] day={trade_date} batch={batch.name} stream_extract_process_fallback=1 "
            f"kind={batch.kind} reuse={int(can_reuse)} symbols={len(configured_symbols)} "
            f"patterns={len(configured_patterns)} max_items={max_items} "
            f"prefetch={int(bool(config.get('prefetch_next_day_extract', False)))}",
            flush=True,
        )
    if stream_supported:
        try:
            report = _run_l2_stream_extract_process(
                batch=batch,
                trade_date=trade_date,
                archive_path=archive_path,
                config=config,
                atomic_db=atomic_db,
                extract_root=extract_root,
                l2_day_root=l2_day_root,
                include_bj=include_bj,
                include_star=include_star,
                include_gem=include_gem,
                main_board_only=main_board_only,
                l2_trade_only=l2_trade_only,
            )
            return report, None, None
        finally:
            shutil.rmtree(Path(str(config["extract_root"])) / ".worker_shards" / batch.name / to_compact(trade_date), ignore_errors=True)
            if cleanup_extracted:
                shutil.rmtree(extract_root, ignore_errors=True)
    if can_reuse:
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} kind={batch.kind} reuse_extracted=1 root={extract_root}", flush=True)
        extract_elapsed = 0.0
    else:
        extract_started = time.perf_counter()
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} kind={batch.kind} extract_start archive={archive_path}", flush=True)
        extract_archive_with_config(archive_path, extract_root, batch.kind, trade_date, config)
        extract_elapsed = elapsed_seconds(extract_started)
    try:
        list_started = time.perf_counter()
        if batch.kind == "legacy":
            items = list_legacy_csvs(extract_root, include_bj, include_star, include_gem, main_board_only)
            items = apply_symbol_filter(items, config.get("symbols", []), is_legacy=True)
        else:
            items = list_l2_symbol_dirs(l2_day_root, include_bj, include_star, include_gem, main_board_only)
            items = apply_symbol_filter(items, config.get("symbols", []), is_legacy=False)
        if max_items > 0:
            items = items[:max_items]
        list_elapsed = elapsed_seconds(list_started)
        print(
            f"[atomic-backfill] day={trade_date} batch={batch.name} extract_done "
            f"item_count={len(items)} workers={config['workers']} l2_trade_only={int(l2_trade_only)} "
            f"extract_sec={extract_elapsed} list_sec={list_elapsed}",
            flush=True,
        )
        prefetch_thread: Optional[threading.Thread] = None
        prefetch_key: Optional[str] = None
        if next_task and bool(config.get("prefetch_next_day_extract", False)):
            prefetch_key = f"{next_task.batch.name}:{next_task.trade_date}"
            if not _prefetch_can_reuse(next_task.batch, next_task.trade_date, config):
                prefetch_thread = threading.Thread(
                    target=_prefetch_extract_task,
                    args=(next_task, config),
                    daemon=True,
                )
                prefetch_thread.start()

        failures: List[Dict[str, str]] = []
        workers = max(1, int(config["workers"]))
        shard_root = Path(str(config["extract_root"])) / ".worker_shards" / batch.name / to_compact(trade_date)
        shutil.rmtree(shard_root, ignore_errors=True)
        shard_root.mkdir(parents=True, exist_ok=True)
        shards = [items[i::workers] for i in range(workers)]
        shard_dbs = [shard_root / f"worker_{idx+1}.db" for idx in range(workers) if shards[idx]]
        seed_artifact_path = Path(str(config.get("postclose_seed_artifact_db") or "").strip()) if str(config.get("postclose_seed_artifact_db") or "").strip() else None
        l2_shard_dbs = [shard_root / f"worker_{idx+1}.seed_l2.db" for idx in range(workers) if shards[idx]] if (seed_artifact_path and batch.kind == "l2" and not l2_trade_only) else []
        total_success = 0
        total_seed_success = 0
        total_seed_rows_5m = 0
        total_seed_rows_daily = 0
        total_seed_failures = 0
        process_started = time.perf_counter()
        if workers == 1:
            print(f"[atomic-backfill] day={trade_date} batch={batch.name} shard_mode=single", flush=True)
            shard_result = _run_process_shard(
                batch.kind,
                trade_date,
                str(shard_dbs[0]),
                [str(x) for x in shards[0]],
                float(config["large_threshold"]),
                float(config["super_threshold"]),
                l2_trade_only,
                str(l2_shard_dbs[0]) if l2_shard_dbs else "",
            )
            total_success += int(shard_result["success_count"])
            failures.extend(shard_result["failures"])
            total_seed_success += int(shard_result.get("postclose_seed_success_count") or 0)
            total_seed_rows_5m += int(shard_result.get("postclose_seed_rows_5m") or 0)
            total_seed_rows_daily += int(shard_result.get("postclose_seed_rows_daily") or 0)
            total_seed_failures += int(shard_result.get("postclose_seed_failure_count") or 0)
        else:
            print(f"[atomic-backfill] day={trade_date} batch={batch.name} shard_mode=process workers={workers}", flush=True)
            with ProcessPoolExecutor(max_workers=workers) as executor:
                future_map = {}
                shard_idx = 0
                for shard in shards:
                    if not shard:
                        continue
                    future_map[
                        executor.submit(
                            _run_process_shard,
                            batch.kind,
                            trade_date,
                            str(shard_dbs[shard_idx]),
                            [str(x) for x in shard],
                            float(config["large_threshold"]),
                            float(config["super_threshold"]),
                            l2_trade_only,
                            str(l2_shard_dbs[shard_idx]) if l2_shard_dbs else "",
                        )
                    ] = shard_idx
                    shard_idx += 1
                for future in as_completed(future_map):
                    shard_result = future.result()
                    total_success += int(shard_result["success_count"])
                    failures.extend(shard_result["failures"])
                    total_seed_success += int(shard_result.get("postclose_seed_success_count") or 0)
                    total_seed_rows_5m += int(shard_result.get("postclose_seed_rows_5m") or 0)
                    total_seed_rows_daily += int(shard_result.get("postclose_seed_rows_daily") or 0)
                    total_seed_failures += int(shard_result.get("postclose_seed_failure_count") or 0)
                    print(
                        f"[atomic-backfill] day={trade_date} batch={batch.name} shard_done "
                        f"success={total_success}/{len(items)} failure={len(failures)} "
                        f"process_sec={elapsed_seconds(process_started)}",
                        flush=True,
                    )
        process_elapsed = elapsed_seconds(process_started)
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} merge_start shard_db_count={len(shard_dbs)}", flush=True)
        merge_started = time.perf_counter()
        _merge_shard_tables(atomic_db, shard_dbs)
        merge_elapsed = elapsed_seconds(merge_started)
        seed_merge_report = None
        if seed_artifact_path is not None and l2_shard_dbs:
            if seed_artifact_path.exists():
                seed_artifact_path.unlink()
            seed_merge_report = merge_l2_day_delta(
                trade_date=trade_date,
                artifact_paths=[str(path) for path in l2_shard_dbs if path.exists()],
                db_path=str(seed_artifact_path),
                source_root=str(extract_root),
                mode="daily_new_atomic_seed",
                message=f"artifact_count={len(l2_shard_dbs)}",
            )
        total_elapsed = elapsed_seconds(day_started)
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} merge_done merge_sec={merge_elapsed}", flush=True)
        print(
            f"[atomic-backfill] day={trade_date} batch={batch.name} worker_done "
            f"success={total_success} failure={len(failures)} total_sec={total_elapsed}",
            flush=True,
        )
        failure_policy = _failure_policy(config, len(items), len(failures))
        report = {
            "batch": batch.name,
            "kind": batch.kind,
            "trade_date": trade_date,
            "archive_path": str(archive_path),
            "item_count": len(items),
            "success_count": total_success,
            "failure_count": len(failures),
            "failures": failures[:20],
            "failure_policy": failure_policy,
            "timing_seconds": {
                "extract": extract_elapsed,
                "list_items": list_elapsed,
                "process_shards": process_elapsed,
                "merge_shards": merge_elapsed,
                "total": total_elapsed,
            },
            "postclose_seed_artifact": (
                {
                    **seed_merge_report,
                    "db_path": str(seed_artifact_path),
                    "seed_success_count": total_seed_success,
                    "seed_failure_count": total_seed_failures,
                }
                if seed_merge_report is not None and seed_artifact_path is not None
                else None
            ),
        }
        if failures and failure_policy["tolerated"]:
            print(
                f"[atomic-backfill] day={trade_date} batch={batch.name} tolerated_failures="
                f"{len(failures)} ratio={failure_policy['failure_ratio']}",
                flush=True,
            )
        if failures and bool(config.get("stop_on_failure", True)) and not failure_policy["tolerated"]:
            raise RuntimeError(json.dumps(report, ensure_ascii=False))
        return report, prefetch_thread, prefetch_key
    finally:
        shutil.rmtree(Path(str(config["extract_root"])) / ".worker_shards" / batch.name / to_compact(trade_date), ignore_errors=True)
        if cleanup_extracted and not can_reuse:
            shutil.rmtree(extract_root, ignore_errors=True)


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Windows 正式原子层批量回补 runner")
    parser.add_argument("--config", required=True, help="JSON config path")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    batches = parse_batches(config.get("batches", []))
    if not batches:
        raise SystemExit("config.batches 为空")

    atomic_db = Path(str(config["atomic_db"]))
    ensure_atomic_db(atomic_db)
    print(f"[atomic-backfill] config={config_path} atomic_db={atomic_db} workers={config['workers']}", flush=True)

    state_path = Path(str(config["state_file"]))
    report_path = Path(str(config["report_file"]))
    state = {
        "status": "running",
        "config": str(config_path),
        "atomic_db": str(atomic_db),
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "completed_days": [],
        "failed_days": [],
    }
    if state_path.exists() and not bool(config.get("force_rerun_completed_days", False)):
        try:
            prev = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(prev.get("completed_days"), list):
                state["completed_days"] = prev["completed_days"]
        except Exception:
            pass
    write_json(state_path, state)

    reports: List[Dict[str, object]] = []
    min_date = min(batch.date_from for batch in batches)
    max_date = max(batch.date_to for batch in batches)
    pending_tasks: List[PendingTask] = []
    for batch in batches:
        for trade_date in daterange(batch.date_from, batch.date_to):
            key = f"{batch.name}:{trade_date}"
            if key in state["completed_days"]:
                continue
            archive_path = discover_archive(batch.kind, Path(str(config["market_root"])), trade_date)
            if not archive_path:
                continue
            pending_tasks.append(PendingTask(batch=batch, trade_date=trade_date, archive_path=archive_path))

    prefetch_thread: Optional[threading.Thread] = None
    prefetch_key: Optional[str] = None
    for idx, task in enumerate(pending_tasks):
        key = f"{task.batch.name}:{task.trade_date}"
        if prefetch_thread and prefetch_key == key:
            prefetch_thread.join()
            prefetch_thread = None
            prefetch_key = None
        try:
            next_task = pending_tasks[idx + 1] if idx + 1 < len(pending_tasks) else None
            report, started_thread, started_key = run_day(
                task.batch,
                task.trade_date,
                task.archive_path,
                config,
                atomic_db,
                next_task=next_task,
            )
            reports.append(report)
            state["completed_days"].append(key)
            write_json(state_path, state)
            if started_thread is not None:
                prefetch_thread = started_thread
                prefetch_key = started_key
        except Exception as exc:
            state["status"] = "failed"
            state["failed_days"].append({"batch": task.batch.name, "trade_date": task.trade_date, "error": str(exc)})
            write_json(state_path, state)
            raise

    if prefetch_thread:
        prefetch_thread.join()

    with sqlite3.connect(atomic_db) as conn:
        print(f"[atomic-backfill] rebuild_limit_state date_from={min_date} date_to={max_date}", flush=True)
        selection_db = str(config.get("selection_db") or "").strip()
        selection_alias = ""
        if selection_db and Path(selection_db).exists():
            conn.execute("ATTACH DATABASE ? AS sel", (str(Path(selection_db).resolve()),))
            selection_alias = "sel"
        rows_5m_limit, daily_rows_limit = build_limit_state(
            conn,
            [],
            min_date,
            max_date,
            include_5m=False,
            selection_alias=selection_alias,
        )
        replace_limit_rows(conn, rows_5m_limit, daily_rows_limit, [], min_date, max_date, replace_5m=False)
        conn.commit()

    state["status"] = "done"
    state["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_json(state_path, state)
    write_json(
        report_path,
        {
            "config": str(config_path),
            "atomic_db": str(atomic_db),
            "reports": reports,
            "postclose_seed_artifact": next(
                (report.get("postclose_seed_artifact") for report in reports if isinstance(report.get("postclose_seed_artifact"), dict)),
                None,
            ),
            "limit_state_5m_rows": None,
            "limit_state_daily_rows": len(daily_rows_limit),
            "completed_day_count": len(state["completed_days"]),
        },
    )
    top_seed_artifact = next(
        (report.get("postclose_seed_artifact") for report in reports if isinstance(report.get("postclose_seed_artifact"), dict)),
        None,
    )
    print(json.dumps({
        "status": state["status"],
        "atomic_db": str(atomic_db),
        "completed_day_count": len(state["completed_days"]),
        "report_file": str(report_path),
        "state_file": str(state_path),
        "limit_state_daily_rows": len(daily_rows_limit),
        "postclose_seed_artifact": top_seed_artifact,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
