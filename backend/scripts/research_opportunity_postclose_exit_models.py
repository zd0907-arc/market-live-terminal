#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
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
OUT_DIR = ROOT / "data/selection/opportunity_discovery/postclose_exit_v0_1"


@dataclass(frozen=True)
class PostCloseExitConfig:
    start_date: str = "2025-01-02"
    end_date: str = "2026-05-14"
    horizon_days: int = 22
    train_exit_topn: int = 5
    initial_capital: float = 1_000_000.0
    random_state: int = 42


WINDOWS: Tuple[Tuple[str, str, str], ...] = (
    ("2026-01", "2026-01-02", "2026-01-31"),
    ("2026-02", "2026-02-01", "2026-02-28"),
    ("2026-03", "2026-03-01", "2026-03-31"),
    ("2026-04-partial", "2026-04-01", "2026-04-30"),
)


ENTRY_STRATEGIES: Tuple[Dict[str, Any], ...] = (
    {"name": "top1", "mode": "top1"},
    {"name": "top1_top2_conditional", "mode": "top1_top2_conditional"},
)


POSTCLOSE_EXIT_POLICIES: Tuple[Dict[str, Any], ...] = (
    {
        "name": "pc_hold22",
        "type": "hold22",
        "max_holding_days": 22,
    },
    {
        "name": "pc_model_th0_stop12",
        "type": "model",
        "exit_threshold": 0.0,
        "min_hold_days": 1,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_model_th3_stop12",
        "type": "model",
        "exit_threshold": 3.0,
        "min_hold_days": 1,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_model_th6_stop12",
        "type": "model",
        "exit_threshold": 6.0,
        "min_hold_days": 1,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_trail15_dd7_stop12",
        "type": "trail",
        "trailing_activate_pct": 15.0,
        "close_trailing_drawdown_pct": 7.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_trail20_dd8_stop12",
        "type": "trail",
        "trailing_activate_pct": 20.0,
        "close_trailing_drawdown_pct": 8.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_model_th3_trail15_dd8",
        "type": "model_trail",
        "exit_threshold": 3.0,
        "trailing_activate_pct": 15.0,
        "close_trailing_drawdown_pct": 8.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_model_th5_trail20_dd10",
        "type": "model_trail",
        "exit_threshold": 5.0,
        "trailing_activate_pct": 20.0,
        "close_trailing_drawdown_pct": 10.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_model_th6_guard8_stop12",
        "type": "model_guard",
        "exit_threshold": 6.0,
        "guard_threshold": 8.0,
        "min_hold_days": 1,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_model_th6_guard12_stop12",
        "type": "model_guard",
        "exit_threshold": 6.0,
        "guard_threshold": 12.0,
        "min_hold_days": 1,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
    },
    {
        "name": "pc_model_th6_guard8_noearlystop",
        "type": "model_guard",
        "exit_threshold": 6.0,
        "guard_threshold": 8.0,
        "min_hold_days": 1,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
        "stop_min_holding_days": 4,
    },
    {
        "name": "pc_model_th3_guard8_trail15",
        "type": "model_guard_trail",
        "exit_threshold": 3.0,
        "guard_threshold": 8.0,
        "trailing_activate_pct": 15.0,
        "close_trailing_drawdown_pct": 8.0,
        "min_hold_days": 2,
        "max_holding_days": 22,
        "close_stop_pct": -12.0,
        "stop_min_holding_days": 4,
    },
)


POSTCLOSE_FEATURES: Tuple[str, ...] = tuple(
    dict.fromkeys(
        list(base.HOLD_FEATURES)
        + [
            "signal_final_score",
            "entry_gap_pct",
            "entry_opportunity_score",
            "entry_max_runup_22d_pct",
            "holding_day_ratio",
            "hit10_so_far",
            "hit15_so_far",
            "hit20_so_far",
            "profit_protect_active",
            "close_stop_distance_pct",
            "peak_profit_over_15_pct",
            "peak_profit_over_20_pct",
            "close_to_entry_pct",
            "peak_close_runup_pct",
            "close_drawdown_from_peak_close_pct",
            "hot_theme_best_rank",
            "hot_theme_score",
            "hot_theme_persistence_score",
            "hot_theme_is_top10",
            "hot_theme_is_climax_hot",
            "hot_theme_is_fading",
            "signal_limit_up_like",
            "signal_broken_limit_up",
        ]
    )
)


