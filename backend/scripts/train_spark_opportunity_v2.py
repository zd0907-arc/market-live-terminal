#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pickle
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import joblib
except Exception:  # pragma: no cover
    joblib = None


ROOT = Path(__file__).resolve().parents[2]
MODEL_VERSION = "2.0"
ARTIFACT_VERSION = "spark_opportunity_v2_0"
SOURCE_ID = "spark_opportunity_selector"
SOURCE_NAME = "星火机会模型 2.0"
OUT_DIR = ROOT / "data/selection/models" / SOURCE_ID / MODEL_VERSION

DEFAULT_TRAIN_DB = Path("/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_v2_2026_train.db")
DEFAULT_MAY_DB = Path("/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_v2_may.db")
DEFAULT_STOCK_SECTOR_DB = Path("/Users/dong/Desktop/AIGC/market-data/market_heat/stock_sector_map.db")

FEATURE_TABLE = "model_feature_daily_v1"
SHAPE_TABLE = "model_feature_intraday_shape_v1"
LABEL_TABLE = "model_label_forward_return_v1"

EXCLUDE_FEATURES = {
    "symbol",
    "trade_date",
    "feature_version",
    "name",
    "board_type",
    "risk_flag_type",
    "limit_state_label",
    "first_touch_limit_up_min",
    "last_touch_limit_up_min",
    "build_run_id",
    "created_at",
    "entry_date",
    "entry_open",
    "entry_gap_pct",
    "entry_buyable",
    "label_end_date",
    "label_complete_asof_date",
    "horizon_days",
    "signal_close",
    "entry_block_reason",
    "max_high",
    "min_low",
    "exit_close",
    "max_runup_pct",
    "max_drawdown_pct",
    "close_return_pct",
    "hit_5pct",
    "hit_8pct",
    "hit_10pct",
    "hit_15pct",
    "hit_20pct",
    "first_hit_8pct_day",
    "first_hit_15pct_day",
    "worst_before_first_hit_15pct",
}

IDENTITY_COLUMNS = [
    "symbol",
    "trade_date",
    "name",
    "board_type",
    "risk_flag_type",
    "close",
    "return_1d_pct",
    "return_5d_pct",
    "return_20d_pct",
    "amount_yi",
    "l2_main_net_ratio",
    "active_buy_strength",
    "hot_theme_best_rank",
    "hot_theme_score",
    "market_advancer_ratio",
    "market_limit_up_count",
    "touch_limit_up",
    "is_limit_up_close",
    "broken_limit_up",
]


@dataclass(frozen=True)
class V2Config:
    train_db: str
    may_db: str
    train_start: str = "2026-01-05"
    train_cutoff_complete_before: str = "2026-04-01"
    validation_start: str = "2026-04-01"
    validation_end: str = "2026-04-09"
    may_start: str = "2026-05-06"
    may_end: str = "2026-05-18"
    stock_sector_db: str = str(DEFAULT_STOCK_SECTOR_DB)
    source_version: str = MODEL_VERSION
    artifact_version: str = ARTIFACT_VERSION
    random_state: int = 42
    min_amount_yi: float = 0.8
    max_return_20d_pct: float = 95.0
    max_gap_up_pct: float = 6.8
    max_gap_down_pct: float = -5.5
    buy_slippage_bp: float = 15.0
    sell_slippage_bp: float = 15.0
    round_trip_fee_bp: float = 20.0


