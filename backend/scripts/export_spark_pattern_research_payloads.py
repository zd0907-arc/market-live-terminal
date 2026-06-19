#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

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
        str(Path(SELECTION_ARTIFACTS_ROOT) / "opportunity_discovery/postclose_exit_v0_2/postclose_exit_trades.csv"),
        str(ROOT / "data/selection/opportunity_discovery/postclose_exit_v0_2/postclose_exit_trades.csv"),
    )
)
DEFAULT_OUT_DIR = Path(RESEARCH_PAYLOADS_ROOT)
DEFAULT_PUBLIC_OUT_DIR = ROOT / "public/research"
WINDOW_BEFORE_ENTRY_DAYS = 40
WINDOW_FROM_ENTRY_DAYS = 50
HARD_EXIT_OFFSET = 21

VARIANTS: List[Dict[str, str]] = [
    {
        "id": "guarded",
        "title": "星火 v2 稳健型形态研究页",
        "description": "展示尽量少踩坑、优先后续能稳定冲高的那套模型。",
        "source": "postclose_exit_v0_2 / pc_model_th6_guard12_stop12",
        "policy": "pc_model_th6_guard12_stop12",
        "top1_strategy": "top1",
        "top3_strategy": "top1_top2_conditional",
        "top1_description": "稳健型每日 Top1，按股票合并。",
        "top3_description": "稳健型扩展档（top1 + 条件扩展信号），按股票合并；包含 Top1 股票。",
        "out_name": "spark_v2_guarded_pattern_research.json",
    },
    {
        "id": "aggressive",
        "title": "星火 v2 进攻型形态研究页",
        "description": "展示优先寻找后续冲得更高的强势票的那套模型。",
        "source": "postclose_exit_v0_2 / pc_model_th6_stop12",
        "policy": "pc_model_th6_stop12",
        "top1_strategy": "top1",
        "top3_strategy": "top1_top2_conditional",
        "top1_description": "进攻型每日 Top1，按股票合并。",
        "top3_description": "进攻型扩展档（top1 + 条件扩展信号），按股票合并；包含 Top1 股票。",
        "out_name": "spark_v2_aggressive_pattern_research.json",
    },
]

NAME_OVERRIDES = {
    "sz000700": "模塑科技",
    "sh603008": "喜临门",
}


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _load_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_names(selection_db: Path, symbols: Sequence[str]) -> Dict[str, str]:
    if not symbols:
        return {}
    placeholders = ",".join("?" for _ in symbols)
    sql = f"""
        SELECT lower(symbol) AS symbol, name, trade_date
        FROM selection_feature_daily
        WHERE lower(symbol) IN ({placeholders})
          AND name IS NOT NULL
          AND trim(name) != ''
          AND lower(name) != lower(symbol)
          AND lower(name) != 'nan'
        ORDER BY trade_date DESC
    """
    names: Dict[str, str] = {}
    with _connect_ro(selection_db) as conn:
        rows = conn.execute(sql, [symbol.lower() for symbol in symbols]).fetchall()
    for row in rows:
        symbol = str(row["symbol"]).lower()
        name = str(row["name"] or "").strip()
        if symbol and name and symbol not in names:
            names[symbol] = name
    names.update(NAME_OVERRIDES)
    return names


def _load_calendar_dates(atomic_db: Path, start_date: str, end_date: str) -> List[str]:
    sql = """
        SELECT DISTINCT trade_date
        FROM atomic_trade_daily
        WHERE trade_date >= ? AND trade_date <= ?
        ORDER BY trade_date ASC
    """
    with _connect_ro(atomic_db) as conn:
        return [str(row[0]) for row in conn.execute(sql, [start_date, end_date]).fetchall()]


def _date_at_offset(all_dates: Sequence[str], anchor: str, offset: int) -> str:
    ordered = list(all_dates)
    if not ordered:
        return anchor
    try:
        index = ordered.index(anchor)
    except ValueError:
        index = 0
        for idx, date_text in enumerate(ordered):
            if date_text >= anchor:
                index = idx
                break
    target_index = max(0, min(len(ordered) - 1, index + offset))
    return ordered[target_index]