def _json_dump(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_model(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if joblib is not None:
        joblib.dump(model, path)
        return
    raise RuntimeError("joblib is required to write post-close exit models")


def _parse_windows(raw: Optional[str]) -> List[Tuple[str, str, str]]:
    if not raw:
        return list(WINDOWS)
    out: List[Tuple[str, str, str]] = []
    for item in raw.split(","):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) != 3:
            raise ValueError(f"bad window spec: {item!r}; expected name:start:end")
        out.append((parts[0], parts[1], parts[2]))
    return out


def _score_split(
    data: pd.DataFrame,
    validation_start: str,
    validation_end: str,
    config: base.OpportunityConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, Pipeline, List[str]]:
    feature_cols = base.available_feature_columns(data, include_orderbook=False)
    train = data[pd.to_datetime(data["label_end_date"]) < pd.to_datetime(validation_start)].copy()
    valid = data[(data["trade_date"] >= validation_start) & (data["trade_date"] <= validation_end)].copy()
    train_filtered = base._apply_historical_entry_filter(train, config)
    valid_filtered = base._apply_historical_entry_filter(valid, config)
    if train_filtered.empty or valid_filtered.empty:
        raise RuntimeError(f"empty split for {validation_start}..{validation_end}")
    model = base._fit_model(train_filtered, feature_cols, config)
    for part in [train_filtered, valid_filtered]:
        part["model_score"] = model.predict(part[list(feature_cols)])
        part["rule_score"] = base._score_rule_baseline(part)
        part["final_score"] = 0.78 * part["model_score"] + 0.22 * part["rule_score"]
    return train_filtered, valid_filtered, model, feature_cols


def _fit_exit_model(samples: pd.DataFrame, random_state: int) -> Tuple[Pipeline, List[str], Dict[str, Any]]:
    if samples.empty:
        raise RuntimeError("No post-close exit samples were built")
    feature_cols = [
        col
        for col in POSTCLOSE_FEATURES
        if col in samples.columns and samples[col].replace([np.inf, -np.inf], np.nan).notna().any()
    ]
    if not feature_cols:
        raise RuntimeError("No post-close exit features are available")
    X = samples[feature_cols].replace([np.inf, -np.inf], np.nan)
    y = pd.to_numeric(samples["hold_advantage_pp"], errors="coerce").fillna(0.0).clip(-40.0, 90.0)
    weight = (
        1.0
        + (pd.to_numeric(samples["future_best_net_return_pct"], errors="coerce").fillna(0.0) >= 15.0).astype(float) * 1.0
        + (pd.to_numeric(samples["close_to_entry_pct"], errors="coerce").fillna(0.0) >= 10.0).astype(float) * 0.8
        + (pd.to_numeric(samples["hold_advantage_pp"], errors="coerce").fillna(0.0) < -3.0).astype(float) * 0.4
    )
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.052,
        max_iter=240,
        max_leaf_nodes=31,
        min_samples_leaf=45,
        l2_regularization=0.08,
        random_state=int(random_state) + 313,
    )
    pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", model),
        ]
    )
    pipe.fit(X, y, model__sample_weight=weight)
    pred = pipe.predict(X)
    metrics: Dict[str, Any] = {"train_mae_hold_advantage": round(float(mean_absolute_error(y, pred)), 4)}
    y_bin = (pd.to_numeric(samples["label_hold"], errors="coerce").fillna(0.0) > 0).astype(int)
    if int(y_bin.nunique()) > 1:
        metrics["train_hold_auc"] = round(float(roc_auc_score(y_bin, pred)), 4)
    return pipe, feature_cols, metrics


def _fit_continuation_model(samples: pd.DataFrame, random_state: int) -> Tuple[Pipeline, List[str], Dict[str, Any]]:
    if samples.empty:
        raise RuntimeError("No post-close continuation samples were built")
    feature_cols = [
        col
        for col in POSTCLOSE_FEATURES
        if col in samples.columns and samples[col].replace([np.inf, -np.inf], np.nan).notna().any()
    ]
    if not feature_cols:
        raise RuntimeError("No post-close continuation features are available")
    X = samples[feature_cols].replace([np.inf, -np.inf], np.nan)
    y = pd.to_numeric(samples["future_extra_upside_pp"], errors="coerce").fillna(0.0).clip(-20.0, 100.0)
    weight = (
        1.0
        + (pd.to_numeric(samples["max_runup_so_far_pct"], errors="coerce").fillna(0.0) >= 8.0).astype(float) * 0.8
        + (pd.to_numeric(samples["future_extra_upside_pp"], errors="coerce").fillna(0.0) >= 8.0).astype(float) * 1.4
        + (pd.to_numeric(samples["holding_days"], errors="coerce").fillna(0.0) <= 4.0).astype(float) * 0.4
    )
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.05,
        max_iter=240,
        max_leaf_nodes=31,
        min_samples_leaf=45,
        l2_regularization=0.08,
        random_state=int(random_state) + 727,
    )
    pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", model),
        ]
    )
    pipe.fit(X, y, model__sample_weight=weight)
    pred = pipe.predict(X)
    metrics: Dict[str, Any] = {"train_mae_future_extra_upside": round(float(mean_absolute_error(y, pred)), 4)}
    y_bin = (pd.to_numeric(samples["future_extra_upside_pp"], errors="coerce").fillna(0.0) >= 8.0).astype(int)
    if int(y_bin.nunique()) > 1:
        metrics["train_extra_upside8_auc"] = round(float(roc_auc_score(y_bin, pred)), 4)
    return pipe, feature_cols, metrics


