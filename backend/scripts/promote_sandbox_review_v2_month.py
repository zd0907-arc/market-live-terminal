"""
把 sandbox_review_v2 的固定池 5m 结果按月提升到生产 history_5m_l2 / history_daily_l2。

适用场景：
- `data/sandbox/review_v2/` 已有固定池真实 5m 数据（约 2788 只）；
- 希望按月把这些历史结果接入新版“历史多维”正式查询；
- 不重新跑 Windows 原始 ZIP，而是直接复用 sandbox V2 已验证产物。

特点：
- 只提升固定池，不改池子口径；
- 按 symbol+month 覆盖写，重复执行幂等；
- 直接写生产 `DB_PATH` 指向的 `history_5m_l2 / history_daily_l2`；
- 每个月处理完成后即可立即被前端消费，无需前端重新发版。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.db.l2_history_db import ensure_l2_history_schema, get_l2_history_connection


REVIEW_5M_SELECT_SQL = """
SELECT
    symbol, datetime, source_date,
    open, high, low, close, total_amount,
    l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
    l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell
FROM review_5m_bars
WHERE source_date >= ? AND source_date <= ?
ORDER BY source_date ASC, datetime ASC
"""


History5mInsertRow = Tuple[
    str,
    str,
    str,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    Optional[str],
]


def _month_bounds(month: str) -> Tuple[str, str]:
    try:
        first = datetime.strptime(month + "-01", "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"非法月份：{month}，格式应为 YYYY-MM") from exc

    if first.month == 12:
        next_month = datetime(first.year + 1, 1, 1)
    else:
        next_month = datetime(first.year, first.month + 1, 1)
    last = next_month.fromordinal(next_month.toordinal() - 1)
    return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")


def _source_root(path: str = "") -> Path:
    if path:
        return Path(path).expanduser().resolve()
    return Path(ROOT_DIR) / "data" / "sandbox" / "review_v2"


def _load_pool_symbols(source_root: Path) -> Tuple[List[str], str]:
    meta_db = source_root / "meta.db"
    if not meta_db.is_file():
        raise FileNotFoundError(f"缺少 sandbox meta.db: {meta_db}")

    conn = sqlite3.connect(str(meta_db))
    try:
        rows = conn.execute(
            """
            SELECT symbol, as_of_date
            FROM sandbox_stock_pool
            ORDER BY market_cap DESC, symbol ASC
            """
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise ValueError(f"sandbox_stock_pool 为空: {meta_db}")
    symbols = [str(row[0]) for row in rows]
    as_of_date = str(rows[0][1] or "").strip()
    return symbols, as_of_date


def _load_symbols_from_file(path: str) -> List[str]:
    rows = Path(path).read_text(encoding="utf-8").splitlines()
    result = []
    for row in rows:
        text = str(row).strip().lower()
        if text.startswith(("sh", "sz", "bj")) and len(text) == 8:
            result.append(text)
    if not result:
        raise ValueError(f"symbols file 为空或无合法 symbol: {path}")
    return result


def export_pool_snapshot(source_root: Path, output_dir: Path) -> Path:
    symbols, as_of_date = _load_pool_symbols(source_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    compact = as_of_date.replace("-", "") if as_of_date else datetime.now().strftime("%Y%m%d")
    snapshot_path = output_dir / f"pool_snapshot_{compact}.symbols.txt"
    snapshot_path.write_text("\n".join(symbols) + "\n", encoding="utf-8")
    return snapshot_path


def _read_symbol_month_rows(symbol_db_path: Path, start_date: str, end_date: str) -> List[History5mInsertRow]:
    conn = sqlite3.connect(str(symbol_db_path))
    try:
        rows = conn.execute(REVIEW_5M_SELECT_SQL, (start_date, end_date)).fetchall()
    finally:
        conn.close()

    result: List[History5mInsertRow] = []
    for row in rows:
        result.append(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                float(row[3] or 0.0),
                float(row[4] or 0.0),
                float(row[5] or 0.0),
                float(row[6] or 0.0),
                float(row[7] or 0.0),
                float(row[8] or 0.0),
                float(row[9] or 0.0),
                float(row[10] or 0.0),
                float(row[11] or 0.0),
                float(row[12] or 0.0),
                float(row[13] or 0.0),
                float(row[14] or 0.0),
                float(row[15] or 0.0),
                None,
            )
        )
    return result


def _group_daily_rows(symbol: str, rows_5m: Sequence[History5mInsertRow]) -> List[Tuple]:
    grouped: Dict[str, List[History5mInsertRow]] = defaultdict(list)
    for row in rows_5m:
        grouped[str(row[2])].append(row)

    daily_rows: List[Tuple] = []
    for trade_date, rows in sorted(grouped.items()):
        daily_row = _compute_daily_row(symbol, trade_date, rows)
        if daily_row is not None:
            daily_rows.append(daily_row)
    return daily_rows


def _compute_daily_row(symbol: str, trade_date: str, rows_5m: Sequence[History5mInsertRow]) -> Optional[Tuple]:
    if not rows_5m:
        return None

    opens = rows_5m[0][3]
    highs = max(row[4] for row in rows_5m)
    lows = min(row[5] for row in rows_5m)
    closes = rows_5m[-1][6]
    total_amount = sum(row[7] for row in rows_5m)
    l1_main_buy = sum(row[8] for row in rows_5m)
    l1_main_sell = sum(row[9] for row in rows_5m)
    l1_super_buy = sum(row[10] for row in rows_5m)
    l1_super_sell = sum(row[11] for row in rows_5m)
    l2_main_buy = sum(row[12] for row in rows_5m)
    l2_main_sell = sum(row[13] for row in rows_5m)
    l2_super_buy = sum(row[14] for row in rows_5m)
    l2_super_sell = sum(row[15] for row in rows_5m)
    quality_messages = [str(row[16]).strip() for row in rows_5m if len(row) > 16 and str(row[16]).strip()]
    quality_info = "；".join(dict.fromkeys(quality_messages)) if quality_messages else None

    def ratio(v: float) -> float:
        return float(v / total_amount * 100) if total_amount > 0 else 0.0

    return (
        symbol,
        trade_date,
        float(opens),
        float(highs),
        float(lows),
        float(closes),
        float(total_amount),
        float(l1_main_buy),
        float(l1_main_sell),
        float(l1_main_buy - l1_main_sell),
        float(l1_super_buy),
        float(l1_super_sell),
        float(l1_super_buy - l1_super_sell),
        float(l2_main_buy),
        float(l2_main_sell),
        float(l2_main_buy - l2_main_sell),
        float(l2_super_buy),
        float(l2_super_sell),
        float(l2_super_buy - l2_super_sell),
        ratio(l1_main_buy + l1_main_sell),
        ratio(l1_super_buy + l1_super_sell),
        ratio(l2_main_buy + l2_main_sell),
        ratio(l2_super_buy + l2_super_sell),
        ratio(l1_main_buy),
        ratio(l1_main_sell),
        ratio(l2_main_buy),
        ratio(l2_main_sell),
        quality_info,
    )


def _replace_symbol_month(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: str,
    end_date: str,
    rows_5m: Sequence[History5mInsertRow],
    rows_daily: Sequence[Tuple],
) -> Tuple[int, int]:
    conn.execute(
        "DELETE FROM history_5m_l2 WHERE symbol=? AND source_date >= ? AND source_date <= ?",
        (symbol, start_date, end_date),
    )
    conn.execute(
        "DELETE FROM history_daily_l2 WHERE symbol=? AND date >= ? AND date <= ?",
        (symbol, start_date, end_date),
    )

    rows_5m_inserted = 0
    rows_daily_inserted = 0
    if rows_5m:
        conn.executemany(
            """
            INSERT INTO history_5m_l2 (
                symbol, datetime, source_date,
                open, high, low, close, total_amount,
                l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell,
                l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell,
                quality_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_5m,
        )
        rows_5m_inserted = len(rows_5m)

    if rows_daily:
        conn.executemany(
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
            rows_daily,
        )
        rows_daily_inserted = len(rows_daily)
    return rows_5m_inserted, rows_daily_inserted


