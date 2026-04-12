#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.backfill_atomic_order_from_raw import _apply_support_ratios, _build_order_rows, _replace_rows as replace_order_rows, load_l2_symbol_bundle
from backend.scripts.build_book_state_from_raw import build_book_rows, replace_book_rows
from backend.scripts.build_limit_state_from_atomic import build_limit_state, ensure_default_rules as ensure_limit_rules, ensure_schema as ensure_limit_schema, replace_rows as replace_limit_rows
from backend.scripts.build_open_auction_summaries import _build_l1_summary_from_frames, _build_l2_summary_from_frames, _build_manifest, _build_phase_l1_summary_from_frames, _build_phase_l2_summary_from_frames, _prepare_order_auction_df, _prepare_quote_auction_df, _prepare_trade_auction_df, _upsert as upsert_auction
from backend.scripts.run_symbol_atomic_validation import (
    ATOMIC_INIT_SCRIPT,
    BOOK_STATE_SCHEMA,
    OPEN_AUCTION_PHASE_SCHEMA,
    OPEN_AUCTION_SCHEMA,
    WIN_7Z,
    _build_atomic_trade_5m_rows_from_l2,
    _build_atomic_trade_5m_rows_from_legacy,
    _build_atomic_trade_daily_row,
    _replace_trade_rows,
)
from backend.scripts.sandbox_review_etl import normalize_symbol
from backend.app.core.l2_package_layout import normalize_month_day_root
from backend.scripts.backfill_atomic_trade_from_raw import normalize_symbol_dir_name

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
        ensure_limit_schema(conn)
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
    return {
        "symbol": symbol,
        "rows_5m": len(rows_5m_trade),
        "order_5m_rows": len(rows_5m_order),
        "book_5m_rows": len(rows_5m_book),
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
    data.setdefault("prefetch_next_day_extract", False)
    data.setdefault("stop_on_failure", True)
    data.setdefault("cleanup_extracted", True)
    data.setdefault("symbols", [])
    data.setdefault("max_items_per_day", 0)
    data.setdefault("reuse_extracted_day_if_exists", False)
    data.setdefault("extractor", "auto")
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
) -> Dict[str, object]:
    shard_db = Path(atomic_db)
    if shard_db.exists():
        shard_db.unlink()
    ensure_atomic_db(shard_db)
    failures: List[Dict[str, str]] = []
    success_count = 0
    worker_fn = _write_legacy_rows_to_conn if kind == "legacy" else _write_l2_rows_to_conn
    with sqlite3.connect(shard_db) as conn:
        _configure_sqlite_for_shard(conn)
        commit_every = 64
        pending_since_commit = 0
        for raw_path in item_paths:
            item = Path(raw_path)
            try:
                worker_fn(conn, item, trade_date, large_threshold, super_threshold)
                success_count += 1
                pending_since_commit += 1
                if pending_since_commit >= commit_every:
                    conn.commit()
                    pending_since_commit = 0
            except Exception as exc:
                failures.append({"item": str(item), "error": repr(exc)})
        if pending_since_commit > 0:
            conn.commit()
    return {
        "success_count": success_count,
        "failure_count": len(failures),
        "failures": failures[:10],
    }


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
    extract_archive(
        task.archive_path,
        extract_root,
        task.batch.kind,
        task.trade_date,
        config.get("symbols", []),
        str(config.get("extractor", "auto")),
    )
    print(f"[atomic-backfill] prefetch_done day={task.trade_date} batch={task.batch.name}", flush=True)


def run_day(
    batch: Batch,
    trade_date: str,
    archive_path: Path,
    config: Dict[str, object],
    atomic_db: Path,
    next_task: Optional[PendingTask] = None,
) -> Tuple[Dict[str, object], Optional[threading.Thread], Optional[str]]:
    extract_root = Path(str(config["extract_root"])) / batch.name / to_compact(trade_date)
    cleanup_extracted = bool(config.get("cleanup_extracted", True))
    include_bj = bool(config.get("include_bj", False))
    include_star = bool(config.get("include_star", False))
    include_gem = bool(config.get("include_gem", True))
    main_board_only = bool(config.get("main_board_only", False))
    reuse_extracted = bool(config.get("reuse_extracted_day_if_exists", False))
    l2_day_root = extract_root / to_compact(trade_date)
    can_reuse = reuse_extracted and (
        (batch.kind == "legacy" and extract_root.exists() and any(extract_root.glob("*.csv")))
        or (batch.kind == "l2" and l2_day_root.exists())
    )
    if can_reuse:
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} kind={batch.kind} reuse_extracted=1 root={extract_root}", flush=True)
    else:
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} kind={batch.kind} extract_start archive={archive_path}", flush=True)
        extract_archive(archive_path, extract_root, batch.kind, trade_date, config.get("symbols", []), str(config.get("extractor", "auto")))
    try:
        if batch.kind == "legacy":
            items = list_legacy_csvs(extract_root, include_bj, include_star, include_gem, main_board_only)
            items = apply_symbol_filter(items, config.get("symbols", []), is_legacy=True)
        else:
            items = list_l2_symbol_dirs(l2_day_root, include_bj, include_star, include_gem, main_board_only)
            items = apply_symbol_filter(items, config.get("symbols", []), is_legacy=False)
        max_items = int(config.get("max_items_per_day", 0) or 0)
        if max_items > 0:
            items = items[:max_items]
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} extract_done item_count={len(items)} workers={config['workers']}", flush=True)
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
        total_success = 0
        if workers == 1:
            print(f"[atomic-backfill] day={trade_date} batch={batch.name} shard_mode=single", flush=True)
            shard_result = _run_process_shard(
                batch.kind,
                trade_date,
                str(shard_dbs[0]),
                [str(x) for x in shards[0]],
                float(config["large_threshold"]),
                float(config["super_threshold"]),
            )
            total_success += int(shard_result["success_count"])
            failures.extend(shard_result["failures"])
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
                        )
                    ] = shard_idx
                    shard_idx += 1
                for future in as_completed(future_map):
                    shard_result = future.result()
                    total_success += int(shard_result["success_count"])
                    failures.extend(shard_result["failures"])
                    print(
                        f"[atomic-backfill] day={trade_date} batch={batch.name} shard_done success={total_success}/{len(items)} failure={len(failures)}",
                        flush=True,
                    )
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} merge_start shard_db_count={len(shard_dbs)}", flush=True)
        _merge_shard_tables(atomic_db, shard_dbs)
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} merge_done", flush=True)
        print(f"[atomic-backfill] day={trade_date} batch={batch.name} worker_done success={total_success} failure={len(failures)}", flush=True)
        report = {
            "batch": batch.name,
            "kind": batch.kind,
            "trade_date": trade_date,
            "archive_path": str(archive_path),
            "item_count": len(items),
            "success_count": total_success,
            "failure_count": len(failures),
            "failures": failures[:20],
        }
        if failures and bool(config.get("stop_on_failure", True)):
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
    if state_path.exists():
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
        rows_5m_limit, daily_rows_limit = build_limit_state(conn, [], min_date, max_date)
        replace_limit_rows(conn, rows_5m_limit, daily_rows_limit, [], min_date, max_date)
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
            "limit_state_5m_rows": len(rows_5m_limit),
            "limit_state_daily_rows": len(daily_rows_limit),
            "completed_day_count": len(state["completed_days"]),
        },
    )
    print(json.dumps({
        "status": state["status"],
        "atomic_db": str(atomic_db),
        "completed_day_count": len(state["completed_days"]),
        "report_file": str(report_path),
        "state_file": str(state_path),
        "limit_state_daily_rows": len(daily_rows_limit),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
