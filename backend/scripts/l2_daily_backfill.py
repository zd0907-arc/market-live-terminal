"""
盘后 L2 日包 -> 生产正式历史底座（5m + daily）回补脚本。

输入目录支持：
1. 旧结构：D:\\MarketData\\20260311\\20260311\\000833.SZ\\...
2. 新结构：D:\\MarketData\\202603\\20260311\\000833.SZ\\...

输出：
- history_5m_l2
- history_daily_l2
- l2_daily_ingest_runs
- l2_daily_ingest_failures
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.l2_package_layout import normalize_month_day_root
from backend.app.db.crud import get_app_config
from backend.app.db.l2_history_db import (
    add_l2_daily_ingest_failures,
    create_l2_daily_ingest_run,
    finish_l2_daily_ingest_run,
    replace_history_5m_l2_rows,
    replace_history_daily_l2_row,
)


REQUIRED_FILES = ("行情.csv", "逐笔成交.csv", "逐笔委托.csv")
ORDER_EVENT_TYPE_MAP = {
    "0": "add",
    "1": "cancel",
    "U": "cancel",
    "A": "add",
    "D": "cancel",
}
ORDER_SIDE_MAP = {
    "B": "buy",
    "S": "sell",
}


def normalize_symbol_dir_name(name: str) -> str:
    raw = (name or "").strip().lower()
    if len(raw) == 9 and raw[6] == ".":
        market = raw[7:]
        code = raw[:6]
        if market in {"sz", "sh", "bj"}:
            return f"{market}{code}"
    return raw


def canonical_trade_date(raw: str) -> str:
    text = (raw or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _format_trade_time(raw_series: pd.Series) -> pd.Series:
    text = raw_series.astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(9)
    hhmmss = text.str[:-3].str.zfill(6)
    return hhmmss.str[0:2] + ":" + hhmmss.str[2:4] + ":" + hhmmss.str[4:6]


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="gb18030", low_memory=False)
    bad_cols = [c for c in df.columns if str(c).strip() == "" or str(c).startswith("Unnamed")]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def list_symbol_dirs(day_root: Path, symbols: Optional[Sequence[str]] = None) -> List[Path]:
    targets = {
        s.lower() for s in symbols
    } if symbols else None
    result: List[Path] = []
    for child in sorted(day_root.iterdir()):
        if not child.is_dir():
            continue
        normalized = normalize_symbol_dir_name(child.name)
        if not normalized.startswith(("sz", "sh", "bj")):
            continue
        if targets and normalized not in targets:
            continue
        result.append(child)
    return result


def validate_symbol_dir(symbol_dir: Path) -> List[str]:
    missing = [name for name in REQUIRED_FILES if not (symbol_dir / name).is_file()]
    return missing


def _build_standardized_order_events(order: pd.DataFrame, trade_date: str) -> Tuple[pd.DataFrame, Dict[str, object]]:
    required_order = ["时间", "交易所委托号", "委托类型", "委托代码", "委托价格", "委托数量"]
    missing_order = [c for c in required_order if c not in order.columns]
    if missing_order:
        raise ValueError(f"逐笔委托缺列: {', '.join(missing_order)}")

    events = pd.DataFrame()
    events["time"] = _format_trade_time(order["时间"])
    events["datetime"] = pd.to_datetime(f"{trade_date} " + events["time"], errors="coerce")
    events["order_id"] = pd.to_numeric(order["交易所委托号"], errors="coerce").fillna(0).astype("int64")
    events["event_code"] = order["委托类型"].astype(str).str.strip().str.upper()
    events["side"] = order["委托代码"].astype(str).str.strip().str.upper().map(ORDER_SIDE_MAP)
    events["price"] = pd.to_numeric(order["委托价格"], errors="coerce") / 10000
    events["volume"] = pd.to_numeric(order["委托数量"], errors="coerce")
    events["event_type"] = events["event_code"].map(ORDER_EVENT_TYPE_MAP)

    events = events.dropna(subset=["datetime", "side", "event_type", "volume"])
    events = events[(events["volume"] > 0) & (events["order_id"] > 0)]

    session_time = events["datetime"].dt.strftime("%H:%M:%S")
    trading_mask = ((session_time >= "09:30:00") & (session_time <= "11:30:00")) | (
        (session_time >= "13:00:00") & (session_time <= "15:00:00")
    )
    events = events[trading_mask].sort_values("datetime").reset_index(drop=True)

    positive_price_rows = events[events["price"] > 0].copy()
    known_price_by_order_id = (
        positive_price_rows.groupby("order_id")["price"].last().to_dict()
        if not positive_price_rows.empty
        else {}
    )
    events["fallback_price"] = events["order_id"].map(known_price_by_order_id)
    events["effective_price"] = events["price"].where(events["price"] > 0, events["fallback_price"])
    events["amount"] = events["effective_price"] * events["volume"]
    events = events.dropna(subset=["amount"])
    events = events[events["amount"] > 0].reset_index(drop=True)

    diagnostics = {
        "order_event_rows": int(len(events)),
        "order_add_rows": int((events["event_type"] == "add").sum()),
        "order_cancel_rows": int((events["event_type"] == "cancel").sum()),
        "order_cancel_zero_price_rows": int(((events["event_type"] == "cancel") & (events["price"] <= 0)).sum()),
        "order_cancel_repriced_rows": int(
            ((events["event_type"] == "cancel") & (events["price"] <= 0) & events["fallback_price"].notna()).sum()
        ),
    }
    return events, diagnostics


def build_standardized_ticks(symbol_dir: Path, trade_date: str) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, object]]:
    trade_path = symbol_dir / "逐笔成交.csv"
    order_path = symbol_dir / "逐笔委托.csv"
    quote_path = symbol_dir / "行情.csv"

    trade = _read_csv(trade_path)
    order = _read_csv(order_path)
    _ = _read_csv(quote_path)  # Read once to fail fast on encoding/shape issues.

    required_trade = ["时间", "成交价格", "成交数量", "BS标志", "叫卖序号", "叫买序号"]
    missing_trade = [c for c in required_trade if c not in trade.columns]
    if missing_trade:
        raise ValueError(f"逐笔成交缺列: {', '.join(missing_trade)}")
    order_events, order_diagnostics = _build_standardized_order_events(order, trade_date)

    ticks = pd.DataFrame()
    ticks["time"] = _format_trade_time(trade["时间"])
    ticks["datetime"] = pd.to_datetime(f"{trade_date} " + ticks["time"], errors="coerce")
    ticks["price"] = pd.to_numeric(trade["成交价格"], errors="coerce") / 10000
    ticks["volume"] = pd.to_numeric(trade["成交数量"], errors="coerce")
    ticks["side"] = trade["BS标志"].astype(str).str.strip().str.upper().map(
        {"B": "buy", "S": "sell"}
    ).fillna("neutral")
    ticks["buy_order_id"] = pd.to_numeric(trade["叫买序号"], errors="coerce").fillna(0).astype("int64")
    ticks["sell_order_id"] = pd.to_numeric(trade["叫卖序号"], errors="coerce").fillna(0).astype("int64")
    ticks["amount"] = ticks["price"] * ticks["volume"]

    ticks = ticks.dropna(subset=["datetime", "price", "volume", "amount"])
    ticks = ticks[(ticks["price"] > 0) & (ticks["volume"] > 0) & (ticks["amount"] > 0)]

    session_time = ticks["datetime"].dt.strftime("%H:%M:%S")
    trading_mask = ((session_time >= "09:30:00") & (session_time <= "11:30:00")) | (
        (session_time >= "13:00:00") & (session_time <= "15:00:00")
    )
    ticks = ticks[trading_mask].sort_values("datetime").reset_index(drop=True)

    order_ids = set(pd.to_numeric(order["交易所委托号"], errors="coerce").dropna().astype("int64").tolist())
    buy_refs = set(ticks.loc[ticks["buy_order_id"] > 0, "buy_order_id"])
    sell_refs = set(ticks.loc[ticks["sell_order_id"] > 0, "sell_order_id"])
    overlap_buy_refs = sorted(buy_refs & order_ids)
    overlap_sell_refs = sorted(sell_refs & order_ids)
    missing_buy_refs = sorted(buy_refs - order_ids)
    missing_sell_refs = sorted(sell_refs - order_ids)
    if (buy_refs and not overlap_buy_refs) and (sell_refs and not overlap_sell_refs):
        raise ValueError(
            f"OrderID 无法在逐笔委托中对齐: buy_missing={len(missing_buy_refs)}, sell_missing={len(missing_sell_refs)}"
        )

    order_parent_totals: Dict[int, float] = {}
    if "委托价格" in order.columns and "委托数量" in order.columns:
        order_amount_df = pd.DataFrame()
        order_amount_df["order_id"] = pd.to_numeric(order["交易所委托号"], errors="coerce")
        order_amount_df["order_price"] = pd.to_numeric(order["委托价格"], errors="coerce") / 10000
        order_amount_df["order_volume"] = pd.to_numeric(order["委托数量"], errors="coerce")
        order_amount_df["order_amount"] = order_amount_df["order_price"] * order_amount_df["order_volume"]
        order_amount_df = order_amount_df.dropna(subset=["order_id", "order_amount"])
        order_amount_df = order_amount_df[order_amount_df["order_amount"] > 0]
        order_parent_totals = (
            order_amount_df.groupby(order_amount_df["order_id"].astype("int64"))["order_amount"].max().to_dict()
        )

    buy_trade_parent_totals = ticks[ticks["buy_order_id"] > 0].groupby("buy_order_id")["amount"].sum().to_dict()
    sell_trade_parent_totals = ticks[ticks["sell_order_id"] > 0].groupby("sell_order_id")["amount"].sum().to_dict()
    ticks["buy_parent_total"] = ticks["buy_order_id"].map(order_parent_totals)
    ticks["buy_parent_total"] = ticks["buy_parent_total"].fillna(ticks["buy_order_id"].map(buy_trade_parent_totals)).fillna(0.0)
    ticks["sell_parent_total"] = ticks["sell_order_id"].map(order_parent_totals)
    ticks["sell_parent_total"] = ticks["sell_parent_total"].fillna(ticks["sell_order_id"].map(sell_trade_parent_totals)).fillna(0.0)

    diagnostics = {
        "trade_rows": int(len(trade)),
        "ticks_rows": int(len(ticks)),
        "order_rows": int(len(order)),
        "trade_date": trade_date,
        "sample_time_range": [
            ticks["time"].min() if not ticks.empty else None,
            ticks["time"].max() if not ticks.empty else None,
        ],
        "order_alignment_buy_overlap": int(len(overlap_buy_refs)),
        "order_alignment_sell_overlap": int(len(overlap_sell_refs)),
        "order_alignment_buy_missing": int(len(missing_buy_refs)),
        "order_alignment_sell_missing": int(len(missing_sell_refs)),
    }
    diagnostics.update(order_diagnostics)
    return ticks, order_events, diagnostics


def _build_quality_info(diagnostics: Dict[str, object]) -> Optional[str]:
    buy_overlap = int(diagnostics.get("order_alignment_buy_overlap", 0) or 0)
    sell_overlap = int(diagnostics.get("order_alignment_sell_overlap", 0) or 0)
    buy_missing = int(diagnostics.get("order_alignment_buy_missing", 0) or 0)
    sell_missing = int(diagnostics.get("order_alignment_sell_missing", 0) or 0)

    messages: List[str] = []
    if buy_missing > 0 and buy_overlap <= 0 and sell_overlap > 0:
        messages.append("L2 买边单边回退，数值可能偏小")
    if sell_missing > 0 and sell_overlap <= 0 and buy_overlap > 0:
        messages.append("L2 卖边单边回退，数值可能偏小")
    if not messages and (buy_missing > 0 or sell_missing > 0):
        messages.append("OrderID 部分缺失，L2 数值可能偏小")
    if not messages:
        return None
    return "；".join(messages)


def compute_5m_bars(
    ticks: pd.DataFrame,
    order_events: pd.DataFrame,
    symbol: str,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
) -> List[Tuple]:
    if ticks.empty:
        return []

    df = ticks.copy()
    df["bucket"] = df["datetime"].dt.floor("5min")

    if "buy_parent_total" not in df.columns:
        buy_parent_totals = (
            df[df["buy_order_id"] > 0].groupby("buy_order_id")["amount"].sum().to_dict()
        )
        df["buy_parent_total"] = df["buy_order_id"].map(buy_parent_totals).fillna(0.0)
    if "sell_parent_total" not in df.columns:
        sell_parent_totals = (
            df[df["sell_order_id"] > 0].groupby("sell_order_id")["amount"].sum().to_dict()
        )
        df["sell_parent_total"] = df["sell_order_id"].map(sell_parent_totals).fillna(0.0)

    df["l1_main_buy_amt"] = ((df["side"] == "buy") & (df["amount"] >= large_threshold)) * df["amount"]
    df["l1_main_sell_amt"] = ((df["side"] == "sell") & (df["amount"] >= large_threshold)) * df["amount"]
    df["l1_super_buy_amt"] = ((df["side"] == "buy") & (df["amount"] >= super_threshold)) * df["amount"]
    df["l1_super_sell_amt"] = ((df["side"] == "sell") & (df["amount"] >= super_threshold)) * df["amount"]

    df["l2_main_buy_amt"] = (df["buy_parent_total"] >= large_threshold) * df["amount"]
    df["l2_main_sell_amt"] = (df["sell_parent_total"] >= large_threshold) * df["amount"]
    df["l2_super_buy_amt"] = (df["buy_parent_total"] >= super_threshold) * df["amount"]
    df["l2_super_sell_amt"] = (df["sell_parent_total"] >= super_threshold) * df["amount"]

    ohlc = df.groupby("bucket")["price"].agg(open="first", high="max", low="min", close="last")
    flow = df.groupby("bucket").agg(
        total_amount=("amount", "sum"),
        total_volume=("volume", "sum"),
        l1_main_buy=("l1_main_buy_amt", "sum"),
        l1_main_sell=("l1_main_sell_amt", "sum"),
        l1_super_buy=("l1_super_buy_amt", "sum"),
        l1_super_sell=("l1_super_sell_amt", "sum"),
        l2_main_buy=("l2_main_buy_amt", "sum"),
        l2_main_sell=("l2_main_sell_amt", "sum"),
        l2_super_buy=("l2_super_buy_amt", "sum"),
        l2_super_sell=("l2_super_sell_amt", "sum"),
        l2_cvd_buy=("amount", lambda s: float(s[df.loc[s.index, "side"] == "buy"].sum())),
        l2_cvd_sell=("amount", lambda s: float(s[df.loc[s.index, "side"] == "sell"].sum())),
    )
    merged = ohlc.join(flow, how="inner")

    if not order_events.empty:
        events = order_events.copy()
        events["bucket"] = events["datetime"].dt.floor("5min")
        event_agg = events.groupby("bucket").agg(
            l2_add_buy_amount=("amount", lambda s: float(s[(events.loc[s.index, "event_type"] == "add") & (events.loc[s.index, "side"] == "buy")].sum())),
            l2_add_sell_amount=("amount", lambda s: float(s[(events.loc[s.index, "event_type"] == "add") & (events.loc[s.index, "side"] == "sell")].sum())),
            l2_cancel_buy_amount=("amount", lambda s: float(s[(events.loc[s.index, "event_type"] == "cancel") & (events.loc[s.index, "side"] == "buy")].sum())),
            l2_cancel_sell_amount=("amount", lambda s: float(s[(events.loc[s.index, "event_type"] == "cancel") & (events.loc[s.index, "side"] == "sell")].sum())),
        )
        merged = merged.join(event_agg, how="left")
    else:
        merged["l2_add_buy_amount"] = None
        merged["l2_add_sell_amount"] = None
        merged["l2_cancel_buy_amount"] = None
        merged["l2_cancel_sell_amount"] = None

    merged["l2_cvd_delta"] = merged["l2_cvd_buy"] - merged["l2_cvd_sell"]
    merged["l2_oib_delta"] = (
        merged["l2_add_buy_amount"].fillna(0.0)
        - merged["l2_cancel_buy_amount"].fillna(0.0)
        - merged["l2_add_sell_amount"].fillna(0.0)
        + merged["l2_cancel_sell_amount"].fillna(0.0)
    )
    merged = merged.reset_index()

    return [
        (
            symbol,
            row["bucket"].strftime("%Y-%m-%d %H:%M:%S"),
            trade_date,
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["total_amount"]),
            float(row["total_volume"]),
            float(row["l1_main_buy"]),
            float(row["l1_main_sell"]),
            float(row["l1_super_buy"]),
            float(row["l1_super_sell"]),
            float(row["l2_main_buy"]),
            float(row["l2_main_sell"]),
            float(row["l2_super_buy"]),
            float(row["l2_super_sell"]),
            float(row["l2_add_buy_amount"]) if pd.notna(row["l2_add_buy_amount"]) else None,
            float(row["l2_add_sell_amount"]) if pd.notna(row["l2_add_sell_amount"]) else None,
            float(row["l2_cancel_buy_amount"]) if pd.notna(row["l2_cancel_buy_amount"]) else None,
            float(row["l2_cancel_sell_amount"]) if pd.notna(row["l2_cancel_sell_amount"]) else None,
            float(row["l2_cvd_delta"]),
            float(row["l2_oib_delta"]) if pd.notna(row["l2_oib_delta"]) else None,
        )
        for _, row in merged.iterrows()
    ]


def compute_daily_row(symbol: str, trade_date: str, rows_5m: Sequence[Tuple]) -> Optional[Tuple]:
    if not rows_5m:
        return None

    opens = rows_5m[0][3]
    highs = max(row[4] for row in rows_5m)
    lows = min(row[5] for row in rows_5m)
    closes = rows_5m[-1][6]
    total_amount = sum(row[7] for row in rows_5m)
    l1_main_buy = sum(row[9] for row in rows_5m)
    l1_main_sell = sum(row[10] for row in rows_5m)
    l1_super_buy = sum(row[11] for row in rows_5m)
    l1_super_sell = sum(row[12] for row in rows_5m)
    l2_main_buy = sum(row[13] for row in rows_5m)
    l2_main_sell = sum(row[14] for row in rows_5m)
    l2_super_buy = sum(row[15] for row in rows_5m)
    l2_super_sell = sum(row[16] for row in rows_5m)
    quality_messages = [str(row[23]).strip() for row in rows_5m if len(row) > 23 and str(row[23]).strip()]
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


def process_symbol_dir(
    symbol_dir: Path,
    trade_date: str,
    large_threshold: float,
    super_threshold: float,
) -> Tuple[str, List[Tuple], Optional[Tuple], Dict[str, object]]:
    missing = validate_symbol_dir(symbol_dir)
    symbol = normalize_symbol_dir_name(symbol_dir.name)
    if missing:
        raise ValueError(f"缺少文件: {', '.join(missing)}")

    ticks, order_events, diagnostics = build_standardized_ticks(symbol_dir, trade_date)
    quality_info = _build_quality_info(diagnostics)
    rows_5m = compute_5m_bars(
        ticks,
        order_events,
        symbol=symbol,
        trade_date=trade_date,
        large_threshold=large_threshold,
        super_threshold=super_threshold,
    )
    if quality_info:
        rows_5m = [tuple(list(row) + [quality_info]) for row in rows_5m]
    else:
        rows_5m = [tuple(list(row) + [None]) for row in rows_5m]
    daily_row = compute_daily_row(symbol, trade_date, rows_5m)
    diagnostics["bars_5m"] = len(rows_5m)
    diagnostics["has_daily"] = daily_row is not None
    diagnostics["quality_info"] = quality_info
    return symbol, rows_5m, daily_row, diagnostics


def _build_empty_result_message(diagnostics: Dict[str, object]) -> str:
    ticks_rows = int(diagnostics.get("ticks_rows", 0) or 0)
    bars_5m = int(diagnostics.get("bars_5m", 0) or 0)
    if ticks_rows <= 0:
        return "无有效 bar：交易时段内无可用逐笔（可能停牌、无成交或原始数据为空）"
    if bars_5m <= 0:
        return "无有效 bar：逐笔可读但未形成正式 5m 结果"
    return "无有效 daily：5m 已生成但未形成正式日线结果"


def backfill_day_package(
    package_path: Path,
    symbols: Optional[Sequence[str]] = None,
    large_threshold: float = 200000.0,
    super_threshold: float = 1000000.0,
    mode: str = "manual",
    dry_run: bool = False,
) -> Dict[str, object]:
    day_root, trade_date_raw = normalize_month_day_root(package_path)
    trade_date = canonical_trade_date(trade_date_raw)
    symbol_dirs = list_symbol_dirs(day_root, symbols=symbols)
    if not symbol_dirs:
        raise ValueError(f"未找到股票目录: {day_root}")

    run_id = None if dry_run else create_l2_daily_ingest_run(trade_date=trade_date, source_root=str(day_root), mode=mode)
    failures: List[Tuple[str, str, str, str]] = []
    success_symbols = 0
    empty_symbols = 0
    rows_5m_total = 0
    rows_daily_total = 0
    symbol_reports: Dict[str, Dict[str, object]] = {}

    try:
        for symbol_dir in symbol_dirs:
            symbol = normalize_symbol_dir_name(symbol_dir.name)
            try:
                normalized_symbol, rows_5m, daily_row, diagnostics = process_symbol_dir(
                    symbol_dir,
                    trade_date,
                    large_threshold,
                    super_threshold,
                )
                symbol_reports[normalized_symbol] = diagnostics
                if not rows_5m or daily_row is None:
                    empty_symbols += 1
                    failures.append(
                        (
                            normalized_symbol,
                            trade_date,
                            str(symbol_dir),
                            _build_empty_result_message(diagnostics),
                        )
                    )
                    continue
                if not dry_run:
                    replace_history_5m_l2_rows(normalized_symbol, trade_date, rows_5m)
                    replace_history_daily_l2_row(normalized_symbol, trade_date, daily_row)
                success_symbols += 1
                rows_5m_total += len(rows_5m)
                rows_daily_total += 1 if daily_row else 0
            except Exception as exc:
                failures.append((symbol, trade_date, str(symbol_dir), str(exc)))

        if not dry_run and run_id is not None:
            if failures:
                add_l2_daily_ingest_failures(run_id, failures)
            finish_l2_daily_ingest_run(
                run_id,
                status="done" if not failures else "partial_done",
                symbol_count=success_symbols,
                rows_5m=rows_5m_total,
                rows_daily=rows_daily_total,
                message=f"success={success_symbols}, failed={len(failures)}, empty={empty_symbols}",
            )
    except Exception as exc:
        if not dry_run and run_id is not None:
            finish_l2_daily_ingest_run(
                run_id,
                status="failed",
                symbol_count=success_symbols,
                rows_5m=rows_5m_total,
                rows_daily=rows_daily_total,
                message=str(exc),
            )
        raise

    return {
        "trade_date": trade_date,
        "day_root": str(day_root),
        "symbol_count": len(symbol_dirs),
        "success_symbols": success_symbols,
        "empty_symbols": empty_symbols,
        "failed_symbols": len(failures),
        "rows_5m": rows_5m_total,
        "rows_daily": rows_daily_total,
        "run_id": run_id,
        "failures": failures,
        "symbol_reports": symbol_reports,
        "dry_run": dry_run,
    }


def _default_thresholds() -> Tuple[float, float]:
    try:
        config = get_app_config()
        return (
            float(config.get("large_threshold", 200000)),
            float(config.get("super_large_threshold", 1000000)),
        )
    except Exception:
        return 200000.0, 1000000.0


def main() -> None:
    default_large, default_super = _default_thresholds()
    parser = argparse.ArgumentParser(description="盘后 L2 日包正式回补（5m + daily）")
    parser.add_argument("package_path", help=r"日包目录，如 D:\MarketData\202603\20260311")
    parser.add_argument("--symbols", default="", help="逗号分隔的 symbol，如 sz000833,sh600519；留空为全目录")
    parser.add_argument("--symbols-file", default="", help="可选 symbols 文件路径；每行一个 symbol，也兼容逗号分隔")
    parser.add_argument("--large-threshold", type=float, default=default_large)
    parser.add_argument("--super-threshold", type=float, default=default_super)
    parser.add_argument("--mode", default="manual", help="run mode，例如 manual/daily_auto")
    parser.add_argument("--db-path", default="", help="可选 DB 路径；默认使用环境变量 DB_PATH 或 data/market_data.db")
    parser.add_argument("--dry-run", action="store_true", help="只解析与统计，不写库")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if args.db_path:
        os.environ["DB_PATH"] = os.path.abspath(args.db_path)

    symbols = [s.strip().lower() for s in args.symbols.split(",") if s.strip()]
    if args.symbols_file:
        text = Path(args.symbols_file).read_text(encoding="utf-8")
        file_symbols = [
            part.strip().lower()
            for line in text.splitlines()
            for part in line.split(",")
            if part.strip()
        ]
        symbols.extend(file_symbols)
        symbols = sorted(set(symbols))
    report = backfill_day_package(
        Path(args.package_path),
        symbols=symbols or None,
        large_threshold=float(args.large_threshold),
        super_threshold=float(args.super_threshold),
        mode=args.mode,
        dry_run=bool(args.dry_run),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[l2-backfill] trade_date={report['trade_date']} "
            f"success={report['success_symbols']} failed={report['failed_symbols']} "
            f"rows_5m={report['rows_5m']} rows_daily={report['rows_daily']} "
            f"run_id={report['run_id']}"
        )
        if report["failures"]:
            print("[l2-backfill] failures:")
            for symbol, trade_date, source_file, error_message in report["failures"]:
                print(f"  - {symbol} {trade_date} {source_file}: {error_message}")


if __name__ == "__main__":
    main()