def _load_daily_bars(atomic_db: Path, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
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
            t.l1_main_net_amount,
            t.l2_main_net_amount,
            t.l1_super_net_amount,
            t.l2_super_net_amount,
            l.is_limit_up_close,
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
    return [
        {
            "symbol": str(row["symbol"]).lower(),
            "trade_date": str(row["trade_date"]),
            "open": round(_safe_float(row["open"]), 4),
            "high": round(_safe_float(row["high"]), 4),
            "low": round(_safe_float(row["low"]), 4),
            "close": round(_safe_float(row["close"]), 4),
            "total_amount": round(_safe_float(row["total_amount"]), 2),
            "total_volume": round(_safe_float(row["total_volume"]), 2),
            "l1_main_net_amount": round(_safe_float(row["l1_main_net_amount"]), 2),
            "l2_main_net_amount": round(_safe_float(row["l2_main_net_amount"]), 2),
            "l1_super_net_amount": round(_safe_float(row["l1_super_net_amount"]), 2),
            "l2_super_net_amount": round(_safe_float(row["l2_super_net_amount"]), 2),
            "is_limit_up_close": int(_safe_float(row["is_limit_up_close"])),
            "limit_state_label": row["limit_state_label"],
        }
        for row in rows
    ]


def _assign_ranks(rows: Iterable[Dict[str, str]]) -> Dict[tuple[str, str, str], int]:
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["trade_date"])].append(row)
    result: Dict[tuple[str, str, str], int] = {}
    for trade_date, items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (-_safe_float(item.get("final_score")), str(item.get("symbol", "")).lower()),
        )
        for index, item in enumerate(ordered, start=1):
            result[(trade_date, str(item["symbol"]).lower(), str(item.get("strategy") or ""))] = index
    return result


def _compute_signal_metrics(
    bars: List[Dict[str, Any]],
    entry_date: str,
    hard_exit_date: str,
    entry_open: float,
    fallback_runup: float,
    fallback_drawdown: float,
    fallback_close_return: float,
) -> Dict[str, float]:
    if not bars or entry_open <= 0:
        return {
            "max_runup_22d_pct": fallback_runup,
            "max_drawdown_22d_pct": fallback_drawdown,
            "close_return_22d_pct": fallback_close_return,
        }
    relevant = [bar for bar in bars if entry_date <= str(bar["trade_date"]) <= hard_exit_date]
    if not relevant:
        return {
            "max_runup_22d_pct": fallback_runup,
            "max_drawdown_22d_pct": fallback_drawdown,
            "close_return_22d_pct": fallback_close_return,
        }
    max_runup = max(((_safe_float(bar["high"]) / entry_open) - 1.0) * 100.0 for bar in relevant)
    max_drawdown = min(((_safe_float(bar["low"]) / entry_open) - 1.0) * 100.0 for bar in relevant)
    close_return = (((_safe_float(relevant[-1]["close"]) / entry_open) - 1.0) * 100.0)
    return {
        "max_runup_22d_pct": round(max_runup, 4),
        "max_drawdown_22d_pct": round(max_drawdown, 4),
        "close_return_22d_pct": round(close_return, 4),
    }


