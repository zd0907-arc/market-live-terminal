"""
Sandbox Review V2 - 5分钟全量回放清洗脚本

输入：Windows 本地历史逐笔 CSV/ZIP（D:\\MarketData）
输出：data/sandbox/review_v2/symbols/{symbol}.db
"""

import argparse
import concurrent.futures
import ctypes
import os
import sys
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from backend.app.db.sandbox_review_v2_db import (
    clear_symbol_review_rows,
    create_month_run,
    create_backfill_run,
    ensure_sandbox_review_v2_schema,
    ensure_symbol_review_5m_schema,
    finish_month_run,
    finish_backfill_run,
    get_symbol_review_dates,
    get_stock_pool,
    record_backfill_failures,
    upsert_symbol_review_rows,
)
from backend.scripts.sandbox_review_etl import (
    L1_MAIN_THRESHOLD,
    L1_SUPER_THRESHOLD,
    extract_date_from_path,
    iter_source_files,
    normalize_symbol,
    standardize_tick_dataframe,
)


SANDBOX_MIN_DATE = "2025-01-01"
SANDBOX_MAX_DATE = "2026-02-28"


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _get_memory_usage_percent() -> Optional[float]:
    if os.name != "nt":
        return None
    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) == 0:
            return None
        return float(status.dwMemoryLoad)
    except Exception:
        return None


def _resolve_dynamic_workers(
    base_workers: int,
    min_workers: int,
    mem_high_watermark: float,
) -> int:
    mem_pct = _get_memory_usage_percent()
    if mem_pct is None:
        return base_workers
    if mem_pct >= mem_high_watermark:
        return min_workers
    if mem_pct >= mem_high_watermark - 5:
        return max(min_workers, base_workers - 1)
    return base_workers


def _is_weekday(date_text: str) -> bool:
    return datetime.strptime(date_text, "%Y-%m-%d").weekday() < 5


def _in_range(date_text: str, start_date: str, end_date: str) -> bool:
    return start_date <= date_text <= end_date


def _collect_target_symbols(symbol_arg: str, max_symbols: int) -> List[str]:
    if symbol_arg:
        symbols = []
        for raw in symbol_arg.split(","):
            item = raw.strip().lower()
            if not item:
                continue
            if item.isdigit() and len(item) == 6:
                item = ("sh" if item.startswith("6") else "sz") + item
            symbols.append(item)
        return sorted(set(symbols))

    pool = get_stock_pool()
    items = pool.get("items", []) if isinstance(pool, dict) else []
    symbols = [str(item.get("symbol", "")).lower() for item in items if item.get("symbol")]
    symbols = [s for s in symbols if s.startswith(("sh", "sz"))]
    if max_symbols > 0:
        symbols = symbols[:max_symbols]
    return sorted(set(symbols))


def _build_files_by_date(src_root: str, start_date: str, end_date: str) -> Dict[str, List[str]]:
    files_by_date: Dict[str, List[str]] = {}
    for path in iter_source_files(src_root):
        date_text = extract_date_from_path(path)
        if not date_text:
            continue
        if not _in_range(date_text, start_date, end_date):
            continue
        if not _is_weekday(date_text):
            continue
        files_by_date.setdefault(date_text, []).append(path)
    return files_by_date


def _month_from_date(date_text: str) -> str:
    return date_text[:7]


def _resolve_target_months(
    files_by_date: Dict[str, List[str]],
    month_arg: str,
) -> List[str]:
    available_months = sorted({_month_from_date(date_text) for date_text in files_by_date.keys()}, reverse=True)
    if not month_arg:
        return available_months

    requested = []
    for raw in month_arg.split(","):
        item = raw.strip()
        if not item:
            continue
        if len(item) != 7 or item[4] != "-":
            raise ValueError(f"非法月份格式: {item}，应为 YYYY-MM")
        requested.append(item)

    requested = list(dict.fromkeys(requested))
    return [month for month in requested if month in available_months]


