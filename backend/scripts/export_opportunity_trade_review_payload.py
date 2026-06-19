#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from backend.app.core.config import RESEARCH_CURRENT_ROOT, RESEARCH_PAYLOADS_ROOT, SELECTION_ARTIFACTS_ROOT, first_existing_path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_ROOT = Path(os.getenv("RESEARCH_CURRENT_ROOT", RESEARCH_CURRENT_ROOT))
DEFAULT_ATOMIC_DB = Path(
    os.getenv(
        "ATOMIC_COMPACT_DB_PATH",
        os.getenv(
            "ATOMIC_MAINBOARD_DB_PATH",
            str(DEFAULT_RESEARCH_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"),
        ),
    )
)
DEFAULT_SELECTION_DB = Path(
    os.getenv(
        "SELECTION_DB_PATH",
        str(DEFAULT_RESEARCH_ROOT / "selection" / "selection_research.db"),
    )
)
DEFAULT_TRADES = Path(
    first_existing_path(
        str(Path(SELECTION_ARTIFACTS_ROOT) / "opportunity_discovery/opportunity_discovery_trade_l2_v0_1/holding_model_portfolio_trades.csv"),
        str(ROOT / "data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/holding_model_portfolio_trades.csv"),
    )
)
DEFAULT_SUMMARY = Path(
    first_existing_path(
        str(Path(SELECTION_ARTIFACTS_ROOT) / "opportunity_discovery/opportunity_discovery_trade_l2_v0_1/holding_model_portfolio_summary.csv"),
        str(ROOT / "data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/holding_model_portfolio_summary.csv"),
    )
)
DEFAULT_OUT = Path(RESEARCH_PAYLOADS_ROOT) / "opportunity_trade_review_payload.json"
DEFAULT_PUBLIC_OUT = ROOT / "public/research/opportunity_trade_review_payload.json"
DEFAULT_CALENDAR_START = "2025-01-02"


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _row_dict(row: pd.Series) -> Dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _load_names(selection_db: Path, symbols: Sequence[str]) -> Dict[str, str]:
    if not symbols:
        return {}
    placeholders = ",".join("?" for _ in symbols)
    sql = f"""
        SELECT lower(symbol) AS symbol, name
        FROM selection_feature_daily
        WHERE lower(symbol) IN ({placeholders})
          AND name IS NOT NULL
          AND name != ''
          AND lower(name) != lower(symbol)
          AND lower(name) != 'nan'
        ORDER BY trade_date DESC
    """
    names: Dict[str, str] = {}
    try:
        with _connect_ro(selection_db) as conn:
            rows = conn.execute(sql, [s.lower() for s in symbols]).fetchall()
    except Exception:
        return names
    for row in rows:
        symbol = str(row["symbol"]).lower()
        name = str(row["name"] or "").strip()
        if symbol and name and symbol not in names:
            names[symbol] = name
    return names


def _date_at_offset(dates: Sequence[str], anchor: str, offset: int) -> str:
    ordered = list(dates)
    if not ordered:
        return anchor
    try:
        idx = ordered.index(anchor)
    except ValueError:
        idx = 0
        for i, date in enumerate(ordered):
            if date >= anchor:
                idx = i
                break
    return ordered[max(0, min(len(ordered) - 1, idx + offset))]


def _load_daily_bars(
    atomic_db: Path,
    symbol: str,
    signal_date: str,
    *,
    lookback_days: int,
    forward_days: int,
    all_dates: Sequence[str],
) -> List[Dict[str, Any]]:
    start_date = _date_at_offset(all_dates, signal_date, -int(lookback_days))
    end_date = _date_at_offset(all_dates, signal_date, int(forward_days))
    sql = """
        SELECT
            lower(t.symbol) AS symbol,
            t.trade_date,
            t.open,
            t.high,
            t.low,
            t.close,
            t.total_amount,
            t.total_volume,
            t.trade_count,
            t.l1_main_net_amount,
            t.l1_super_net_amount,
            t.l2_main_net_amount,
            t.l2_super_net_amount,
            t.l2_buy_ratio,
            t.l2_sell_ratio,
            l.up_limit_price,
            l.down_limit_price,
            l.is_limit_up_close,
            l.broken_limit_up,
            l.limit_state_label
        FROM atomic_trade_daily AS t
        LEFT JOIN atomic_limit_state_daily AS l
          ON l.symbol = t.symbol
         AND l.trade_date = t.trade_date
        WHERE lower(t.symbol) = ?
          AND t.trade_date >= ?
          AND t.trade_date <= ?
        ORDER BY t.trade_date ASC
    """
    with _connect_ro(atomic_db) as conn:
        rows = conn.execute(sql, [symbol.lower(), start_date, end_date]).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload["l2_main_net_ratio"] = _safe_float(payload.get("l2_main_net_amount")) / max(_safe_float(payload.get("total_amount")), 1.0)
        payload["l2_super_net_ratio"] = _safe_float(payload.get("l2_super_net_amount")) / max(_safe_float(payload.get("total_amount")), 1.0)
        payload["active_buy_strength"] = _safe_float(payload.get("l2_buy_ratio")) - _safe_float(payload.get("l2_sell_ratio"))
        out.append({k: _jsonable(v) for k, v in payload.items()})
    return out


def _load_calendar_dates(atomic_db: Path, start_date: str, end_date: str) -> List[str]:
    sql = """
        SELECT DISTINCT trade_date
        FROM atomic_trade_daily
        WHERE trade_date >= ? AND trade_date <= ?
        ORDER BY trade_date ASC
    """
    with _connect_ro(atomic_db) as conn:
        return [str(row[0]) for row in conn.execute(sql, [start_date, end_date]).fetchall()]


def _mark_positions(
    atomic_db: Path,
    positions: List[Dict[str, Any]],
    trade_date: str,
    fallback_cash: float,
) -> float:
    if not positions:
        return 0.0
    symbols = sorted({str(pos["symbol"]).lower() for pos in positions})
    placeholders = ",".join("?" for _ in symbols)
    sql = f"""
        SELECT lower(symbol) AS symbol, close
        FROM atomic_trade_daily
        WHERE lower(symbol) IN ({placeholders})
          AND trade_date = ?
    """
    with _connect_ro(atomic_db) as conn:
        prices = {str(row["symbol"]).lower(): _safe_float(row["close"]) for row in conn.execute(sql, [*symbols, trade_date]).fetchall()}
    total = 0.0
    for pos in positions:
        price = prices.get(str(pos["symbol"]).lower())
        if price and price > 0:
            total += int(pos["shares"]) * price
        else:
            total += _safe_float(pos.get("cost_cash"), fallback_cash)
    return total


def _build_daily_equity(atomic_db: Path, trades: pd.DataFrame, initial_capital: float) -> List[Dict[str, Any]]:
    if trades.empty:
        return []
    entry_min = str(trades["entry_date"].min())
    exit_max = str(trades["exit_date"].max())
    dates = _load_calendar_dates(atomic_db, entry_min, exit_max)
    by_entry: Dict[str, List[Dict[str, Any]]] = {}
    by_exit: Dict[str, List[Dict[str, Any]]] = {}
    for idx, row in trades.reset_index(drop=True).iterrows():
        item = _row_dict(row)
        item["trade_id"] = f"T{idx + 1:02d}"
        by_entry.setdefault(str(item["entry_date"]), []).append(item)
        by_exit.setdefault(str(item["exit_date"]), []).append(item)

    cash = float(initial_capital)
    positions: List[Dict[str, Any]] = []
    curve: List[Dict[str, Any]] = []
    for trade_date in dates:
        for trade in by_entry.get(trade_date, []):
            cost = _safe_float(trade.get("position_cash"))
            cash -= cost
            positions.append(
                {
                    "trade_id": trade["trade_id"],
                    "symbol": str(trade["symbol"]).lower(),
                    "shares": int(_safe_float(trade.get("shares"))),
                    "cost_cash": cost,
                }
            )
        for trade in by_exit.get(trade_date, []):
            target_id = str(trade["trade_id"])
            positions = [pos for pos in positions if str(pos["trade_id"]) != target_id]
            cash += _safe_float(trade.get("position_cash")) + _safe_float(trade.get("pnl_cash"))
        market_value = _mark_positions(atomic_db, positions, trade_date, 0.0)
        equity = cash + market_value
        curve.append(
            {
                "trade_date": trade_date,
                "cash": round(cash, 2),
                "market_value": round(market_value, 2),
                "equity": round(equity, 2),
                "open_positions": len(positions),
                "return_pct": round((equity / initial_capital - 1.0) * 100.0, 4),
            }
        )
    return curve


def export_payload(args: argparse.Namespace) -> None:
    trades_path = Path(args.trades)
    summary_path = Path(args.summary)
    atomic_db = Path(args.atomic_db)
    selection_db = Path(args.selection_db)
    out_path = Path(args.out)
    initial_capital = float(args.initial_capital)
    review_lookback_days = int(args.review_lookback_days)
    review_forward_days = int(args.review_forward_days)

    all_trades = pd.read_csv(trades_path)
    mask = all_trades["mode"].astype(str).eq(args.mode) & all_trades["policy"].astype(str).eq(args.policy)
    trades = all_trades[mask].copy()
    if trades.empty:
        raise RuntimeError(f"No trades found for mode={args.mode} policy={args.policy}")
    trades = trades.sort_values(["entry_date", "exit_date", "symbol"]).reset_index(drop=True)
    trades.insert(0, "trade_id", [f"T{i + 1:02d}" for i in range(len(trades))])

    summaries = pd.read_csv(summary_path)
    summary_row = summaries[summaries["mode"].astype(str).eq(args.mode) & summaries["policy"].astype(str).eq(args.policy)]
    summary = _row_dict(summary_row.iloc[0]) if not summary_row.empty else {}

    symbols = sorted(set(trades["symbol"].astype(str).str.lower()))
    names = _load_names(selection_db, symbols)
    name_overrides = {
        "sz000890": "法尔胜",
        "sh600123": "兰花科创",
        "sh600370": "三房巷",
        "sh603175": "超颖电子",
        "sh603618": "杭电股份",
        "sz002468": "申通快递",
        "sh603529": "爱玛科技",
        "sz002980": "华盛昌",
        "sh605299": "舒华体育",
        "sz002437": "誉衡药业",
    }
    names.update(name_overrides)
    calendar_start = str(args.calendar_start)
    if not calendar_start:
        calendar_start = str(all_trades["trade_date"].min())
    calendar_start = min(calendar_start, str(all_trades["trade_date"].min()))
    if not trades.empty:
        calendar_start = min(calendar_start, str(trades["trade_date"].min()))
    calendar_end = str(all_trades["exit_date"].max())
    if not trades.empty:
        calendar_end = max(calendar_end, str(trades["exit_date"].max()))
    all_dates = _load_calendar_dates(atomic_db, calendar_start, calendar_end)

    detail_trades: List[Dict[str, Any]] = []
    for _, row in trades.iterrows():
        item = _row_dict(row)
        symbol = str(item["symbol"]).lower()
        item["symbol"] = symbol
        item["name"] = names.get(symbol, symbol)
        item["buy_amount"] = item.get("position_cash")
        item["sell_amount"] = round(_safe_float(item.get("position_cash")) + _safe_float(item.get("pnl_cash")), 2)
        item["entry_cost_price"] = item.get("net_entry_price")
        item["exit_net_price"] = item.get("net_exit_price")
        bars = _load_daily_bars(
            atomic_db,
            symbol,
            str(item["trade_date"]),
            lookback_days=review_lookback_days,
            forward_days=review_forward_days,
            all_dates=all_dates,
        )
        detail_trades.append({**item, "bars": bars})

    curve = _build_daily_equity(atomic_db, trades, initial_capital)
    payload = {
        "meta": {
            "version": "opportunity_trade_review_v1",
            "strategy": "机会发现模型",
            "mode": args.mode,
            "policy": args.policy,
            "description": "Top1 + 15%止盈 + 12%硬止损 + 简化持仓模型退出壳",
            "initial_capital": initial_capital,
            "trade_count": int(len(detail_trades)),
            "review_window": {
                "lookback_trading_days": review_lookback_days,
                "forward_trading_days": review_forward_days,
                "anchor": "signal_date",
            },
            "signal_start": str(trades["trade_date"].min()),
            "signal_end": str(trades["trade_date"].max()),
            "entry_start": str(trades["entry_date"].min()),
            "exit_end": str(trades["exit_date"].max()),
            "source_trades": str(trades_path),
        },
        "summary": summary,
        "trades": detail_trades,
        "equity_curve": curve,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    public_out = str(getattr(args, "public_out", "") or "").strip()
    if public_out:
        public_path = Path(public_out)
        if public_path.resolve() != out_path.resolve():
            public_path.parent.mkdir(parents=True, exist_ok=True)
            public_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"out": str(out_path), "public_out": public_out or None, "trades": len(detail_trades), "curve_rows": len(curve)},
            ensure_ascii=False,
        )
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Export opportunity trade review static payload")
    parser.add_argument("--atomic-db", default=str(DEFAULT_ATOMIC_DB))
    parser.add_argument("--selection-db", default=str(DEFAULT_SELECTION_DB))
    parser.add_argument("--trades", default=str(DEFAULT_TRADES))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--mode", default="top1")
    parser.add_argument("--policy", default="hold_model_tp15_stop12")
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--calendar-start", default=DEFAULT_CALENDAR_START)
    parser.add_argument("--review-lookback-days", type=int, default=10)
    parser.add_argument("--review-forward-days", type=int, default=22)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--public-out", default=str(DEFAULT_PUBLIC_OUT), help="页面发布副本；传空字符串可跳过")
    args = parser.parse_args(argv)
    export_payload(args)


if __name__ == "__main__":
    main()