def _connect_ro(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def _json_dump(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_model(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if joblib is not None:
        joblib.dump(model, path)
        return
    with path.open("wb") as f:
        pickle.dump(model, f)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _apply_buy_cost(price: float, config: V2Config) -> float:
    return float(price) * (1.0 + float(config.buy_slippage_bp) / 10_000.0 + float(config.round_trip_fee_bp) / 20_000.0)


def _apply_sell_cost(price: float, config: V2Config) -> float:
    return float(price) * (1.0 - float(config.sell_slippage_bp) / 10_000.0 - float(config.round_trip_fee_bp) / 20_000.0)


def _column_names(conn: sqlite3.Connection, table: str) -> List[str]:
    return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _numeric_feature_columns(df: pd.DataFrame) -> List[str]:
    blocked = set(EXCLUDE_FEATURES)
    out: List[str] = []
    for col in df.columns:
        if col in blocked or col.endswith("_time") or col.endswith("_at"):
            continue
        if col in IDENTITY_COLUMNS:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            if df[col].replace([np.inf, -np.inf], np.nan).notna().any():
                out.append(col)
    return out


def _available_feature_columns(df: pd.DataFrame) -> List[str]:
    return [
        col
        for col in _numeric_feature_columns(df)
        if df[col].replace([np.inf, -np.inf], np.nan).notna().any()
    ]


def _load_feature_rows(db_path: Path, start: str, end: str) -> pd.DataFrame:
    with _connect_ro(db_path) as conn:
        feature_cols = _column_names(conn, FEATURE_TABLE)
        shape_cols = _column_names(conn, SHAPE_TABLE)
        select_f = ", ".join(f"f.{col}" for col in feature_cols)
        shape_keep = [
            col
            for col in shape_cols
            if col not in {"symbol", "trade_date", "feature_version", "build_run_id", "created_at", "first_bar_time", "last_bar_time"}
        ]
        select_s = ", ".join(f"s.{col} AS shape_{col}" for col in shape_keep)
        sql = f"""
            SELECT {select_f}{', ' + select_s if select_s else ''}
            FROM {FEATURE_TABLE} AS f
            LEFT JOIN {SHAPE_TABLE} AS s
              ON s.symbol = f.symbol
             AND s.trade_date = f.trade_date
             AND s.feature_version = f.feature_version
            WHERE f.trade_date >= ? AND f.trade_date <= ?
        """
        df = pd.read_sql_query(sql, conn, params=[start, end])
    if df.empty:
        return df
    df["symbol"] = df["symbol"].astype(str).str.lower()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    for col in df.columns:
        if col in {"symbol", "trade_date", "name", "board_type", "risk_flag_type", "limit_state_label"}:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _load_name_map(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        with _connect_ro(path) as conn:
            rows = conn.execute(
                """
                SELECT lower(symbol) AS symbol, name
                FROM stock_sector_memberships
                WHERE name IS NOT NULL AND name != ''
                ORDER BY fetched_at DESC
                """
            ).fetchall()
    except Exception:
        return {}
    names: Dict[str, str] = {}
    for row in rows:
        symbol = str(row["symbol"] or "").lower()
        name = str(row["name"] or "").strip()
        if symbol and name and name.lower() not in {symbol, "nan", "none", "null"} and symbol not in names:
            names[symbol] = name
    return names


def _apply_names(df: pd.DataFrame, names: Dict[str, str]) -> pd.DataFrame:
    if df.empty or not names:
        return df
    out = df.copy()
    mapped = out["symbol"].astype(str).str.lower().map(names)
    if "name" not in out.columns:
        out["name"] = mapped
    else:
        current = out["name"].astype(str)
        bad = out["name"].isna() | current.str.lower().isin({"nan", "none", "null", ""}) | current.eq(out["symbol"].astype(str))
        out.loc[bad, "name"] = mapped.loc[bad]
    return out


def _load_labeled(db_path: Path, horizon_days: int, start: str, end: str) -> pd.DataFrame:
    features = _load_feature_rows(db_path, start, end)
    if features.empty:
        return features
    with _connect_ro(db_path) as conn:
        labels = pd.read_sql_query(
            f"""
            SELECT *
            FROM {LABEL_TABLE}
            WHERE horizon_days = ?
              AND trade_date >= ?
              AND trade_date <= ?
            """,
            conn,
            params=[int(horizon_days), start, end],
        )
    if labels.empty:
        return pd.DataFrame()
    labels["symbol"] = labels["symbol"].astype(str).str.lower()
    labels["trade_date"] = pd.to_datetime(labels["trade_date"]).dt.strftime("%Y-%m-%d")
    data = features.merge(labels, on=["symbol", "trade_date"], how="inner", suffixes=("", "_label"))
    return _apply_entry_filter(data)


def _apply_entry_filter(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out = out[out["risk_flag_type"].fillna("normal").eq("normal")].copy()
    out = out[pd.to_numeric(out["entry_buyable"], errors="coerce").fillna(0).astype(int).eq(1)].copy()
    out = out[pd.to_numeric(out["entry_gap_pct"], errors="coerce").fillna(0.0).between(-5.5, 6.8)].copy()
    out = out[pd.to_numeric(out["amount_yi"], errors="coerce").fillna(0.0) >= 0.8].copy()
    out = out[pd.to_numeric(out["return_20d_pct"], errors="coerce").fillna(0.0) <= 95.0].copy()
    return out


def _opportunity_target(df: pd.DataFrame, horizon_days: int) -> pd.Series:
    mfe = pd.to_numeric(df["max_runup_pct"], errors="coerce").fillna(0.0)
    mdd = pd.to_numeric(df["max_drawdown_pct"], errors="coerce").fillna(0.0)
    gap = pd.to_numeric(df["entry_gap_pct"], errors="coerce").fillna(0.0)
    worst_to_15 = pd.to_numeric(df.get("worst_before_first_hit_15pct", 0.0), errors="coerce").fillna(0.0)
    if int(horizon_days) <= 5:
        speed_penalty = pd.to_numeric(df.get("first_hit_8pct_day", 0), errors="coerce").fillna(0.0).clip(lower=0.0) * 0.45
        target = mfe - np.maximum(0.0, -mdd - 5.0) * 0.85 - np.maximum(0.0, gap - 3.0) * 1.2 - speed_penalty
        return target.clip(-35.0, 60.0)
    target = (
        mfe
        - np.maximum(0.0, -mdd - 12.0) * 0.22
        - np.maximum(0.0, -worst_to_15 - 7.0) * 0.75
        - np.maximum(0.0, gap - 3.5) * 1.4
    )
    return target.clip(-45.0, 90.0)


def _fit_regressor(train: pd.DataFrame, features: Sequence[str], target: pd.Series, random_state: int) -> Pipeline:
    X = train[list(features)].replace([np.inf, -np.inf], np.nan)
    y = pd.to_numeric(target, errors="coerce").fillna(0.0)
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.052,
        max_iter=240,
        max_leaf_nodes=31,
        min_samples_leaf=40,
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
    weight = 1.0 + (pd.to_numeric(train["max_runup_pct"], errors="coerce").fillna(0.0) >= 15.0).astype(float) * 1.2
    pipe.fit(X, y, model__sample_weight=weight)
    return pipe


def _score(model: Pipeline, df: pd.DataFrame, features: Sequence[str]) -> np.ndarray:
    work = df.copy()
    for col in features:
        if col not in work.columns:
            work[col] = 0.0
    return model.predict(work[list(features)].replace([np.inf, -np.inf], np.nan))


def _rule_score(df: pd.DataFrame) -> pd.Series:
    def norm(col: str, low: float, high: float) -> pd.Series:
        values = pd.to_numeric(df.get(col, 0.0), errors="coerce").fillna(0.0)
        return ((values - low) / (high - low)).clip(0.0, 1.0) * 100.0

    hot_rank = pd.to_numeric(df.get("hot_theme_best_rank", 999.0), errors="coerce").fillna(999.0)
    return (
        0.13 * norm("breakout_vs_prev20_high_pct", -2, 6)
        + 0.11 * norm("price_position_20d", 0.25, 0.88)
        + 0.15 * norm("l2_main_net_ratio", -0.02, 0.06)
        + 0.10 * norm("l2_super_net_ratio", -0.01, 0.04)
        + 0.12 * norm("active_buy_strength", -1.0, 8.0)
        + 0.10 * norm("amount_ratio_20d", 0.8, 2.6)
        + 0.08 * norm("market_advancer_ratio", 0.35, 0.65)
        + 0.06 * ((1000.0 - hot_rank).clip(0.0, 1000.0) / 1000.0 * 100.0)
        - 0.08 * norm("return_20d_pct", 45, 100)
        - 0.06 * norm("broken_limit_up", 0, 1)
    ).fillna(0.0)


def _rank_daily(df: pd.DataFrame, score_col: str, top_ks: Sequence[int] = (1, 2, 3, 5, 10)) -> Dict[str, Any]:
    ranked = df.sort_values(["trade_date", score_col, "symbol"], ascending=[True, False, True]).copy()
    rows: List[Dict[str, Any]] = []
    daily: List[Dict[str, Any]] = []
    for k in top_ks:
        picks = ranked.groupby("trade_date", as_index=False).head(int(k)).copy()
        if picks.empty:
            continue
        mfe = pd.to_numeric(picks["max_runup_pct"], errors="coerce").fillna(0.0)
        mdd = pd.to_numeric(picks["max_drawdown_pct"], errors="coerce").fillna(0.0)
        close_ret = pd.to_numeric(picks["close_return_pct"], errors="coerce").fillna(0.0)
        row = {
            "top_k": int(k),
            "days": int(picks["trade_date"].nunique()),
            "picks": int(len(picks)),
            "avg_max_runup_pct": round(float(mfe.mean()), 4),
            "median_max_runup_pct": round(float(mfe.median()), 4),
            "avg_close_return_pct": round(float(close_ret.mean()), 4),
            "median_close_return_pct": round(float(close_ret.median()), 4),
            "avg_max_drawdown_pct": round(float(mdd.mean()), 4),
            "hit5_rate": round(float((mfe >= 5.0).mean()), 4),
            "hit8_rate": round(float((mfe >= 8.0).mean()), 4),
            "hit10_rate": round(float((mfe >= 10.0).mean()), 4),
            "hit15_rate": round(float((mfe >= 15.0).mean()), 4),
            "hit20_rate": round(float((mfe >= 20.0).mean()), 4),
            "avg_entry_gap_pct": round(float(pd.to_numeric(picks["entry_gap_pct"], errors="coerce").fillna(0.0).mean()), 4),
        }
        rows.append(row)
    top3 = ranked.groupby("trade_date", as_index=False).head(3)
    for date, g in top3.groupby("trade_date", sort=True):
        daily.append(
            {
                "trade_date": str(date),
                "symbols": ",".join(g["symbol"].astype(str).tolist()),
                "names": ",".join(g.get("name", g["symbol"]).astype(str).tolist()),
                "best_mfe_pct": round(float(pd.to_numeric(g["max_runup_pct"], errors="coerce").fillna(0.0).max()), 4),
                "avg_mfe_pct": round(float(pd.to_numeric(g["max_runup_pct"], errors="coerce").fillna(0.0).mean()), 4),
                "hit15_count": int((pd.to_numeric(g["max_runup_pct"], errors="coerce").fillna(0.0) >= 15.0).sum()),
            }
        )
    return {"summary": rows, "daily": daily}


def _simulate_policy(picks: pd.DataFrame, target_profit_pct: float, stop_loss_pct: Optional[float], horizon_days: int, config: V2Config) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, row in picks.iterrows():
        entry = _safe_float(row.get("entry_open"))
        if entry <= 0:
            continue
        mfe = _safe_float(row.get("max_runup_pct"))
        mdd = _safe_float(row.get("max_drawdown_pct"))
        close_ret = _safe_float(row.get("close_return_pct"))
        gross_ret = close_ret
        reason = f"time_exit_day{horizon_days}"
        if stop_loss_pct is not None and mdd <= float(stop_loss_pct) and mfe >= target_profit_pct:
            gross_ret = float(stop_loss_pct)
            reason = "stop_loss_same_window"
        elif stop_loss_pct is not None and mdd <= float(stop_loss_pct):
            gross_ret = float(stop_loss_pct)
            reason = "stop_loss"
        elif mfe >= target_profit_pct:
            gross_ret = float(target_profit_pct)
            reason = "take_profit"
        net_entry = _apply_buy_cost(entry, config)
        gross_exit = entry * (1.0 + gross_ret / 100.0)
        net_exit = _apply_sell_cost(gross_exit, config)
        rows.append(
            {
                "trade_date": row["trade_date"],
                "entry_date": row.get("entry_date"),
                "symbol": row["symbol"],
                "name": row.get("name", row["symbol"]),
                "gross_entry_price": round(entry, 4),
                "gross_exit_price": round(gross_exit, 4),
                "gross_return_pct": round(float(gross_ret), 4),
                "net_return_pct": round(float((net_exit / net_entry - 1.0) * 100.0), 4),
                "exit_reason": reason,
                "max_runup_pct": round(float(mfe), 4),
                "max_drawdown_pct": round(float(mdd), 4),
                "close_return_pct": round(float(close_ret), 4),
            }
        )
    return pd.DataFrame(rows)


def _policy_summary(scored: pd.DataFrame, score_col: str, horizon_days: int, config: V2Config) -> Tuple[pd.DataFrame, pd.DataFrame]:
    ranked = scored.sort_values(["trade_date", score_col, "symbol"], ascending=[True, False, True]).copy()
    top1 = ranked.groupby("trade_date", as_index=False).head(1).copy()
    policies = [
        ("tp8_else_time", 8.0, None),
        ("tp8_sl6_else_time", 8.0, -6.0),
        ("tp15_else_time", 15.0, None),
        ("tp15_sl10_else_time", 15.0, -10.0),
    ]
    parts: List[pd.DataFrame] = []
    summary: List[Dict[str, Any]] = []
    for name, target, stop in policies:
        trades = _simulate_policy(top1, target, stop, horizon_days, config)
        if trades.empty:
            continue
        trades["policy"] = name
        returns = pd.to_numeric(trades["net_return_pct"], errors="coerce").fillna(0.0)
        equity = (1.0 + returns / 100.0).cumprod()
        dd = equity / equity.cummax() - 1.0
        summary.append(
            {
                "policy": name,
                "horizon_days": int(horizon_days),
                "trades": int(len(trades)),
                "win_rate": round(float((returns > 0).mean()), 4),
                "avg_net_return_pct": round(float(returns.mean()), 4),
                "median_net_return_pct": round(float(returns.median()), 4),
                "compound_equal_weight_pct": round(float((equity.iloc[-1] - 1.0) * 100.0), 4),
                "max_drawdown_equal_weight_pct": round(float(dd.min() * 100.0), 4),
                "take_profit_rate": round(float(trades["exit_reason"].eq("take_profit").mean()), 4),
                "stop_loss_rate": round(float(trades["exit_reason"].str.contains("stop_loss").mean()), 4),
            }
        )
        parts.append(trades)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(), pd.DataFrame(summary)


def _feature_importance(train: pd.DataFrame, features: Sequence[str], target: pd.Series, random_state: int) -> pd.DataFrame:
    sample = train.sample(n=min(60_000, len(train)), random_state=int(random_state)) if len(train) > 60_000 else train
    y = pd.to_numeric(target.loc[sample.index], errors="coerce").fillna(0.0)
    X = sample[list(features)].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    rf = RandomForestRegressor(
        n_estimators=60,
        max_depth=7,
        min_samples_leaf=80,
        max_features="sqrt",
        n_jobs=-1,
        random_state=int(random_state),
    )
    rf.fit(X, y)
    return pd.DataFrame({"feature": list(features), "importance": rf.feature_importances_}).sort_values("importance", ascending=False)


def _latest_candidates(features: pd.DataFrame, model22: Pipeline, model5: Pipeline, feature_cols: Sequence[str], config: V2Config) -> pd.DataFrame:
    latest_date = str(features["trade_date"].max())
    latest = features[features["trade_date"].astype(str).eq(latest_date)].copy()
    latest = latest[latest["risk_flag_type"].fillna("normal").eq("normal")].copy()
    latest = latest[pd.to_numeric(latest["amount_yi"], errors="coerce").fillna(0.0) >= float(config.min_amount_yi)].copy()
    latest = latest[pd.to_numeric(latest["return_20d_pct"], errors="coerce").fillna(0.0) <= float(config.max_return_20d_pct)].copy()
    if latest.empty:
        return latest
    feature_cols22, feature_cols5 = feature_cols
    latest["score_22_model"] = _score(model22, latest, feature_cols22)
    latest["score_h5_model"] = _score(model5, latest, feature_cols5)
    latest["rule_score"] = _rule_score(latest)
    latest["score_22"] = 0.78 * latest["score_22_model"] + 0.22 * latest["rule_score"]
    latest["score_h5"] = 0.78 * latest["score_h5_model"] + 0.22 * latest["rule_score"]
    latest["fusion_score"] = 0.72 * latest["score_22"] + 0.28 * latest["score_h5"]
    latest["operability_penalty"] = (
        pd.to_numeric(latest.get("is_limit_up_close", 0), errors="coerce").fillna(0.0) * 9.0
        + pd.to_numeric(latest.get("return_20d_pct", 0), errors="coerce").fillna(0.0).sub(70.0).clip(lower=0.0) / 25.0 * 7.0
        + pd.to_numeric(latest.get("broken_limit_up", 0), errors="coerce").fillna(0.0) * 4.0
    )
    latest["action_score"] = latest["fusion_score"] - latest["operability_penalty"]
    latest = latest.sort_values(["action_score", "symbol"], ascending=[False, True]).copy()
    latest["rank"] = np.arange(1, len(latest) + 1)
    keep = [
        "trade_date",
        "symbol",
        "name",
        "rank",
        "action_score",
        "fusion_score",
        "score_22",
        "score_h5",
        "rule_score",
        "close",
        "return_1d_pct",
        "return_5d_pct",
        "return_20d_pct",
        "amount_yi",
        "l2_main_net_ratio",
        "active_buy_strength",
        "hot_theme_best_rank",
        "hot_theme_score",
        "market_advancer_ratio",
        "market_limit_up_count",
        "is_limit_up_close",
        "broken_limit_up",
    ]
    return latest[[col for col in keep if col in latest.columns]].head(80)


def _standard_candidates_json(latest: pd.DataFrame) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for _, row in latest.head(30).iterrows():
        risk_tags: List[str] = []
        if _safe_float(row.get("is_limit_up_close")) > 0:
            risk_tags.append("信号日涨停，次日高开接力风险")
        if _safe_float(row.get("return_20d_pct")) >= 70:
            risk_tags.append("20日涨幅过热")
        if _safe_float(row.get("broken_limit_up")) > 0:
            risk_tags.append("信号日炸板")
        rows.append(
            {
                "trade_date": str(row["trade_date"]),
                "symbol": str(row["symbol"]),
                "name": str(row.get("name") or row["symbol"]),
                "source_id": SOURCE_ID,
                "source_name": SOURCE_NAME,
                "source_type": "model",
                "source_version": MODEL_VERSION,
                "artifact_version": ARTIFACT_VERSION,
                "rank": int(row["rank"]),
                "score": round(_safe_float(row.get("action_score")), 6),
                "score_scale": "raw",
                "horizon": "22d+5d",
                "suggested_action": "candidate_buy" if not risk_tags else "watch",
                "action_label": "明日可买" if not risk_tags else "观察",
                "entry_allowed": not bool(risk_tags),
                "buy_rule": "次日开盘高开不超过6.8%，且不接近涨停/一字板才考虑",
                "reason_summary": "22日机会分与5日短线确认分共同靠前",
                "risk_tags": risk_tags,
                "entry_block_reasons": [],
                "explain_factors": {
                    "fusion_score": _safe_float(row.get("fusion_score")),
                    "score_22": _safe_float(row.get("score_22")),
                    "score_h5": _safe_float(row.get("score_h5")),
                    "rule_score": _safe_float(row.get("rule_score")),
                    "l2_main_net_ratio": _safe_float(row.get("l2_main_net_ratio")),
                    "active_buy_strength": _safe_float(row.get("active_buy_strength")),
                    "hot_theme_best_rank": _safe_float(row.get("hot_theme_best_rank"), 999.0),
                    "market_advancer_ratio": _safe_float(row.get("market_advancer_ratio")),
                },
                "raw_payload": {
                    "close": _safe_float(row.get("close")),
                    "return_5d_pct": _safe_float(row.get("return_5d_pct")),
                    "return_20d_pct": _safe_float(row.get("return_20d_pct")),
                },
            }
        )
    return rows


def _train_and_evaluate(config: V2Config, out_dir: Path) -> Dict[str, Any]:
    names = _load_name_map(Path(config.stock_sector_db))
    train22_all = _load_labeled(Path(config.train_db), 22, config.train_start, config.validation_end)
    train22_all = _apply_names(train22_all, names)
    train22 = train22_all[pd.to_datetime(train22_all["label_complete_asof_date"]) < pd.to_datetime(config.train_cutoff_complete_before)].copy()
    valid22 = train22_all[(train22_all["trade_date"] >= config.validation_start) & (train22_all["trade_date"] <= config.validation_end)].copy()
    if train22.empty or valid22.empty:
        raise RuntimeError("22d train/validation split is empty")

    train5 = _load_labeled(Path(config.train_db), 5, config.train_start, "2026-04-17")
    train5 = _apply_names(train5, names)
    may5 = _load_labeled(Path(config.may_db), 5, config.may_start, config.may_end)
    may5 = _apply_names(may5, names)
    if train5.empty or may5.empty:
        raise RuntimeError("5d train/may validation split is empty")

    feature_cols22 = _available_feature_columns(train22)
    feature_cols5 = _available_feature_columns(train5)
    if not feature_cols22 or not feature_cols5:
        raise RuntimeError("No safe feature columns are available")
    target22 = _opportunity_target(train22, 22)
    model22 = _fit_regressor(train22, feature_cols22, target22, config.random_state)
    target5 = _opportunity_target(train5, 5)
    model5 = _fit_regressor(train5, feature_cols5, target5, config.random_state + 5)

    for df, model, features, prefix in [
        (train22, model22, feature_cols22, "score22"),
        (valid22, model22, feature_cols22, "score22"),
        (may5, model5, feature_cols5, "score5"),
    ]:
        df[prefix + "_model"] = _score(model, df, features)
        df["rule_score"] = _rule_score(df)
        df["final_score"] = 0.78 * df[prefix + "_model"] + 0.22 * df["rule_score"]

    valid22_eval = _rank_daily(valid22, "final_score")
    may5_eval = _rank_daily(may5, "final_score")
    valid22_trades, valid22_policy = _policy_summary(valid22, "final_score", 22, config)
    may5_trades, may5_policy = _policy_summary(may5, "final_score", 5, config)

    latest_features = _load_feature_rows(Path(config.may_db), config.may_start, config.may_end)
    latest_features = _apply_names(latest_features, names)
    latest = _latest_candidates(latest_features, model22, model5, (feature_cols22, feature_cols5), config)
    top_features = _feature_importance(train22, feature_cols22, target22, config.random_state).head(40)

    out_dir.mkdir(parents=True, exist_ok=True)
    valid22.sort_values(["trade_date", "final_score"], ascending=[True, False]).groupby("trade_date").head(20).to_csv(
        out_dir / "validation_22d_topk.csv", index=False
    )
    may5.sort_values(["trade_date", "final_score"], ascending=[True, False]).groupby("trade_date").head(20).to_csv(
        out_dir / "validation_5d_may_topk.csv", index=False
    )
    valid22_trades.to_csv(out_dir / "validation_22d_policy_trades.csv", index=False)
    may5_trades.to_csv(out_dir / "validation_5d_may_policy_trades.csv", index=False)
    valid22_policy.to_csv(out_dir / "validation_22d_policy_summary.csv", index=False)
    may5_policy.to_csv(out_dir / "validation_5d_may_policy_summary.csv", index=False)
    latest.to_csv(out_dir / "latest_candidates.csv", index=False)
    top_features.to_csv(out_dir / "feature_importance_proxy.csv", index=False)
    _write_model(out_dir / "model_22d.joblib", model22)
    _write_model(out_dir / "model_5d.joblib", model5)
    _json_dump(
        out_dir / "feature_columns.json",
        {
            "model_version": MODEL_VERSION,
            "artifact_version": ARTIFACT_VERSION,
            "features_22d": feature_cols22,
            "features_5d": feature_cols5,
        },
    )
    _json_dump(out_dir / "sample_candidates_2026-05-18.json", {"candidates": _standard_candidates_json(latest)})

    def auc_payload(df: pd.DataFrame, pred_col: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        pred = pd.to_numeric(df[pred_col], errors="coerce").fillna(0.0)
        for threshold in [5.0, 8.0, 10.0, 15.0, 20.0]:
            y = (pd.to_numeric(df["max_runup_pct"], errors="coerce").fillna(0.0) >= threshold).astype(int)
            if int(y.nunique()) > 1:
                out[f"hit{int(threshold)}_auc"] = round(float(roc_auc_score(y, pred)), 4)
        return out

    summary = {
        "model_version": MODEL_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "config": asdict(config),
        "data": {
            "train22_rows": int(len(train22)),
            "train22_dates": [str(train22["trade_date"].min()), str(train22["trade_date"].max())],
            "valid22_rows": int(len(valid22)),
            "valid22_dates": [str(valid22["trade_date"].min()), str(valid22["trade_date"].max())],
            "train5_rows": int(len(train5)),
            "train5_dates": [str(train5["trade_date"].min()), str(train5["trade_date"].max())],
            "may5_rows": int(len(may5)),
            "may5_dates": [str(may5["trade_date"].min()), str(may5["trade_date"].max())],
            "feature_count_22d": int(len(feature_cols22)),
            "feature_count_5d": int(len(feature_cols5)),
            "latest_candidate_date": str(latest["trade_date"].max()) if not latest.empty else None,
            "name_map_rows": int(len(names)),
        },
        "metrics": {
            "valid22_mae": round(float(mean_absolute_error(_opportunity_target(valid22, 22), valid22["score22_model"])), 4),
            **auc_payload(valid22, "score22_model"),
            "valid22_topk": valid22_eval["summary"],
            "valid22_daily_top3": valid22_eval["daily"],
            "valid22_policy_summary": valid22_policy.to_dict(orient="records"),
            "may5_mae": round(float(mean_absolute_error(_opportunity_target(may5, 5), may5["score5_model"])), 4),
            **{f"may5_{k}": v for k, v in auc_payload(may5, "score5_model").items()},
            "may5_topk": may5_eval["summary"],
            "may5_daily_top3": may5_eval["daily"],
            "may5_policy_summary": may5_policy.to_dict(orient="records"),
        },
        "top_features_proxy": top_features.to_dict(orient="records"),
        "latest_candidates_top10": latest.head(10).to_dict(orient="records") if not latest.empty else [],
        "caveats": [
            "本次 2.0 只使用 2026 年已跑出的数据，样本短，不能作为投产结论。",
            "22日验证只到 2026-04-09，因为 5 月上半月没有成熟 22 日标签。",
            "5月只做 5 日短线验证和最新候选前推观察。",
            "指数字段缺失，csi1000 相关字段暂为空；主题热度 2026-05 个股 heat 为空。",
        ],
        "files": {
            "model_22d": str(out_dir / "model_22d.joblib"),
            "model_5d": str(out_dir / "model_5d.joblib"),
            "feature_columns": str(out_dir / "feature_columns.json"),
            "latest_candidates": str(out_dir / "latest_candidates.csv"),
            "sample_candidates": str(out_dir / "sample_candidates_2026-05-18.json"),
        },
    }
    _json_dump(out_dir / "backtest_summary.json", summary)
    _json_dump(
        out_dir / "source_manifest.json",
        {
            "source_id": SOURCE_ID,
            "source_name": SOURCE_NAME,
            "source_type": "model",
            "source_version": MODEL_VERSION,
            "artifact_version": ARTIFACT_VERSION,
            "package_id": f"{SOURCE_ID}@{MODEL_VERSION}",
            "horizon": "22d+5d",
            "status": "research_only",
            "artifact_paths": {
                "model_22d": "model_22d.joblib",
                "model_5d": "model_5d.joblib",
                "feature_columns": "feature_columns.json",
                "backtest_summary": "backtest_summary.json",
                "latest_candidates": "latest_candidates.csv",
                "sample_candidates": "sample_candidates_2026-05-18.json",
            },
            "train_start_date": str(train22["trade_date"].min()),
            "train_end_date": str(train22["trade_date"].max()),
            "label_definition": "D日盘后信号，D+1开盘买入；22日模型预测未来22交易日冲高机会，5日模型做短线确认。",
            "data_sources": [config.train_db, config.may_db],
            "name_source": config.stock_sector_db,
            "point_in_time_safe": True,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    return summary


def run_command(args: argparse.Namespace) -> None:
    config = V2Config(
        train_db=str(Path(args.train_db)),
        may_db=str(Path(args.may_db)),
        train_cutoff_complete_before=args.train_cutoff_complete_before,
        validation_start=args.validation_start,
        validation_end=args.validation_end,
        may_start=args.may_start,
        may_end=args.may_end,
        random_state=int(args.random_state),
    )
    summary = _train_and_evaluate(config, Path(args.out))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:16000])


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Train Spark Opportunity Model 2.0 from model_feature_store.")
    run = parser.add_subparsers(dest="command", required=True).add_parser("run")
    run.add_argument("--train-db", default=str(DEFAULT_TRAIN_DB))
    run.add_argument("--may-db", default=str(DEFAULT_MAY_DB))
    run.add_argument("--train-cutoff-complete-before", default="2026-04-01")
    run.add_argument("--validation-start", default="2026-04-01")
    run.add_argument("--validation-end", default="2026-04-09")
    run.add_argument("--may-start", default="2026-05-06")
    run.add_argument("--may-end", default="2026-05-18")
    run.add_argument("--random-state", type=int, default=42)
    run.add_argument("--out", default=str(OUT_DIR))
    run.set_defaults(func=run_command)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
