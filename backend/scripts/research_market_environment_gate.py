#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ROOT = Path(os.getenv("RESEARCH_CURRENT_ROOT", "/Users/dong/Desktop/AIGC/market-data/research/current"))
DATA_ROOT = Path(os.getenv("DATA_DIR", "/Users/dong/Desktop/AIGC/market-data"))

DEFAULT_ATOMIC_DB = RESEARCH_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"
DEFAULT_SELECTION_DB = RESEARCH_ROOT / "selection" / "selection_research.db"
DEFAULT_FEATURE_DB = RESEARCH_ROOT / "selection" / "model_feature_store.db"
DEFAULT_META_DB = DATA_ROOT / "live" / "market_data.db"
DEFAULT_OUT_DIR = ROOT / "docs" / "selection" / "market_environment_gate_2026-06-10"

WINDOWS = (1, 3, 5, 10, 20)
HORIZONS = (5, 10, 22)
MARKET_METRIC_SPECS = [
    ("all_up_ratio", "全市场上涨占比"),
    ("all_med_ret", "全市场中位涨跌幅"),
    ("small_up_ratio", "小盘上涨占比"),
    ("small_med_ret", "小盘中位涨跌幅"),
    ("large_up_ratio", "大盘上涨占比"),
    ("large_med_ret", "大盘中位涨跌幅"),
]
SOURCE_LABELS = {
    "spark_opportunity_selector": "星火机会模型",
    "stable_capital_callback": "资金流回调稳健策略",
    "trend_continuation_callback": "趋势延续策略",
    "probe_day0_watch": "试盘识别-当日观察",
    "probe_d3_confirmed": "试盘识别-三日确认",
}


