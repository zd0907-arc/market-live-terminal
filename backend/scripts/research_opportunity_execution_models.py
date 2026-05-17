#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pickle
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import research_opportunity_discovery_model as base

try:
    import joblib
except Exception:  # pragma: no cover
    joblib = None


ROOT = Path(__file__).resolve().parents[2]
MODEL_VERSION = "execution_v0_1"
OUT_DIR = ROOT / "data/selection/opportunity_discovery" / MODEL_VERSION
OPP22_DIR = ROOT / "data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1"
SHORT_DIR = ROOT / "data/selection/opportunity_discovery/short_horizon_v0_1"
DEFAULT_STOCK_SECTOR_DB = Path("/Users/dong/Desktop/AIGC/market-data/market_heat/stock_sector_map.db")


@dataclass(frozen=True)
class ExecutionConfig:
    start_date: str = "2025-01-02"
    end_date: str = "2026-05-14"
    validation_start: str = "2026-03-02"
    horizon_days: int = 22
    candidate_pool_topn: int = 20
    train_sell_topn: int = 5
    max_open_gap_up_pct: float = 6.8
    max_open_gap_down_pct: float = -5.5
    initial_capital: float = 1_000_000.0
    random_state: int = 42


ENTRY_FEATURES = [
    "rank_22_full",
    "rank_h5_full",
    "score_22",
    "score_h5",
    "h5_score_on_22_scale",
    "entry_gap_pct",
    "entry_near_limit_up",
    "entry_locked_limit_up",
    "daily_return_pct",
    "return_3d_pct",
    "return_5d_pct",
    "return_20d_pct",
    "dist_ma20_pct",
    "price_position_20d",
    "breakout_score",
    "stealth_score",
    "distribution_score",
    "l2_main_net_ratio",
    "l2_super_net_ratio",
    "active_buy_strength",
    "amount_anomaly_20d_atomic",
    "hot_theme_best_rank",
    "hot_theme_score",
    "hot_theme_is_climax_hot",
    "signal_limit_up_like",
    "signal_locked_limit_up_like",
    "market_advancing_ratio",
    "market_l2_main_net_ratio",
]

BUY_POINT_FEATURES = ENTRY_FEATURES + [
    "entry_model_score",
    "auction_gap_pct",
    "auction_match_amount_ratio",
    "auction_l2_add_buy_ratio",
    "auction_l2_add_sell_ratio",
    "auction_l2_cancel_buy_ratio",
    "auction_l2_cancel_sell_ratio",
    "first5_return_from_open_pct",
    "first5_range_pct",
    "first5_l2_main_net_ratio",
    "first5_l2_super_net_ratio",
    "first15_return_from_open_pct",
    "first15_range_pct",
    "first15_l2_main_net_ratio",
    "first15_l2_super_net_ratio",
    "first15_order_imbalance_ratio",
    "first15_cvd_ratio",
    "first15_add_buy_ratio",
    "first15_add_sell_ratio",
    "first15_cancel_buy_ratio",
    "first15_cancel_sell_ratio",
]


DYNAMIC_EXIT_POLICIES: Tuple[Dict[str, Any], ...] = (
    {
        "name": "sell_model_no_tp_stop12_th2",
        "hard_stop_pct": -12.0,
        "exit_threshold": 2.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
    },
    {
        "name": "sell_model_no_tp_stop10_th3",
        "hard_stop_pct": -10.0,
        "exit_threshold": 3.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
    },
    {
        "name": "sell_model_trail_no_tp_stop12_th2",
        "hard_stop_pct": -12.0,
        "exit_threshold": 2.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
        "trailing_activate_pct": 12.0,
        "trailing_drawdown_pct": 7.0,
    },
)


def _connect_ro(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _json_dump(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_model(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if joblib is not None:
        joblib.dump(model, path)
        return
    with path.open("wb") as f:
        pickle.dump(model, f)


def _read_model(path: Path) -> Any:
    if joblib is not None:
        return joblib.load(path)
    with path.open("rb") as f:
        return pickle.load(f)


def _safe_float(value: Any, default: float = 0.0) -> float:
    return base._to_float(value, default)


def _safe_div(num: float, den: float) -> float:
    den = float(den or 0.0)
    return float(num or 0.0) / den if abs(den) > 1e-12 else 0.0


def _month_key(date: str) -> str:
    return str(date)[:7]


def _entry_target(df: pd.DataFrame) -> pd.Series:
    mfe = pd.to_numeric(df["max_runup_22d_pct"], errors="coerce").fillna(0.0)
    mdd_to_mfe = pd.to_numeric(df["mdd_to_mfe_pct"], errors="coerce").fillna(0.0)
    max_dd = pd.to_numeric(df["max_drawdown_22d_pct"], errors="coerce").fillna(0.0)
    gap = pd.to_numeric(df["entry_gap_pct"], errors="coerce").fillna(0.0)
    locked = pd.to_numeric(df.get("entry_locked_limit_up", 0.0), errors="coerce").fillna(0.0)
    near = pd.to_numeric(df.get("entry_near_limit_up", 0.0), errors="coerce").fillna(0.0)
    path_penalty = np.maximum(0.0, -mdd_to_mfe - 5.0) * 0.90 + np.maximum(0.0, -max_dd - 12.0) * 0.20
    gap_penalty = np.maximum(0.0, gap - 3.5) * 1.55 + np.maximum(0.0, -gap - 4.5) * 0.65
    block_penalty = locked * 25.0 + np.maximum(0.0, near - locked) * 8.0
    return (mfe - path_penalty - gap_penalty - block_penalty).clip(-50.0, 90.0)


def _zscore_by_day(df: pd.DataFrame, col: str) -> pd.Series:
    values = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    mean = values.groupby(df["trade_date"]).transform("mean")
    std = values.groupby(df["trade_date"]).transform("std").replace(0.0, np.nan).fillna(1.0)
    return ((values - mean) / std).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def _fit_regressor(train: pd.DataFrame, feature_cols: Sequence[str], target_col: str, random_state: int) -> Pipeline:
    observed_features = [
        col
        for col in feature_cols
        if col in train.columns and train[col].replace([np.inf, -np.inf], np.nan).notna().any()
    ]
    X = train[list(observed_features)].replace([np.inf, -np.inf], np.nan)
    y = pd.to_numeric(train[target_col], errors="coerce").fillna(0.0)
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.052,
        max_iter=220,
        max_leaf_nodes=31,
        min_samples_leaf=35,
        l2_regularization=0.06,
        random_state=int(random_state),
    )
    pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", model),
        ]
    )
    weight = 1.0 + (y >= 15.0).astype(float) * 1.2 + (y < 0.0).astype(float) * 0.4
    pipe.fit(X, y, model__sample_weight=weight)
    return pipe


def _predict_with_features(model: Pipeline, df: pd.DataFrame, features: Sequence[str]) -> np.ndarray:
    work = df.copy()
    for col in features:
        if col not in work.columns:
            work[col] = 0.0
    return model.predict(work[list(features)].replace([np.inf, -np.inf], np.nan))


