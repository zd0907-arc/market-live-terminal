from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
HEAT_DB = Path("/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db")
ATOMIC_DB = Path("/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_compact_current.db")
DOC_DIR = ROOT / "docs/strategy-rework/strategies/aggressive-10cm/experiments/hot-theme-agent"
DATA_DIR = ROOT / "data/selection/aggressive_10cm/hot_theme_agent"
SUMMARY_JSON = DATA_DIR / "summary.json"
TRADES_CSV = DATA_DIR / "trades.csv"
README_MD = DOC_DIR / "README.md"

INITIAL_CAPITAL = 1_000_000.0
BUY_COST_RATE = 0.0012
SELL_COST_RATE = 0.0012


@dataclass(frozen=True)
class VariantConfig:
    name: str
    label: str
    description: str
    top_n_per_day: int
    max_positions: int
    per_position_pct: float
    max_gap_up_pct: float
    max_gap_down_pct: float
    min_total_amount: float
    hard_stop_pct: float
    take_profit_pct: float
    trailing_activate_pct: float
    trailing_drawdown_pct: float
    max_holding_days: int
    theme_decay_rank: int
    min_signal_return_1d: float
    max_signal_return_1d: float
    min_amount_ratio_20d: float
    min_price_position_20d: float
    max_price_position_20d: float
    min_stock_l2_main_yi: float


LEADER_ATTACK = VariantConfig(
    name="leader_attack",
    label="热点龙头进攻",
    description="只做日内最强热点里的 leader/volume_core，强调主线热度、强度和个股承接。",
    top_n_per_day=3,
    max_positions=3,
    per_position_pct=0.30,
    max_gap_up_pct=0.065,
    max_gap_down_pct=-0.03,
    min_total_amount=250_000_000.0,
    hard_stop_pct=-0.065,
    take_profit_pct=0.18,
    trailing_activate_pct=0.12,
    trailing_drawdown_pct=-0.07,
    max_holding_days=6,
    theme_decay_rank=18,
    min_signal_return_1d=3.0,
    max_signal_return_1d=9.8,
    min_amount_ratio_20d=1.25,
    min_price_position_20d=0.45,
    max_price_position_20d=1.02,
    min_stock_l2_main_yi=0.10,
)

THEME_RESONANCE = VariantConfig(
    name="theme_resonance",
    label="板块共振扩散",
    description="只做同日落在多个热点主题里的重叠成员，强调主题共振、扩散与容量承接。",
    top_n_per_day=3,
    max_positions=3,
    per_position_pct=0.30,
    max_gap_up_pct=0.055,
    max_gap_down_pct=-0.035,
    min_total_amount=220_000_000.0,
    hard_stop_pct=-0.07,
    take_profit_pct=0.20,
    trailing_activate_pct=0.14,
    trailing_drawdown_pct=-0.08,
    max_holding_days=7,
    theme_decay_rank=25,
    min_signal_return_1d=2.0,
    max_signal_return_1d=9.8,
    min_amount_ratio_20d=1.10,
    min_price_position_20d=0.30,
    max_price_position_20d=0.85,
    min_stock_l2_main_yi=0.02,
)


def connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def is_mainboard_10cm_symbol(symbol: str) -> bool:
    s = str(symbol).lower()
    return s.startswith(("sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def linear_score(value: Any, low: float, high: float) -> float:
    v = safe_float(value, default=low)
    if high <= low:
        return 0.0
    return 100.0 * clip((v - low) / (high - low), 0.0, 1.0)


def max_drawdown_from_curve(values: Sequence[float]) -> float:
    peak = None
    worst = 0.0
    for value in values:
        if peak is None or value > peak:
            peak = value
        if peak and peak > 0:
            dd = (value / peak - 1.0) * 100.0
            worst = min(worst, dd)
    return round(worst, 2)


def previous_trade_date(trade_dates: Sequence[str], trade_date: str) -> Optional[str]:
    prev = None
    for day in trade_dates:
        if str(day) >= str(trade_date):
            return prev
        prev = str(day)
    return prev


def next_trade_date(trade_dates: Sequence[str], trade_date: str) -> Optional[str]:
    for day in trade_dates:
        if str(day) > str(trade_date):
            return str(day)
    return None


def trade_dates_between(start_date: str, end_date: str) -> List[str]:
    with connect_ro(ATOMIC_DB) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM atomic_trade_daily
            WHERE trade_date BETWEEN ? AND ?
            ORDER BY trade_date
            """,
            [start_date, end_date],
        ).fetchall()
    return [str(row[0]) for row in rows]


def load_atomic_panel(start_date: str, end_date: str) -> pd.DataFrame:
    sql = """
        SELECT
            lower(t.symbol) AS symbol,
            t.trade_date,
            t.open,
            t.high,
            t.low,
            t.close,
            t.total_amount,
            t.l2_main_net_amount,
            t.l2_super_net_amount,
            l.prev_close,
            l.up_limit_price,
            l.down_limit_price,
            l.limit_pct,
            l.board_type,
            l.risk_flag_type,
            l.touch_limit_up,
            l.is_limit_up_close,
            l.is_limit_down_close,
            l.broken_limit_up
        FROM atomic_trade_daily t
        LEFT JOIN atomic_limit_state_daily l
          ON l.symbol = t.symbol
         AND l.trade_date = t.trade_date
        WHERE t.trade_date BETWEEN ? AND ?
          AND (
            lower(t.symbol) LIKE 'sh600%%'
            OR lower(t.symbol) LIKE 'sh601%%'
            OR lower(t.symbol) LIKE 'sh603%%'
            OR lower(t.symbol) LIKE 'sh605%%'
            OR lower(t.symbol) LIKE 'sz000%%'
            OR lower(t.symbol) LIKE 'sz001%%'
            OR lower(t.symbol) LIKE 'sz002%%'
            OR lower(t.symbol) LIKE 'sz003%%'
          )
        ORDER BY lower(t.symbol), t.trade_date
    """
    with connect_ro(ATOMIC_DB) as conn:
        df = pd.read_sql_query(sql, conn, params=[start_date, end_date])
    if df.empty:
        return df
    for col in [
        "open",
        "high",
        "low",
        "close",
        "total_amount",
        "l2_main_net_amount",
        "l2_super_net_amount",
        "prev_close",
        "up_limit_price",
        "down_limit_price",
        "limit_pct",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["touch_limit_up", "is_limit_up_close", "is_limit_down_close", "broken_limit_up"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["risk_flag_type"] = df["risk_flag_type"].fillna("normal")
    return df


def load_hot_theme_panel(start_date: str, end_date: str, rank_limit: int = 20) -> pd.DataFrame:
    sql = """
        SELECT
            m.trade_date,
            lower(m.symbol) AS symbol,
            m.name,
            m.role,
            m.return_1d,
            m.return_3d,
            m.return_5d,
            m.return_20d,
            m.amount_ratio_20d,
            m.l2_main_net_yi,
            m.l2_super_net_yi,
            m.price_position_20d,
            h.theme_id,
            h.sector_name,
            h.hot_rank,
            h.persistence_rank,
            h.hot_score,
            h.persistence_score,
            h.member_count,
            h.up_ratio,
            h.strong_count,
            h.limit_up_count,
            h.amount_yi,
            h.l2_main_net_yi AS theme_l2_main_net_yi,
            h.leader_symbol,
            h.leader_name,
            h.leader_return_1d,
            h.leader_strength,
            h.leader_concentration,
            h.risk_tags_json
        FROM fine_theme_member_daily m
        JOIN fine_theme_heat_daily h
          ON h.trade_date = m.trade_date
         AND h.theme_id = m.theme_id
        WHERE m.trade_date BETWEEN ? AND ?
          AND h.hot_rank <= ?
    """
    with connect_ro(HEAT_DB) as conn:
        df = pd.read_sql_query(sql, conn, params=[start_date, end_date, rank_limit])
    if df.empty:
        return df
    numeric_cols = [
        "return_1d",
        "return_3d",
        "return_5d",
        "return_20d",
        "amount_ratio_20d",
        "l2_main_net_yi",
        "l2_super_net_yi",
        "price_position_20d",
        "hot_rank",
        "persistence_rank",
        "hot_score",
        "persistence_score",
        "member_count",
        "up_ratio",
        "strong_count",
        "limit_up_count",
        "amount_yi",
        "theme_l2_main_net_yi",
        "leader_return_1d",
        "leader_strength",
        "leader_concentration",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["name"] = df["name"].fillna("")
    df["role"] = df["role"].fillna("")
    df["is_mainboard"] = df["symbol"].map(is_mainboard_10cm_symbol)
    df["is_st"] = df["name"].str.contains("ST", case=False, na=False)
    df["role_leader"] = df["role"].str.contains("leader", na=False)
    df["role_volume_core"] = df["role"].str.contains("volume_core", na=False)
    df["role_lowpos"] = df["role"].str.contains("low_position_candidate", na=False)
    df = df[df["is_mainboard"] & ~df["is_st"]].copy()
    return df


def build_daily_symbol_summary(theme_panel: pd.DataFrame) -> pd.DataFrame:
    if theme_panel.empty:
        return theme_panel

    def joined(values: Iterable[Any]) -> str:
        items = sorted({str(v) for v in values if str(v)})
        return "|".join(items)

    grouped = (
        theme_panel.groupby(["trade_date", "symbol"], as_index=False)
        .agg(
            name=("name", "first"),
            theme_hits=("theme_id", "nunique"),
            top10_hits=("hot_rank", lambda s: int((pd.to_numeric(s, errors="coerce") <= 10).sum())),
            best_rank=("hot_rank", "min"),
            avg_hot_score=("hot_score", "mean"),
            avg_persistence_score=("persistence_score", "mean"),
            max_member_count=("member_count", "max"),
            avg_up_ratio=("up_ratio", "mean"),
            total_strong_count=("strong_count", "sum"),
            total_limit_up_count=("limit_up_count", "sum"),
            total_theme_amount_yi=("amount_yi", "sum"),
            total_theme_l2_main_yi=("theme_l2_main_net_yi", "sum"),
            stock_return_1d=("return_1d", "max"),
            stock_return_3d=("return_3d", "max"),
            stock_return_5d=("return_5d", "max"),
            stock_return_20d=("return_20d", "max"),
            stock_amount_ratio_20d=("amount_ratio_20d", "max"),
            stock_l2_main_yi=("l2_main_net_yi", "max"),
            stock_l2_super_yi=("l2_super_net_yi", "max"),
            stock_price_position_20d=("price_position_20d", "max"),
            leader_hits=("role_leader", "sum"),
            volume_hits=("role_volume_core", "sum"),
            lowpos_hits=("role_lowpos", "sum"),
            theme_names=("sector_name", joined),
        )
    )
    return grouped


def build_maps(
    atomic_panel: pd.DataFrame,
    theme_panel: pd.DataFrame,
    summary_panel: pd.DataFrame,
) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Dict[Tuple[str, str], Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    atomic_map = {
        (str(row["symbol"]), str(row["trade_date"])): row.to_dict()
        for _, row in atomic_panel.iterrows()
    }
    summary_map = {
        (str(row["symbol"]), str(row["trade_date"])): row.to_dict()
        for _, row in summary_panel.iterrows()
    }
    theme_day_symbol_best: Dict[str, Dict[str, Any]] = {}
    if not theme_panel.empty:
        temp = theme_panel.copy()
        temp["signal_score_proxy"] = (
            0.45 * (21 - temp["hot_rank"].fillna(20).clip(upper=20))
            + 0.25 * temp["hot_score"].fillna(0)
            + 0.15 * temp["persistence_score"].fillna(0)
            + 0.10 * temp["amount_ratio_20d"].fillna(0) * 10
            + 0.05 * temp["l2_main_net_yi"].fillna(0) * 8
        )
        temp = temp.sort_values(
            ["trade_date", "symbol", "signal_score_proxy", "hot_rank"],
            ascending=[True, True, False, True],
        ).drop_duplicates(["trade_date", "symbol"], keep="first")
        theme_day_symbol_best = {
            f"{row['trade_date']}|{row['symbol']}": row.to_dict()
            for _, row in temp.iterrows()
        }
    return atomic_map, summary_map, theme_day_symbol_best


def score_leader_attack(row: Dict[str, Any]) -> float:
    score = (
        0.22 * linear_score(9 - safe_float(row.get("hot_rank")), 1, 8)
        + 0.16 * linear_score(row.get("hot_score"), 84, 97)
        + 0.10 * linear_score(row.get("persistence_score"), 58, 88)
        + 0.12 * linear_score(row.get("strong_count"), 1, 8)
        + 0.08 * linear_score(row.get("limit_up_count"), 0, 4)
        + 0.14 * linear_score(row.get("amount_ratio_20d"), 1.0, 3.0)
        + 0.10 * linear_score(row.get("l2_main_net_yi"), 0.0, 2.5)
        + 0.08 * linear_score(row.get("return_1d"), 3.0, 9.2)
    )
    role_bonus = 7.0 if row.get("role_leader") else 4.0 if row.get("role_volume_core") else 0.0
    overheat_penalty = 0.10 * linear_score(row.get("return_20d"), 28, 65)
    price_penalty = 0.08 * linear_score(row.get("price_position_20d"), 0.96, 1.10)
    return round(max(0.0, min(100.0, score + role_bonus - overheat_penalty - price_penalty)), 2)


def score_theme_resonance(row: Dict[str, Any]) -> float:
    score = (
        0.20 * linear_score(row.get("theme_hits"), 2, 5)
        + 0.14 * linear_score(21 - safe_float(row.get("best_rank")), 1, 20)
        + 0.16 * linear_score(row.get("avg_hot_score"), 82, 94)
        + 0.10 * linear_score(row.get("avg_persistence_score"), 55, 85)
        + 0.10 * linear_score(row.get("total_limit_up_count"), 2, 12)
        + 0.10 * linear_score(row.get("stock_amount_ratio_20d"), 1.0, 2.5)
        + 0.08 * linear_score(row.get("stock_l2_main_yi"), 0.0, 2.0)
        + 0.06 * linear_score(row.get("stock_return_1d"), 2.0, 8.5)
        + 0.06 * linear_score(row.get("total_theme_l2_main_yi"), 0.0, 15.0)
    )
    role_bonus = 5.0 if safe_float(row.get("leader_hits")) >= 1 else 3.0 if safe_float(row.get("volume_hits")) >= 1 else 0.0
    overheat_penalty = 0.12 * linear_score(row.get("stock_return_20d"), 24, 55)
    crowded_penalty = 0.08 * linear_score(row.get("stock_price_position_20d"), 0.92, 1.02)
    return round(max(0.0, min(100.0, score + role_bonus - overheat_penalty - crowded_penalty)), 2)


def leader_attack_candidates(
    signal_date: str,
    cfg: VariantConfig,
    theme_panel: pd.DataFrame,
    atomic_map: Dict[Tuple[str, str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    day = theme_panel[theme_panel["trade_date"] == signal_date].copy()
    if day.empty:
        return []
    day = day[
        (day["hot_rank"] <= 8)
        & (day["hot_score"] >= 84)
        & (day["persistence_score"] >= 58)
        & (day["amount_ratio_20d"] >= cfg.min_amount_ratio_20d)
        & (day["price_position_20d"].between(cfg.min_price_position_20d, cfg.max_price_position_20d, inclusive="both"))
        & (day["return_1d"].between(cfg.min_signal_return_1d, cfg.max_signal_return_1d, inclusive="both"))
        & (day["l2_main_net_yi"] >= cfg.min_stock_l2_main_yi)
        & (day["role_leader"] | day["role_volume_core"])
    ].copy()
    if day.empty:
        return []
    candidates: List[Dict[str, Any]] = []
    for _, row in day.iterrows():
        atomic_row = atomic_map.get((str(row["symbol"]), signal_date))
        if not atomic_row:
            continue
        if safe_float(atomic_row.get("total_amount")) < cfg.min_total_amount:
            continue
        if str(atomic_row.get("risk_flag_type") or "normal") != "normal":
            continue
        item = row.to_dict()
        item["score"] = score_leader_attack(item)
        item["signal_variant"] = cfg.name
        item["signal_reason"] = f"{row['sector_name']} rank#{int(safe_float(row['hot_rank']))}"
        item["theme_names"] = str(row["sector_name"])
        item["theme_hits"] = 1
        item["best_rank"] = int(safe_float(row["hot_rank"]))
        candidates.append(item)
    if not candidates:
        return []
    day_df = pd.DataFrame(candidates).sort_values(["score", "hot_rank"], ascending=[False, True])
    day_df = day_df.drop_duplicates(["symbol"], keep="first")
    return day_df.sort_values(["score", "hot_rank"], ascending=[False, True]).head(cfg.top_n_per_day).to_dict("records")


def theme_resonance_candidates(
    signal_date: str,
    cfg: VariantConfig,
    summary_panel: pd.DataFrame,
    atomic_map: Dict[Tuple[str, str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    day = summary_panel[summary_panel["trade_date"] == signal_date].copy()
    if day.empty:
        return []
    day = day[
        (day["theme_hits"] >= 2)
        & (day["avg_hot_score"] >= 83)
        & (day["avg_persistence_score"] >= 55)
        & (day["stock_amount_ratio_20d"] >= cfg.min_amount_ratio_20d)
        & (day["stock_price_position_20d"].between(cfg.min_price_position_20d, cfg.max_price_position_20d, inclusive="both"))
        & (day["stock_return_1d"].between(cfg.min_signal_return_1d, cfg.max_signal_return_1d, inclusive="both"))
        & (day["stock_l2_main_yi"] >= cfg.min_stock_l2_main_yi)
        & (day["total_theme_l2_main_yi"] > 0)
        & ((day["leader_hits"] >= 1) | (day["volume_hits"] >= 1) | (day["lowpos_hits"] >= 1))
    ].copy()
    if day.empty:
        return []
    candidates: List[Dict[str, Any]] = []
    for _, row in day.iterrows():
        atomic_row = atomic_map.get((str(row["symbol"]), signal_date))
        if not atomic_row:
            continue
        if safe_float(atomic_row.get("total_amount")) < cfg.min_total_amount:
            continue
        if str(atomic_row.get("risk_flag_type") or "normal") != "normal":
            continue
        item = row.to_dict()
        item["score"] = score_theme_resonance(item)
        item["signal_variant"] = cfg.name
        item["signal_reason"] = f"theme_hits={int(safe_float(row['theme_hits']))}, best_rank={int(safe_float(row['best_rank']))}"
        candidates.append(item)
    if not candidates:
        return []
    day_df = pd.DataFrame(candidates).sort_values(["score", "theme_hits", "best_rank"], ascending=[False, False, True])
    return day_df.head(cfg.top_n_per_day).to_dict("records")


def entry_ok(atomic_row: Dict[str, Any], cfg: VariantConfig) -> Tuple[bool, str]:
    open_price = safe_float(atomic_row.get("open"))
    prev_close = safe_float(atomic_row.get("prev_close"))
    up_limit_price = safe_float(atomic_row.get("up_limit_price"))
    if open_price <= 0 or prev_close <= 0:
        return False, "bad_price"
    gap = open_price / prev_close - 1.0
    if gap > cfg.max_gap_up_pct:
        return False, "gap_up_too_high"
    if gap < cfg.max_gap_down_pct:
        return False, "gap_down_too_low"
    if up_limit_price > 0 and open_price >= up_limit_price * 0.997:
        return False, "open_near_limit_up"
    return True, "ok"


def simulate_variant(
    cfg: VariantConfig,
    signal_start: str,
    signal_end: str,
    replay_end: str,
    trade_dates: Sequence[str],
    atomic_map: Dict[Tuple[str, str], Dict[str, Any]],
    summary_map: Dict[Tuple[str, str], Dict[str, Any]],
    theme_panel: pd.DataFrame,
    summary_panel: pd.DataFrame,
) -> Dict[str, Any]:
    signal_dates = [d for d in trade_dates if signal_start <= d <= signal_end]
    simulation_dates = [d for d in trade_dates if signal_start <= d <= replay_end]
    pending_entries: Dict[str, List[Dict[str, Any]]] = {}
    daily_signals: List[Dict[str, Any]] = []

    for signal_date in signal_dates:
        if cfg.name == LEADER_ATTACK.name:
            picks = leader_attack_candidates(signal_date, cfg, theme_panel, atomic_map)
        else:
            picks = theme_resonance_candidates(signal_date, cfg, summary_panel, atomic_map)
        entry_date = next_trade_date(simulation_dates, signal_date)
        daily_signals.append(
            {
                "signal_date": signal_date,
                "entry_date": entry_date,
                "candidate_count": len(picks),
                "symbols": [item["symbol"] for item in picks],
            }
        )
        if not entry_date:
            continue
        for item in picks:
            pending_entries.setdefault(entry_date, []).append(item)

    cash = INITIAL_CAPITAL
    positions: Dict[str, Dict[str, Any]] = {}
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []

    def close_position(pos: Dict[str, Any], trade_date: str, gross_exit_price: float, reason: str) -> None:
        nonlocal cash
        shares = safe_float(pos["shares"])
        net_exit_price = gross_exit_price * (1.0 - SELL_COST_RATE)
        proceeds = shares * net_exit_price
        cash += proceeds
        invested_cash = safe_float(pos["invested_cash"])
        realized_cash = proceeds
        trade = {
            "variant": cfg.name,
            "variant_label": cfg.label,
            "signal_period_start": signal_start,
            "signal_period_end": signal_end,
            "replay_end": replay_end,
            "symbol": pos["symbol"],
            "name": pos["name"],
            "signal_date": pos["signal_date"],
            "entry_date": pos["entry_date"],
            "exit_date": trade_date,
            "signal_score": round(safe_float(pos["signal_score"]), 2),
            "signal_reason": pos["signal_reason"],
            "theme_names": pos["theme_names"],
            "theme_hits": pos["theme_hits"],
            "best_rank": pos["best_rank"],
            "entry_price": round(safe_float(pos["entry_price"]), 4),
            "exit_price": round(gross_exit_price, 4),
            "invested_cash": round(invested_cash, 2),
            "realized_cash": round(realized_cash, 2),
            "holding_days": int(pos["holding_days"]),
            "max_runup_pct": round(safe_float(pos["max_runup_pct"]), 2),
            "max_drawdown_pct": round(safe_float(pos["max_drawdown_pct"]), 2),
            "exit_reason": reason,
        }
        trade["net_return_pct"] = round((realized_cash / invested_cash - 1.0) * 100.0, 2) if invested_cash > 0 else 0.0
        trades.append(trade)
        positions.pop(pos["symbol"], None)

    for trade_date in simulation_dates:
        for symbol, pos in list(positions.items()):
            if pos.get("pending_exit_reason"):
                atomic_row = atomic_map.get((symbol, trade_date))
                if atomic_row:
                    close_position(pos, trade_date, safe_float(atomic_row["open"]), str(pos["pending_exit_reason"]))
                else:
                    close_position(pos, trade_date, safe_float(pos["entry_price"]), str(pos["pending_exit_reason"]))
                continue

            atomic_row = atomic_map.get((symbol, trade_date))
            if not atomic_row:
                continue
            entry_price = safe_float(pos["entry_price"])
            high = safe_float(atomic_row["high"])
            low = safe_float(atomic_row["low"])
            close_price = safe_float(atomic_row["close"])
            open_price = safe_float(atomic_row["open"])
            pos["holding_days"] += 1
            pos["peak_price"] = max(safe_float(pos["peak_price"]), high)
            pos["max_runup_pct"] = max(safe_float(pos["max_runup_pct"]), (high / entry_price - 1.0) * 100.0)
            pos["max_drawdown_pct"] = min(safe_float(pos["max_drawdown_pct"]), (low / entry_price - 1.0) * 100.0)

            stop_price = entry_price * (1.0 + cfg.hard_stop_pct)
            if low <= stop_price:
                realized = stop_price if open_price >= stop_price else open_price
                close_position(pos, trade_date, realized, "hard_stop")
                continue

            if high >= entry_price * (1.0 + cfg.take_profit_pct):
                pos["take_profit_armed"] = True

            if safe_float(pos["peak_price"]) >= entry_price * (1.0 + cfg.trailing_activate_pct):
                pullback = close_price / safe_float(pos["peak_price"]) - 1.0
                if pullback <= cfg.trailing_drawdown_pct:
                    pos["pending_exit_reason"] = "trailing_exit"

            daily_summary = summary_map.get((symbol, trade_date), {})
            close_return = close_price / entry_price - 1.0
            if cfg.name == LEADER_ATTACK.name:
                best_rank = safe_float(daily_summary.get("best_rank"), 999.0)
                if best_rank > cfg.theme_decay_rank and close_return <= 0:
                    pos["pending_exit_reason"] = "theme_decay"
            else:
                theme_hits = safe_float(daily_summary.get("theme_hits"), 0.0)
                best_rank = safe_float(daily_summary.get("best_rank"), 999.0)
                if theme_hits < 2 and best_rank > cfg.theme_decay_rank and close_return <= 0.01:
                    pos["pending_exit_reason"] = "resonance_fade"

            if pos["holding_days"] >= cfg.max_holding_days:
                pos["pending_exit_reason"] = "time_exit"

        day_entries = sorted(
            pending_entries.get(trade_date, []),
            key=lambda item: (-safe_float(item.get("score")), str(item.get("symbol"))),
        )
        for item in day_entries:
            if item["symbol"] in positions:
                continue
            if len(positions) >= cfg.max_positions:
                break
            atomic_row = atomic_map.get((str(item["symbol"]), trade_date))
            if not atomic_row:
                continue
            ok, reason = entry_ok(atomic_row, cfg)
            if not ok:
                continue
            position_cash = min(cash, INITIAL_CAPITAL * cfg.per_position_pct)
            if position_cash < 50_000:
                continue
            gross_open = safe_float(atomic_row["open"])
            net_entry = gross_open * (1.0 + BUY_COST_RATE)
            shares = position_cash / net_entry
            if shares <= 0:
                continue
            cash -= position_cash
            positions[str(item["symbol"])] = {
                "symbol": str(item["symbol"]),
                "name": str(item.get("name") or item["symbol"]),
                "signal_date": str(item["trade_date"]),
                "entry_date": trade_date,
                "entry_price": net_entry,
                "shares": shares,
                "invested_cash": position_cash,
                "signal_score": safe_float(item.get("score")),
                "signal_reason": str(item.get("signal_reason") or ""),
                "theme_names": str(item.get("theme_names") or item.get("sector_name") or ""),
                "theme_hits": int(safe_float(item.get("theme_hits"), 1.0)),
                "best_rank": int(safe_float(item.get("best_rank"), 999.0)),
                "holding_days": 0,
                "peak_price": net_entry,
                "max_runup_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "pending_exit_reason": None,
                "take_profit_armed": False,
            }

        equity = cash
        for symbol, pos in positions.items():
            atomic_row = atomic_map.get((symbol, trade_date))
            mark_price = safe_float(atomic_row["close"]) if atomic_row else safe_float(pos["entry_price"])
            equity += safe_float(pos["shares"]) * mark_price
        equity_curve.append(
            {
                "date": trade_date,
                "equity": round(equity, 2),
                "cash": round(cash, 2),
                "open_positions": len(positions),
            }
        )

    if simulation_dates:
        last_date = simulation_dates[-1]
        for symbol, pos in list(positions.items()):
            atomic_row = atomic_map.get((symbol, last_date))
            gross_exit = safe_float(atomic_row["close"]) if atomic_row else safe_float(pos["entry_price"])
            close_position(pos, last_date, gross_exit, "window_end")
        if equity_curve:
            equity_curve[-1]["equity"] = round(cash, 2)
            equity_curve[-1]["cash"] = round(cash, 2)
            equity_curve[-1]["open_positions"] = 0

    return {
        "variant": cfg.name,
        "variant_label": cfg.label,
        "config": asdict(cfg),
        "signal_start": signal_start,
        "signal_end": signal_end,
        "replay_end": replay_end,
        "daily_signals": daily_signals,
        "trades": trades,
        "equity_curve": equity_curve,
        "summary": summarize_trades(trades, equity_curve),
    }


def summarize_trades(trades: List[Dict[str, Any]], equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
    returns = [safe_float(item.get("net_return_pct")) for item in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    holdings = [int(item.get("holding_days") or 0) for item in trades]
    final_equity = safe_float(equity_curve[-1]["equity"]) if equity_curve else INITIAL_CAPITAL
    summary = {
        "trade_count": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
        "median_return_pct": round(float(pd.Series(returns).median()), 2) if returns else 0.0,
        "max_return_pct": round(max(returns), 2) if returns else 0.0,
        "min_return_pct": round(min(returns), 2) if returns else 0.0,
        "avg_holding_days": round(sum(holdings) / len(holdings), 2) if holdings else 0.0,
        "profit_factor": round(abs(sum(wins) / sum(losses)), 2) if losses and sum(losses) != 0 else None,
        "final_equity": round(final_equity, 2),
        "net_return_pct": round((final_equity / INITIAL_CAPITAL - 1.0) * 100.0, 2),
        "max_drawdown_pct": max_drawdown_from_curve([safe_float(item["equity"]) for item in equity_curve]),
        "big_winner_gt_10pct": sum(1 for r in returns if r > 10.0),
        "big_loss_le_-7pct": sum(1 for r in returns if r <= -7.0),
    }
    return summary


def pick_best_variant(run_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    scored = []
    for name, payload in run_map.items():
        summary = payload["summary"]
        scored.append(
            (
                safe_float(summary.get("net_return_pct")),
                -abs(safe_float(summary.get("max_drawdown_pct"))),
                safe_float(summary.get("win_rate_pct")),
                name,
            )
        )
    scored.sort(reverse=True)
    best_name = scored[0][3]
    return {
        "variant": best_name,
        "variant_label": run_map[best_name]["variant_label"],
        "summary": run_map[best_name]["summary"],
    }


def write_outputs(payload: Dict[str, Any]) -> None:
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    trade_rows = payload["all_trades"]
    fieldnames = [
        "variant",
        "variant_label",
        "signal_period_start",
        "signal_period_end",
        "replay_end",
        "symbol",
        "name",
        "signal_date",
        "entry_date",
        "exit_date",
        "signal_score",
        "signal_reason",
        "theme_names",
        "theme_hits",
        "best_rank",
        "entry_price",
        "exit_price",
        "invested_cash",
        "realized_cash",
        "net_return_pct",
        "holding_days",
        "max_runup_pct",
        "max_drawdown_pct",
        "exit_reason",
    ]
    with TRADES_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in trade_rows:
            writer.writerow({key: row.get(key) for key in fieldnames})

    april = payload["runs"]["april_replay"]
    full = payload["runs"]["full_window"]
    best = payload["best_variant"]
    lines = [
        "# 热点主线 / 板块共振 aggressive 10cm 实验",
        "",
        f"- 数据源：`{HEAT_DB}`、`{ATOMIC_DB}`",
        "- 初始资金：100万，主板 10cm，信号日收盘后打分，下一交易日开盘买入。",
        "- 统一约束：不使用任何信号日之后的字段；买入一律 T+1；持仓退出只使用持仓当日及以前数据。",
        "",
        "## 变体",
        "",
        f"- `{LEADER_ATTACK.name}`：{LEADER_ATTACK.description}",
        f"- `{THEME_RESONANCE.name}`：{THEME_RESONANCE.description}",
        "",
        "## 结果",
        "",
        "| period | variant | net_return_pct | max_drawdown_pct | trade_count | win_rate_pct | avg_return_pct |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for period_key, period_label in [("april_replay", "2026-04-01~2026-04-30 -> 2026-05-11"), ("full_window", "2026-03-02~2026-05-11")]:
        for variant_name in [LEADER_ATTACK.name, THEME_RESONANCE.name]:
            summary = payload["runs"][period_key][variant_name]["summary"]
            lines.append(
                f"| {period_label} | {variant_name} | {summary['net_return_pct']:.2f} | {summary['max_drawdown_pct']:.2f} | {summary['trade_count']} | {summary['win_rate_pct']:.2f} | {summary['avg_return_pct']:.2f} |"
            )
    lines.extend(
        [
            "",
            "## 最优变体",
            "",
            f"- 以全区间 `net_return_pct` 优先、`max_drawdown_pct` 次优筛选，当前最优：`{best['variant']}`。",
            f"- 全区间表现：收益 {best['summary']['net_return_pct']:.2f}% ，最大回撤 {best['summary']['max_drawdown_pct']:.2f}% ，交易 {best['summary']['trade_count']} 笔，胜率 {best['summary']['win_rate_pct']:.2f}%。",
            "",
            "## 无未来函数说明",
            "",
            "- 信号端只读取当日 `fine_theme_heat_daily` / `fine_theme_member_daily` 和当日 `atomic_*_daily`。",
            "- 买入执行固定为下一交易日开盘，且过滤过高缺口和开盘近涨停情形。",
            "- 止损 / 趋势衰减 / 超时退出只依据持仓期间当日 OHLC 与当日热点状态，若是收盘后触发则下一交易日开盘卖出。",
        ]
    )
    README_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate hot-theme aggressive 10cm strategies without lookahead")
    parser.add_argument("--signal-start-1", default="2026-04-01")
    parser.add_argument("--signal-end-1", default="2026-04-30")
    parser.add_argument("--replay-end-1", default="2026-05-11")
    parser.add_argument("--signal-start-2", default="2026-03-02")
    parser.add_argument("--signal-end-2", default="2026-05-11")
    parser.add_argument("--replay-end-2", default="2026-05-11")
    args = parser.parse_args()

    overall_start = min(args.signal_start_1, args.signal_start_2)
    overall_end = max(args.replay_end_1, args.replay_end_2)
    trade_dates = trade_dates_between(overall_start, overall_end)
    if not trade_dates:
        raise SystemExit("No trade dates found in atomic DB")

    atomic_panel = load_atomic_panel(overall_start, overall_end)
    theme_panel = load_hot_theme_panel(overall_start, overall_end, rank_limit=20)
    summary_panel = build_daily_symbol_summary(theme_panel)
    atomic_map, summary_map, _ = build_maps(atomic_panel, theme_panel, summary_panel)

    runs: Dict[str, Dict[str, Any]] = {"april_replay": {}, "full_window": {}}
    period_specs = {
        "april_replay": (args.signal_start_1, args.signal_end_1, args.replay_end_1),
        "full_window": (args.signal_start_2, args.signal_end_2, args.replay_end_2),
    }
    for period_key, spec in period_specs.items():
        signal_start, signal_end, replay_end = spec
        for cfg in [LEADER_ATTACK, THEME_RESONANCE]:
            runs[period_key][cfg.name] = simulate_variant(
                cfg=cfg,
                signal_start=signal_start,
                signal_end=signal_end,
                replay_end=replay_end,
                trade_dates=trade_dates,
                atomic_map=atomic_map,
                summary_map=summary_map,
                theme_panel=theme_panel,
                summary_panel=summary_panel,
            )

    best_variant = pick_best_variant(runs["full_window"])
    all_trades: List[Dict[str, Any]] = []
    for period_runs in runs.values():
        for payload in period_runs.values():
            all_trades.extend(payload["trades"])
    all_trades = sorted(all_trades, key=lambda item: (str(item["variant"]), str(item["signal_date"]), str(item["symbol"])))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_sources": {
            "heat_db": str(HEAT_DB),
            "atomic_db": str(ATOMIC_DB),
        },
        "constraints": {
            "initial_capital": INITIAL_CAPITAL,
            "universe": "mainboard_10cm_only",
            "buy_rule": "signal_close_then_t_plus_1_open",
            "lookahead": False,
        },
        "coverage": {
            "trade_date_start": trade_dates[0],
            "trade_date_end": trade_dates[-1],
            "trade_dates": len(trade_dates),
            "theme_rows_top20": int(len(theme_panel)),
            "theme_symbol_rows": int(len(summary_panel)),
        },
        "variants": {
            LEADER_ATTACK.name: {
                "label": LEADER_ATTACK.label,
                "description": LEADER_ATTACK.description,
                "config": asdict(LEADER_ATTACK),
            },
            THEME_RESONANCE.name: {
                "label": THEME_RESONANCE.label,
                "description": THEME_RESONANCE.description,
                "config": asdict(THEME_RESONANCE),
            },
        },
        "runs": runs,
        "best_variant": best_variant,
        "all_trades": all_trades,
    }
    write_outputs(payload)
    print(json.dumps({"best_variant": best_variant, "summary_json": str(SUMMARY_JSON), "trades_csv": str(TRADES_CSV), "readme_md": str(README_MD)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