def _feature_row(
    *,
    symbol: str,
    signal_date: str,
    day: pd.Series,
    entry_row: pd.Series,
    gross_entry: float,
    peak_high: float,
    peak_close: float,
    trough_low: float,
    close_hist: List[float],
    main_hist: List[float],
    super_hist: List[float],
    amount_hist: List[float],
    cum_main: float,
    cum_super: float,
    cum_amount: float,
    offset: int,
    feature_lookup: pd.DataFrame,
    horizon_days: int,
) -> Dict[str, Any]:
    trade_date = str(day.get("trade_date"))
    close_p = base._to_float(day.get("atomic_close", day.get("close", 0.0)))
    prev_close = close_hist[-2] if len(close_hist) >= 2 else gross_entry
    amount_3 = sum(amount_hist[-3:])
    row_data: Dict[str, Any] = {}
    if (symbol, trade_date) in feature_lookup.index:
        rec = feature_lookup.loc[(symbol, trade_date)]
        if isinstance(rec, pd.DataFrame):
            rec = rec.iloc[0]
        for col in POSTCLOSE_FEATURES:
            if col in rec:
                row_data[col] = base._to_float(rec.get(col))
    peak_close = max(peak_close, close_p)
    close_return = (close_p / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0
    max_runup = (peak_high / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0
    row_data.update(
        {
            "symbol": symbol,
            "signal_date": signal_date,
            "trade_date": trade_date,
            "holding_days": int(offset),
            "holding_day_ratio": float(offset) / max(float(horizon_days), 1.0),
            "gross_entry_price": round(gross_entry, 4),
            "close": round(close_p, 4),
            "unrealized_close_return_pct": close_return,
            "close_to_entry_pct": close_return,
            "max_runup_so_far_pct": max_runup,
            "drawdown_from_peak_pct": (close_p / peak_high - 1.0) * 100.0 if peak_high > 0 else 0.0,
            "max_drawdown_so_far_pct": (trough_low / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0,
            "day_return_pct": (close_p / prev_close - 1.0) * 100.0 if prev_close > 0 else 0.0,
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
            "hit10_so_far": float(max_runup >= 10.0),
            "hit15_so_far": float(max_runup >= 15.0),
            "hit20_so_far": float(max_runup >= 20.0),
            "profit_protect_active": float(max_runup >= 15.0),
            "close_stop_distance_pct": close_return - (-12.0),
            "peak_profit_over_15_pct": max(0.0, max_runup - 15.0),
            "peak_profit_over_20_pct": max(0.0, max_runup - 20.0),
            "peak_close_runup_pct": (peak_close / gross_entry - 1.0) * 100.0 if gross_entry > 0 else 0.0,
            "close_drawdown_from_peak_close_pct": (close_p / peak_close - 1.0) * 100.0 if peak_close > 0 else 0.0,
            "signal_final_score": base._to_float(entry_row.get("final_score")),
            "entry_gap_pct": base._to_float(entry_row.get("entry_gap_pct")),
            "entry_opportunity_score": base._to_float(entry_row.get("opportunity_score")),
            "entry_max_runup_22d_pct": base._to_float(entry_row.get("max_runup_22d_pct")),
        }
    )
    return row_data


def _build_postclose_exit_samples(
    entries: pd.DataFrame,
    atomic_panel: pd.DataFrame,
    feature_panel: pd.DataFrame,
    config: base.OpportunityConfig,
    *,
    score_col: str = "final_score",
    top_k: int = 5,
) -> pd.DataFrame:
    ranked = entries.sort_values(["trade_date", score_col, "symbol"], ascending=[True, False, True])
    top = ranked.groupby("trade_date", as_index=False).head(int(top_k)).copy()
    keys = [(str(row["symbol"]), str(row["trade_date"])) for _, row in top.iterrows()]
    path_map = base._future_path_map(atomic_panel, config, keys=keys)
    feature_lookup = feature_panel.set_index(["symbol", "trade_date"], drop=False)
    rows: List[Dict[str, Any]] = []
    for _, entry_row in top.iterrows():
        symbol = str(entry_row["symbol"])
        signal_date = str(entry_row["trade_date"])
        future = path_map.get((symbol, signal_date))
        if future is None or len(future) < 2:
            continue
        future = future.sort_values("trade_date").reset_index(drop=True)
        gross_entry = base._to_float(future.iloc[0].get("open"))
        if gross_entry <= 0:
            continue
        net_entry = base._apply_buy_cost(gross_entry, config)
        peak_high = gross_entry
        peak_close = gross_entry
        trough_low = gross_entry
        close_hist: List[float] = []
        main_hist: List[float] = []
        super_hist: List[float] = []
        amount_hist: List[float] = []
        cum_amount = 0.0
        cum_main = 0.0
        cum_super = 0.0
        for offset, day in enumerate(future.itertuples(index=False), start=1):
            if offset >= len(future):
                break
            day_s = pd.Series(day._asdict())
            trade_date = str(day_s.get("trade_date"))
            high_p = base._to_float(day_s.get("high"))
            low_p = base._to_float(day_s.get("low"))
            close_p = base._to_float(day_s.get("atomic_close", day_s.get("close", 0.0)))
            amount = base._to_float(day_s.get("total_amount"))
            main_net = base._to_float(day_s.get("l2_main_net_amount"))
            super_net = base._to_float(day_s.get("l2_super_net_amount"))
            if high_p <= 0 or low_p <= 0 or close_p <= 0:
                continue
            peak_high = max(peak_high, high_p)
            peak_close = max(peak_close, close_p)
            trough_low = min(trough_low, low_p)
            close_hist.append(close_p)
            main_hist.append(main_net)
            super_hist.append(super_net)
            amount_hist.append(amount)
            cum_amount += amount
            cum_main += main_net
            cum_super += super_net
            next_open = base._to_float(future.iloc[offset].get("open"), close_p)
            if next_open <= 0:
                continue
            sell_next_net_return = (base._apply_sell_cost(next_open, config) / net_entry - 1.0) * 100.0
            remaining = future.iloc[offset:].copy()
            future_best_high = float(pd.to_numeric(remaining["high"], errors="coerce").fillna(0.0).max())
            future_low = float(pd.to_numeric(remaining["low"], errors="coerce").fillna(close_p).min())
            future_close = base._to_float(remaining.iloc[-1].get("atomic_close", remaining.iloc[-1].get("close", close_p)), close_p)
            future_best_net_return = (base._apply_sell_cost(future_best_high, config) / net_entry - 1.0) * 100.0 if future_best_high > 0 else sell_next_net_return
            future_close_net_return = (base._apply_sell_cost(future_close, config) / net_entry - 1.0) * 100.0 if future_close > 0 else sell_next_net_return
            future_dd_from_close = (future_low / close_p - 1.0) * 100.0 if close_p > 0 and future_low > 0 else 0.0
            dd_penalty = max(0.0, -future_dd_from_close - 8.0) * 0.65
            giveback_penalty = max(0.0, sell_next_net_return - future_close_net_return - 8.0) * 0.25
            hold_advantage = future_best_net_return - sell_next_net_return - dd_penalty - giveback_penalty
            row = _feature_row(
                symbol=symbol,
                signal_date=signal_date,
                day=day_s,
                entry_row=entry_row,
                gross_entry=gross_entry,
                peak_high=peak_high,
                peak_close=peak_close,
                trough_low=trough_low,
                close_hist=close_hist,
                main_hist=main_hist,
                super_hist=super_hist,
                amount_hist=amount_hist,
                cum_main=cum_main,
                cum_super=cum_super,
                cum_amount=cum_amount,
                offset=offset,
                feature_lookup=feature_lookup,
                horizon_days=int(config.horizon_days),
            )
            row.update(
                {
                    "next_open": round(next_open, 4),
                    "sell_next_net_return_pct": round(float(sell_next_net_return), 4),
                    "future_best_net_return_pct": round(float(future_best_net_return), 4),
                    "future_close_net_return_pct": round(float(future_close_net_return), 4),
                    "future_dd_from_close_pct": round(float(future_dd_from_close), 4),
                    "hold_advantage_pp": round(float(np.clip(hold_advantage, -50.0, 120.0)), 4),
                    "future_extra_upside_pp": round(float(np.clip(future_best_net_return - sell_next_net_return, -30.0, 120.0)), 4),
                    "label_hold": int(hold_advantage >= 2.0),
                    "label_sell": int(hold_advantage < 0.0),
                    "entry_date": str(future.iloc[0]["trade_date"]),
                    "decision_date": trade_date,
                }
            )
            rows.append(row)
    samples = pd.DataFrame(rows)
    if samples.empty:
        return samples
    for col in list(POSTCLOSE_FEATURES) + [
        "sell_next_net_return_pct",
        "future_best_net_return_pct",
        "future_close_net_return_pct",
        "future_dd_from_close_pct",
        "hold_advantage_pp",
        "future_extra_upside_pp",
        "label_hold",
        "label_sell",
    ]:
        if col in samples.columns:
            samples[col] = pd.to_numeric(samples[col], errors="coerce").fillna(0.0)
    return samples


def _select_entries(scored: pd.DataFrame, strategy: Dict[str, Any]) -> pd.DataFrame:
    ranked = scored.sort_values(["trade_date", "final_score", "symbol"], ascending=[True, False, True]).copy()
    rows: List[pd.DataFrame] = []
    for _, day in ranked.groupby("trade_date", sort=True):
        if str(strategy["mode"]) == "top1":
            picks = day.head(1).copy()
            picks["weight"] = 0.80
        elif str(strategy["mode"]) == "top1_top2_conditional":
            picks = day.head(2).copy()
            if len(picks) >= 2:
                top1_score = base._to_float(picks.iloc[0].get("final_score"))
                top2_score = base._to_float(picks.iloc[1].get("final_score"))
                if top2_score < top1_score - 6.0:
                    picks = picks.head(1).copy()
                    picks["weight"] = 0.70
                else:
                    picks["weight"] = [0.55, 0.35]
            else:
                picks["weight"] = 0.70
        else:
            raise ValueError(f"unknown entry strategy: {strategy}")
        if not picks.empty:
            rows.append(picks)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _predict_exit(model: Pipeline, features: Sequence[str], row_data: Dict[str, Any]) -> float:
    x = pd.DataFrame([{col: row_data.get(col, 0.0) for col in features}])
    return float(model.predict(x)[0])


def _simulate_postclose_exit_trade(
    future: pd.DataFrame,
    feature_lookup: pd.DataFrame,
    exit_model: Pipeline,
    exit_features: Sequence[str],
    continuation_model: Pipeline,
    continuation_features: Sequence[str],
    config: base.OpportunityConfig,
    policy: Dict[str, Any],
    entry_row: pd.Series,
) -> Dict[str, Any]:
    if future.empty:
        return {"exit_reason": "no_future_path", "net_return_pct": 0.0, "holding_days": 0}
    future = future.sort_values("trade_date").reset_index(drop=True)
    gross_entry = base._to_float(future.iloc[0].get("open"))
    if gross_entry <= 0:
        return {"exit_reason": "bad_entry_price", "net_return_pct": 0.0, "holding_days": 0}
    net_entry = base._apply_buy_cost(gross_entry, config)
    peak_high = gross_entry
    peak_close = gross_entry
    trough_low = gross_entry
    close_hist: List[float] = []
    main_hist: List[float] = []
    super_hist: List[float] = []
    amount_hist: List[float] = []
    cum_amount = 0.0
    cum_main = 0.0
    cum_super = 0.0
    max_runup = 0.0
    max_drawdown = 0.0
    exit_price = base._to_float(future.iloc[-1].get("atomic_close", future.iloc[-1].get("close", 0.0)))
    exit_date = str(future.iloc[-1]["trade_date"])
    exit_reason = "time_exit_close"
    decision_date = ""
    exit_pred = np.nan
    continuation_pred = np.nan
    holding_days = int(len(future))
    path_predictions: List[Dict[str, Any]] = []
    max_holding_days = int(policy.get("max_holding_days", config.horizon_days))
    min_hold_days = int(policy.get("min_hold_days", 1))
    close_stop_pct = policy.get("close_stop_pct")
    exit_threshold = float(policy.get("exit_threshold", -999.0))
    trailing_activate_pct = policy.get("trailing_activate_pct")
    close_trailing_drawdown_pct = policy.get("close_trailing_drawdown_pct")
    stop_min_holding_days = int(policy.get("stop_min_holding_days", 1))
    guard_threshold = policy.get("guard_threshold")
    policy_type = str(policy.get("type", "model"))

    for offset, day in enumerate(future.itertuples(index=False), start=1):
        day_s = pd.Series(day._asdict())
        trade_date = str(day_s.get("trade_date"))
        open_p = base._to_float(day_s.get("open"))
        high_p = base._to_float(day_s.get("high"))
        low_p = base._to_float(day_s.get("low"))
        close_p = base._to_float(day_s.get("atomic_close", day_s.get("close", 0.0)))
        amount = base._to_float(day_s.get("total_amount"))
        main_net = base._to_float(day_s.get("l2_main_net_amount"))
        super_net = base._to_float(day_s.get("l2_super_net_amount"))
        if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
            continue
        peak_high = max(peak_high, high_p)
        peak_close = max(peak_close, close_p)
        trough_low = min(trough_low, low_p)
        close_hist.append(close_p)
        main_hist.append(main_net)
        super_hist.append(super_net)
        amount_hist.append(amount)
        cum_amount += amount
        cum_main += main_net
        cum_super += super_net
        max_runup = max(max_runup, (high_p / gross_entry - 1.0) * 100.0)
        max_drawdown = min(max_drawdown, (low_p / gross_entry - 1.0) * 100.0)

        if offset >= max_holding_days or offset >= len(future):
            exit_price = close_p
            exit_date = trade_date
            exit_reason = "time_exit_close"
            decision_date = trade_date
            holding_days = offset
            break

        row_data = _feature_row(
            symbol=str(entry_row["symbol"]),
            signal_date=str(entry_row["trade_date"]),
            day=day_s,
            entry_row=entry_row,
            gross_entry=gross_entry,
            peak_high=peak_high,
            peak_close=peak_close,
            trough_low=trough_low,
            close_hist=close_hist,
            main_hist=main_hist,
            super_hist=super_hist,
            amount_hist=amount_hist,
            cum_main=cum_main,
            cum_super=cum_super,
            cum_amount=cum_amount,
            offset=offset,
            feature_lookup=feature_lookup,
            horizon_days=int(config.horizon_days),
        )
        pred = _predict_exit(exit_model, exit_features, row_data)
        cont_pred = _predict_exit(continuation_model, continuation_features, row_data)
        path_predictions.append(
            {
                "trade_date": trade_date,
                "holding_days": offset,
                "pred_hold_advantage_pp": round(pred, 4),
                "pred_extra_upside_pp": round(cont_pred, 4),
            }
        )

        should_exit = False
        reason = ""
        close_return = (close_p / gross_entry - 1.0) * 100.0
        if offset >= max(min_hold_days, stop_min_holding_days) and close_stop_pct is not None and close_return <= float(close_stop_pct):
            should_exit = True
            reason = "postclose_close_stop_next_open"
        if not should_exit and policy_type in {"trail", "model_trail", "model_guard_trail"} and trailing_activate_pct is not None and close_trailing_drawdown_pct is not None:
            if max_runup >= float(trailing_activate_pct):
                close_drawdown = (close_p / peak_close - 1.0) * 100.0 if peak_close > 0 else 0.0
                if close_drawdown <= -float(close_trailing_drawdown_pct):
                    should_exit = True
                    reason = "postclose_trailing_next_open"
        if not should_exit and policy_type in {"model", "model_trail", "model_guard", "model_guard_trail"} and offset >= min_hold_days and pred < exit_threshold:
            should_exit = True
            reason = "postclose_model_next_open"
        if should_exit and guard_threshold is not None:
            guard_active = (
                cont_pred >= float(guard_threshold)
                or (offset <= 4 and cont_pred >= float(guard_threshold) * 0.65)
                or (max_runup >= 15.0 and cont_pred >= float(guard_threshold) * 0.50)
            )
            if guard_active:
                should_exit = False
                reason = ""
        if should_exit:
            next_row = future.iloc[offset]
            next_open = base._to_float(next_row.get("open"), close_p)
            exit_price = next_open if next_open > 0 else close_p
            exit_date = str(next_row["trade_date"])
            exit_reason = reason
            decision_date = trade_date
            exit_pred = pred
            continuation_pred = cont_pred
            holding_days = offset + 1
            break

    net_exit = base._apply_sell_cost(exit_price, config)
    after_exit = future[future["trade_date"].astype(str) > exit_date].copy()
    if after_exit.empty:
        best_after_net_return = (net_exit / net_entry - 1.0) * 100.0
        post_exit_missed_pp = 0.0
    else:
        best_after_high = float(pd.to_numeric(after_exit["high"], errors="coerce").fillna(0.0).max())
        best_after_net_return = (base._apply_sell_cost(best_after_high, config) / net_entry - 1.0) * 100.0 if best_after_high > 0 else 0.0
        post_exit_missed_pp = max(0.0, best_after_net_return - (net_exit / net_entry - 1.0) * 100.0)
    full_high = float(pd.to_numeric(future["high"], errors="coerce").fillna(0.0).max())
    full_mfe_net_return = (base._apply_sell_cost(full_high, config) / net_entry - 1.0) * 100.0 if full_high > 0 else 0.0
    return {
        "entry_date": str(future.iloc[0]["trade_date"]),
        "exit_date": exit_date,
        "decision_date": decision_date,
        "exit_reason": exit_reason,
        "gross_entry_price": round(gross_entry, 4),
        "net_entry_price": net_entry,
        "gross_exit_price": round(float(exit_price), 4),
        "net_exit_price": net_exit,
        "gross_return_pct": round(float((exit_price / gross_entry - 1.0) * 100.0), 4),
        "net_return_pct": round(float((net_exit / net_entry - 1.0) * 100.0), 4),
        "holding_days": int(holding_days),
        "max_runup_before_exit_pct": round(float(max_runup), 4),
        "max_drawdown_before_exit_pct": round(float(max_drawdown), 4),
        "exit_pred_hold_advantage_pp": round(float(exit_pred), 4) if not np.isnan(exit_pred) else np.nan,
        "exit_pred_extra_upside_pp": round(float(continuation_pred), 4) if not np.isnan(continuation_pred) else np.nan,
        "best_after_exit_net_return_pct": round(float(best_after_net_return), 4),
        "post_exit_missed_pp": round(float(post_exit_missed_pp), 4),
        "sold_fly_after_exit": int(post_exit_missed_pp >= 3.0),
        "severe_sold_fly_after_exit": int(post_exit_missed_pp >= 10.0),
        "full_mfe_net_return_pct": round(float(full_mfe_net_return), 4),
        "path_predictions": json.dumps(path_predictions, ensure_ascii=False),
    }


def _build_orders(
    scored: pd.DataFrame,
    atomic_panel: pd.DataFrame,
    feature_panel: pd.DataFrame,
    exit_model: Pipeline,
    exit_features: Sequence[str],
    continuation_model: Pipeline,
    continuation_features: Sequence[str],
    config: base.OpportunityConfig,
    strategy: Dict[str, Any],
    policy: Dict[str, Any],
    window: str,
) -> List[Dict[str, Any]]:
    entries = _select_entries(scored, strategy)
    if entries.empty:
        return []
    keys = [(str(row["symbol"]), str(row["trade_date"])) for _, row in entries.iterrows()]
    path_map = base._future_path_map(atomic_panel, config, keys=keys)
    feature_lookup = feature_panel.set_index(["symbol", "trade_date"], drop=False)
    orders: List[Dict[str, Any]] = []
    for _, row in entries.iterrows():
        symbol = str(row["symbol"])
        signal_date = str(row["trade_date"])
        future = path_map.get((symbol, signal_date))
        if future is None or future.empty:
            continue
        sim = _simulate_postclose_exit_trade(
            future,
            feature_lookup,
            exit_model,
            exit_features,
            continuation_model,
            continuation_features,
            config,
            policy,
            row,
        )
        if base._to_float(sim.get("gross_entry_price")) <= 0 or base._to_float(sim.get("gross_exit_price")) <= 0:
            continue
        orders.append(
            {
                "window": window,
                "strategy": str(strategy["name"]),
                "mode": str(strategy["mode"]),
                "exit_policy": str(policy["name"]),
                "trade_date": signal_date,
                "symbol": symbol,
                "weight": float(row.get("weight", 0.80)),
                "final_score": round(base._to_float(row.get("final_score")), 4),
                "max_runup_22d_pct": round(base._to_float(row.get("max_runup_22d_pct")), 4),
                "entry_gap_pct": round(base._to_float(row.get("entry_gap_pct")), 4),
                **sim,
            }
        )
    return orders


def _simulate_account(
    orders: List[Dict[str, Any]],
    atomic: pd.DataFrame,
    config: base.OpportunityConfig,
    initial_capital: float,
    *,
    scope: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    if not orders:
        return pd.DataFrame(), pd.DataFrame(), {"scope": scope, "orders": 0, "trades": 0}
    price_lookup = atomic.set_index(["symbol", "trade_date"], drop=False)
    all_dates = sorted(str(d) for d in atomic["trade_date"].unique())
    min_date = min(str(order["entry_date"]) for order in orders)
    max_date = max(str(order["exit_date"]) for order in orders)
    calendar = [d for d in all_dates if min_date <= d <= max_date]
    orders_by_entry: Dict[str, List[Dict[str, Any]]] = {}
    for order in sorted(orders, key=lambda x: (str(x["entry_date"]), str(x["trade_date"]), str(x["symbol"]))):
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
        return float(pos["shares"]) * base._apply_sell_cost(price, config) if price > 0 else float(pos["cost_cash"])

    cash = float(initial_capital)
    min_position_cash = max(20_000.0, initial_capital * 0.02)
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
                cost_cash = float(pos["cost_cash"])
                pnl = sale_cash - cost_cash
                record = dict(pos["order"])
                record.update(
                    {
                        "scope": scope,
                        "shares": int(pos["shares"]),
                        "position_cash": round(cost_cash, 2),
                        "pnl_cash": round(float(pnl), 2),
                        "equity_after": round(cash + sum(mark_position(p, current_date, "open") for p in positions if p is not pos), 2),
                        "net_return_pct": round(float(pnl / cost_cash * 100.0), 4) if cost_cash else 0.0,
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
            budget = min(cash, equity_for_sizing * float(order.get("weight", 0.80)))
            if budget < min_position_cash:
                skipped_cash += 1
                continue
            shares = math.floor(budget / float(order["net_entry_price"]) / 100.0) * 100
            if shares < 100:
                skipped_cash += 1
                continue
            cost_cash = shares * float(order["net_entry_price"])
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
                "scope": scope,
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
        return trades_df, curve_df, {"scope": scope, "orders": int(len(orders)), "trades": 0}
    equity_curve = pd.Series([float(initial_capital)] + curve_df["equity"].astype(float).tolist())
    dd = equity_curve / equity_curve.cummax() - 1.0
    returns = pd.to_numeric(trades_df.get("net_return_pct", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    missed = pd.to_numeric(trades_df.get("post_exit_missed_pp", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    summary = {
        "scope": scope,
        "orders": int(len(orders)),
        "trades": int(len(trades_df)),
        "skipped_cash": int(skipped_cash),
        "skipped_duplicate_symbol": int(skipped_duplicate),
        "final_equity": round(float(curve_df["equity"].iloc[-1]), 2),
        "total_return_pct": round(float((curve_df["equity"].iloc[-1] / initial_capital - 1.0) * 100.0), 4),
        "max_drawdown_pct": round(float(dd.min() * 100.0), 4),
        "win_rate": round(float((returns > 0).mean()), 4) if not returns.empty else 0.0,
        "avg_trade_net_return_pct": round(float(returns.mean()), 4) if not returns.empty else 0.0,
        "median_trade_net_return_pct": round(float(returns.median()), 4) if not returns.empty else 0.0,
        "avg_holding_days": round(float(pd.to_numeric(trades_df.get("holding_days", pd.Series(dtype=float)), errors="coerce").mean()), 2)
        if not trades_df.empty
        else 0.0,
        "sold_fly_after_exit_rate": round(float(pd.to_numeric(trades_df.get("sold_fly_after_exit", pd.Series(dtype=float)), errors="coerce").fillna(0.0).mean()), 4)
        if not trades_df.empty
        else 0.0,
        "severe_sold_fly_after_exit_rate": round(
            float(pd.to_numeric(trades_df.get("severe_sold_fly_after_exit", pd.Series(dtype=float)), errors="coerce").fillna(0.0).mean()), 4
        )
        if not trades_df.empty
        else 0.0,
        "avg_post_exit_missed_pp": round(float(missed.mean()), 4) if not missed.empty else 0.0,
        "max_open_positions": int(curve_df["open_positions"].max()) if "open_positions" in curve_df else 0,
        "avg_cash_pct": round(float((curve_df["cash"].astype(float) / curve_df["equity"].replace(0, np.nan).astype(float)).mean() * 100.0), 4),
        "exit_reason_counts": json.dumps(trades_df["exit_reason"].value_counts().to_dict(), ensure_ascii=False)
        if "exit_reason" in trades_df
        else "{}",
    }
    return trades_df, curve_df, summary


def run_command(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_dir = out_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    config = PostCloseExitConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        horizon_days=int(args.horizon_days),
        train_exit_topn=int(args.train_exit_topn),
        initial_capital=float(args.initial_capital),
    )
    base_config = base.OpportunityConfig(
        start_date=config.start_date,
        end_date=config.end_date,
        horizon_days=config.horizon_days,
    )
    windows = _parse_windows(args.windows)
    atomic_db = Path(args.atomic_db)
    selection_db = Path(args.selection_db)
    heat_db = Path(args.heat_db)

    print("building full opportunity dataset...", flush=True)
    data, feature_panel = base.build_dataset(base_config, atomic_db, selection_db, heat_db)
    if data.empty:
        raise RuntimeError("No labeled opportunity dataset was built")
    atomic = base.add_atomic_features(base.load_atomic_daily(config.start_date, config.end_date, atomic_db))

    all_orders: List[Dict[str, Any]] = []
    all_samples: List[pd.DataFrame] = []
    all_trades: List[pd.DataFrame] = []
    all_curves: List[pd.DataFrame] = []
    summary_rows: List[Dict[str, Any]] = []
    window_metrics: List[Dict[str, Any]] = []

    for window, validation_start, validation_end in windows:
        print(f"running post-close exit window {window} {validation_start}..{validation_end}", flush=True)
        split_config = base.OpportunityConfig(
            start_date=config.start_date,
            end_date=config.end_date,
            validation_start=validation_start,
            validation_end=validation_end,
            horizon_days=config.horizon_days,
        )
        train_scored, valid_scored, selector_model, selector_features = _score_split(data, validation_start, validation_end, split_config)
        exit_samples = _build_postclose_exit_samples(
            train_scored,
            atomic,
            feature_panel,
            split_config,
            score_col="final_score",
            top_k=config.train_exit_topn,
        )
        exit_samples["window_train_for"] = window
        exit_model, exit_features, metrics = _fit_exit_model(exit_samples, config.random_state)
        continuation_model, continuation_features, continuation_metrics = _fit_continuation_model(exit_samples, config.random_state)
        metrics.update(continuation_metrics)
        _write_model(model_dir / f"{window}_selector.joblib", selector_model)
        _write_model(model_dir / f"{window}_postclose_exit.joblib", exit_model)
        _write_model(model_dir / f"{window}_postclose_continuation.joblib", continuation_model)
        all_samples.append(exit_samples)
        metrics.update(
            {
                "window": window,
                "train_samples": int(len(exit_samples)),
                "train_dates": f"{train_scored['trade_date'].min()} ~ {train_scored['trade_date'].max()}",
                "validation_dates": f"{valid_scored['trade_date'].min()} ~ {valid_scored['trade_date'].max()}",
                "selector_features": int(len(selector_features)),
                "exit_features": int(len(exit_features)),
            }
        )
        window_metrics.append(metrics)

        for strategy in ENTRY_STRATEGIES:
            for policy in POSTCLOSE_EXIT_POLICIES:
                orders = _build_orders(
                    valid_scored,
                    atomic,
                    feature_panel,
                    exit_model,
                    exit_features,
                    continuation_model,
                    continuation_features,
                    split_config,
                    strategy,
                    policy,
                    window,
                )
                for order in orders:
                    order["selector_validation_start"] = validation_start
                    order["selector_validation_end"] = validation_end
                all_orders.extend(orders)
                scope = f"monthly:{window}:{strategy['name']}:{policy['name']}"
                trades, curve, account_summary = _simulate_account(
                    orders,
                    atomic,
                    split_config,
                    config.initial_capital,
                    scope=scope,
                )
                account_summary.update(
                    {
                        "window": window,
                        "strategy": strategy["name"],
                        "mode": strategy["mode"],
                        "exit_policy": policy["name"],
                        "validation_start": validation_start,
                        "validation_end": validation_end,
                    }
                )
                summary_rows.append(account_summary)
                if not trades.empty:
                    all_trades.append(trades)
                if not curve.empty:
                    all_curves.append(curve)

    print("running continuous account views...", flush=True)
    orders_df = pd.DataFrame(all_orders)
    if not orders_df.empty:
        for (strategy_name, policy_name), group in orders_df.groupby(["strategy", "exit_policy"], sort=True):
            orders = group.to_dict(orient="records")
            scope = f"continuous:{strategy_name}:{policy_name}"
            trades, curve, account_summary = _simulate_account(
                orders,
                atomic,
                base_config,
                config.initial_capital,
                scope=scope,
            )
            account_summary.update(
                {
                    "window": "continuous",
                    "strategy": strategy_name,
                    "mode": str(group["mode"].iloc[0]) if "mode" in group else "",
                    "exit_policy": policy_name,
                    "validation_start": windows[0][1],
                    "validation_end": windows[-1][2],
                }
            )
            summary_rows.append(account_summary)
            if not trades.empty:
                all_trades.append(trades)
            if not curve.empty:
                all_curves.append(curve)

    summary = pd.DataFrame(summary_rows)
    samples = pd.concat(all_samples, ignore_index=True, sort=False) if all_samples else pd.DataFrame()
    trades_all = pd.concat(all_trades, ignore_index=True, sort=False) if all_trades else pd.DataFrame()
    curves_all = pd.concat(all_curves, ignore_index=True, sort=False) if all_curves else pd.DataFrame()
    metrics_df = pd.DataFrame(window_metrics)

    summary.to_csv(out_dir / "postclose_exit_strategy_summary.csv", index=False)
    orders_df.to_csv(out_dir / "postclose_exit_orders.csv", index=False)
    trades_all.to_csv(out_dir / "postclose_exit_trades.csv", index=False)
    curves_all.to_csv(out_dir / "postclose_exit_equity_curves.csv", index=False)
    samples.to_csv(out_dir / "postclose_exit_train_samples.csv.gz", index=False, compression="gzip")
    metrics_df.to_csv(out_dir / "postclose_exit_window_metrics.csv", index=False)

    best_monthly = (
        summary[summary["window"].ne("continuous")]
        .sort_values(["window", "total_return_pct", "max_drawdown_pct"], ascending=[True, False, False])
        .groupby("window", as_index=False)
        .head(5)
    )
    best_continuous = summary[summary["window"].eq("continuous")].sort_values(
        ["total_return_pct", "max_drawdown_pct"], ascending=[False, False]
    )
    payload = {
        "model_version": "postclose_exit_v0_1",
        "config": asdict(config),
        "windows": [{"name": w, "start": s, "end": e} for w, s, e in windows],
        "window_metrics": window_metrics,
        "best_monthly_top5_each": best_monthly.to_dict(orient="records") if not best_monthly.empty else [],
        "best_continuous_top10": best_continuous.head(10).to_dict(orient="records") if not best_continuous.empty else [],
        "files": {
            "strategy_summary": str(out_dir / "postclose_exit_strategy_summary.csv"),
            "orders": str(out_dir / "postclose_exit_orders.csv"),
            "trades": str(out_dir / "postclose_exit_trades.csv"),
            "equity_curves": str(out_dir / "postclose_exit_equity_curves.csv"),
            "train_samples": str(out_dir / "postclose_exit_train_samples.csv.gz"),
            "window_metrics": str(out_dir / "postclose_exit_window_metrics.csv"),
        },
        "caveats": [
            "All exit decisions use post-close features only and execute at the next trading day's open.",
            "The model is trained from 22-trading-day labeled paths, so April remains partial with only mature labels through early April.",
            "post_exit_missed_pp is still an upper-bound audit metric because it uses later daily highs inside the labeled window.",
        ],
    }
    _json_dump(out_dir / "summary.json", payload)
    print("=== continuous top10 ===")
    print(
        best_continuous[
            [
                "strategy",
                "exit_policy",
                "trades",
                "total_return_pct",
                "max_drawdown_pct",
                "win_rate",
                "avg_holding_days",
                "sold_fly_after_exit_rate",
                "avg_post_exit_missed_pp",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )
    print("=== monthly best ===")
    print(
        best_monthly[
            [
                "window",
                "strategy",
                "exit_policy",
                "trades",
                "total_return_pct",
                "max_drawdown_pct",
                "win_rate",
                "avg_holding_days",
                "sold_fly_after_exit_rate",
                "avg_post_exit_missed_pp",
            ]
        ]
        .to_string(index=False)
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Train and backtest post-close exit models for opportunity discovery")
    parser.add_argument("--atomic-db", default=str(base.DEFAULT_ATOMIC_DB))
    parser.add_argument("--selection-db", default=str(base.DEFAULT_SELECTION_DB))
    parser.add_argument("--heat-db", default=str(base.DEFAULT_HEAT_DB))
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run post-close exit model research")
    run.add_argument("--start-date", default="2025-01-02")
    run.add_argument("--end-date", default="2026-05-14")
    run.add_argument("--horizon-days", type=int, default=22)
    run.add_argument("--train-exit-topn", type=int, default=5)
    run.add_argument("--initial-capital", type=float, default=1_000_000.0)
    run.add_argument("--windows", default=None, help="Comma list: name:start:end,name:start:end")
    run.add_argument("--out", default=str(OUT_DIR))
    run.set_defaults(func=run_command)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