def _build_section(
    section_id: str,
    title: str,
    description: str,
    strategy: str,
    policy: str,
    rows: List[Dict[str, str]],
    names: Dict[str, str],
    atomic_db: Path,
    all_dates: Sequence[str],
) -> Dict[str, Any]:
    scoped_rows = [
        row for row in rows
        if str(row.get("strategy") or "") == strategy and str(row.get("exit_policy") or "") == policy
    ]
    rank_map = _assign_ranks(scoped_rows)
    by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in sorted(scoped_rows, key=lambda item: (str(item["trade_date"]), str(item["symbol"]).lower())):
        symbol = str(row["symbol"]).lower()
        signal_date = str(row["trade_date"])
        entry_date = str(row["entry_date"])
        hard_exit_date = _date_at_offset(all_dates, entry_date, HARD_EXIT_OFFSET)
        window_start = _date_at_offset(all_dates, entry_date, -WINDOW_BEFORE_ENTRY_DAYS)
        window_end = _date_at_offset(all_dates, entry_date, WINDOW_FROM_ENTRY_DAYS)
        entry_open = _safe_float(row.get("gross_entry_price")) or _safe_float(row.get("net_entry_price"))
        signal_window_bars = _load_daily_bars(atomic_db, symbol, entry_date, hard_exit_date)
        metrics = _compute_signal_metrics(
            signal_window_bars,
            entry_date=entry_date,
            hard_exit_date=hard_exit_date,
            entry_open=entry_open,
            fallback_runup=_safe_float(row.get("max_runup_22d_pct")),
            fallback_drawdown=_safe_float(row.get("max_drawdown_before_exit_pct")),
            fallback_close_return=_safe_float(row.get("gross_return_pct")),
        )
        rank_key = (signal_date, symbol, strategy)
        by_symbol[symbol].append(
            {
                "rank": int(rank_map.get(rank_key, 1)),
                "signal_date": signal_date,
                "entry_date": entry_date,
                "hard_exit_date": hard_exit_date,
                "entry_open": round(entry_open, 4),
                "final_score": round(_safe_float(row.get("final_score")), 4),
                "max_runup_22d_pct": metrics["max_runup_22d_pct"],
                "max_drawdown_22d_pct": metrics["max_drawdown_22d_pct"],
                "close_return_22d_pct": metrics["close_return_22d_pct"],
                "mdd_to_mfe_pct": round(_safe_float(row.get("max_drawdown_before_exit_pct")), 4),
                "days_to_mfe": None,
                "_window_start": window_start,
                "_window_end": window_end,
            }
        )

    items: List[Dict[str, Any]] = []
    for symbol, signals in by_symbol.items():
        ordered_signals = sorted(signals, key=lambda item: (item["signal_date"], item["entry_date"]))
        window_start = min(signal["_window_start"] for signal in ordered_signals)
        window_end = max(signal["_window_end"] for signal in ordered_signals)
        bars = _load_daily_bars(atomic_db, symbol, window_start, window_end)
        close_by_date = {str(bar["trade_date"]): _safe_float(bar["close"]) for bar in bars}
        base_close = close_by_date.get(ordered_signals[0]["signal_date"]) or _safe_float(bars[0]["close"] if bars else 0.0)
        normalized_bars: List[Dict[str, Any]] = []
        for bar in bars:
            close_value = _safe_float(bar.get("close"))
            normalized_bars.append(
                {
                    **bar,
                    "return_from_first_signal_pct": round((((close_value / base_close) - 1.0) * 100.0), 4) if base_close > 0 else None,
                }
            )
        signal_count = len(ordered_signals)
        best_max_runup = max(signal["max_runup_22d_pct"] for signal in ordered_signals)
        avg_max_runup = sum(signal["max_runup_22d_pct"] for signal in ordered_signals) / signal_count
        avg_close_return = sum(signal["close_return_22d_pct"] for signal in ordered_signals) / signal_count
        worst_max_drawdown = min(signal["max_drawdown_22d_pct"] for signal in ordered_signals)
        avg_final_score = sum(signal["final_score"] for signal in ordered_signals) / signal_count
        items.append(
            {
                "id": f"{section_id}_{symbol}",
                "tier": section_id,
                "symbol": symbol,
                "name": names.get(symbol, symbol),
                "signal_count": signal_count,
                "first_signal_date": ordered_signals[0]["signal_date"],
                "last_signal_date": ordered_signals[-1]["signal_date"],
                "last_hard_exit_date": max(signal["hard_exit_date"] for signal in ordered_signals),
                "max_final_score": round(max(signal["final_score"] for signal in ordered_signals), 4),
                "avg_final_score": round(avg_final_score, 4),
                "best_max_runup_22d_pct": round(best_max_runup, 4),
                "avg_max_runup_22d_pct": round(avg_max_runup, 4),
                "avg_close_return_22d_pct": round(avg_close_return, 4),
                "worst_max_drawdown_22d_pct": round(worst_max_drawdown, 4),
                "signals": [
                    {key: value for key, value in signal.items() if not key.startswith("_")}
                    for signal in ordered_signals
                ],
                "window": {
                    "requested_before_entry_days": WINDOW_BEFORE_ENTRY_DAYS,
                    "requested_from_entry_days": WINDOW_FROM_ENTRY_DAYS,
                    "actual_bars": len(normalized_bars),
                    "start_date": normalized_bars[0]["trade_date"] if normalized_bars else window_start,
                    "end_date": normalized_bars[-1]["trade_date"] if normalized_bars else window_end,
                },
                "bars": normalized_bars,
            }
        )
    ordered_items = sorted(items, key=lambda item: (item["first_signal_date"], item["last_signal_date"], item["symbol"]))
    return {
        "id": section_id,
        "title": title,
        "description": description,
        "source_signal_count": len(scoped_rows),
        "stock_count": len(ordered_items),
        "items": ordered_items,
    }