def _read_day_symbol_frames(
    day_files: Sequence[str],
    target_symbols: set[str],
) -> Dict[str, List[Tuple[str, pd.DataFrame]]]:
    symbol_frames: Dict[str, List[Tuple[str, pd.DataFrame]]] = {}
    for path in day_files:
        lower = path.lower()
        if lower.endswith(".csv"):
            symbol = normalize_symbol(path)
            if symbol in target_symbols:
                try:
                    df = pd.read_csv(path, engine="c", on_bad_lines="skip")
                    symbol_frames.setdefault(symbol, []).append((path, df))
                except Exception:
                    continue
            continue

        if not lower.endswith(".zip"):
            continue

        try:
            with zipfile.ZipFile(path, "r") as zf:
                for member in zf.namelist():
                    if not member.lower().endswith(".csv"):
                        continue
                    symbol = normalize_symbol(member)
                    if symbol not in target_symbols:
                        continue
                    with zf.open(member) as fp:
                        try:
                            df = pd.read_csv(fp, engine="c", on_bad_lines="skip")
                            symbol_frames.setdefault(symbol, []).append((f"{path}::{member}", df))
                        except Exception:
                            continue
        except Exception:
            continue
    return symbol_frames


def _iter_day_symbol_frame_batches(
    day_files: Sequence[str],
    target_symbols: set[str],
    batch_size: int,
):
    batch: Dict[str, List[Tuple[str, pd.DataFrame]]] = {}

    def flush():
        nonlocal batch
        if not batch:
            return None
        out = batch
        batch = {}
        return out

    for path in day_files:
        lower = path.lower()
        if lower.endswith(".csv"):
            symbol = normalize_symbol(path)
            if symbol not in target_symbols:
                continue
            if symbol not in batch and len(batch) >= batch_size:
                out = flush()
                if out:
                    yield out
            try:
                df = pd.read_csv(path, engine="c", on_bad_lines="skip")
                batch.setdefault(symbol, []).append((path, df))
            except Exception:
                continue
            continue

        if not lower.endswith(".zip"):
            continue

        try:
            with zipfile.ZipFile(path, "r") as zf:
                for member in zf.namelist():
                    if not member.lower().endswith(".csv"):
                        continue
                    symbol = normalize_symbol(member)
                    if symbol not in target_symbols:
                        continue
                    if symbol not in batch and len(batch) >= batch_size:
                        out = flush()
                        if out:
                            yield out
                    try:
                        with zf.open(member) as fp:
                            df = pd.read_csv(fp, engine="c", on_bad_lines="skip")
                        batch.setdefault(symbol, []).append((f"{path}::{member}", df))
                    except Exception:
                        continue
        except Exception:
            continue

    out = flush()
    if out:
        yield out