def promote_month(
    month: str,
    source_root: Path,
    symbols: Sequence[str],
    report_path: Optional[Path] = None,
    limit_symbols: int = 0,
) -> Dict[str, object]:
    ensure_l2_history_schema()
    start_date, end_date = _month_bounds(month)
    resolved_symbols = list(symbols)
    if not resolved_symbols:
        resolved_symbols, _ = _load_pool_symbols(source_root)
    target_symbols = list(resolved_symbols[:limit_symbols]) if limit_symbols > 0 else list(resolved_symbols)

    report: Dict[str, object] = {
        "month": month,
        "start_date": start_date,
        "end_date": end_date,
        "source_root": str(source_root),
        "symbol_count_target": len(target_symbols),
        "symbols_with_rows": 0,
        "symbols_missing_db": [],
        "symbols_empty_month": [],
        "rows_5m_inserted": 0,
        "rows_daily_inserted": 0,
        "trade_dates_covered": [],
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    trade_dates_covered = set()
    target_conn = get_l2_history_connection()
    target_conn.execute("PRAGMA journal_mode=WAL;")
    target_conn.execute("PRAGMA synchronous=NORMAL;")
    try:
        with target_conn:
            for idx, symbol in enumerate(target_symbols, start=1):
                symbol_db = source_root / "symbols" / f"{symbol}.db"
                if not symbol_db.is_file():
                    report["symbols_missing_db"].append(symbol)
                    continue

                rows_5m = _read_symbol_month_rows(symbol_db, start_date, end_date)
                if not rows_5m:
                    report["symbols_empty_month"].append(symbol)
                    continue

                daily_rows = _group_daily_rows(symbol, rows_5m)
                inserted_5m, inserted_daily = _replace_symbol_month(
                    target_conn,
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    rows_5m=rows_5m,
                    rows_daily=daily_rows,
                )
                report["symbols_with_rows"] += 1
                report["rows_5m_inserted"] += inserted_5m
                report["rows_daily_inserted"] += inserted_daily
                trade_dates_covered.update({str(row[2]) for row in rows_5m})

                if idx % 200 == 0:
                    print(
                        f"[promote-month] {month} progress {idx}/{len(target_symbols)} "
                        f"symbols_with_rows={report['symbols_with_rows']} "
                        f"rows_5m={report['rows_5m_inserted']} rows_daily={report['rows_daily_inserted']}"
                    )
    finally:
        target_conn.close()

    report["trade_dates_covered"] = sorted(trade_dates_covered)
    report["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report["status"] = "done"

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="按月把 sandbox_review_v2 固定池数据提升到 history_5m_l2/history_daily_l2")
    parser.add_argument("--month", required=True, help="目标月份，格式 YYYY-MM")
    parser.add_argument("--source-root", default="", help="sandbox_review_v2 根目录")
    parser.add_argument("--symbols-file", default="", help="固定池快照文件；留空则直接读 meta.db 中的 sandbox_stock_pool")
    parser.add_argument("--write-snapshot-dir", default="", help="可选：导出当前固定池快照到指定目录")
    parser.add_argument("--report-path", default="", help="可选：输出 JSON 报告路径")
    parser.add_argument("--limit-symbols", type=int, default=0, help="仅前 N 个 symbol（调试用）")
    parser.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    args = parser.parse_args()

    source_root = _source_root(args.source_root)
    if args.symbols_file:
        symbols = _load_symbols_from_file(args.symbols_file)
    else:
        symbols, _ = _load_pool_symbols(source_root)

    snapshot_path = None
    if args.write_snapshot_dir:
        snapshot_path = export_pool_snapshot(source_root, Path(args.write_snapshot_dir))

    report = promote_month(
        month=args.month,
        source_root=source_root,
        symbols=symbols,
        report_path=Path(args.report_path) if args.report_path else None,
        limit_symbols=max(0, args.limit_symbols),
    )
    if snapshot_path:
        report["snapshot_path"] = str(snapshot_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"[promote-month] month={report['month']} status={report['status']}")
    print(
        f"[promote-month] symbols_with_rows={report['symbols_with_rows']}/{report['symbol_count_target']} "
        f"rows_5m={report['rows_5m_inserted']} rows_daily={report['rows_daily_inserted']}"
    )
    print(f"[promote-month] trade_dates={','.join(report['trade_dates_covered'])}")
    if report["symbols_missing_db"]:
        print(f"[promote-month] missing_db={len(report['symbols_missing_db'])}")
    if report["symbols_empty_month"]:
        print(f"[promote-month] empty_month={len(report['symbols_empty_month'])}")
    if snapshot_path:
        print(f"[promote-month] snapshot_path={snapshot_path}")


if __name__ == "__main__":
    main()