def _build_variant_payload(
    variant: Dict[str, str],
    rows: List[Dict[str, str]],
    names: Dict[str, str],
    atomic_db: Path,
    all_dates: Sequence[str],
) -> Dict[str, Any]:
    top1_section = _build_section(
        section_id="top1",
        title="第一档：Top1",
        description=variant["top1_description"],
        strategy=variant["top1_strategy"],
        policy=variant["policy"],
        rows=rows,
        names=names,
        atomic_db=atomic_db,
        all_dates=all_dates,
    )
    top3_section = _build_section(
        section_id="top3",
        title="第二档：Top3",
        description=variant["top3_description"],
        strategy=variant["top3_strategy"],
        policy=variant["policy"],
        rows=rows,
        names=names,
        atomic_db=atomic_db,
        all_dates=all_dates,
    )
    return {
        "meta": {
            "title": variant["title"],
            "source": variant["source"],
            "window_rule": "同一股票合并；每个信号按买入日前 40 个交易日 + 买入日起 50 个交易日取窗口，并对多次信号取并集。图中标出信号日、次日买入日和 22 日硬退出日。",
            "top1_signal_count": top1_section["source_signal_count"],
            "top1_stock_count": top1_section["stock_count"],
            "top3_raw_signal_count": top3_section["source_signal_count"],
            "top3_raw_stock_count": top3_section["stock_count"],
            "top3_signal_count": top3_section["source_signal_count"],
            "top3_stock_count": top3_section["stock_count"],
            "name_source": "selection_feature_daily",
        },
        "sections": [top1_section, top3_section],
    }


def export_payloads(args: argparse.Namespace) -> None:
    atomic_db = Path(args.atomic_db)
    selection_db = Path(args.selection_db)
    trades_path = Path(args.trades)
    out_dir = Path(args.out_dir)
    public_out_dir_text = str(getattr(args, "public_out_dir", "") or "").strip()
    public_out_dir = Path(public_out_dir_text) if public_out_dir_text else None

    rows = _load_csv_rows(trades_path)
    symbols = sorted({str(row["symbol"]).lower() for row in rows if str(row.get("symbol") or "").strip()})
    names = _load_names(selection_db, symbols)

    start_date = min(str(row["trade_date"]) for row in rows)
    end_date = max(str(row["entry_date"]) for row in rows)
    all_dates = _load_calendar_dates(atomic_db, start_date, _date_at_offset(_load_calendar_dates(atomic_db, start_date, max(str(row["exit_date"]) for row in rows)), end_date, WINDOW_FROM_ENTRY_DAYS))
    out_dir.mkdir(parents=True, exist_ok=True)
    if public_out_dir:
        public_out_dir.mkdir(parents=True, exist_ok=True)

    outputs = []
    for variant in VARIANTS:
        payload = _build_variant_payload(variant, rows, names, atomic_db, all_dates)
        out_path = out_dir / variant["out_name"]
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        public_out = None
        if public_out_dir:
            public_path = public_out_dir / variant["out_name"]
            if public_path.resolve() != out_path.resolve():
                public_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            public_out = str(public_path)
        outputs.append(
            {
                "variant": variant["id"],
                "out": str(out_path),
                "public_out": public_out,
                "top1_stock_count": payload["meta"]["top1_stock_count"],
                "top3_stock_count": payload["meta"]["top3_stock_count"],
            }
        )
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Export spark pattern research payloads for v2 guarded/aggressive pages")
    parser.add_argument("--atomic-db", default=str(DEFAULT_ATOMIC_DB))
    parser.add_argument("--selection-db", default=str(DEFAULT_SELECTION_DB))
    parser.add_argument("--trades", default=str(DEFAULT_TRADES))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--public-out-dir", default=str(DEFAULT_PUBLIC_OUT_DIR), help="页面发布副本目录；传空字符串可跳过")
    args = parser.parse_args(argv)
    export_payloads(args)


if __name__ == "__main__":
    main()