def _compute_5m_review_bars(
    ticks: pd.DataFrame,
    symbol: str,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
) -> pd.DataFrame:
    if ticks.empty:
        return pd.DataFrame()

    df = ticks.copy()
    df["bucket"] = df["datetime"].dt.floor("5min")

    buy_parent_totals = (
        df[df["buy_order_id"] != ""].groupby("buy_order_id")["amount"].sum().to_dict()
    )
    sell_parent_totals = (
        df[df["sell_order_id"] != ""].groupby("sell_order_id")["amount"].sum().to_dict()
    )
    df["buy_parent_total"] = df["buy_order_id"].map(buy_parent_totals).fillna(0.0)
    df["sell_parent_total"] = df["sell_order_id"].map(sell_parent_totals).fillna(0.0)

    df["l1_main_buy_amt"] = ((df["side"] == "buy") & (df["amount"] >= large_threshold)) * df["amount"]
    df["l1_main_sell_amt"] = ((df["side"] == "sell") & (df["amount"] >= large_threshold)) * df["amount"]
    df["l1_super_buy_amt"] = ((df["side"] == "buy") & (df["amount"] >= super_threshold)) * df["amount"]
    df["l1_super_sell_amt"] = ((df["side"] == "sell") & (df["amount"] >= super_threshold)) * df["amount"]

    # L2 按买卖双方独立记账，允许主力对倒时上下同时放大。
    df["l2_main_buy_amt"] = (df["buy_parent_total"] >= large_threshold) * df["amount"]
    df["l2_main_sell_amt"] = (df["sell_parent_total"] >= large_threshold) * df["amount"]
    df["l2_super_buy_amt"] = (df["buy_parent_total"] >= super_threshold) * df["amount"]
    df["l2_super_sell_amt"] = (df["sell_parent_total"] >= super_threshold) * df["amount"]

    ohlc = df.groupby("bucket")["price"].agg(open="first", high="max", low="min", close="last")
    flow = df.groupby("bucket").agg(
        total_amount=("amount", "sum"),
        l1_main_buy=("l1_main_buy_amt", "sum"),
        l1_main_sell=("l1_main_sell_amt", "sum"),
        l1_super_buy=("l1_super_buy_amt", "sum"),
        l1_super_sell=("l1_super_sell_amt", "sum"),
        l2_main_buy=("l2_main_buy_amt", "sum"),
        l2_main_sell=("l2_main_sell_amt", "sum"),
        l2_super_buy=("l2_super_buy_amt", "sum"),
        l2_super_sell=("l2_super_sell_amt", "sum"),
    )
    merged = ohlc.join(flow, how="inner").reset_index()
    merged["symbol"] = symbol
    merged["datetime"] = merged["bucket"].dt.strftime("%Y-%m-%d %H:%M:%S")
    merged["source_date"] = trade_date
    return merged[
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
    ]