def _score_dataset(
    config: ExecutionConfig,
    atomic_db: Path,
    selection_db: Path,
    heat_db: Path,
    opp22_dir: Path,
    short_dir: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    base_config = base.OpportunityConfig(
        start_date=config.start_date,
        end_date=config.end_date,
        validation_start=config.validation_start,
        horizon_days=config.horizon_days,
        max_open_gap_up_pct=config.max_open_gap_up_pct,
        max_open_gap_down_pct=config.max_open_gap_down_pct,
    )
    data, panel = base.build_dataset(base_config, atomic_db, selection_db, heat_db)
    if data.empty:
        raise RuntimeError("No labeled opportunity dataset was built")
    data = base._apply_historical_entry_filter(data, base_config).copy()
    if data.empty:
        raise RuntimeError("No candidates left after historical entry filter")

    feature_22 = _load_json(opp22_dir / "feature_columns.json")["features"]
    feature_h5 = _load_json(short_dir / "feature_columns.json")["features"]
    model_22 = _read_model(opp22_dir / "model.joblib")
    model_h5 = _read_model(short_dir / "model_h5.joblib")
    for col in sorted(set(feature_22).union(feature_h5)):
        if col not in data.columns:
            data[col] = 0.0

    data["rule_score"] = base._score_rule_baseline(data)
    data["score_22_model"] = model_22.predict(data[list(feature_22)])
    data["score_h5_model"] = model_h5.predict(data[list(feature_h5)])
    data["score_22"] = 0.78 * data["score_22_model"] + 0.22 * data["rule_score"]
    data["score_h5"] = 0.78 * data["score_h5_model"] + 0.22 * data["rule_score"]
    data = data.sort_values(["trade_date", "score_22", "symbol"], ascending=[True, False, True]).copy()
    data["rank_22_full"] = data.groupby("trade_date").cumcount() + 1
    data = data.sort_values(["trade_date", "score_h5", "symbol"], ascending=[True, False, True]).copy()
    data["rank_h5_full"] = data.groupby("trade_date").cumcount() + 1
    data["z22_day"] = _zscore_by_day(data, "score_22")
    data["zh5_day"] = _zscore_by_day(data, "score_h5")
    score_22_mean = data["score_22"].groupby(data["trade_date"]).transform("mean")
    score_22_std = data["score_22"].groupby(data["trade_date"]).transform("std").replace(0.0, np.nan).fillna(1.0)
    data["h5_score_on_22_scale"] = score_22_mean + data["zh5_day"] * score_22_std
    data["entry_target"] = _entry_target(data)
    pool = data[pd.to_numeric(data["rank_22_full"], errors="coerce").fillna(999999) <= int(config.candidate_pool_topn)].copy()
    label_before_validation = pd.to_datetime(pool["label_complete_asof_date"]) < pd.to_datetime(config.validation_start)
    signal_in_validation = pd.to_datetime(pool["trade_date"]) >= pd.to_datetime(config.validation_start)
    pool["split"] = np.select(
        [label_before_validation, signal_in_validation],
        ["train", "validation"],
        default="gap",
    )
    pool = pool[pool["split"].isin(["train", "validation"])].copy()
    return pool, panel


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
            rows = conn.execute(sql, [str(s).lower() for s in symbols]).fetchall()
    except Exception:
        return names
    for row in rows:
        symbol = str(row["symbol"]).lower()
        name = str(row["name"] or "").strip()
        if symbol and name and name.lower() not in {symbol, "nan"} and symbol not in names:
            names[symbol] = name
    sector_db = DEFAULT_STOCK_SECTOR_DB
    if sector_db.exists():
        placeholders = ",".join("?" for _ in symbols)
        try:
            with _connect_ro(sector_db) as conn:
                rows = conn.execute(
                    f"""
                    SELECT lower(symbol) AS symbol, name
                    FROM stock_sector_memberships
                    WHERE lower(symbol) IN ({placeholders})
                      AND name IS NOT NULL
                      AND name != ''
                    ORDER BY fetched_at DESC
                    """,
                    [str(s).lower() for s in symbols],
                ).fetchall()
            for row in rows:
                symbol = str(row["symbol"]).lower()
                name = str(row["name"] or "").strip()
                if symbol and name and name.lower() not in {symbol, "nan"} and symbol not in names:
                    names[symbol] = name
        except Exception:
            pass
    return names


def _load_entry_intraday_features(candidates: pd.DataFrame, atomic_db: Path) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    keys = (
        candidates[["symbol", "entry_date", "entry_open", "total_amount"]]
        .dropna(subset=["symbol", "entry_date"])
        .drop_duplicates(["symbol", "entry_date"])
        .copy()
    )
    keys["symbol"] = keys["symbol"].astype(str).str.lower()
    by_date: Dict[str, List[str]] = {}
    for date, group in keys.groupby("entry_date", sort=True):
        by_date[str(date)] = sorted(set(group["symbol"].astype(str)))

    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    with _connect_ro(atomic_db) as conn:
        for entry_date, symbols in by_date.items():
            placeholders = ",".join("?" for _ in symbols)
            if not placeholders:
                continue
            trade_sql = f"""
                SELECT lower(symbol) AS symbol, trade_date, bucket_start, open, high, low, close,
                       total_amount, l2_main_net_amount, l2_super_net_amount,
                       l2_main_buy_amount, l2_main_sell_amount,
                       l2_super_buy_amount, l2_super_sell_amount
                FROM atomic_trade_5m
                WHERE trade_date = ?
                  AND lower(symbol) IN ({placeholders})
                  AND substr(bucket_start, 12, 8) <= '09:40:00'
                ORDER BY lower(symbol), bucket_start
            """
            trade = pd.read_sql_query(trade_sql, conn, params=[entry_date, *symbols])
            order_sql = f"""
                SELECT lower(symbol) AS symbol, trade_date, bucket_start,
                       add_buy_amount, add_sell_amount, cancel_buy_amount, cancel_sell_amount,
                       cvd_delta_amount, oib_delta_amount, order_event_count
                FROM atomic_order_5m
                WHERE trade_date = ?
                  AND lower(symbol) IN ({placeholders})
                  AND substr(bucket_start, 12, 8) <= '09:40:00'
                ORDER BY lower(symbol), bucket_start
            """
            try:
                order = pd.read_sql_query(order_sql, conn, params=[entry_date, *symbols])
            except Exception:
                order = pd.DataFrame()
            l1_sql = f"""
                SELECT lower(symbol) AS symbol, trade_date, auction_price,
                       auction_match_amount, auction_price_change_pct_vs_prev_close,
                       auction_trade_amount_total
                FROM atomic_open_auction_l1_daily
                WHERE trade_date = ?
                  AND lower(symbol) IN ({placeholders})
            """
            try:
                auction_l1 = pd.read_sql_query(l1_sql, conn, params=[entry_date, *symbols])
            except Exception:
                auction_l1 = pd.DataFrame()
            l2_sql = f"""
                SELECT lower(symbol) AS symbol, trade_date,
                       auction_order_add_buy_amount, auction_order_add_sell_amount,
                       auction_order_cancel_buy_amount, auction_order_cancel_sell_amount,
                       auction_trade_amount_total
                FROM atomic_open_auction_l2_daily
                WHERE trade_date = ?
                  AND lower(symbol) IN ({placeholders})
            """
            try:
                auction_l2 = pd.read_sql_query(l2_sql, conn, params=[entry_date, *symbols])
            except Exception:
                auction_l2 = pd.DataFrame()

            order_map: Dict[str, pd.DataFrame] = {}
            if not order.empty:
                order["symbol"] = order["symbol"].astype(str).str.lower()
                order_map = {s: g.sort_values("bucket_start").copy() for s, g in order.groupby("symbol", sort=False)}
            a1 = auction_l1.set_index("symbol").to_dict(orient="index") if not auction_l1.empty else {}
            a2 = auction_l2.set_index("symbol").to_dict(orient="index") if not auction_l2.empty else {}
            if trade.empty:
                for symbol in symbols:
                    rows[(symbol, entry_date)] = {"symbol": symbol, "entry_date": entry_date, "has_first5": 0}
                continue
            trade["symbol"] = trade["symbol"].astype(str).str.lower()
            for symbol, g0 in trade.groupby("symbol", sort=False):
                g = g0.sort_values("bucket_start").copy()
                first = g.head(1)
                first3 = g.head(3)
                daily_amount = _safe_float(keys[(keys["symbol"] == symbol) & (keys["entry_date"].astype(str) == entry_date)]["total_amount"].iloc[0], 0.0)
                entry_open = _safe_float(keys[(keys["symbol"] == symbol) & (keys["entry_date"].astype(str) == entry_date)]["entry_open"].iloc[0], 0.0)
                first5_close = _safe_float(first["close"].iloc[-1], 0.0) if not first.empty else 0.0
                first15_close = _safe_float(first3["close"].iloc[-1], 0.0) if not first3.empty else 0.0
                first5_amount = float(pd.to_numeric(first.get("total_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                first15_amount = float(pd.to_numeric(first3.get("total_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                first15_main = float(pd.to_numeric(first3.get("l2_main_net_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                first15_super = float(pd.to_numeric(first3.get("l2_super_net_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                first5_main = float(pd.to_numeric(first.get("l2_main_net_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                first5_super = float(pd.to_numeric(first.get("l2_super_net_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                payload: Dict[str, Any] = {
                    "symbol": symbol,
                    "entry_date": entry_date,
                    "has_first5": int(first5_close > 0),
                    "first5_entry_price": round(first5_close, 4) if first5_close > 0 else np.nan,
                    "first15_entry_price": round(first15_close, 4) if first15_close > 0 else np.nan,
                    "first5_return_from_open_pct": round((first5_close / entry_open - 1.0) * 100.0, 4) if entry_open > 0 and first5_close > 0 else 0.0,
                    "first5_range_pct": round((_safe_float(first["high"].max(), 0.0) / max(_safe_float(first["low"].min(), 0.0), 1e-9) - 1.0) * 100.0, 4)
                    if not first.empty
                    else 0.0,
                    "first5_l2_main_net_ratio": round(_safe_div(first5_main, first5_amount), 6),
                    "first5_l2_super_net_ratio": round(_safe_div(first5_super, first5_amount), 6),
                    "first15_return_from_open_pct": round((first15_close / entry_open - 1.0) * 100.0, 4) if entry_open > 0 and first15_close > 0 else 0.0,
                    "first15_range_pct": round((_safe_float(first3["high"].max(), 0.0) / max(_safe_float(first3["low"].min(), 0.0), 1e-9) - 1.0) * 100.0, 4)
                    if not first3.empty
                    else 0.0,
                    "first15_amount_ratio": round(_safe_div(first15_amount, daily_amount), 6),
                    "first15_l2_main_net_ratio": round(_safe_div(first15_main, first15_amount), 6),
                    "first15_l2_super_net_ratio": round(_safe_div(first15_super, first15_amount), 6),
                }
                og = order_map.get(symbol)
                if og is not None and not og.empty:
                    o3 = og.head(3)
                    add_buy = float(pd.to_numeric(o3.get("add_buy_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                    add_sell = float(pd.to_numeric(o3.get("add_sell_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                    cancel_buy = float(pd.to_numeric(o3.get("cancel_buy_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                    cancel_sell = float(pd.to_numeric(o3.get("cancel_sell_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
                    payload.update(
                        {
                            "first15_order_imbalance_ratio": round(_safe_div(float(pd.to_numeric(o3.get("oib_delta_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()), first15_amount), 6),
                            "first15_cvd_ratio": round(_safe_div(float(pd.to_numeric(o3.get("cvd_delta_amount", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()), first15_amount), 6),
                            "first15_add_buy_ratio": round(_safe_div(add_buy, first15_amount), 6),
                            "first15_add_sell_ratio": round(_safe_div(add_sell, first15_amount), 6),
                            "first15_cancel_buy_ratio": round(_safe_div(cancel_buy, first15_amount), 6),
                            "first15_cancel_sell_ratio": round(_safe_div(cancel_sell, first15_amount), 6),
                        }
                    )
                a1row = a1.get(symbol, {})
                a2row = a2.get(symbol, {})
                auction_amount = _safe_float(a1row.get("auction_match_amount"), _safe_float(a1row.get("auction_trade_amount_total"), 0.0))
                payload.update(
                    {
                        "auction_gap_pct": round(_safe_float(a1row.get("auction_price_change_pct_vs_prev_close"), np.nan), 4)
                        if a1row
                        else np.nan,
                        "auction_match_amount_ratio": round(_safe_div(auction_amount, daily_amount), 6),
                        "auction_l2_add_buy_ratio": round(_safe_div(_safe_float(a2row.get("auction_order_add_buy_amount"), 0.0), max(auction_amount, 1.0)), 6),
                        "auction_l2_add_sell_ratio": round(_safe_div(_safe_float(a2row.get("auction_order_add_sell_amount"), 0.0), max(auction_amount, 1.0)), 6),
                        "auction_l2_cancel_buy_ratio": round(_safe_div(_safe_float(a2row.get("auction_order_cancel_buy_amount"), 0.0), max(auction_amount, 1.0)), 6),
                        "auction_l2_cancel_sell_ratio": round(_safe_div(_safe_float(a2row.get("auction_order_cancel_sell_amount"), 0.0), max(auction_amount, 1.0)), 6),
                    }
                )
                rows[(symbol, entry_date)] = payload
            for symbol in symbols:
                rows.setdefault((symbol, entry_date), {"symbol": symbol, "entry_date": entry_date, "has_first5": 0})
    return pd.DataFrame(rows.values())


def _add_first5_target(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    entry_open = pd.to_numeric(out["entry_open"], errors="coerce").replace(0.0, np.nan)
    first5 = pd.to_numeric(out.get("first5_entry_price", np.nan), errors="coerce").replace(0.0, np.nan)
    max_high = entry_open * (1.0 + pd.to_numeric(out["max_runup_22d_pct"], errors="coerce").fillna(0.0) / 100.0)
    low_to_mfe = entry_open * (1.0 + pd.to_numeric(out["mdd_to_mfe_pct"], errors="coerce").fillna(0.0) / 100.0)
    runup = (max_high / first5 - 1.0) * 100.0
    mdd = (low_to_mfe / first5 - 1.0) * 100.0
    gap = pd.to_numeric(out["entry_gap_pct"], errors="coerce").fillna(0.0)
    out["first5_entry_target"] = (
        runup.fillna(-20.0)
        - np.maximum(0.0, -mdd.fillna(-20.0) - 5.0) * 0.90
        - np.maximum(0.0, gap - 3.5) * 0.8
    ).clip(-50.0, 90.0)
    return out


def _future_path_map(atomic_panel: pd.DataFrame, keys: Iterable[Tuple[str, str]], horizon_days: int) -> Dict[Tuple[str, str], pd.DataFrame]:
    config = base.OpportunityConfig(horizon_days=int(horizon_days))
    return base._future_path_map(atomic_panel, config, keys=keys)


def _simulate_dynamic_exit_trade(
    future: pd.DataFrame,
    feature_lookup: pd.DataFrame,
    sell_model: Pipeline,
    sell_features: Sequence[str],
    config: base.OpportunityConfig,
    policy: Dict[str, Any],
    *,
    gross_entry_price: float,
) -> Dict[str, Any]:
    if future.empty:
        return {"exit_reason": "no_future_path", "net_return_pct": 0.0, "holding_days": 0}
    gross_entry = float(gross_entry_price)
    if gross_entry <= 0:
        return {"exit_reason": "bad_entry_price", "net_return_pct": 0.0, "holding_days": 0}
    entry_price = base._apply_buy_cost(gross_entry, config)
    peak_high = gross_entry
    trough_low = gross_entry
    cum_amount = 0.0
    cum_main = 0.0
    cum_super = 0.0
    close_hist: List[float] = []
    main_hist: List[float] = []
    super_hist: List[float] = []
    amount_hist: List[float] = []
    pending_exit_reason: Optional[str] = None
    pending_exit_day: Optional[str] = None
    exit_price = base._to_float(future.iloc[-1].get("atomic_close"))
    exit_date = str(future.iloc[-1]["trade_date"])
    exit_reason = "fallback_horizon_close"
    holding_days = int(len(future))
    max_runup = 0.0
    max_drawdown = 0.0
    hard_stop = policy.get("hard_stop_pct")
    min_hold_days = int(policy.get("min_hold_days", 2))
    max_holding_days = int(policy.get("max_holding_days", 22))
    exit_threshold = float(policy.get("exit_threshold", 2.0))
    trailing_activate = policy.get("trailing_activate_pct")
    trailing_drawdown = policy.get("trailing_drawdown_pct")

    for offset, day in enumerate(future.itertuples(index=False), start=1):
        trade_date = str(getattr(day, "trade_date"))
        open_p = base._to_float(getattr(day, "open", 0.0))
        high_p = base._to_float(getattr(day, "high", 0.0))
        low_p = base._to_float(getattr(day, "low", 0.0))
        close_p = base._to_float(getattr(day, "atomic_close", 0.0))
        amount = base._to_float(getattr(day, "total_amount", 0.0))
        main_net = base._to_float(getattr(day, "l2_main_net_amount", 0.0))
        super_net = base._to_float(getattr(day, "l2_super_net_amount", 0.0))
        if pending_exit_reason is not None and offset > 1:
            exit_price = open_p if open_p > 0 else close_p
            exit_date = trade_date
            exit_reason = pending_exit_reason
            holding_days = offset
            break
        if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
            continue
        peak_high = max(peak_high, high_p)
        trough_low = min(trough_low, low_p)
        max_runup = max(max_runup, (high_p / gross_entry - 1.0) * 100.0)
        max_drawdown = min(max_drawdown, (low_p / gross_entry - 1.0) * 100.0)
        cum_amount += amount
        cum_main += main_net
        cum_super += super_net
        close_hist.append(close_p)
        main_hist.append(main_net)
        super_hist.append(super_net)
        amount_hist.append(amount)

        if offset >= 2 and hard_stop is not None and low_p <= gross_entry * (1.0 + float(hard_stop) / 100.0):
            stop_price = gross_entry * (1.0 + float(hard_stop) / 100.0)
            exit_price = stop_price if open_p > stop_price else open_p
            exit_date = trade_date
            exit_reason = "hard_stop_intraday"
            holding_days = offset
            break
        if (
            offset >= 2
            and trailing_activate is not None
            and trailing_drawdown is not None
            and (peak_high / gross_entry - 1.0) * 100.0 >= float(trailing_activate)
        ):
            trail_price = peak_high * (1.0 - float(trailing_drawdown) / 100.0)
            if low_p <= trail_price:
                exit_price = trail_price if open_p > trail_price else open_p
                exit_date = trade_date
                exit_reason = "trailing_stop_intraday"
                holding_days = offset
                break
        if offset >= max_holding_days:
            exit_price = close_p
            exit_date = trade_date
            exit_reason = "fallback_horizon_close"
            holding_days = offset
            break
        if offset < min_hold_days:
            continue

        row_data: Dict[str, Any] = {}
        symbol = str(getattr(day, "symbol"))
        if (symbol, trade_date) in feature_lookup.index:
            rec = feature_lookup.loc[(symbol, trade_date)]
            if isinstance(rec, pd.DataFrame):
                rec = rec.iloc[0]
            for col in sell_features:
                if col in rec:
                    row_data[col] = base._to_float(rec.get(col))
        prev_close = close_hist[-2] if len(close_hist) >= 2 else gross_entry
        amount_3 = sum(amount_hist[-3:])
        row_data.update(
            {
                "holding_days": int(offset),
                "unrealized_close_return_pct": (close_p / gross_entry - 1.0) * 100.0,
                "max_runup_so_far_pct": (peak_high / gross_entry - 1.0) * 100.0,
                "drawdown_from_peak_pct": (close_p / peak_high - 1.0) * 100.0 if peak_high else 0.0,
                "max_drawdown_so_far_pct": (trough_low / gross_entry - 1.0) * 100.0,
                "day_return_pct": (close_p / prev_close - 1.0) * 100.0 if prev_close else 0.0,
                "return_3d_from_hold_pct": (close_p / close_hist[-4] - 1.0) * 100.0
                if len(close_hist) >= 4 and close_hist[-4] > 0
                else 0.0,
                "return_5d_from_hold_pct": (close_p / close_hist[-6] - 1.0) * 100.0
                if len(close_hist) >= 6 and close_hist[-6] > 0
                else 0.0,
                "main_net_3d_hold_ratio": sum(main_hist[-3:]) / amount_3 if amount_3 else 0.0,
                "super_net_3d_hold_ratio": sum(super_hist[-3:]) / amount_3 if amount_3 else 0.0,
                "main_net_cum_hold_ratio": cum_main / cum_amount if cum_amount else 0.0,
                "super_net_cum_hold_ratio": cum_super / cum_amount if cum_amount else 0.0,
            }
        )
        x = pd.DataFrame([{col: row_data.get(col, 0.0) for col in sell_features}])
        hold_value_pred = float(sell_model.predict(x)[0])
        if hold_value_pred < exit_threshold:
            pending_exit_reason = "sell_model_exit_next_open"
            pending_exit_day = trade_date

    net_exit = base._apply_sell_cost(exit_price, config)
    return {
        "exit_date": exit_date,
        "exit_reason": exit_reason,
        "gross_exit_price": round(float(exit_price), 4),
        "net_exit_price": base._apply_sell_cost(exit_price, config),
        "gross_return_pct": round(float((exit_price / gross_entry - 1.0) * 100.0), 4),
        "net_return_pct": round(float((net_exit / entry_price - 1.0) * 100.0), 4),
        "holding_days": int(holding_days),
        "max_runup_before_exit_pct": round(float(max_runup), 4),
        "max_drawdown_before_exit_pct": round(float(max_drawdown), 4),
        "pending_exit_day": pending_exit_day,
    }


def _select_entries(scored: pd.DataFrame, strategy: Dict[str, Any]) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame()
    mode = str(strategy["mode"])
    h5_rank_max = strategy.get("h5_rank_max")
    entry_score_min = strategy.get("entry_score_min")
    buy_point_min = strategy.get("buy_point_min")
    ranked = scored.sort_values(["trade_date", "rank_22_full", "symbol"], ascending=[True, True, True]).copy()
    rows: List[pd.DataFrame] = []
    for _, day0 in ranked.groupby("trade_date", sort=True):
        day = day0.copy()
        if mode == "top1":
            day = day[day["rank_22_full"].astype(float) <= 1].copy()
            day["weight"] = 0.80
        elif mode == "top2":
            day = day[day["rank_22_full"].astype(float) <= 2].copy()
            day["weight"] = np.where(day["rank_22_full"].astype(float) <= 1, 0.55, 0.35)
        elif mode == "top1_plus_confirmed_top2":
            top1 = day[day["rank_22_full"].astype(float) <= 1].copy()
            top1["weight"] = 0.55
            top2 = day[day["rank_22_full"].astype(float).eq(2)].copy()
            top2["weight"] = 0.35
            day = pd.concat([top1, top2], ignore_index=True)
        else:
            raise ValueError(f"unknown entry mode: {mode}")
        if day.empty:
            continue
        if h5_rank_max is not None:
            keep = day["rank_h5_full"].astype(float) <= float(h5_rank_max)
            if mode == "top1_plus_confirmed_top2":
                keep = keep | day["rank_22_full"].astype(float).le(1)
            day = day[keep].copy()
        if entry_score_min is not None:
            keep = pd.to_numeric(day["entry_model_score"], errors="coerce").fillna(-999.0) >= float(entry_score_min)
            if mode == "top1_plus_confirmed_top2":
                keep = keep | day["rank_22_full"].astype(float).le(1)
            day = day[keep].copy()
        if buy_point_min is not None:
            keep = pd.to_numeric(day["buy_point_score"], errors="coerce").fillna(-999.0) >= float(buy_point_min)
            if mode == "top1_plus_confirmed_top2":
                keep = keep | day["rank_22_full"].astype(float).le(1)
            day = day[keep].copy()
        if not day.empty:
            rows.append(day)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _build_orders(
    scored: pd.DataFrame,
    atomic_panel: pd.DataFrame,
    feature_panel: pd.DataFrame,
    sell_model: Pipeline,
    sell_features: Sequence[str],
    config: ExecutionConfig,
    base_config: base.OpportunityConfig,
    strategy: Dict[str, Any],
    exit_policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    entries = _select_entries(scored, strategy)
    if entries.empty:
        return [], {"selected": 0, "skipped_gap_or_limit": 0, "skipped_no_path": 0, "skipped_no_price": 0}
    keys = [(str(row["symbol"]), str(row["trade_date"])) for _, row in entries.iterrows()]
    path_map = _future_path_map(atomic_panel, keys, config.horizon_days)
    feature_lookup = feature_panel.set_index(["symbol", "trade_date"], drop=False)
    orders: List[Dict[str, Any]] = []
    counters = {"selected": int(len(entries)), "skipped_gap_or_limit": 0, "skipped_no_path": 0, "skipped_no_price": 0}
    for _, row in entries.iterrows():
        symbol = str(row["symbol"])
        signal_date = str(row["trade_date"])
        entry_gap = base._to_float(row.get("entry_gap_pct"))
        locked = base._to_float(row.get("entry_locked_limit_up"))
        if locked > 0 or entry_gap > config.max_open_gap_up_pct or entry_gap < config.max_open_gap_down_pct:
            counters["skipped_gap_or_limit"] += 1
            continue
        future = path_map.get((symbol, signal_date))
        if future is None or future.empty:
            counters["skipped_no_path"] += 1
            continue
        entry_mode = str(strategy["entry_mode"])
        gross_entry = base._to_float(future.iloc[0].get("open"))
        entry_phase = "open"
        if entry_mode == "wait5":
            if base._to_float(row.get("has_first5")) <= 0:
                counters["skipped_no_price"] += 1
                continue
            gross_entry = base._to_float(row.get("first5_entry_price"))
            entry_phase = "first5"
        elif entry_mode == "hybrid_gapdown_wait5":
            if entry_gap < 0:
                if base._to_float(row.get("has_first5")) <= 0:
                    counters["skipped_no_price"] += 1
                    continue
                first5_ret = base._to_float(row.get("first5_return_from_open_pct"))
                first5_main = base._to_float(row.get("first5_l2_main_net_ratio"))
                if first5_ret < 0.0 or first5_main < -0.002:
                    counters["skipped_gap_or_limit"] += 1
                    continue
                gross_entry = base._to_float(row.get("first5_entry_price"))
                entry_phase = "first5"
        if gross_entry <= 0:
            counters["skipped_no_price"] += 1
            continue
        sim = _simulate_dynamic_exit_trade(
            future,
            feature_lookup,
            sell_model,
            sell_features,
            base_config,
            exit_policy,
            gross_entry_price=gross_entry,
        )
        gross_exit = base._to_float(sim.get("gross_exit_price"))
        exit_date = str(sim.get("exit_date", ""))
        if gross_exit <= 0 or not exit_date:
            counters["skipped_no_path"] += 1
            continue
        orders.append(
            {
                "strategy": str(strategy["name"]),
                "entry_mode": entry_mode,
                "exit_policy": str(exit_policy["name"]),
                "mode": str(strategy["mode"]),
                "trade_date": signal_date,
                "entry_date": str(future.iloc[0]["trade_date"]),
                "entry_phase": entry_phase,
                "symbol": symbol,
                "weight": float(row.get("weight", 0.80)),
                "rank_22_full": int(base._to_float(row.get("rank_22_full"), 0)),
                "rank_h5_full": int(base._to_float(row.get("rank_h5_full"), 0)),
                "score_22": round(base._to_float(row.get("score_22")), 4),
                "score_h5": round(base._to_float(row.get("score_h5")), 4),
                "entry_model_score": round(base._to_float(row.get("entry_model_score")), 4),
                "buy_point_score": round(base._to_float(row.get("buy_point_score")), 4),
                "entry_gap_pct": round(entry_gap, 4),
                "first5_return_from_open_pct": round(base._to_float(row.get("first5_return_from_open_pct")), 4),
                "max_runup_22d_pct": round(base._to_float(row.get("max_runup_22d_pct")), 4),
                "gross_entry_price": round(gross_entry, 4),
                "net_entry_price": base._apply_buy_cost(gross_entry, base_config),
                **sim,
            }
        )
    return orders, counters


def _simulate_account(
    orders: List[Dict[str, Any]],
    atomic: pd.DataFrame,
    base_config: base.OpportunityConfig,
    initial_capital: float,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    if not orders:
        return pd.DataFrame(), pd.DataFrame(), {"orders": 0, "trades": 0}
    price_lookup = atomic.set_index(["symbol", "trade_date"], drop=False)
    all_dates = sorted(str(d) for d in atomic["trade_date"].unique())
    min_date = min(str(order["entry_date"]) for order in orders)
    max_date = max(str(order["exit_date"]) for order in orders)
    calendar = [d for d in all_dates if min_date <= d <= max_date]
    orders_by_entry: Dict[str, List[Dict[str, Any]]] = {}
    for order in orders:
        orders_by_entry.setdefault(str(order["entry_date"]), []).append(order)

    def record_at(symbol: str, trade_date: str) -> Optional[pd.Series]:
        try:
            rec = price_lookup.loc[(symbol, trade_date)]
        except KeyError:
            return None
        if isinstance(rec, pd.DataFrame):
            rec = rec.iloc[0]
        return rec

    def mark_position(pos: Dict[str, Any], trade_date: str, price_col: str = "atomic_close") -> float:
        rec = record_at(str(pos["symbol"]), trade_date)
        if rec is None:
            return float(pos["cost_cash"])
        price = base._to_float(rec.get(price_col), 0.0)
        if price <= 0 and price_col != "atomic_close":
            price = base._to_float(rec.get("atomic_close"), 0.0)
        return float(pos["shares"]) * base._apply_sell_cost(price, base_config) if price > 0 else float(pos["cost_cash"])

    min_position_cash = max(20_000.0, initial_capital * 0.02)
    cash = float(initial_capital)
    positions: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    curve: List[Dict[str, Any]] = []
    skipped_cash = 0
    skipped_duplicate = 0

    for current_date in calendar:
        still_open: List[Dict[str, Any]] = []
        for pos in positions:
            if str(pos["exit_date"]) == current_date:
                sale_cash = float(pos["shares"]) * float(pos["net_exit_price"])
                cash += sale_cash
                pnl = sale_cash - float(pos["cost_cash"])
                record = dict(pos["order"])
                record.update(
                    {
                        "shares": int(pos["shares"]),
                        "position_cash": round(float(pos["cost_cash"]), 2),
                        "pnl_cash": round(float(pnl), 2),
                        "equity_after": round(cash + sum(mark_position(p, current_date, "open") for p in positions if p is not pos), 2),
                        "net_return_pct": round(float(pnl / float(pos["cost_cash"]) * 100.0), 4) if pos["cost_cash"] else 0.0,
                    }
                )
                trades.append(record)
            else:
                still_open.append(pos)
        positions = still_open

        equity_for_sizing = cash + sum(mark_position(pos, current_date, "open") for pos in positions)
        for order in orders_by_entry.get(current_date, []):
            if any(str(pos["symbol"]) == str(order["symbol"]) for pos in positions):
                skipped_duplicate += 1
                continue
            budget = min(cash, equity_for_sizing * float(order["weight"]))
            if budget < min_position_cash:
                skipped_cash += 1
                continue
            shares = math.floor(budget / float(order["net_entry_price"]) / 100.0) * 100
            if shares < 100:
                skipped_cash += 1
                continue
            cost_cash = float(shares) * float(order["net_entry_price"])
            if cost_cash > cash + 1e-6:
                skipped_cash += 1
                continue
            cash -= cost_cash
            positions.append(
                {
                    "symbol": str(order["symbol"]),
                    "shares": int(shares),
                    "cost_cash": cost_cash,
                    "exit_date": str(order["exit_date"]),
                    "net_exit_price": float(order["net_exit_price"]),
                    "order": order,
                }
            )

        equity = cash + sum(mark_position(pos, current_date, "atomic_close") for pos in positions)
        curve.append(
            {
                "trade_date": current_date,
                "equity": round(float(equity), 2),
                "cash": round(float(cash), 2),
                "open_positions": int(len(positions)),
                "invested_cash": round(float(sum(pos["cost_cash"] for pos in positions)), 2),
            }
        )

    trades_df = pd.DataFrame(trades)
    curve_df = pd.DataFrame(curve)
    if curve_df.empty:
        return trades_df, curve_df, {"orders": int(len(orders)), "trades": 0}
    equity_curve = pd.Series([float(initial_capital)] + curve_df["equity"].astype(float).tolist())
    peak = equity_curve.cummax()
    drawdown = equity_curve / peak - 1.0
    returns = pd.to_numeric(trades_df.get("net_return_pct", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    summary = {
        "orders": int(len(orders)),
        "trades": int(len(trades_df)),
        "skipped_cash": int(skipped_cash),
        "skipped_duplicate_symbol": int(skipped_duplicate),
        "final_equity": round(float(curve_df["equity"].iloc[-1]), 2),
        "total_return_pct": round(float((curve_df["equity"].iloc[-1] / initial_capital - 1.0) * 100.0), 4),
        "max_drawdown_pct": round(float(drawdown.min() * 100.0), 4),
        "win_rate": round(float((returns > 0).mean()), 4) if not returns.empty else 0.0,
        "avg_trade_net_return_pct": round(float(returns.mean()), 4) if not returns.empty else 0.0,
        "median_trade_net_return_pct": round(float(returns.median()), 4) if not returns.empty else 0.0,
        "avg_holding_days": round(float(pd.to_numeric(trades_df.get("holding_days", pd.Series(dtype=float)), errors="coerce").mean()), 2)
        if not trades_df.empty
        else 0.0,
        "max_open_positions": int(curve_df["open_positions"].max()) if "open_positions" in curve_df else 0,
        "avg_cash_pct": round(float((curve_df["cash"].astype(float) / curve_df["equity"].replace(0, np.nan).astype(float)).mean() * 100.0), 4),
        "exit_reason_counts": trades_df["exit_reason"].value_counts().to_dict() if "exit_reason" in trades_df else {},
    }
    return trades_df, curve_df, summary


def _build_strategy_grid(train_pool: pd.DataFrame) -> List[Dict[str, Any]]:
    q_entry_40 = float(train_pool["entry_model_score"].quantile(0.40))
    q_entry_55 = float(train_pool["entry_model_score"].quantile(0.55))
    q_bp_50 = float(train_pool["buy_point_score"].quantile(0.50))
    q_bp_65 = float(train_pool["buy_point_score"].quantile(0.65))
    return [
        {"name": "top1_open_baseline", "mode": "top1", "entry_mode": "open"},
        {"name": "top1_h5rank20_open", "mode": "top1", "entry_mode": "open", "h5_rank_max": 20},
        {"name": "top1_h5rank50_open", "mode": "top1", "entry_mode": "open", "h5_rank_max": 50},
        {"name": "top1_entry_q40_open", "mode": "top1", "entry_mode": "open", "entry_score_min": q_entry_40},
        {"name": "top1_entry_q55_open", "mode": "top1", "entry_mode": "open", "entry_score_min": q_entry_55},
        {"name": "top1_wait5_buy_q50", "mode": "top1", "entry_mode": "wait5", "buy_point_min": q_bp_50},
        {"name": "top1_wait5_buy_q65", "mode": "top1", "entry_mode": "wait5", "buy_point_min": q_bp_65},
        {"name": "top1_hybrid_gapdown_wait5", "mode": "top1", "entry_mode": "hybrid_gapdown_wait5", "entry_score_min": q_entry_40},
        {"name": "top2_open_baseline", "mode": "top2", "entry_mode": "open"},
        {"name": "top2_h5rank50_entry_q40_open", "mode": "top2", "entry_mode": "open", "h5_rank_max": 50, "entry_score_min": q_entry_40},
        {"name": "top1_plus_confirmed_top2", "mode": "top1_plus_confirmed_top2", "entry_mode": "open", "h5_rank_max": 50, "entry_score_min": q_entry_40},
        {"name": "top1_plus_confirmed_top2_wait5", "mode": "top1_plus_confirmed_top2", "entry_mode": "wait5", "h5_rank_max": 50, "buy_point_min": q_bp_50},
    ]


def _latest_candidates(
    pool: pd.DataFrame,
    out_dir: Path,
    config: ExecutionConfig,
    selection_db: Path,
) -> pd.DataFrame:
    latest_date = str(pool["trade_date"].max())
    latest = pool[pool["trade_date"].astype(str).eq(latest_date)].copy()
    if latest.empty:
        return latest
    names = _load_names(selection_db, latest["symbol"].astype(str).str.lower().tolist())
    if names:
        latest["name"] = latest["symbol"].astype(str).str.lower().map(names).fillna(latest.get("name", ""))
    latest = latest.sort_values(["rank_22_full", "symbol"], ascending=[True, True]).copy()
    latest["execution_note"] = np.select(
        [
            latest["rank_h5_full"].astype(float) <= 20,
            latest["entry_model_score"].astype(float) >= float(pool["entry_model_score"].quantile(0.55)),
            latest["buy_point_score"].astype(float) >= float(pool["buy_point_score"].quantile(0.65)),
        ],
        ["H5短线确认强", "开盘买入适配较好", "等待5分钟确认较好"],
        default="只作为22日主候选观察",
    )
    keep = [
        "trade_date",
        "symbol",
        "name",
        "rank_22_full",
        "rank_h5_full",
        "score_22",
        "score_h5",
        "entry_model_score",
        "buy_point_score",
        "entry_gap_pct",
        "first5_return_from_open_pct",
        "first15_l2_main_net_ratio",
        "close",
        "daily_return_pct",
        "return_5d_pct",
        "return_20d_pct",
        "total_amount",
        "breakout_score",
        "stealth_score",
        "distribution_score",
        "signal_limit_up_like",
        "signal_locked_limit_up_like",
        "execution_note",
    ]
    out = latest[[col for col in keep if col in latest.columns]].head(30).copy()
    out.to_csv(out_dir / "latest_execution_candidates.csv", index=False)
    return out


def run_command(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = ExecutionConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        validation_start=args.validation_start,
        horizon_days=int(args.horizon_days),
        candidate_pool_topn=int(args.candidate_pool_topn),
        train_sell_topn=int(args.train_sell_topn),
        initial_capital=float(args.initial_capital),
    )
    base_config = base.OpportunityConfig(
        start_date=config.start_date,
        end_date=config.end_date,
        validation_start=config.validation_start,
        horizon_days=config.horizon_days,
        max_open_gap_up_pct=config.max_open_gap_up_pct,
        max_open_gap_down_pct=config.max_open_gap_down_pct,
    )
    atomic_db = Path(args.atomic_db)
    selection_db = Path(args.selection_db)
    heat_db = Path(args.heat_db)
    opp22_dir = Path(args.opp22_dir)
    short_dir = Path(args.short_dir)

    print("building scored candidate pool...", flush=True)
    pool, feature_panel = _score_dataset(config, atomic_db, selection_db, heat_db, opp22_dir, short_dir)
    names = _load_names(selection_db, sorted(set(pool["symbol"].astype(str).str.lower())))
    if names:
        pool["name"] = pool["symbol"].astype(str).str.lower().map(names).fillna(pool.get("name", ""))
    train_pool = pool[pool["split"].eq("train")].copy()
    valid_pool = pool[pool["split"].eq("validation")].copy()
    if train_pool.empty or valid_pool.empty:
        raise RuntimeError("Train/validation candidate pool is empty")

    print("loading entry intraday features...", flush=True)
    intraday = _load_entry_intraday_features(pool, atomic_db)
    if not intraday.empty:
        pool = pool.merge(intraday, on=["symbol", "entry_date"], how="left")
    for col in BUY_POINT_FEATURES:
        if col not in pool.columns:
            pool[col] = 0.0
    pool["has_first5"] = pd.to_numeric(pool.get("has_first5", 0), errors="coerce").fillna(0).astype(int)
    pool = _add_first5_target(pool)
    train_pool = pool[pool["split"].eq("train")].copy()
    valid_pool = pool[pool["split"].eq("validation")].copy()

    print("training entry and buy-point models...", flush=True)
    entry_features = [
        col
        for col in ENTRY_FEATURES
        if col in pool.columns and train_pool[col].replace([np.inf, -np.inf], np.nan).notna().any()
    ]
    entry_model = _fit_regressor(train_pool, entry_features, "entry_target", config.random_state + 101)
    pool["entry_model_score"] = _predict_with_features(entry_model, pool, entry_features)
    train_pool = pool[pool["split"].eq("train")].copy()
    valid_pool = pool[pool["split"].eq("validation")].copy()
    buy_features = [
        col
        for col in BUY_POINT_FEATURES
        if col in pool.columns and train_pool[col].replace([np.inf, -np.inf], np.nan).notna().any()
    ]
    buy_train = train_pool[train_pool["has_first5"].astype(int).gt(0)].copy()
    if buy_train.empty:
        buy_train = train_pool.copy()
    buy_model = _fit_regressor(buy_train, buy_features, "first5_entry_target", config.random_state + 202)
    pool["buy_point_score"] = _predict_with_features(buy_model, pool, buy_features)
    train_pool = pool[pool["split"].eq("train")].copy()
    valid_pool = pool[pool["split"].eq("validation")].copy()

    print("training dynamic sell model...", flush=True)
    atomic_for_exit = base.add_atomic_features(base.load_atomic_daily(config.start_date, config.end_date, atomic_db))
    sell_train_entries = train_pool.copy()
    sell_train_entries["final_score"] = sell_train_entries["score_22"]
    sell_samples = base._build_holding_training_samples(
        sell_train_entries,
        atomic_for_exit,
        feature_panel,
        base_config,
        score_col="final_score",
        top_k=int(config.train_sell_topn),
    )
    sell_model, sell_features = base._fit_holding_model(sell_samples, base_config)

    print("running execution backtests...", flush=True)
    strategies = _build_strategy_grid(train_pool)
    summary_rows: List[Dict[str, Any]] = []
    trade_parts: List[pd.DataFrame] = []
    curve_parts: List[pd.DataFrame] = []
    for strategy in strategies:
        for exit_policy in DYNAMIC_EXIT_POLICIES:
            orders, counters = _build_orders(
                valid_pool,
                atomic_for_exit,
                feature_panel,
                sell_model,
                sell_features,
                config,
                base_config,
                strategy,
                exit_policy,
            )
            trades, curve, account_summary = _simulate_account(orders, atomic_for_exit, base_config, config.initial_capital)
            account_summary.update(
                {
                    "strategy": strategy["name"],
                    "mode": strategy["mode"],
                    "entry_mode": strategy["entry_mode"],
                    "exit_policy": exit_policy["name"],
                    "h5_rank_max": strategy.get("h5_rank_max"),
                    "entry_score_min": strategy.get("entry_score_min"),
                    "buy_point_min": strategy.get("buy_point_min"),
                    **{f"order_{k}": v for k, v in counters.items()},
                }
            )
            summary_rows.append(account_summary)
            if not trades.empty:
                trades["strategy"] = strategy["name"]
                trades["exit_policy"] = exit_policy["name"]
                trade_parts.append(trades)
            if not curve.empty:
                curve["strategy"] = strategy["name"]
                curve["exit_policy"] = exit_policy["name"]
                curve_parts.append(curve)

    summary_df = pd.DataFrame(summary_rows)
    trades_df = pd.concat(trade_parts, ignore_index=True, sort=False) if trade_parts else pd.DataFrame()
    curves_df = pd.concat(curve_parts, ignore_index=True, sort=False) if curve_parts else pd.DataFrame()
    latest_df = _latest_candidates(pool, out_dir, config, selection_db)

    pool.to_csv(out_dir / "candidate_scores.csv.gz", index=False, compression="gzip")
    intraday.to_csv(out_dir / "entry_intraday_features.csv.gz", index=False, compression="gzip")
    sell_samples.to_csv(out_dir / "sell_train_samples.csv.gz", index=False, compression="gzip")
    summary_df.to_csv(out_dir / "execution_strategy_summary.csv", index=False)
    trades_df.to_csv(out_dir / "execution_trades.csv", index=False)
    curves_df.to_csv(out_dir / "execution_equity_curves.csv", index=False)
    _write_model(out_dir / "entry_model.joblib", entry_model)
    _write_model(out_dir / "buy_point_model.joblib", buy_model)
    _write_model(out_dir / "sell_model.joblib", sell_model)
    _json_dump(out_dir / "entry_feature_columns.json", {"model_version": MODEL_VERSION, "features": entry_features})
    _json_dump(out_dir / "buy_point_feature_columns.json", {"model_version": MODEL_VERSION, "features": buy_features})
    _json_dump(out_dir / "sell_feature_columns.json", {"model_version": MODEL_VERSION, "features": sell_features, "policies": list(DYNAMIC_EXIT_POLICIES)})

    y_valid = pd.to_numeric(valid_pool["entry_target"], errors="coerce").fillna(0.0)
    entry_pred = pd.to_numeric(valid_pool["entry_model_score"], errors="coerce").fillna(0.0)
    buy_valid = valid_pool[valid_pool["has_first5"].astype(int).gt(0)].copy()
    metrics: Dict[str, Any] = {
        "entry_model_mae": round(float(mean_absolute_error(y_valid, entry_pred)), 4),
        "buy_point_model_rows_validation": int(len(buy_valid)),
    }
    y_bin = (pd.to_numeric(valid_pool["max_runup_22d_pct"], errors="coerce").fillna(0.0) >= 15.0).astype(int)
    if int(y_bin.nunique()) > 1:
        metrics["entry_model_hit15_auc"] = round(float(roc_auc_score(y_bin, entry_pred)), 4)
    if not buy_valid.empty:
        y_buy = pd.to_numeric(buy_valid["first5_entry_target"], errors="coerce").fillna(0.0)
        p_buy = pd.to_numeric(buy_valid["buy_point_score"], errors="coerce").fillna(0.0)
        metrics["buy_point_model_mae"] = round(float(mean_absolute_error(y_buy, p_buy)), 4)
        y_buy_bin = (pd.to_numeric(buy_valid["max_runup_22d_pct"], errors="coerce").fillna(0.0) >= 15.0).astype(int)
        if int(y_buy_bin.nunique()) > 1:
            metrics["buy_point_hit15_auc"] = round(float(roc_auc_score(y_buy_bin, p_buy)), 4)

    best = (
        summary_df.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).head(12).to_dict(orient="records")
        if not summary_df.empty
        else []
    )
    baseline = (
        summary_df[summary_df["strategy"].eq("top1_open_baseline")]
        .sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False])
        .head(5)
        .to_dict(orient="records")
        if not summary_df.empty
        else []
    )
    summary = {
        "model_version": MODEL_VERSION,
        "config": asdict(config),
        "data": {
            "candidate_rows": int(len(pool)),
            "train_rows": int(len(train_pool)),
            "validation_rows": int(len(valid_pool)),
            "train_dates": [str(train_pool["trade_date"].min()), str(train_pool["trade_date"].max())],
            "validation_dates": [str(valid_pool["trade_date"].min()), str(valid_pool["trade_date"].max())],
            "intraday_feature_rows": int(len(intraday)),
            "sell_sample_rows": int(len(sell_samples)),
            "latest_date": str(pool["trade_date"].max()),
        },
        "metrics": metrics,
        "best_strategies": best,
        "baseline_top1_open": baseline,
        "latest_execution_top10": latest_df.head(10).to_dict(orient="records") if not latest_df.empty else [],
        "files": {
            "candidate_scores": str(out_dir / "candidate_scores.csv.gz"),
            "entry_intraday_features": str(out_dir / "entry_intraday_features.csv.gz"),
            "sell_train_samples": str(out_dir / "sell_train_samples.csv.gz"),
            "strategy_summary": str(out_dir / "execution_strategy_summary.csv"),
            "trades": str(out_dir / "execution_trades.csv"),
            "equity_curves": str(out_dir / "execution_equity_curves.csv"),
            "latest": str(out_dir / "latest_execution_candidates.csv"),
            "entry_model": str(out_dir / "entry_model.joblib"),
            "buy_point_model": str(out_dir / "buy_point_model.joblib"),
            "sell_model": str(out_dir / "sell_model.joblib"),
        },
        "caveats": [
            "22日模型仍只负责主候选排序，本实验不覆盖旧模型。",
            "买点模型使用D+1开盘和早盘5分钟信息，真实执行时必须等这些信息出现后才能触发。",
            "挂单/集合竞价L2从2026-03-02才完整，相关特征在训练集中主要作为缺失/弱特征处理，当前结论偏研究性质。",
            "动态卖点模型仍有22个交易日的成熟样本上限，22日只是回测兜底边界，不是固定离场壳。",
        ],
    }
    _json_dump(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:16000])


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Train and backtest opportunity execution models")
    parser.add_argument("--atomic-db", default=str(base.DEFAULT_ATOMIC_DB))
    parser.add_argument("--selection-db", default=str(base.DEFAULT_SELECTION_DB))
    parser.add_argument("--heat-db", default=str(base.DEFAULT_HEAT_DB))
    parser.add_argument("--opp22-dir", default=str(OPP22_DIR))
    parser.add_argument("--short-dir", default=str(SHORT_DIR))
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--start-date", default="2025-01-02")
    run.add_argument("--end-date", default="2026-05-14")
    run.add_argument("--validation-start", default="2026-03-02")
    run.add_argument("--horizon-days", type=int, default=22)
    run.add_argument("--candidate-pool-topn", type=int, default=20)
    run.add_argument("--train-sell-topn", type=int, default=5)
    run.add_argument("--initial-capital", type=float, default=1_000_000.0)
    run.add_argument("--out", default=str(OUT_DIR))
    run.set_defaults(func=run_command)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