@dataclass(frozen=True)
class PriceRow:
    symbol: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def mean(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if not vals:
        return None
    return sum(vals) / len(vals)


def median(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if not vals:
        return None
    return statistics.median(vals)


def pct(part: float, total: float) -> Optional[float]:
    if total <= 0:
        return None
    return part / total * 100.0


def round_or_none(value: Any, digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    v = safe_float(value, default=float("nan"))
    if math.isnan(v):
        return None
    return round(v, digits)


def pitfall_reason(close_pct: Any, mae_pct: Any) -> Tuple[int, str]:
    close_bad = safe_float(close_pct, default=float("nan")) <= -5.0
    drawdown_bad = safe_float(mae_pct, default=float("nan")) <= -8.0
    if close_bad and drawdown_bad:
        return 1, "收盘亏5%且最大浮亏8%"
    if close_bad:
        return 1, "收盘亏5%"
    if drawdown_bad:
        return 1, "最大浮亏8%"
    return 0, ""


def stat(values: Iterable[Any]) -> Dict[str, Any]:
    vals = sorted(safe_float(v, default=float("nan")) for v in values)
    vals = [v for v in vals if not math.isnan(v)]
    if not vals:
        return {
            "n": 0,
            "avg": None,
            "median": None,
            "win_rate": None,
            "loss_rate": None,
            "p10": None,
            "p25": None,
            "worst": None,
            "best": None,
        }
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 4),
        "median": round(statistics.median(vals), 4),
        "win_rate": round(sum(1 for v in vals if v > 0) / len(vals) * 100.0, 4),
        "loss_rate": round(sum(1 for v in vals if v < 0) / len(vals) * 100.0, 4),
        "p10": round(vals[int((len(vals) - 1) * 0.10)], 4),
        "p25": round(vals[int((len(vals) - 1) * 0.25)], 4),
        "worst": round(vals[0], 4),
        "best": round(vals[-1], 4),
    }


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def read_rows(db_path: Path, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
    with sqlite3.connect(str(db_path), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        return list(conn.execute(sql, params))


def load_market_cap_buckets(meta_db: Path) -> Dict[str, str]:
    if not meta_db.exists():
        return {}
    rows = read_rows(
        meta_db,
        """
        SELECT symbol, market_cap
        FROM stock_universe_meta
        WHERE market_cap IS NOT NULL AND market_cap > 0
        ORDER BY market_cap
        """,
    )
    if not rows:
        return {}
    caps = [(str(r["symbol"]), safe_float(r["market_cap"])) for r in rows]
    small_cut = caps[int((len(caps) - 1) * 0.40)][1]
    large_cut = caps[int((len(caps) - 1) * 0.80)][1]
    buckets: Dict[str, str] = {}
    for symbol, cap in caps:
        if cap <= small_cut:
            buckets[symbol] = "small"
        elif cap >= large_cut:
            buckets[symbol] = "large"
        else:
            buckets[symbol] = "mid"
    return buckets


def load_prices(atomic_db: Path) -> Tuple[Dict[str, List[PriceRow]], List[str], Dict[str, Dict[str, PriceRow]]]:
    rows = read_rows(
        atomic_db,
        """
        SELECT symbol, trade_date, open, high, low, close
        FROM atomic_trade_daily
        ORDER BY symbol, trade_date
        """,
    )
    by_symbol: Dict[str, List[PriceRow]] = defaultdict(list)
    dates_set = set()
    by_symbol_date: Dict[str, Dict[str, PriceRow]] = defaultdict(dict)
    for row in rows:
        item = PriceRow(
            symbol=str(row["symbol"]),
            trade_date=str(row["trade_date"]),
            open=safe_float(row["open"]),
            high=safe_float(row["high"]),
            low=safe_float(row["low"]),
            close=safe_float(row["close"]),
        )
        by_symbol[item.symbol].append(item)
        by_symbol_date[item.symbol][item.trade_date] = item
        dates_set.add(item.trade_date)
    return dict(by_symbol), sorted(dates_set), dict(by_symbol_date)


def load_index_state(feature_db: Path) -> Dict[str, Dict[str, Any]]:
    if not feature_db.exists():
        return {}
    rows = read_rows(
        feature_db,
        """
        SELECT
          trade_date,
          csi1000_return_1d_pct, csi1000_return_5d_pct, csi1000_return_20d_pct,
          csi500_return_1d_pct, csi500_return_5d_pct, csi500_return_20d_pct,
          hs300_return_1d_pct, hs300_return_5d_pct, hs300_return_20d_pct,
          sh_index_return_1d_pct, sh_index_return_5d_pct, sh_index_return_20d_pct,
          gem_index_return_1d_pct, gem_index_return_5d_pct, gem_index_return_20d_pct,
          limit_up_count, limit_down_count, broken_limit_up_ratio,
          market_total_amount_yi, market_amount_ratio_20d,
          has_index_data, has_heat_data, has_order_data, has_book_data
        FROM model_market_state_daily_v1
        ORDER BY trade_date
        """,
    )
    state = {str(r["trade_date"]): dict(r) for r in rows}
    with sqlite3.connect(str(feature_db), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        has_index_table = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='model_market_index_daily'
            """
        ).fetchone()
        if not has_index_table:
            return state
        idx_rows = list(
            conn.execute(
                """
                SELECT index_code, trade_date, close
                FROM model_market_index_daily
                ORDER BY index_code, trade_date
                """
            )
        )
    by_index: Dict[str, List[sqlite3.Row]] = defaultdict(list)
    for row in idx_rows:
        by_index[str(row["index_code"])].append(row)
    prefix_map = {
        "000852.SH": "csi1000",
        "000905.SH": "csi500",
        "000300.SH": "hs300",
        "000001.SH": "sh_index",
        "399006.SZ": "gem_index",
    }
    for index_code, idx_items in by_index.items():
        prefix = prefix_map.get(index_code)
        if not prefix:
            continue
        for i, row in enumerate(idx_items):
            trade_date = str(row["trade_date"])
            close = safe_float(row["close"])
            if trade_date not in state:
                state[trade_date] = {"trade_date": trade_date}
            for window in (1, 5, 20):
                key = f"{prefix}_return_{window}d_pct"
                if i < window or state[trade_date].get(key) is not None:
                    continue
                prev_close = safe_float(idx_items[i - window]["close"])
                if close > 0 and prev_close > 0:
                    state[trade_date][key] = (close / prev_close - 1.0) * 100.0
    return state


def build_market_state(
    prices_by_symbol: Dict[str, List[PriceRow]],
    trade_dates: Sequence[str],
    cap_buckets: Dict[str, str],
    index_state: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    values: Dict[Tuple[str, str, int], List[float]] = defaultdict(list)
    for symbol, rows in prices_by_symbol.items():
        bucket = cap_buckets.get(symbol)
        for i, row in enumerate(rows):
            for window in WINDOWS:
                if i < window:
                    continue
                prev = rows[i - window]
                if prev.close <= 0:
                    continue
                ret = (row.close / prev.close - 1.0) * 100.0
                values[(row.trade_date, "all", window)].append(ret)
                if bucket in {"small", "large"}:
                    values[(row.trade_date, bucket, window)].append(ret)

    state_rows: List[Dict[str, Any]] = []
    for trade_date in trade_dates:
        out: Dict[str, Any] = {"trade_date": trade_date}
        for bucket in ("all", "small", "large"):
            for window in WINDOWS:
                vals = values.get((trade_date, bucket, window), [])
                out[f"{bucket}_sample_{window}d"] = len(vals)
                out[f"{bucket}_med_ret_{window}d"] = round_or_none(median(vals), 4)
                out[f"{bucket}_up_ratio_{window}d"] = round_or_none(pct(sum(1 for v in vals if v > 0), len(vals)), 4)
                out[f"{bucket}_down5_ratio_{window}d"] = round_or_none(pct(sum(1 for v in vals if v <= -5), len(vals)), 4)
                out[f"{bucket}_strong10_ratio_{window}d"] = round_or_none(pct(sum(1 for v in vals if v >= 10), len(vals)), 4)

        idx = index_state.get(trade_date, {})
        for key in (
            "csi1000_return_1d_pct",
            "csi1000_return_5d_pct",
            "csi1000_return_20d_pct",
            "csi500_return_5d_pct",
            "hs300_return_5d_pct",
            "sh_index_return_5d_pct",
            "gem_index_return_5d_pct",
            "limit_up_count",
            "limit_down_count",
            "broken_limit_up_ratio",
            "market_total_amount_yi",
            "market_amount_ratio_20d",
            "has_index_data",
            "has_heat_data",
            "has_order_data",
            "has_book_data",
        ):
            out[key] = idx.get(key)

        all_up_5 = safe_float(out.get("all_up_ratio_5d"))
        all_med_5 = safe_float(out.get("all_med_ret_5d"))
        all_up_1 = safe_float(out.get("all_up_ratio_1d"))
        all_med_1 = safe_float(out.get("all_med_ret_1d"))
        all_up_3 = safe_float(out.get("all_up_ratio_3d"))
        all_med_3 = safe_float(out.get("all_med_ret_3d"))
        all_up_10 = safe_float(out.get("all_up_ratio_10d"))
        all_med_10 = safe_float(out.get("all_med_ret_10d"))
        small_up_3 = safe_float(out.get("small_up_ratio_3d"))
        small_up_5 = safe_float(out.get("small_up_ratio_5d"))
        small_med_5 = safe_float(out.get("small_med_ret_5d"))
        csi1000_5 = safe_float(out.get("csi1000_return_5d_pct"))

        breadth_score = all_up_5
        small_score = small_up_5 if small_up_5 > 0 else all_up_5
        ret_score = clamp(50.0 + all_med_5 * 8.0, 0.0, 100.0)
        trend_score = clamp(50.0 + all_med_10 * 5.0, 0.0, 100.0)
        index_score = clamp(50.0 + csi1000_5 * 7.0, 0.0, 100.0) if out.get("csi1000_return_5d_pct") is not None else 50.0
        score = 0.32 * breadth_score + 0.24 * small_score + 0.20 * ret_score + 0.16 * trend_score + 0.08 * index_score
        out["water_score"] = round(score, 4)

        defense = all_up_5 < 30.0 or all_med_5 <= -3.0 or small_up_5 < 25.0
        attack = all_up_5 >= 55.0 and all_med_5 > 0.0 and small_up_5 >= 50.0 and small_med_5 > -1.0
        if defense:
            regime = "defense"
            action = "暂停新开仓"
            if all_up_3 < 25.0 and all_med_3 <= -2.5 and small_up_3 < 25.0:
                detail = "defense_active_decline"
                detail_label = "防守-持续下跌"
            elif (all_up_1 >= 55.0 and all_med_1 > 0.0) or (all_up_3 >= 40.0 and all_med_3 > -1.0):
                detail = "defense_repair"
                detail_label = "防守-修复观察"
            else:
                detail = "defense_pressure"
                detail_label = "防守-弱势承压"
        elif attack:
            regime = "attack"
            action = "可参与"
            detail = "attack"
            detail_label = "攻击"
        else:
            regime = "caution"
            action = "观察为主"
            detail = "caution"
            detail_label = "谨慎"
        out["market_regime"] = regime
        out["market_detail"] = detail
        out["market_detail_label"] = detail_label
        out["default_action"] = action

        reasons = []
        if all_up_5 < 30.0:
            reasons.append(f"5日全市场上涨占比{all_up_5:.1f}%")
        if all_med_5 <= -3.0:
            reasons.append(f"5日全市场中位涨跌幅{all_med_5:.1f}%")
        if small_up_5 < 25.0:
            reasons.append(f"5日小盘上涨占比{small_up_5:.1f}%")
        if attack:
            reasons.append(f"5日全市场上涨占比{all_up_5:.1f}%")
            reasons.append(f"5日全市场中位涨跌幅{all_med_5:.1f}%")
            reasons.append(f"5日小盘上涨占比{small_up_5:.1f}%")
        if not reasons:
            reasons.append(f"5日上涨占比{all_up_5:.1f}%")
            reasons.append(f"10日上涨占比{all_up_10:.1f}%")
            reasons.append(f"10日中位涨跌幅{all_med_10:.1f}%")
        out["reason_top3"] = "；".join(reasons[:3])
        state_rows.append(out)
    return state_rows


def load_candidates(selection_db: Path) -> List[Dict[str, Any]]:
    rows = read_rows(
        selection_db,
        """
        SELECT trade_date, symbol, name, source_id, source_name, source_type, source_version,
               rank, score, score_scale, horizon, suggested_action, action_label, entry_allowed,
               reason_summary
        FROM selection_candidate_sources
        ORDER BY trade_date, source_id, rank, symbol
        """,
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["business_source_name"] = SOURCE_LABELS.get(str(item["source_id"]), str(item["source_name"]))
        out.append(item)
    return out


def build_source_coverage(candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, int], List[Dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[
            (
                str(row.get("business_source_name")),
                str(row.get("source_id")),
                str(row.get("suggested_action")),
                safe_int(row.get("entry_allowed")),
            )
        ].append(row)
    out = []
    for (name, source_id, action, allowed), rows in sorted(grouped.items()):
        dates = sorted(str(r["trade_date"]) for r in rows)
        out.append(
            {
                "business_source_name": name,
                "source_id": source_id,
                "suggested_action": action,
                "entry_allowed": allowed,
                "n": len(rows),
                "min_trade_date": dates[0],
                "max_trade_date": dates[-1],
            }
        )
    return out


def enrich_candidate_outcomes(
    candidates: Sequence[Dict[str, Any]],
    trade_dates: Sequence[str],
    prices_by_symbol_date: Dict[str, Dict[str, PriceRow]],
    market_state_by_date: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    date_index = {d: i for i, d in enumerate(trade_dates)}
    out: List[Dict[str, Any]] = []
    for item in candidates:
        signal_date = str(item["trade_date"])
        symbol = str(item["symbol"])
        i = date_index.get(signal_date)
        if i is None or i + 1 >= len(trade_dates):
            continue
        entry_date = trade_dates[i + 1]
        entry_row = prices_by_symbol_date.get(symbol, {}).get(entry_date)
        if entry_row is None or entry_row.open <= 0:
            continue
        rec = dict(item)
        rec["entry_date"] = entry_date
        rec["entry_open"] = round(entry_row.open, 4)
        market = market_state_by_date.get(signal_date, {})
        for key in (
            "market_regime",
            "market_detail",
            "market_detail_label",
            "default_action",
            "water_score",
            "reason_top3",
            "csi1000_return_5d_pct",
            "csi1000_return_20d_pct",
        ):
            rec[key] = market.get(key)
        for prefix, _label in MARKET_METRIC_SPECS:
            for window in WINDOWS:
                rec[f"{prefix}_{window}d"] = market.get(f"{prefix}_{window}d")
        for horizon in HORIZONS:
            rows: List[PriceRow] = []
            for offset in range(1, horizon + 1):
                if i + offset >= len(trade_dates):
                    break
                row = prices_by_symbol_date.get(symbol, {}).get(trade_dates[i + offset])
                if row is not None:
                    rows.append(row)
            if not rows:
                rec[f"full_{horizon}d"] = 0
                rec[f"days_{horizon}d"] = 0
                rec[f"mfe_{horizon}d_pct"] = None
                rec[f"mae_{horizon}d_pct"] = None
                rec[f"close_{horizon}d_pct"] = None
                rec[f"pitfall_{horizon}d"] = None
                rec[f"pitfall_reason_{horizon}d"] = ""
                continue
            max_high = max(r.high for r in rows)
            min_low = min(r.low for r in rows)
            close_last = rows[-1].close
            mfe_pct = round((max_high / entry_row.open - 1.0) * 100.0, 4)
            mae_pct = round((min_low / entry_row.open - 1.0) * 100.0, 4)
            close_pct = round((close_last / entry_row.open - 1.0) * 100.0, 4)
            pitfall, reason = pitfall_reason(close_pct, mae_pct)
            rec[f"full_{horizon}d"] = 1 if len(rows) >= horizon else 0
            rec[f"days_{horizon}d"] = len(rows)
            rec[f"mfe_{horizon}d_pct"] = mfe_pct
            rec[f"mae_{horizon}d_pct"] = mae_pct
            rec[f"close_{horizon}d_pct"] = close_pct
            rec[f"pitfall_{horizon}d"] = pitfall
            rec[f"pitfall_reason_{horizon}d"] = reason
        rec["buyable"] = 1 if str(rec.get("suggested_action")) == "candidate_buy" and safe_int(rec.get("entry_allowed")) == 1 else 0
        out.append(rec)
    return out


def summarize_group(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return summarize_group_horizon(rows, 22)


def summarize_group_horizon(rows: Sequence[Dict[str, Any]], horizon: int) -> Dict[str, Any]:
    n = len(rows)
    if not rows:
        return {
            "n": 0,
            f"avg_mfe_{horizon}d_pct": None,
            "hit10_rate": None,
            "hit15_rate": None,
            "hit20_rate": None,
            f"avg_close_{horizon}d_pct": None,
            "close_loss_rate": None,
            f"avg_mae_{horizon}d_pct": None,
            "stop5_rate": None,
            "pitfall_rate": None,
            f"full{horizon}_rate": None,
        }
    mfe = [safe_float(r.get(f"mfe_{horizon}d_pct"), default=float("nan")) for r in rows]
    close = [safe_float(r.get(f"close_{horizon}d_pct"), default=float("nan")) for r in rows]
    mae = [safe_float(r.get(f"mae_{horizon}d_pct"), default=float("nan")) for r in rows]
    mfe = [v for v in mfe if not math.isnan(v)]
    close = [v for v in close if not math.isnan(v)]
    mae = [v for v in mae if not math.isnan(v)]
    return {
        "n": n,
        f"avg_mfe_{horizon}d_pct": round_or_none(mean(mfe), 4),
        f"median_mfe_{horizon}d_pct": round_or_none(median(mfe), 4),
        "hit10_rate": round_or_none(pct(sum(1 for v in mfe if v >= 10.0), len(mfe)), 4),
        "hit15_rate": round_or_none(pct(sum(1 for v in mfe if v >= 15.0), len(mfe)), 4),
        "hit20_rate": round_or_none(pct(sum(1 for v in mfe if v >= 20.0), len(mfe)), 4),
        f"avg_close_{horizon}d_pct": round_or_none(mean(close), 4),
        f"median_close_{horizon}d_pct": round_or_none(median(close), 4),
        "close_loss_rate": round_or_none(pct(sum(1 for v in close if v < 0.0), len(close)), 4),
        "close_loss5_rate": round_or_none(pct(sum(1 for v in close if v <= -5.0), len(close)), 4),
        f"avg_mae_{horizon}d_pct": round_or_none(mean(mae), 4),
        f"worst_mae_{horizon}d_pct": round_or_none(min(mae), 4) if mae else None,
        "stop5_rate": round_or_none(pct(sum(1 for v in mae if v <= -5.0), len(mae)), 4),
        "stop8_rate": round_or_none(pct(sum(1 for v in mae if v <= -8.0), len(mae)), 4),
        "pitfall_rate": round_or_none(
            pct(
                sum(
                    1
                    for r in rows
                    if safe_float(r.get(f"close_{horizon}d_pct")) <= -5.0
                    or safe_float(r.get(f"mae_{horizon}d_pct")) <= -8.0
                ),
                n,
            ),
            4,
        ),
        f"full{horizon}_rate": round_or_none(pct(sum(1 for r in rows if safe_int(r.get(f"full_{horizon}d")) == 1), n), 4),
    }


def group_summary(rows: Sequence[Dict[str, Any]], group_keys: Sequence[str]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(k) for k in group_keys)].append(row)
    out = []
    for key, items in sorted(grouped.items(), key=lambda kv: tuple("" if x is None else str(x) for x in kv[0])):
        rec = {group_keys[i]: key[i] for i in range(len(group_keys))}
        rec.update(summarize_group(items))
        out.append(rec)
    return out


def bucket_spark(score: Any) -> str:
    value = safe_float(score)
    if value < 35.0:
        return "<35"
    if value < 40.0:
        return "35-40"
    return ">=40"


def build_policy_comparison(buy_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return build_policy_comparison_horizon(buy_rows, 22)


def build_policy_comparison_horizon(buy_rows: Sequence[Dict[str, Any]], horizon: int) -> List[Dict[str, Any]]:
    baseline = list(buy_rows)
    policies = [
        (
            "baseline_all_buyable",
            baseline,
            False,
        ),
        (
            "pause_defense_allowed",
            [r for r in baseline if r.get("market_regime") != "defense"],
            False,
        ),
        (
            "pause_defense_blocked",
            [r for r in baseline if r.get("market_regime") == "defense"],
            True,
        ),
        (
            "pause_active_decline_allowed",
            [r for r in baseline if r.get("market_detail") != "defense_active_decline"],
            False,
        ),
        (
            "pause_active_decline_blocked",
            [r for r in baseline if r.get("market_detail") == "defense_active_decline"],
            True,
        ),
    ]
    rows = []
    for policy, items, is_blocked in policies:
        rec = {"policy": policy}
        rec.update(summarize_group_horizon(items, horizon))
        rec["coverage_rate"] = round_or_none(pct(len(items), len(baseline)), 4) if baseline else None
        rec["blocked_hit15_count"] = sum(1 for r in items if safe_float(r.get(f"mfe_{horizon}d_pct")) >= 15.0) if is_blocked else None
        rec["blocked_hit20_count"] = sum(1 for r in items if safe_float(r.get(f"mfe_{horizon}d_pct")) >= 20.0) if is_blocked else None
        rows.append(rec)
    return rows


def build_probe_funnel(candidates: Sequence[Dict[str, Any]], trade_dates: Sequence[str]) -> List[Dict[str, Any]]:
    date_index = {d: i for i, d in enumerate(trade_dates)}
    d3_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        if row.get("source_id") == "probe_d3_confirmed":
            d3_by_symbol[str(row["symbol"])].append(row)
    for rows in d3_by_symbol.values():
        rows.sort(key=lambda r: str(r["trade_date"]))

    day0_rows = [r for r in candidates if r.get("source_id") == "probe_day0_watch"]
    details = []
    for row in day0_rows:
        d0 = str(row["trade_date"])
        symbol = str(row["symbol"])
        i = date_index.get(d0)
        if i is None:
            continue
        window_dates = set(trade_dates[i + 1 : min(len(trade_dates), i + 6)])
        matches = [r for r in d3_by_symbol.get(symbol, []) if str(r["trade_date"]) in window_dates]
        confirmed = 1 if matches else 0
        buy_confirmed = 1 if any(str(r.get("suggested_action")) == "candidate_buy" and safe_int(r.get("entry_allowed")) == 1 for r in matches) else 0
        first_match = matches[0] if matches else {}
        details.append(
            {
                "trade_date": d0,
                "symbol": symbol,
                "name": row.get("name"),
                "confirmed_1_5d": confirmed,
                "buy_confirmed_1_5d": buy_confirmed,
                "first_confirm_date": first_match.get("trade_date"),
                "first_confirm_action": first_match.get("suggested_action"),
                "first_confirm_entry_allowed": first_match.get("entry_allowed"),
            }
        )
    by_month: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in details:
        by_month[str(row["trade_date"])[:7]].append(row)
    out = []
    for month, rows in sorted(by_month.items()):
        out.append(
            {
                "month": month,
                "day0_watch_n": len(rows),
                "d3_confirm_1_5d_n": sum(safe_int(r.get("confirmed_1_5d")) for r in rows),
                "d3_confirm_1_5d_rate": round_or_none(pct(sum(safe_int(r.get("confirmed_1_5d")) for r in rows), len(rows)), 4),
                "d3_buy_confirm_1_5d_n": sum(safe_int(r.get("buy_confirmed_1_5d")) for r in rows),
                "d3_buy_confirm_1_5d_rate": round_or_none(pct(sum(safe_int(r.get("buy_confirmed_1_5d")) for r in rows), len(rows)), 4),
            }
        )
    total = {
        "month": "ALL",
        "day0_watch_n": len(details),
        "d3_confirm_1_5d_n": sum(safe_int(r.get("confirmed_1_5d")) for r in details),
        "d3_confirm_1_5d_rate": round_or_none(pct(sum(safe_int(r.get("confirmed_1_5d")) for r in details), len(details)), 4),
        "d3_buy_confirm_1_5d_n": sum(safe_int(r.get("buy_confirmed_1_5d")) for r in details),
        "d3_buy_confirm_1_5d_rate": round_or_none(pct(sum(safe_int(r.get("buy_confirmed_1_5d")) for r in details), len(details)), 4),
    }
    return [total] + out


def build_monthly_market(market_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in market_rows:
        grouped[str(row["trade_date"])[:7]].append(row)
    out = []
    for month, rows in sorted(grouped.items()):
        rec = {
            "month": month,
            "days": len(rows),
            "avg_water_score": round_or_none(mean([safe_float(r.get("water_score")) for r in rows]), 4),
            "avg_all_up_ratio_5d": round_or_none(mean([safe_float(r.get("all_up_ratio_5d")) for r in rows]), 4),
            "avg_all_med_ret_5d": round_or_none(mean([safe_float(r.get("all_med_ret_5d")) for r in rows]), 4),
            "avg_small_up_ratio_5d": round_or_none(mean([safe_float(r.get("small_up_ratio_5d")) for r in rows]), 4),
            "defense_day_rate": round_or_none(pct(sum(1 for r in rows if r.get("market_regime") == "defense"), len(rows)), 4),
            "attack_day_rate": round_or_none(pct(sum(1 for r in rows if r.get("market_regime") == "attack"), len(rows)), 4),
        }
        out.append(rec)
    return out


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    pairs = [(x, y) for x, y in zip(xs, ys) if not math.isnan(x) and not math.isnan(y)]
    if len(pairs) < 3:
        return None
    xvals = [p[0] for p in pairs]
    yvals = [p[1] for p in pairs]
    mx = sum(xvals) / len(xvals)
    my = sum(yvals) / len(yvals)
    cov = sum((x - mx) * (y - my) for x, y in pairs)
    vx = sum((x - mx) ** 2 for x in xvals)
    vy = sum((y - my) ** 2 for y in yvals)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def ranks(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = rank
        i = j + 1
    return out


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    pairs = [(x, y) for x, y in zip(xs, ys) if not math.isnan(x) and not math.isnan(y)]
    if len(pairs) < 3:
        return None
    return pearson(ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs]))


def build_correlations(buy_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    daily: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in buy_rows:
        daily[(str(row["business_source_name"]), str(row["source_id"]), str(row["trade_date"]))].append(row)
    agg = []
    for (source_name, source_id, trade_date), rows in daily.items():
        avg_mfe = mean([safe_float(r.get("mfe_22d_pct"), default=float("nan")) for r in rows])
        pit = pct(sum(1 for r in rows if safe_int(r.get("pitfall_22d")) == 1), len(rows))
        first = rows[0]
        rec = {
            "source_name": source_name,
            "source_id": source_id,
            "trade_date": trade_date,
            "n": len(rows),
            "avg_mfe_22d_pct": avg_mfe,
            "pitfall_rate": pit,
        }
        for prefix, _label in MARKET_METRIC_SPECS:
            for window in WINDOWS:
                rec[f"{prefix}_{window}d"] = safe_float(first.get(f"{prefix}_{window}d"), default=float("nan"))
        agg.append(rec)
    out = []
    metrics = (
        "all_up_ratio_1d",
        "all_up_ratio_3d",
        "all_up_ratio_5d",
        "all_up_ratio_10d",
        "all_up_ratio_20d",
        "all_med_ret_3d",
        "all_med_ret_5d",
        "all_med_ret_10d",
        "small_up_ratio_3d",
        "small_up_ratio_5d",
        "small_up_ratio_10d",
        "small_med_ret_5d",
    )
    for source_id in sorted({r["source_id"] for r in agg}):
        rows = [r for r in agg if r["source_id"] == source_id]
        for metric in metrics:
            xs = [safe_float(r[metric], default=float("nan")) for r in rows]
            ys = [safe_float(r["avg_mfe_22d_pct"], default=float("nan")) for r in rows]
            ps = [safe_float(r["pitfall_rate"], default=float("nan")) for r in rows]
            out.append(
                {
                    "source_id": source_id,
                    "source_name": SOURCE_LABELS.get(source_id, source_id),
                    "metric": metric,
                    "days": len(rows),
                    "pearson_mfe": round_or_none(pearson(xs, ys), 4),
                    "spearman_mfe": round_or_none(spearman(xs, ys), 4),
                    "pearson_pitfall": round_or_none(pearson(xs, ps), 4),
                    "spearman_pitfall": round_or_none(spearman(xs, ps), 4),
                }
            )
    return out


def quantile_thresholds(values: Sequence[float]) -> Optional[Tuple[float, float]]:
    vals = sorted(v for v in values if not math.isnan(v))
    if len(vals) < 9:
        return None
    low = vals[int((len(vals) - 1) / 3)]
    high = vals[int((len(vals) - 1) * 2 / 3)]
    if low == high:
        return None
    return low, high


def bucket_by_threshold(value: Any, thresholds: Optional[Tuple[float, float]]) -> Optional[str]:
    if thresholds is None:
        return None
    v = safe_float(value, default=float("nan"))
    if math.isnan(v):
        return None
    low, high = thresholds
    if v <= low:
        return "low"
    if v >= high:
        return "high"
    return "mid"


def label_metric_bucket(bucket: str) -> str:
    return {"low": "低水位", "mid": "中水位", "high": "高水位"}.get(bucket, bucket)


def build_metric_bucket_summary(buy_rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    bucket_rows: List[Dict[str, Any]] = []
    score_rows: List[Dict[str, Any]] = []
    for prefix, metric_label in MARKET_METRIC_SPECS:
        for window in WINDOWS:
            metric = f"{prefix}_{window}d"
            thresholds = quantile_thresholds([safe_float(r.get(metric), default=float("nan")) for r in buy_rows])
            if thresholds is None:
                continue
            sources = [("ALL", "全部来源")] + sorted(
                {(str(r.get("source_id")), str(r.get("business_source_name"))) for r in buy_rows},
                key=lambda x: x[1],
            )
            for source_id, source_name in sources:
                source_rows = buy_rows if source_id == "ALL" else [r for r in buy_rows if r.get("source_id") == source_id]
                if len(source_rows) < 8:
                    continue
                for horizon in HORIZONS:
                    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                    for row in source_rows:
                        bucket = bucket_by_threshold(row.get(metric), thresholds)
                        if bucket:
                            grouped[bucket].append(row)
                    for bucket in ("low", "mid", "high"):
                        items = grouped.get(bucket, [])
                        rec = {
                            "source_id": source_id,
                            "business_source_name": source_name,
                            "metric": metric,
                            "metric_label": metric_label,
                            "window": window,
                            "horizon": horizon,
                            "bucket": bucket,
                            "bucket_label": label_metric_bucket(bucket),
                            "threshold_low": round_or_none(thresholds[0], 4),
                            "threshold_high": round_or_none(thresholds[1], 4),
                        }
                        rec.update(summarize_group_horizon(items, horizon))
                        bucket_rows.append(rec)

                    low_summary = summarize_group_horizon(grouped.get("low", []), horizon)
                    high_summary = summarize_group_horizon(grouped.get("high", []), horizon)
                    low_n = safe_int(low_summary.get("n"))
                    high_n = safe_int(high_summary.get("n"))
                    if low_n < 3 or high_n < 3:
                        confidence = "low_sample"
                    elif low_n < 10 or high_n < 10:
                        confidence = "medium_sample"
                    else:
                        confidence = "ok"
                    high_mfe = high_summary.get(f"avg_mfe_{horizon}d_pct")
                    low_mfe = low_summary.get(f"avg_mfe_{horizon}d_pct")
                    high_close = high_summary.get(f"avg_close_{horizon}d_pct")
                    low_close = low_summary.get(f"avg_close_{horizon}d_pct")
                    high_pit = high_summary.get("pitfall_rate")
                    low_pit = low_summary.get("pitfall_rate")
                    mfe_lift = None if high_mfe is None or low_mfe is None else round(safe_float(high_mfe) - safe_float(low_mfe), 4)
                    close_lift = None if high_close is None or low_close is None else round(safe_float(high_close) - safe_float(low_close), 4)
                    pitfall_reduction = None if high_pit is None or low_pit is None else round(safe_float(low_pit) - safe_float(high_pit), 4)
                    supports = (
                        mfe_lift is not None
                        and close_lift is not None
                        and pitfall_reduction is not None
                        and mfe_lift > 0
                        and close_lift > 0
                        and pitfall_reduction > 0
                    )
                    score_rows.append(
                        {
                            "source_id": source_id,
                            "business_source_name": source_name,
                            "metric": metric,
                            "metric_label": metric_label,
                            "window": window,
                            "horizon": horizon,
                            "threshold_low": round_or_none(thresholds[0], 4),
                            "threshold_high": round_or_none(thresholds[1], 4),
                            "low_n": low_n,
                            "high_n": high_n,
                            "low_avg_mfe": low_summary.get(f"avg_mfe_{horizon}d_pct"),
                            "high_avg_mfe": high_summary.get(f"avg_mfe_{horizon}d_pct"),
                            "mfe_lift_high_minus_low": mfe_lift,
                            "low_avg_close": low_summary.get(f"avg_close_{horizon}d_pct"),
                            "high_avg_close": high_summary.get(f"avg_close_{horizon}d_pct"),
                            "close_lift_high_minus_low": close_lift,
                            "low_pitfall_rate": low_summary.get("pitfall_rate"),
                            "high_pitfall_rate": high_summary.get("pitfall_rate"),
                            "pitfall_reduction_low_minus_high": pitfall_reduction,
                            "supports_good_market_hypothesis": 1 if supports else 0,
                            "confidence": confidence,
                        }
                    )
    return bucket_rows, score_rows


def build_metric_leaderboard(score_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [
        r
        for r in score_rows
        if r.get("source_id") == "ALL"
        and safe_int(r.get("horizon")) in {5, 10}
        and r.get("confidence") == "ok"
    ]
    grouped: Dict[Tuple[str, int, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["metric_label"]), safe_int(row["window"]), str(row["metric"]))].append(row)
    out = []
    for (metric_label, window, metric), items in sorted(grouped.items()):
        avg_mfe_lift = mean([safe_float(r.get("mfe_lift_high_minus_low"), default=float("nan")) for r in items])
        avg_close_lift = mean([safe_float(r.get("close_lift_high_minus_low"), default=float("nan")) for r in items])
        avg_pitfall_reduction = mean([safe_float(r.get("pitfall_reduction_low_minus_high"), default=float("nan")) for r in items])
        support_count = sum(safe_int(r.get("supports_good_market_hypothesis")) for r in items)
        out.append(
            {
                "metric": metric,
                "metric_label": metric_label,
                "window": window,
                "tested_horizons": len(items),
                "support_count": support_count,
                "avg_mfe_lift": round_or_none(avg_mfe_lift, 4),
                "avg_close_lift": round_or_none(avg_close_lift, 4),
                "avg_pitfall_reduction": round_or_none(avg_pitfall_reduction, 4),
                "business_rank_score": round_or_none((avg_pitfall_reduction or 0) * 1.2 + (avg_close_lift or 0) * 0.7 + (avg_mfe_lift or 0) * 0.25, 4),
            }
        )
    return sorted(out, key=lambda r: safe_float(r.get("business_rank_score")), reverse=True)


def build_daily_source_aggregates(buy_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    grouped_all: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in buy_rows:
        grouped[(str(row.get("source_id")), str(row.get("business_source_name")), str(row.get("trade_date")))].append(row)
        grouped_all[str(row.get("trade_date"))].append(row)

    out: List[Dict[str, Any]] = []

    def make_row(source_id: str, source_name: str, trade_date: str, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        first = rows[0]
        rec: Dict[str, Any] = {
            "source_id": source_id,
            "business_source_name": source_name,
            "trade_date": trade_date,
            "candidate_n": len(rows),
            "market_regime": first.get("market_regime"),
            "market_detail": first.get("market_detail"),
            "market_detail_label": first.get("market_detail_label"),
            "water_score": first.get("water_score"),
        }
        for prefix, _label in MARKET_METRIC_SPECS:
            for window in WINDOWS:
                rec[f"{prefix}_{window}d"] = first.get(f"{prefix}_{window}d")
        for horizon in HORIZONS:
            mfe = [safe_float(r.get(f"mfe_{horizon}d_pct"), default=float("nan")) for r in rows]
            close = [safe_float(r.get(f"close_{horizon}d_pct"), default=float("nan")) for r in rows]
            mae = [safe_float(r.get(f"mae_{horizon}d_pct"), default=float("nan")) for r in rows]
            mfe = [v for v in mfe if not math.isnan(v)]
            close = [v for v in close if not math.isnan(v)]
            mae = [v for v in mae if not math.isnan(v)]
            pit_count = sum(
                1
                for r in rows
                if safe_float(r.get(f"close_{horizon}d_pct")) <= -5.0
                or safe_float(r.get(f"mae_{horizon}d_pct")) <= -8.0
            )
            rec[f"avg_mfe_{horizon}d_pct"] = round_or_none(mean(mfe), 4)
            rec[f"hit10_rate_{horizon}d"] = round_or_none(pct(sum(1 for v in mfe if v >= 10.0), len(mfe)), 4)
            rec[f"hit15_rate_{horizon}d"] = round_or_none(pct(sum(1 for v in mfe if v >= 15.0), len(mfe)), 4)
            rec[f"avg_close_{horizon}d_pct"] = round_or_none(mean(close), 4)
            rec[f"close_loss5_rate_{horizon}d"] = round_or_none(pct(sum(1 for v in close if v <= -5.0), len(close)), 4)
            rec[f"stop8_rate_{horizon}d"] = round_or_none(pct(sum(1 for v in mae if v <= -8.0), len(mae)), 4)
            rec[f"pitfall_rate_{horizon}d"] = round_or_none(pct(pit_count, len(rows)), 4)
            rec[f"full_rate_{horizon}d"] = round_or_none(pct(sum(1 for r in rows if safe_int(r.get(f"full_{horizon}d")) == 1), len(rows)), 4)
        return rec

    for (source_id, source_name, trade_date), rows in sorted(grouped.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        out.append(make_row(source_id, source_name, trade_date, rows))
    for trade_date, rows in sorted(grouped_all.items()):
        out.append(make_row("ALL", "全部来源", trade_date, rows))
    return out


def summarize_daily_aggregate_rows(rows: Sequence[Dict[str, Any]], horizon: int) -> Dict[str, Any]:
    if not rows:
        return {
            "day_n": 0,
            "candidate_n": 0,
            "avg_candidates_per_day": None,
            f"avg_mfe_{horizon}d_pct": None,
            f"avg_close_{horizon}d_pct": None,
            "hit10_rate": None,
            "hit15_rate": None,
            "close_loss5_rate": None,
            "stop8_rate": None,
            "pitfall_rate": None,
        }
    return {
        "day_n": len(rows),
        "candidate_n": sum(safe_int(r.get("candidate_n")) for r in rows),
        "avg_candidates_per_day": round_or_none(mean([safe_float(r.get("candidate_n")) for r in rows]), 4),
        f"avg_mfe_{horizon}d_pct": round_or_none(mean([safe_float(r.get(f"avg_mfe_{horizon}d_pct"), default=float("nan")) for r in rows]), 4),
        f"avg_close_{horizon}d_pct": round_or_none(mean([safe_float(r.get(f"avg_close_{horizon}d_pct"), default=float("nan")) for r in rows]), 4),
        "hit10_rate": round_or_none(mean([safe_float(r.get(f"hit10_rate_{horizon}d"), default=float("nan")) for r in rows]), 4),
        "hit15_rate": round_or_none(mean([safe_float(r.get(f"hit15_rate_{horizon}d"), default=float("nan")) for r in rows]), 4),
        "close_loss5_rate": round_or_none(mean([safe_float(r.get(f"close_loss5_rate_{horizon}d"), default=float("nan")) for r in rows]), 4),
        "stop8_rate": round_or_none(mean([safe_float(r.get(f"stop8_rate_{horizon}d"), default=float("nan")) for r in rows]), 4),
        "pitfall_rate": round_or_none(mean([safe_float(r.get(f"pitfall_rate_{horizon}d"), default=float("nan")) for r in rows]), 4),
        f"full{horizon}_rate": round_or_none(mean([safe_float(r.get(f"full_rate_{horizon}d"), default=float("nan")) for r in rows]), 4),
    }


def build_daily_metric_validation(daily_rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    bucket_rows: List[Dict[str, Any]] = []
    score_rows: List[Dict[str, Any]] = []
    unique_by_date: Dict[str, Dict[str, Any]] = {}
    for row in daily_rows:
        if row.get("source_id") == "ALL":
            unique_by_date[str(row["trade_date"])] = row

    for prefix, metric_label in MARKET_METRIC_SPECS:
        for window in WINDOWS:
            metric = f"{prefix}_{window}d"
            thresholds = quantile_thresholds([safe_float(r.get(metric), default=float("nan")) for r in unique_by_date.values()])
            if thresholds is None:
                continue
            for source_id, source_name in sorted({(str(r.get("source_id")), str(r.get("business_source_name"))) for r in daily_rows}, key=lambda x: x[1]):
                source_rows = [r for r in daily_rows if r.get("source_id") == source_id]
                if len(source_rows) < 3:
                    continue
                for horizon in HORIZONS:
                    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                    for row in source_rows:
                        bucket = bucket_by_threshold(row.get(metric), thresholds)
                        if bucket:
                            grouped[bucket].append(row)
                    for bucket in ("low", "mid", "high"):
                        items = grouped.get(bucket, [])
                        rec = {
                            "source_id": source_id,
                            "business_source_name": source_name,
                            "metric": metric,
                            "metric_label": metric_label,
                            "window": window,
                            "horizon": horizon,
                            "bucket": bucket,
                            "bucket_label": label_metric_bucket(bucket),
                            "threshold_low": round_or_none(thresholds[0], 4),
                            "threshold_high": round_or_none(thresholds[1], 4),
                        }
                        rec.update(summarize_daily_aggregate_rows(items, horizon))
                        bucket_rows.append(rec)
                    low_summary = summarize_daily_aggregate_rows(grouped.get("low", []), horizon)
                    high_summary = summarize_daily_aggregate_rows(grouped.get("high", []), horizon)
                    low_days = safe_int(low_summary.get("day_n"))
                    high_days = safe_int(high_summary.get("day_n"))
                    if low_days < 10 or high_days < 10:
                        confidence = "low_sample"
                    elif low_days < 30 or high_days < 30:
                        confidence = "directional"
                    else:
                        confidence = "initial_conclusion"
                    high_mfe = high_summary.get(f"avg_mfe_{horizon}d_pct")
                    low_mfe = low_summary.get(f"avg_mfe_{horizon}d_pct")
                    high_close = high_summary.get(f"avg_close_{horizon}d_pct")
                    low_close = low_summary.get(f"avg_close_{horizon}d_pct")
                    high_pit = high_summary.get("pitfall_rate")
                    low_pit = low_summary.get("pitfall_rate")
                    mfe_lift = None if high_mfe is None or low_mfe is None else round(safe_float(high_mfe) - safe_float(low_mfe), 4)
                    close_lift = None if high_close is None or low_close is None else round(safe_float(high_close) - safe_float(low_close), 4)
                    pitfall_reduction = None if high_pit is None or low_pit is None else round(safe_float(low_pit) - safe_float(high_pit), 4)
                    supports = (
                        mfe_lift is not None
                        and close_lift is not None
                        and pitfall_reduction is not None
                        and mfe_lift > 0
                        and close_lift > 0
                        and pitfall_reduction > 0
                    )
                    score_rows.append(
                        {
                            "source_id": source_id,
                            "business_source_name": source_name,
                            "metric": metric,
                            "metric_label": metric_label,
                            "window": window,
                            "horizon": horizon,
                            "threshold_low": round_or_none(thresholds[0], 4),
                            "threshold_high": round_or_none(thresholds[1], 4),
                            "low_day_n": low_days,
                            "high_day_n": high_days,
                            "low_candidate_n": low_summary.get("candidate_n"),
                            "high_candidate_n": high_summary.get("candidate_n"),
                            "low_avg_mfe": low_mfe,
                            "high_avg_mfe": high_mfe,
                            "mfe_lift_high_minus_low": mfe_lift,
                            "low_avg_close": low_close,
                            "high_avg_close": high_close,
                            "close_lift_high_minus_low": close_lift,
                            "low_pitfall_rate": low_pit,
                            "high_pitfall_rate": high_pit,
                            "pitfall_reduction_low_minus_high": pitfall_reduction,
                            "supports_good_market_hypothesis": 1 if supports else 0,
                            "confidence": confidence,
                        }
                    )
    leaderboard = build_daily_metric_leaderboard(score_rows)
    return bucket_rows, score_rows, leaderboard


def build_daily_metric_leaderboard(score_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [
        r
        for r in score_rows
        if r.get("source_id") == "ALL"
        and safe_int(r.get("horizon")) in {5, 10}
        and r.get("confidence") in {"directional", "initial_conclusion"}
    ]
    grouped: Dict[Tuple[str, int, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["metric_label"]), safe_int(row["window"]), str(row["metric"]))].append(row)
    out = []
    for (metric_label, window, metric), items in sorted(grouped.items()):
        avg_mfe_lift = mean([safe_float(r.get("mfe_lift_high_minus_low"), default=float("nan")) for r in items])
        avg_close_lift = mean([safe_float(r.get("close_lift_high_minus_low"), default=float("nan")) for r in items])
        avg_pitfall_reduction = mean([safe_float(r.get("pitfall_reduction_low_minus_high"), default=float("nan")) for r in items])
        support_count = sum(safe_int(r.get("supports_good_market_hypothesis")) for r in items)
        out.append(
            {
                "metric": metric,
                "metric_label": metric_label,
                "window": window,
                "tested_horizons": len(items),
                "support_count": support_count,
                "avg_mfe_lift": round_or_none(avg_mfe_lift, 4),
                "avg_close_lift": round_or_none(avg_close_lift, 4),
                "avg_pitfall_reduction": round_or_none(avg_pitfall_reduction, 4),
                "business_rank_score": round_or_none((avg_pitfall_reduction or 0) * 1.2 + (avg_close_lift or 0) * 0.7 + (avg_mfe_lift or 0) * 0.25, 4),
            }
        )
    return sorted(out, key=lambda r: safe_float(r.get("business_rank_score")), reverse=True)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv_preview(path: Path, max_rows: int = 5) -> List[Dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))[:max_rows]


def make_markdown_report(
    out_dir: Path,
    monthly_market: Sequence[Dict[str, Any]],
    policy_5d_rows: Sequence[Dict[str, Any]],
    policy_10d_rows: Sequence[Dict[str, Any]],
    policy_rows: Sequence[Dict[str, Any]],
    policy_full22_rows: Sequence[Dict[str, Any]],
    source_regime_rows: Sequence[Dict[str, Any]],
    spark_rows: Sequence[Dict[str, Any]],
    probe_funnel_rows: Sequence[Dict[str, Any]],
    source_coverage_rows: Sequence[Dict[str, Any]],
    latest_market: Dict[str, Any],
) -> str:
    def table(rows: Sequence[Dict[str, Any]], fields: Sequence[str], labels: Sequence[str]) -> List[str]:
        lines = ["| " + " | ".join(labels) + " |", "|" + "|".join("---" for _ in labels) + "|"]
        for row in rows:
            vals = []
            for field in fields:
                value = row.get(field)
                vals.append("" if value is None else str(value))
            lines.append("| " + " | ".join(vals) + " |")
        return lines

    defense_policy = next((r for r in policy_rows if r.get("policy") == "pause_defense_allowed"), {})
    blocked_policy = next((r for r in policy_rows if r.get("policy") == "pause_defense_blocked"), {})
    baseline_policy = next((r for r in policy_rows if r.get("policy") == "baseline_all_buyable"), {})

    lines = [
        "# 市场环境水位门控离线研究结果",
        "",
        "## 结论",
        "",
        "- 第一版结果按“少亏、少踩坑”口径输出，防守环境默认建议暂停新开仓。",
        f"- 当前样本中，暂停防守环境后，可参与覆盖率约为 `{defense_policy.get('coverage_rate')}`%，被拦截样本覆盖率约为 `{blocked_policy.get('coverage_rate')}`%。",
        f"- 基线买入样本踩坑率 `{baseline_policy.get('pitfall_rate')}`%，防守期被拦截样本踩坑率 `{blocked_policy.get('pitfall_rate')}`%。",
        "- 5 日、10 日短线口径支持“防守/持续下跌时暂停次日新开仓”；完整 22 日样本提示弱市后仍可能有修复机会，所以不能把门控解释成来源长期失效。",
        "- 防守期被拦截样本仍有冲高机会，误杀成本必须复盘；但在“少亏优先”口径下，暂停新开仓具备提示试运行价值。",
        "- 星火机会模型 40 分以上样本过少且弱市未证明优势，高置信例外不进入默认建议。",
        "",
        "## 最新市场状态",
        "",
        f"- 日期：`{latest_market.get('trade_date')}`",
        f"- 水位：`{latest_market.get('market_regime')}`，默认动作：`{latest_market.get('default_action')}`",
        f"- 水位分数：`{latest_market.get('water_score')}`",
        f"- 主要原因：{latest_market.get('reason_top3')}",
        "",
        "## 月度市场水位",
        "",
    ]
    lines += table(
        monthly_market[-12:],
        ("month", "days", "avg_water_score", "avg_all_up_ratio_5d", "avg_all_med_ret_5d", "defense_day_rate", "attack_day_rate"),
        ("月份", "天数", "水位均分", "5日上涨占比", "5日中位涨跌", "防守日占比", "攻击日占比"),
    )
    lines += [
        "",
        "## 门控策略对比：5 日短线体验",
        "",
    ]
    lines += table(
        policy_5d_rows,
        (
            "policy",
            "n",
            "coverage_rate",
            "avg_mfe_5d_pct",
            "hit10_rate",
            "avg_close_5d_pct",
            "close_loss5_rate",
            "stop8_rate",
            "pitfall_rate",
        ),
        ("策略", "样本", "覆盖率", "MFE5", "冲高10", "5日收盘", "收盘亏5", "回撤8", "踩坑率"),
    )
    lines += [
        "",
        "## 门控策略对比：10 日短线体验",
        "",
    ]
    lines += table(
        policy_10d_rows,
        (
            "policy",
            "n",
            "coverage_rate",
            "avg_mfe_10d_pct",
            "hit10_rate",
            "avg_close_10d_pct",
            "close_loss5_rate",
            "stop8_rate",
            "pitfall_rate",
        ),
        ("策略", "样本", "覆盖率", "MFE10", "冲高10", "10日收盘", "收盘亏5", "回撤8", "踩坑率"),
    )
    lines += [
        "",
        "## 门控策略对比：22 日观察结果",
        "",
    ]
    lines += table(
        policy_rows,
        (
            "policy",
            "n",
            "coverage_rate",
            "avg_mfe_22d_pct",
            "hit15_rate",
            "avg_close_22d_pct",
            "close_loss5_rate",
            "stop8_rate",
            "pitfall_rate",
        ),
        ("策略", "样本", "覆盖率", "MFE22", "冲高15", "收盘收益", "收盘亏5", "回撤8", "踩坑率"),
    )
    lines += [
        "",
        "## 防守细分状态",
        "",
        "- `防守-持续下跌`：短周期和小盘都在继续走弱，默认暂停新开仓。",
        "- `防守-弱势承压`：仍是弱势，但未达到持续下跌条件，默认观察。",
        "- `防守-修复观察`：5 日仍弱，但 1 日或 3 日已经修复，不能和持续下跌混成同一类。",
        "- 5 日、10 日口径优先用于“次日是否新开仓”；22 日口径只用于观察是否会错过后续修复机会。",
        "",
        "",
        "## 门控策略对比：只看完整 22 日样本",
        "",
    ]
    lines += table(
        policy_full22_rows,
        (
            "policy",
            "n",
            "coverage_rate",
            "avg_mfe_22d_pct",
            "hit15_rate",
            "avg_close_22d_pct",
            "close_loss5_rate",
            "stop8_rate",
            "pitfall_rate",
        ),
        ("策略", "样本", "覆盖率", "MFE22", "冲高15", "收盘收益", "收盘亏5", "回撤8", "踩坑率"),
    )
    lines += [
        "",
        "## 来源 x 市场状态",
        "",
    ]
    lines += table(
        source_regime_rows,
        (
            "business_source_name",
            "market_regime",
            "n",
            "avg_mfe_22d_pct",
            "hit15_rate",
            "avg_close_22d_pct",
            "close_loss5_rate",
            "stop8_rate",
            "pitfall_rate",
        ),
        ("来源", "水位", "样本", "MFE22", "冲高15", "收盘收益", "收盘亏5", "回撤8", "踩坑率"),
    )
    lines += [
        "",
        "## 来源快照覆盖",
        "",
    ]
    lines += table(
        source_coverage_rows,
        ("business_source_name", "suggested_action", "entry_allowed", "n", "min_trade_date", "max_trade_date"),
        ("来源", "动作", "可买", "样本", "起始", "结束"),
    )
    lines += [
        "",
        "## 试盘识别观察到确认漏斗",
        "",
    ]
    lines += table(
        probe_funnel_rows,
        ("month", "day0_watch_n", "d3_confirm_1_5d_n", "d3_confirm_1_5d_rate", "d3_buy_confirm_1_5d_n", "d3_buy_confirm_1_5d_rate"),
        ("月份", "D0观察", "1-5日确认", "确认率", "1-5日可买确认", "可买确认率"),
    )
    lines += [
        "",
        "## 星火机会模型分数例外验证",
        "",
    ]
    lines += table(
        spark_rows,
        (
            "spark_score_bucket",
            "market_regime",
            "n",
            "avg_mfe_22d_pct",
            "hit15_rate",
            "avg_close_22d_pct",
            "close_loss5_rate",
            "stop8_rate",
            "pitfall_rate",
        ),
        ("分数层", "水位", "样本", "MFE22", "冲高15", "收盘收益", "收盘亏5", "回撤8", "踩坑率"),
    )
    lines += [
        "",
        "## 产物",
        "",
        "- `market_state_daily.csv`：2024-09-02 起每日市场水位。",
        "- `candidate_outcomes.csv`：统一候选池候选的未来 5/10/22 日结果。",
        "- `gate_policy_comparison_5d.csv`：5 日短线体验下的门控对比。",
        "- `gate_policy_comparison_10d.csv`：10 日短线体验下的门控对比。",
        "- `gate_policy_comparison.csv`：防守暂停门控与基线对比。",
        "- `gate_policy_comparison_full22.csv`：只看完整 22 日样本的门控对比。",
        "- `gate_summary_by_source_regime.csv`：各来源在不同市场水位下的表现。",
        "- `spark_score_exception.csv`：星火机会模型分数分层验证。",
        "- `probe_funnel_summary.csv`：试盘当日观察到三日确认的漏斗。",
        "- `source_coverage.csv`：各来源快照覆盖范围。",
        "- `correlation_by_source.csv`：各来源表现与市场指标相关性。",
        "",
        "## 使用限制",
        "",
        "- 当前统一候选池只覆盖 2026-03/04 之后；2024-09 起长样本用于市场水位稳定性，不代表当时已有这些每日推荐。",
        "- 未跑满 22 日的样本已标记 `full_22d=0`，近期结果只能作为截至当前的观察。",
        "- 趋势延续策略正式快照在 2026-04-24 后断更，应先复核接入口径，再做近期优劣判断。",
        "- 小盘/大盘分层使用当前市值近似，正式规则前应评估历史偏差。",
    ]
    path = out_dir / "research_conclusion.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def make_correlation_readout(
    out_dir: Path,
    metric_leaderboard: Sequence[Dict[str, Any]],
    metric_scorecard: Sequence[Dict[str, Any]],
    daily_metric_leaderboard: Sequence[Dict[str, Any]],
    daily_metric_scorecard: Sequence[Dict[str, Any]],
) -> str:
    def table(rows: Sequence[Dict[str, Any]], fields: Sequence[str], labels: Sequence[str]) -> List[str]:
        lines = ["| " + " | ".join(labels) + " |", "|" + "|".join("---" for _ in labels) + "|"]
        for row in rows:
            lines.append("| " + " | ".join("" if row.get(f) is None else str(row.get(f)) for f in fields) + " |")
        return lines

    def find_score(
        source_name: str,
        metric: str,
        window: int,
        horizon: int,
    ) -> Optional[Dict[str, Any]]:
        for row in daily_metric_scorecard:
            if (
                row.get("business_source_name") == source_name
                and row.get("metric") == metric
                and safe_int(row.get("window")) == window
                and safe_int(row.get("horizon")) == horizon
            ):
                return row
        return None

    def evidence(row: Optional[Dict[str, Any]]) -> str:
        if not row:
            return "无可用结果"
        return (
            f"{row.get('metric_label')}{row.get('window')}日看{row.get('horizon')}日："
            f"低/高水位推荐日 {row.get('low_day_n')}/{row.get('high_day_n')}，"
            f"MFE差 {row.get('mfe_lift_high_minus_low')}pct，"
            f"收盘差 {row.get('close_lift_high_minus_low')}pct，"
            f"痛苦持仓下降 {row.get('pitfall_reduction_low_minus_high')}pct"
        )

    direct_answer_rows = [
        {
            "question": "整体候选池",
            "answer": "支持。市场好时短线表现更好，市场差时更容易痛苦持仓。",
            "evidence": evidence(find_score("全部来源", "all_up_ratio_5d", 5, 5)),
            "usable": "可以作为每日新开仓主门控",
        },
        {
            "question": "星火机会模型",
            "answer": "支持。它在弱市不是高胜率穿越型，市场水位能解释最近体验变差。",
            "evidence": evidence(find_score("星火机会模型", "all_up_ratio_5d", 5, 10)),
            "usable": "防守时不建议给星火开高分例外，除非后续分数层证明",
        },
        {
            "question": "资金流回调稳健策略",
            "answer": "方向支持，但样本还不够硬。更像适合修复/顺风，不适合普跌抄底。",
            "evidence": evidence(find_score("资金流回调稳健策略", "small_med_ret_5d", 5, 10)),
            "usable": "先做提示级门控，不直接下最终规则",
        },
        {
            "question": "试盘识别-三日确认",
            "answer": "不能下结论。少数样本看起来有相关性，但高/低水位推荐日太少。",
            "evidence": evidence(find_score("试盘识别-三日确认", "all_up_ratio_3d", 3, 5)),
            "usable": "继续当资金异动观察器，不作为弱市买入依据",
        },
        {
            "question": "趋势延续策略",
            "answer": "不能下结论。正式快照近期断更，有效推荐日不足。",
            "evidence": evidence(find_score("趋势延续策略", "all_up_ratio_10d", 10, 10)),
            "usable": "先修复/确认候选流，再评估低频高价值",
        },
    ]

    top_all = list(daily_metric_leaderboard[:12])
    best_10d = next((r for r in daily_metric_leaderboard if safe_int(r.get("window")) == 10), None)
    best_20d = next((r for r in daily_metric_leaderboard if safe_int(r.get("window")) == 20), None)
    source_focus = [
        r
        for r in daily_metric_scorecard
        if r.get("source_id") != "ALL"
        and safe_int(r.get("horizon")) in {5, 10}
        and str(r.get("metric")) in {
            "all_up_ratio_3d",
            "all_up_ratio_5d",
            "all_up_ratio_10d",
            "all_med_ret_3d",
            "all_med_ret_5d",
            "all_med_ret_10d",
            "small_up_ratio_5d",
            "small_med_ret_5d",
        }
    ]
    source_focus = [
        r
        for r in source_focus
        if r.get("confidence") != "low_sample"
    ]
    low_confidence_focus = [
        r
        for r in daily_metric_scorecard
        if r.get("source_id") != "ALL"
        and safe_int(r.get("horizon")) in {5, 10}
        and r.get("confidence") == "low_sample"
        and str(r.get("metric")) in {
            "all_up_ratio_3d",
            "all_up_ratio_5d",
            "all_up_ratio_10d",
            "all_med_ret_5d",
            "small_up_ratio_5d",
            "small_med_ret_5d",
        }
    ]
    source_focus = sorted(
        source_focus,
        key=lambda r: (
            str(r.get("business_source_name")),
            safe_int(r.get("horizon")),
            -safe_float(r.get("pitfall_reduction_low_minus_high"), default=-999),
        ),
    )

    lines = [
        "# 市场环境相关性业务验证",
        "",
        "## 先给结论",
        "",
        "这次验证补上的是：市场环境好坏，是否真的会影响四个来源的候选表现。",
        "",
        "答案是：整体候选池和星火机会模型支持这个判断；资金流回调稳健策略方向支持但样本偏少；试盘识别、趋势延续策略目前不能下定论。",
        "",
        "最实用的结论不是笼统的“进攻/防守”，而是：",
        "",
        "- 主门控用 5 日市场水位，因为它在 MFE、收盘收益、痛苦持仓下降上同时稳定。",
        "- 3 日市场水位做预警，因为它对情绪急变更敏感，但容易抖动。",
        "- 10 日市场水位做确认，因为它能判断弱势是不是持续，但反应会慢。",
        "- 1 日太噪，20 日太慢，都不适合作为“明天要不要新开仓”的主判断。",
        "- 22 日结果只用于复盘机会模型，不用于判断次日开仓体验。",
        "",
        "本报告的关键口径：按“来源 + 推荐日”聚合，再比较高水位和低水位表现；不是按候选条数简单堆样本。",
        "",
        "## 直接回答你的问题",
        "",
    ]
    lines += table(
        direct_answer_rows,
        ("question", "answer", "evidence", "usable"),
        ("对象", "能不能回答", "核心数据", "怎么用"),
    )
    lines += [
        "",
        "读法：`MFE差` 是高水位相对低水位的最大冲高提升；`收盘差` 是高水位相对低水位的期末收益提升；`痛苦持仓下降` 是低水位痛苦持仓率减去高水位痛苦持仓率。",
        "",
        "## 踩坑率是什么",
        "",
        "上一版叫“踩坑率”不够清楚，后续建议改叫“痛苦持仓率”。它不是实际账户亏损率，而是衡量买进去以后会不会很难拿。",
        "",
        "定义：次日开盘买入后，在指定观察期内满足任一条件，就算踩坑：",
        "",
        "- 观察期收盘收益小于等于 -5%。",
        "- 观察期内最大浮亏小于等于 -8%。",
        "",
        "业务含义：它衡量的是“买进去后是否很难受”，用于判断要不要新开仓，不用于还原真实交易收益。",
        "",
        "## 哪个市场周期更有用",
        "",
        "用 5 日和 10 日候选结果做验证后，排在前面的几乎都是 3 日、5 日市场指标；10 日指标仍有正向解释力，但弱于 3/5 日，更适合做确认。",
        (
            f"20 日指标不适合作主门控：最好的 20 日指标是"
            f"{best_20d.get('metric_label') if best_20d else '无'}，"
            f"业务分 {best_20d.get('business_rank_score') if best_20d else '无'}，"
            f"痛苦持仓下降 {best_20d.get('avg_pitfall_reduction') if best_20d else '无'}pct；"
            f"而最好的 10 日指标业务分为 {best_10d.get('business_rank_score') if best_10d else '无'}。"
        ),
        "",
    ]
    lines += table(
        top_all,
        (
            "metric_label",
            "window",
            "tested_horizons",
            "support_count",
            "avg_mfe_lift",
            "avg_close_lift",
            "avg_pitfall_reduction",
            "business_rank_score",
        ),
        ("指标", "周期", "验证周期数", "支持次数", "MFE提升", "收盘提升", "踩坑下降", "业务分"),
    )
    lines += [
        "",
        "读法：`踩坑下降` 是低水位踩坑率减去高水位踩坑率，越高说明市场好时越少踩坑。",
        "本表按来源+推荐日聚合，不按候选条数直接放大样本。",
        "",
        "## 分来源相关性摘要",
        "",
    ]
    lines += table(
        source_focus[:80],
        (
            "business_source_name",
            "metric_label",
            "window",
            "horizon",
            "low_day_n",
            "high_day_n",
            "low_candidate_n",
            "high_candidate_n",
            "mfe_lift_high_minus_low",
            "close_lift_high_minus_low",
            "pitfall_reduction_low_minus_high",
            "supports_good_market_hypothesis",
            "confidence",
        ),
        ("来源", "指标", "周期", "结果周期", "低天数", "高天数", "低候选", "高候选", "MFE差", "收盘差", "踩坑下降", "是否支持", "置信度"),
    )
    lines += [
        "",
        "## 低置信来源提示",
        "",
        "以下结果只列事实，不下判断。原因是高/低水位有效推荐日少于 10 天。",
        "",
    ]
    lines += table(
        low_confidence_focus[:50],
        (
            "business_source_name",
            "metric_label",
            "window",
            "horizon",
            "low_day_n",
            "high_day_n",
            "mfe_lift_high_minus_low",
            "close_lift_high_minus_low",
            "pitfall_reduction_low_minus_high",
        ),
        ("来源", "指标", "周期", "结果周期", "低天数", "高天数", "MFE差", "收盘差", "踩坑下降"),
    )
    lines += [
        "",
        "## 业务解释",
        "",
        "可以回答：市场好时，整体候选短期表现更好；市场坏时，整体候选更容易踩坑。这个结论在全部来源合并后的 5 日、10 日短线口径上更清楚。",
        "",
        "还不能回答：每一个来源都已经找到稳定的最佳市场周期。原因是趋势延续策略、试盘三日确认样本太少，且趋势延续策略近期快照断更。",
        "",
        "当前推荐口径：",
        "",
        "- 主门控用 5 日全市场上涨占比 + 5 日中位涨跌幅 + 小盘 5 日上涨占比。",
        "- 3 日用于预警情绪急变。",
        "- 10 日用于确认弱势是否持续。",
        "- 22 日只做复盘，不作为次日新开仓门控主周期。",
        "",
        "## 下一步",
        "",
        "把这套相关性验证接入前向试运行。每天记录原始推荐、市场水位、门控建议和后续 5/10 日结果，再判断是否从研究发现升级为可用规则。",
    ]
    path = out_dir / "correlation_readout.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research market environment gate for daily selection candidates.")
    parser.add_argument("--atomic-db", type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument("--selection-db", type=Path, default=DEFAULT_SELECTION_DB)
    parser.add_argument("--feature-db", type=Path, default=DEFAULT_FEATURE_DB)
    parser.add_argument("--meta-db", type=Path, default=DEFAULT_META_DB)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    cap_buckets = load_market_cap_buckets(args.meta_db)
    prices_by_symbol, trade_dates, prices_by_symbol_date = load_prices(args.atomic_db)
    index_state = load_index_state(args.feature_db)
    market_rows = build_market_state(prices_by_symbol, trade_dates, cap_buckets, index_state)
    market_by_date = {str(r["trade_date"]): r for r in market_rows}
    candidates = load_candidates(args.selection_db)
    source_coverage = build_source_coverage(candidates)
    outcomes = enrich_candidate_outcomes(candidates, trade_dates, prices_by_symbol_date, market_by_date)
    buy_rows = [r for r in outcomes if safe_int(r.get("buyable")) == 1]
    watch_rows = [r for r in outcomes if safe_int(r.get("buyable")) == 0]

    for row in outcomes:
        if row.get("source_id") == "spark_opportunity_selector":
            row["spark_score_bucket"] = bucket_spark(row.get("score"))
        rank = safe_int(row.get("rank"))
        row["rank_bucket"] = "top1" if rank <= 1 else ("top3" if rank <= 3 else ("top5" if rank <= 5 else "other"))

    monthly_market = build_monthly_market(market_rows)
    source_regime = group_summary(buy_rows, ("business_source_name", "source_id", "market_regime"))
    source_detail = group_summary(buy_rows, ("business_source_name", "source_id", "market_detail_label"))
    action_summary = group_summary(outcomes, ("business_source_name", "source_id", "suggested_action", "entry_allowed", "market_regime"))
    policy_rows = build_policy_comparison(buy_rows)
    policy_5d_rows = build_policy_comparison_horizon(buy_rows, 5)
    policy_10d_rows = build_policy_comparison_horizon(buy_rows, 10)
    policy_full22_rows = build_policy_comparison([r for r in buy_rows if safe_int(r.get("full_22d")) == 1])
    spark_rows = group_summary(
        [r for r in buy_rows if r.get("source_id") == "spark_opportunity_selector"],
        ("spark_score_bucket", "market_regime"),
    )
    rank_rows = group_summary(buy_rows, ("business_source_name", "source_id", "rank_bucket", "market_regime"))
    correlation_rows = build_correlations(buy_rows)
    metric_bucket_rows, metric_score_rows = build_metric_bucket_summary(buy_rows)
    metric_leaderboard_rows = build_metric_leaderboard(metric_score_rows)
    daily_source_rows = build_daily_source_aggregates(buy_rows)
    daily_metric_bucket_rows, daily_metric_score_rows, daily_metric_leaderboard_rows = build_daily_metric_validation(daily_source_rows)
    probe_funnel_rows = build_probe_funnel(candidates, trade_dates)

    write_csv(args.out_dir / "market_state_daily.csv", market_rows)
    write_csv(args.out_dir / "candidate_outcomes.csv", outcomes)
    write_csv(args.out_dir / "source_coverage.csv", source_coverage)
    write_csv(args.out_dir / "market_regime_monthly.csv", monthly_market)
    write_csv(args.out_dir / "gate_summary_by_source_regime.csv", source_regime)
    write_csv(args.out_dir / "gate_summary_by_source_detail.csv", source_detail)
    write_csv(args.out_dir / "candidate_action_summary.csv", action_summary)
    write_csv(args.out_dir / "gate_policy_comparison_5d.csv", policy_5d_rows)
    write_csv(args.out_dir / "gate_policy_comparison_10d.csv", policy_10d_rows)
    write_csv(args.out_dir / "gate_policy_comparison.csv", policy_rows)
    write_csv(args.out_dir / "gate_policy_comparison_full22.csv", policy_full22_rows)
    write_csv(args.out_dir / "spark_score_exception.csv", spark_rows)
    write_csv(args.out_dir / "rank_bucket_exception.csv", rank_rows)
    write_csv(args.out_dir / "correlation_by_source.csv", correlation_rows)
    write_csv(args.out_dir / "market_metric_bucket_summary.csv", metric_bucket_rows)
    write_csv(args.out_dir / "market_metric_scorecard.csv", metric_score_rows)
    write_csv(args.out_dir / "market_metric_leaderboard.csv", metric_leaderboard_rows)
    write_csv(args.out_dir / "source_day_outcomes.csv", daily_source_rows)
    write_csv(args.out_dir / "market_metric_source_day_bucket_summary.csv", daily_metric_bucket_rows)
    write_csv(args.out_dir / "market_metric_source_day_scorecard.csv", daily_metric_score_rows)
    write_csv(args.out_dir / "market_metric_source_day_leaderboard.csv", daily_metric_leaderboard_rows)
    write_csv(args.out_dir / "probe_funnel_summary.csv", probe_funnel_rows)

    latest_market = market_rows[-1] if market_rows else {}
    report_path = make_markdown_report(
        args.out_dir,
        monthly_market,
        policy_5d_rows,
        policy_10d_rows,
        policy_rows,
        policy_full22_rows,
        source_regime,
        spark_rows,
        probe_funnel_rows,
        source_coverage,
        latest_market,
    )
    correlation_report_path = make_correlation_readout(
        args.out_dir,
        metric_leaderboard_rows,
        metric_score_rows,
        daily_metric_leaderboard_rows,
        daily_metric_score_rows,
    )

    summary = {
        "atomic_db": str(args.atomic_db),
        "selection_db": str(args.selection_db),
        "feature_db": str(args.feature_db),
        "meta_db": str(args.meta_db),
        "out_dir": str(args.out_dir),
        "trade_date_min": trade_dates[0] if trade_dates else None,
        "trade_date_max": trade_dates[-1] if trade_dates else None,
        "market_state_rows": len(market_rows),
        "candidate_rows": len(outcomes),
        "buyable_rows": len(buy_rows),
        "watch_rows": len(watch_rows),
        "latest_market": latest_market,
        "policy_comparison": policy_rows,
        "policy_comparison_5d": policy_5d_rows,
        "policy_comparison_10d": policy_10d_rows,
        "policy_comparison_full22": policy_full22_rows,
        "outputs": {
            "market_state_daily": str(args.out_dir / "market_state_daily.csv"),
            "candidate_outcomes": str(args.out_dir / "candidate_outcomes.csv"),
            "source_coverage": str(args.out_dir / "source_coverage.csv"),
            "market_regime_monthly": str(args.out_dir / "market_regime_monthly.csv"),
            "gate_summary_by_source_regime": str(args.out_dir / "gate_summary_by_source_regime.csv"),
            "gate_summary_by_source_detail": str(args.out_dir / "gate_summary_by_source_detail.csv"),
            "candidate_action_summary": str(args.out_dir / "candidate_action_summary.csv"),
            "gate_policy_comparison_5d": str(args.out_dir / "gate_policy_comparison_5d.csv"),
            "gate_policy_comparison_10d": str(args.out_dir / "gate_policy_comparison_10d.csv"),
            "gate_policy_comparison": str(args.out_dir / "gate_policy_comparison.csv"),
            "gate_policy_comparison_full22": str(args.out_dir / "gate_policy_comparison_full22.csv"),
            "spark_score_exception": str(args.out_dir / "spark_score_exception.csv"),
            "rank_bucket_exception": str(args.out_dir / "rank_bucket_exception.csv"),
            "correlation_by_source": str(args.out_dir / "correlation_by_source.csv"),
            "market_metric_bucket_summary": str(args.out_dir / "market_metric_bucket_summary.csv"),
            "market_metric_scorecard": str(args.out_dir / "market_metric_scorecard.csv"),
            "market_metric_leaderboard": str(args.out_dir / "market_metric_leaderboard.csv"),
            "source_day_outcomes": str(args.out_dir / "source_day_outcomes.csv"),
            "market_metric_source_day_bucket_summary": str(args.out_dir / "market_metric_source_day_bucket_summary.csv"),
            "market_metric_source_day_scorecard": str(args.out_dir / "market_metric_source_day_scorecard.csv"),
            "market_metric_source_day_leaderboard": str(args.out_dir / "market_metric_source_day_leaderboard.csv"),
            "correlation_readout": correlation_report_path,
            "probe_funnel_summary": str(args.out_dir / "probe_funnel_summary.csv"),
            "research_conclusion": report_path,
        },
    }
    (args.out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