def _process_symbol_day(
    symbol: str,
    trade_date: str,
    frames: Sequence[Tuple[str, pd.DataFrame]],
    large_threshold: float,
    super_threshold: float,
    force_volume_multiplier: Optional[int],
    require_order_ids: bool,
) -> Tuple[str, int, List[Tuple], List[Tuple[str, str, str, str]]]:
    standardized: List[pd.DataFrame] = []
    failures: List[Tuple[str, str, str, str]] = []
    for source_name, raw_df in frames:
        ticks, diag = standardize_tick_dataframe(
            raw_df,
            trade_date,
            force_volume_multiplier,
            require_order_ids=require_order_ids,
        )
        if "fatal_error" in diag:
            failures.append((symbol, trade_date, source_name, str(diag["fatal_error"])))
            continue
        if not ticks.empty:
            standardized.append(ticks)

    if not standardized:
        return symbol, 0, [], failures

    merged_ticks = pd.concat(standardized, ignore_index=True).sort_values("datetime")
    bars = _compute_5m_review_bars(
        merged_ticks,
        symbol=symbol,
        trade_date=trade_date,
        large_threshold=large_threshold,
        super_threshold=super_threshold,
    )
    if bars.empty:
        return symbol, 0, [], failures

    rows = [
        (
            row["symbol"],
            row["datetime"],
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["total_amount"]),
            float(row["l1_main_buy"]),
            float(row["l1_main_sell"]),
            float(row["l1_super_buy"]),
            float(row["l1_super_sell"]),
            float(row["l2_main_buy"]),
            float(row["l2_main_sell"]),
            float(row["l2_super_buy"]),
            float(row["l2_super_sell"]),
            row["source_date"],
        )
        for _, row in bars.iterrows()
    ]
    return symbol, len(rows), rows, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Sandbox Review V2 5m 回放清洗（自动分片+可续跑）")
    parser.add_argument("src_root", help="Windows 历史逐笔根目录，如 D:\\MarketData")
    parser.add_argument("--start-date", default=SANDBOX_MIN_DATE)
    parser.add_argument("--end-date", default=SANDBOX_MAX_DATE)
    parser.add_argument("--symbols", default="", help="逗号分隔，留空则使用股票池")
    parser.add_argument("--max-symbols", type=int, default=0, help="仅前N只股票（0不限制）")
    parser.add_argument("--months", default="", help="按月批次过滤，逗号分隔，如 2026-02,2026-01；留空则自动按月份逆序跑全区间")
    parser.add_argument("--workers", type=int, default=8, help="日内并发处理symbol数（建议8-12，内存紧张自动降档）")
    parser.add_argument("--min-workers", type=int, default=6, help="内存紧张时的最小并发")
    parser.add_argument("--mem-high-watermark", type=float, default=75.0, help="内存占用超过该阈值时降并发(%%)")
    parser.add_argument("--day-symbol-batch-size", type=int, default=240, help="单个交易日单批读入内存的股票数，默认240")
    parser.add_argument("--resume", action="store_true", help="仅跳过已完成 symbol+trade_date 的数据，允许断点续跑")
    parser.add_argument("--replace", action="store_true", help="先清空目标symbol历史再写入")
    parser.add_argument("--large-threshold", type=float, default=L1_MAIN_THRESHOLD)
    parser.add_argument("--super-threshold", type=float, default=L1_SUPER_THRESHOLD)
    parser.add_argument("--force-volume-multiplier", type=int, choices=[1, 100], default=None)
    parser.add_argument("--allow-missing-order-ids", action="store_true")
    args = parser.parse_args()

    if args.start_date < SANDBOX_MIN_DATE or args.end_date > SANDBOX_MAX_DATE:
        raise ValueError(
            f"区间超限，仅支持 {SANDBOX_MIN_DATE} 至 {SANDBOX_MAX_DATE}"
        )
    if args.end_date < args.start_date:
        raise ValueError("结束日期必须大于等于开始日期")

    ensure_sandbox_review_v2_schema()
    symbols = _collect_target_symbols(args.symbols, args.max_symbols)
    if not symbols:
        raise ValueError("股票池为空，请先执行 sandbox_review_v2_pool.py")

    if args.min_workers < 1:
        raise ValueError("min-workers 必须 >= 1")
    if args.min_workers > args.workers:
        raise ValueError("min-workers 不能大于 workers")

    if not symbols:
        print("[v2-backfill] 无待处理 symbol，任务结束")
        return

    for symbol in symbols:
        ensure_symbol_review_5m_schema(symbol)
        if args.replace:
            clear_symbol_review_rows(symbol)

    run_id = create_backfill_run(
        start_date=args.start_date,
        end_date=args.end_date,
        workers=max(1, args.workers),
        symbol_count=len(symbols),
        message="sandbox v2 5m backfill running",
    )

    files_by_date = _build_files_by_date(args.src_root, args.start_date, args.end_date)
    target_months = _resolve_target_months(files_by_date, args.months)
    require_order_ids = not args.allow_missing_order_ids

    if not target_months:
        finish_backfill_run(
            run_id=run_id,
            status="done",
            total_rows=0,
            failed_count=0,
            message="未匹配到任何月份，任务结束",
        )
        print("[v2-backfill] 未匹配到任何月份，任务结束")
        return

    existing_dates_by_symbol: Dict[str, set[str]] = {}
    if args.resume:
        for symbol in symbols:
            existing_dates_by_symbol[symbol] = get_symbol_review_dates(symbol, args.start_date, args.end_date)
        completed_pairs = sum(len(v) for v in existing_dates_by_symbol.values())
        print(
            f"[v2-backfill] resume 模式：总symbol={len(symbols)} 已完成 symbol-date={completed_pairs}"
        )

    print(
        f"[v2-backfill] run_id={run_id} symbols={len(symbols)} "
        f"days={len(files_by_date)} months={len(target_months)} workers={args.workers}"
    )

    total_rows = 0
    all_failures: List[Tuple[str, str, str, str]] = []
    try:
        for month in target_months:
            month_dates = sorted(
                [date_text for date_text in files_by_date.keys() if _month_from_date(date_text) == month],
                reverse=True,
            )
            month_run_id = create_month_run(
                month=month,
                workers=max(1, int(args.workers)),
                trade_day_count=len(month_dates),
                symbol_count=len(symbols),
                message="monthly reverse backfill running",
            )
            month_rows = 0
            month_failures_start = len(all_failures)
            print(
                f"[v2-backfill] ===== 开始月份 {month} "
                f"(trade_days={len(month_dates)}, symbols={len(symbols)}) ====="
            )
            try:
                for trade_date in month_dates:
                    if args.resume:
                        pending_symbols = {
                            symbol
                            for symbol in symbols
                            if trade_date not in existing_dates_by_symbol.get(symbol, set())
                        }
                    else:
                        pending_symbols = set(symbols)

                    if not pending_symbols:
                        print(f"[v2-backfill] month={month} {trade_date} 全部已完成，跳过")
                        continue

                    processed_day_symbols = 0
                    for day_frames in _iter_day_symbol_frame_batches(
                        files_by_date[trade_date],
                        pending_symbols,
                        batch_size=max(1, int(args.day_symbol_batch_size)),
                    ):
                        if not day_frames:
                            continue

                        dynamic_workers = _resolve_dynamic_workers(
                            base_workers=max(1, int(args.workers)),
                            min_workers=max(1, int(args.min_workers)),
                            mem_high_watermark=float(args.mem_high_watermark),
                        )
                        mem_pct = _get_memory_usage_percent()
                        futures = []
                        max_workers = max(1, min(dynamic_workers, len(day_frames)))
                        if mem_pct is not None:
                            print(
                                f"[v2-backfill] month={month} {trade_date} mem={mem_pct:.1f}% "
                                f"workers={max_workers} batch_symbols={len(day_frames)}"
                            )
                        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                            for symbol, frames in day_frames.items():
                                futures.append(
                                    executor.submit(
                                        _process_symbol_day,
                                        symbol,
                                        trade_date,
                                        frames,
                                        float(args.large_threshold),
                                        float(args.super_threshold),
                                        args.force_volume_multiplier,
                                        require_order_ids,
                                    )
                                )

                            for future in concurrent.futures.as_completed(futures):
                                symbol, row_count, rows, failures = future.result()
                                if rows:
                                    upsert_symbol_review_rows(symbol, rows)
                                    if args.resume:
                                        existing_dates_by_symbol.setdefault(symbol, set()).add(trade_date)
                                month_rows += row_count
                                total_rows += row_count
                                processed_day_symbols += 1
                                if failures:
                                    all_failures.extend(failures)
                                print(
                                    f"[v2-backfill] month={month} {trade_date} {symbol} "
                                    f"rows={row_count} failures={len(failures)}"
                                )

                    if processed_day_symbols == 0:
                        print(f"[v2-backfill] month={month} {trade_date} 无待处理数据")
                        continue

                month_failed_count = len(all_failures) - month_failures_start
                month_status = "done" if month_failed_count == 0 else "partial_done"
                finish_month_run(
                    month_run_id=month_run_id,
                    status=month_status,
                    total_rows=month_rows,
                    failed_count=month_failed_count,
                    message=f"month={month}, rows={month_rows}, failures={month_failed_count}",
                )
                print(
                    f"[v2-backfill] ===== 月份完成 {month} "
                    f"rows={month_rows} failures={month_failed_count} ====="
                )
            except Exception as exc:
                month_failed_count = len(all_failures) - month_failures_start
                finish_month_run(
                    month_run_id=month_run_id,
                    status="failed",
                    total_rows=month_rows,
                    failed_count=month_failed_count,
                    message=str(exc),
                )
                raise

        record_backfill_failures(run_id, all_failures)
        status = "done" if not all_failures else "partial_done"
        finish_backfill_run(
            run_id=run_id,
            status=status,
            total_rows=total_rows,
            failed_count=len(all_failures),
            message=f"rows={total_rows}, failures={len(all_failures)}",
        )
        print(f"[v2-backfill] 完成 run_id={run_id}, rows={total_rows}, failures={len(all_failures)}")
    except Exception as exc:
        finish_backfill_run(
            run_id=run_id,
            status="failed",
            total_rows=total_rows,
            failed_count=len(all_failures),
            message=str(exc),
        )
        raise


if __name__ == "__main__":
    main()
