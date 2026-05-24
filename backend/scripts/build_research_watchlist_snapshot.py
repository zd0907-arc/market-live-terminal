#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backend.app.core.config import candidate_atomic_db_paths


REPO_ROOT = Path(__file__).resolve().parents[2]
MARKET_DATA_ROOT = Path("/Users/dong/Desktop/AIGC/market-data")
WATCHLIST_PATH = REPO_ROOT / "data" / "selection" / "research_watchlist" / "watchlist.json"
SNAPSHOT_DIR = REPO_ROOT / "data" / "selection" / "research_watchlist" / "snapshots"
DAILY_DOC_DIR = REPO_ROOT / "docs" / "selection" / "research_watchlist" / "daily"
SELECTION_DB = MARKET_DATA_ROOT / "selection" / "selection_research.db"


def resolve_atomic_db() -> Path:
    explicit = str(os.getenv("ATOMIC_MAINBOARD_DB_PATH") or os.getenv("ATOMIC_DB_PATH") or "").strip()
    if explicit:
        return Path(explicit)
    for raw in candidate_atomic_db_paths():
        path = Path(str(raw))
        if path.exists():
            return path
    return MARKET_DATA_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"


ATOMIC_DB = resolve_atomic_db()


def query_one(db_path: Path, sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def query_all(db_path: Path, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
    finally:
        conn.close()


def latest_trade_date(symbols: List[str], requested_date: Optional[str]) -> str:
    if requested_date:
        return requested_date
    placeholders = ",".join("?" for _ in symbols)
    row = query_one(
        ATOMIC_DB,
        f"SELECT max(trade_date) AS trade_date FROM atomic_trade_daily WHERE symbol IN ({placeholders})",
        symbols,
    )
    if not row or not row.get("trade_date"):
        raise SystemExit("No trade_date found for watchlist symbols")
    return str(row["trade_date"])


def as_yi(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value) / 100000000


def round_or_none(value: Any, digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def load_watchlist() -> Dict[str, Any]:
    if not WATCHLIST_PATH.exists():
        raise SystemExit(f"Watchlist not found: {WATCHLIST_PATH}")
    return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))


def build_row(item: Dict[str, Any], trade_date: str) -> Dict[str, Any]:
    symbol = item["symbol"]
    trade = query_one(
        ATOMIC_DB,
        """
        SELECT *
        FROM atomic_trade_daily
        WHERE symbol=? AND trade_date<=?
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        (symbol, trade_date),
    )
    if not trade:
        return {
            "symbol": symbol,
            "name": item.get("name"),
            "status": item.get("status"),
            "trade_date": trade_date,
            "data_status": "missing_atomic_trade",
        }
    actual_date = trade["trade_date"]
    order = query_one(
        ATOMIC_DB,
        "SELECT * FROM atomic_order_daily WHERE symbol=? AND trade_date=?",
        (symbol, actual_date),
    ) or {}
    feature = query_one(
        SELECTION_DB,
        "SELECT * FROM selection_feature_daily WHERE symbol=? AND trade_date=?",
        (symbol, actual_date),
    ) or {}
    signal = query_one(
        SELECTION_DB,
        "SELECT * FROM selection_signal_daily WHERE symbol=? AND trade_date=?",
        (symbol, actual_date),
    ) or {}

    return {
        "symbol": symbol,
        "code": item.get("code"),
        "name": item.get("name"),
        "status": item.get("status"),
        "trade_date": actual_date,
        "data_status": "ok",
        "close": round_or_none(trade.get("close")),
        "high": round_or_none(trade.get("high")),
        "low": round_or_none(trade.get("low")),
        "amount_yi": round_or_none(as_yi(trade.get("total_amount"))),
        "l2_main_yi": round_or_none(as_yi(trade.get("l2_main_net_amount"))),
        "l2_super_yi": round_or_none(as_yi(trade.get("l2_super_net_amount"))),
        "oib_yi": round_or_none(as_yi(order.get("oib_delta_amount"))),
        "cvd_yi": round_or_none(as_yi(order.get("cvd_delta_amount"))),
        "buy_support_ratio": round_or_none(order.get("buy_support_ratio")),
        "sell_pressure_ratio": round_or_none(order.get("sell_pressure_ratio")),
        "return_3d_pct": round_or_none(feature.get("return_3d_pct")),
        "return_5d_pct": round_or_none(feature.get("return_5d_pct")),
        "return_10d_pct": round_or_none(feature.get("return_10d_pct")),
        "return_20d_pct": round_or_none(feature.get("return_20d_pct")),
        "dist_ma20_pct": round_or_none(feature.get("dist_ma20_pct")),
        "dist_ma60_pct": round_or_none(feature.get("dist_ma60_pct")),
        "l2_main_3d_yi": round_or_none(as_yi(feature.get("l2_main_net_3d"))),
        "l2_oib_3d_yi": round_or_none(as_yi(feature.get("l2_oib_3d"))),
        "l2_cvd_3d_yi": round_or_none(as_yi(feature.get("l2_cvd_3d"))),
        "breakout_score": round_or_none(signal.get("breakout_score")),
        "distribution_score": round_or_none(signal.get("distribution_score")),
        "exit_signal": signal.get("exit_signal"),
        "manual_focus": " / ".join(item.get("daily_focus", [])[:3]),
        "buy_triggers": " / ".join(item.get("buy_triggers", [])[:2]),
        "risk_triggers": " / ".join(item.get("risk_triggers", [])[:2]),
        "source_research": " / ".join(item.get("source_research", [])),
    }


def write_csv(rows: List[Dict[str, Any]], trade_date: str) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{trade_date}.csv"
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def fmt(value: Any) -> str:
    return "--" if value is None else str(value)


def write_daily_doc(rows: List[Dict[str, Any]], trade_date: str) -> Path:
    DAILY_DOC_DIR.mkdir(parents=True, exist_ok=True)
    path = DAILY_DOC_DIR / f"{trade_date}.md"
    lines = [
        f"# 研究跟踪清单快照 {trade_date}",
        "",
        "## 自动数据",
        "",
        "| 股票 | 状态 | 收盘 | 成交额 | L2主力 | 超级单 | OIB | CVD | 20日涨幅 | 出货分 | 触发检查 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        trigger_hint = "人工复核"
        if row.get("exit_signal"):
            trigger_hint = "有退出风险信号"
        lines.append(
            "| {name} `{symbol}` | {status} | {close} | {amount_yi}亿 | {l2_main_yi}亿 | {l2_super_yi}亿 | {oib_yi}亿 | {cvd_yi}亿 | {return_20d_pct}% | {distribution_score} | {trigger_hint} |".format(
                trigger_hint=trigger_hint,
                **{key: fmt(value) for key, value in row.items()},
            )
        )
    lines.extend(
        [
            "",
            "## 人工盯盘记录",
            "",
            "- 新闻/公告：",
            "- 行业价格：",
            "- 盘口与资金判断：",
            "- 是否触发买点：",
            "- 是否调整状态：",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build research watchlist daily snapshot")
    parser.add_argument("--date", help="Target trade date, default latest available")
    args = parser.parse_args()

    watchlist = load_watchlist()
    items = [item for item in watchlist.get("items", []) if item.get("status") not in {"closed", "paused"}]
    if not items:
        raise SystemExit("No active watchlist items")
    trade_date = latest_trade_date([item["symbol"] for item in items], args.date)
    rows = [build_row(item, trade_date) for item in items]
    csv_path = write_csv(rows, trade_date)
    doc_path = write_daily_doc(rows, trade_date)
    print(f"snapshot_csv={csv_path}")
    print(f"daily_doc={doc_path}")


if __name__ == "__main__":
    main()
