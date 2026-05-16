#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import DATA_DIR
from backend.app.services.market_heat import ensure_market_heat_dir, latest_trade_date


DEFAULT_HEAT_DB = Path(
    os.getenv("FINE_THEME_HEAT_V2_DB", os.path.join(DATA_DIR, "market_heat", "fine_theme_heat_daily_v2.db"))
)
DEFAULT_FORECAST_DB = Path(
    os.getenv("FINE_THEME_HEAT_FORECAST_DB", os.path.join(DATA_DIR, "market_heat", "fine_theme_heat_forecast.db"))
)
DEFAULT_MODEL_DIR = Path(os.getenv("FINE_THEME_HEAT_MODEL_DIR", os.path.join(DATA_DIR, "market_heat", "models")))

HORIZONS = (3, 5)
RANK_BANDS = (10, 15, 30)
MAINLINE_EXTENSION_TARGET = "future_mainline_extension_5d"
PRIMARY_TARGET = MAINLINE_EXTENSION_TARGET
DEFAULT_UNIVERSE = "mainline_extension"

BASE_FEATURE_COLUMNS = [
    "member_count",
    "rank_today",
    "rank_prev",
    "rank_delta",
    "hot_score",
    "pct_change",
    "return_5d",
    "return_10d",
    "return_20d",
    "up_ratio",
    "amount_ratio",
    "l2_net_inflow_yi",
    "l2_positive_ratio",
    "strong_count",
    "limit_up_count",
    "touch_limit_up_count",
    "broken_limit_up_count",
    "rank_improve_3d",
    "rank_improve_5d",
    "hot_change_3d",
    "hot_change_5d",
    "top5_hits_5d",
    "top10_hits_5d",
    "top15_hits_5d",
    "top30_hits_5d",
    "top5_hits_20d",
    "top10_hits_20d",
    "top15_hits_20d",
    "top30_hits_20d",
    "best_rank_20d",
    "out_top30_streak",
    "today_strong",
    "first_hot",
    "mainline_accel",
    "warming",
    "mainline_continue",
    "fading_watch",
]

ENGINEERED_FEATURE_COLUMNS = [
    "rank_score",
    "rank_prev_score",
    "best_rank_20d_score",
    "rank_top5_now",
    "rank_top10_now",
    "rank_top15_now",
    "rank_top30_now",
    "amount_ratio_log",
    "l2_positive",
    "l2_negative",
    "limit_pressure",
    "lead_stock_pressure",
    "breadth_strength",
    "limit_up_ratio",
    "strong_ratio",
    "hot_score_pct_rank",
    "pct_change_pct_rank",
    "return_5d_pct_rank",
    "return_20d_pct_rank",
    "amount_ratio_pct_rank",
    "l2_net_inflow_pct_rank",
    "is_active_extension",
    "is_reheat_candidate",
    "is_mainline_extension_candidate",
    "is_recent_exit",
    "is_warm_not_hot",
    "is_cold_start",
    "continuation_reheat_universe",
]

FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + ENGINEERED_FEATURE_COLUMNS


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def load_heat_frame(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(f"fine theme heat db not found: {db_path}")
    with sqlite3.connect(str(db_path), timeout=60) as conn:
        df = pd.read_sql_query(
            """
            SELECT trade_date, theme_id, theme_name, sector_code, sector_type,
                   member_count, rank_today, rank_prev, rank_delta, hot_score, pct_change,
                   return_5d, return_10d, return_20d, up_ratio, amount_ratio,
                   l2_net_inflow_yi, l2_positive_ratio, strong_count, limit_up_count,
                   touch_limit_up_count, broken_limit_up_count, rank_improve_3d, rank_improve_5d,
                   hot_change_3d, hot_change_5d, top5_hits_5d, top10_hits_5d, top15_hits_5d,
                   top30_hits_5d, top5_hits_20d, top10_hits_20d, top15_hits_20d, top30_hits_20d,
                   best_rank_20d, out_top30_streak, today_strong, first_hot, mainline_accel,
                   warming, mainline_continue, fading_watch
            FROM fine_theme_heat_daily_v2
            ORDER BY trade_date, theme_id
            """,
            conn,
        )
    if df.empty:
        raise RuntimeError("fine_theme_heat_daily_v2 is empty")
    return df


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in BASE_FEATURE_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    theme_count = out.groupby("trade_date")["theme_id"].transform("count").astype(float).clip(lower=1)
    out["rank_prev"] = out["rank_prev"].fillna(theme_count)
    out["rank_score"] = 1.0 - ((out["rank_today"].astype(float) - 1.0) / (theme_count - 1.0).replace(0, 1))
    out["rank_prev_score"] = 1.0 - ((out["rank_prev"].astype(float) - 1.0) / (theme_count - 1.0).replace(0, 1))
    out["best_rank_20d_score"] = 1.0 - ((out["best_rank_20d"].astype(float) - 1.0) / (theme_count - 1.0).replace(0, 1))
    out["rank_top5_now"] = (out["rank_today"] <= 5).astype(int)
    out["rank_top10_now"] = (out["rank_today"] <= 10).astype(int)
    out["rank_top15_now"] = (out["rank_today"] <= 15).astype(int)
    out["rank_top30_now"] = (out["rank_today"] <= 30).astype(int)
    out["amount_ratio_log"] = np.log1p(out["amount_ratio"].clip(lower=0, upper=20))
    out["l2_positive"] = (out["l2_net_inflow_yi"] > 0).astype(int)
    out["l2_negative"] = (out["l2_net_inflow_yi"] < 0).astype(int)
    out["limit_pressure"] = out["touch_limit_up_count"].fillna(0) - out["broken_limit_up_count"].fillna(0)
    member_count = out["member_count"].astype(float).clip(lower=1)
    out["limit_up_ratio"] = (out["limit_up_count"].fillna(0) / member_count).clip(lower=0, upper=1)
    out["strong_ratio"] = (out["strong_count"].fillna(0) / member_count).clip(lower=0, upper=1)
    out["breadth_strength"] = (
        0.45 * (out["up_ratio"].fillna(0) / 100).clip(lower=0, upper=1)
        + 0.35 * out["strong_ratio"]
        + 0.20 * (out["l2_positive_ratio"].fillna(0) / 100).clip(lower=0, upper=1)
    )
    # Soft penalty for "one stock drags the whole basket": no hard member-count cutoff.
    out["lead_stock_pressure"] = (
        (out["pct_change"].fillna(0) >= 3.0)
        & (out["breadth_strength"] < 0.34)
        & (out["strong_count"].fillna(0) <= 1)
        & (out["limit_up_count"].fillna(0) <= 1)
    ).astype(int)
    out["is_active_extension"] = (
        (out["rank_today"] <= 30)
        & ((out["top30_hits_20d"] >= 3) | (out["top15_hits_20d"] >= 2) | (out["top5_hits_20d"] >= 1))
    ).astype(int)
    out["is_reheat_candidate"] = (
        (out["rank_today"] > 30)
        & (out["top30_hits_20d"] >= 3)
        & (out["out_top30_streak"] <= 5)
    ).astype(int)
    out["is_mainline_extension_candidate"] = (
        (out["rank_today"] <= 30)
        & (
            (out["top30_hits_20d"] >= 5)
            | (out["top15_hits_20d"] >= 3)
            | (out["top5_hits_20d"] >= 2)
        )
    ).astype(int)
    out["is_recent_exit"] = (
        (out["rank_today"] > 30)
        & (out["out_top30_streak"] >= 1)
        & (out["out_top30_streak"] <= 5)
    ).astype(int)
    out["is_warm_not_hot"] = (
        (out["rank_today"] > 30)
        & (out["top30_hits_20d"] >= 1)
        & (out["top30_hits_20d"] <= 4)
    ).astype(int)
    out["is_cold_start"] = ((out["rank_today"] > 30) & (out["top30_hits_20d"] == 0)).astype(int)
    out["continuation_reheat_universe"] = (
        (out["is_active_extension"] == 1)
        | (out["is_reheat_candidate"] == 1)
        | (
            (out["rank_today"] <= 45)
            & (out["top30_hits_20d"] >= 2)
            & (out["out_top30_streak"] <= 8)
        )
    ).astype(int)

    for source, dest in [
        ("hot_score", "hot_score_pct_rank"),
        ("pct_change", "pct_change_pct_rank"),
        ("return_5d", "return_5d_pct_rank"),
        ("return_20d", "return_20d_pct_rank"),
        ("amount_ratio", "amount_ratio_pct_rank"),
        ("l2_net_inflow_yi", "l2_net_inflow_pct_rank"),
    ]:
        out[dest] = out.groupby("trade_date")[source].rank(method="average", pct=True)

    for col in FEATURE_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out


def add_future_labels(df: pd.DataFrame, horizons: Sequence[int], bands: Sequence[int]) -> pd.DataFrame:
    out = df.sort_values(["theme_id", "trade_date"]).copy()
    grouped = out.groupby("theme_id", group_keys=False)
    for horizon in horizons:
        future_rank_frame = pd.concat(
            [grouped["rank_today"].shift(-offset) for offset in range(1, horizon + 1)],
            axis=1,
        )
        future_rank_frame.columns = list(range(1, horizon + 1))
        future_best = future_rank_frame.min(axis=1)
        out[f"future_best_rank_{horizon}d"] = future_best
        for band in bands:
            out[f"future_top{band}_{horizon}d"] = (future_best <= band).astype(int)
        if horizon == 5:
            future_top30_hits = future_rank_frame.le(30).sum(axis=1)
            future_breadth_frame = pd.concat(
                [grouped["lead_stock_pressure"].shift(-offset).fillna(1).eq(0) for offset in range(1, horizon + 1)],
                axis=1,
            )
            future_breadth_frame.columns = list(range(1, horizon + 1))
            future_valid_hot = (future_rank_frame.le(15) & future_breadth_frame).any(axis=1)
            out[MAINLINE_EXTENSION_TARGET] = (future_valid_hot & (future_top30_hits >= 2)).astype(int)
    return out.sort_values(["trade_date", "theme_id"]).reset_index(drop=True)


def target_columns() -> List[str]:
    return [MAINLINE_EXTENSION_TARGET]


def apply_universe(df: pd.DataFrame, universe: str) -> pd.DataFrame:
    if universe == "all":
        return df.copy()
    if universe == "continuation_reheat":
        return df[df["continuation_reheat_universe"] == 1].copy()
    if universe == "mainline_extension":
        return df[df["is_mainline_extension_candidate"] == 1].copy()
    if universe == "mainline_watch":
        return df[
            (df["rank_today"] <= 45)
            & (
                (df["top30_hits_20d"] >= 4)
                | (df["top15_hits_20d"] >= 2)
                | (df["top5_hits_20d"] >= 1)
            )
            & (df["out_top30_streak"] <= 3)
        ].copy()
    if universe == "active_extension":
        return df[df["is_active_extension"] == 1].copy()
    if universe == "reheat":
        return df[df["is_reheat_candidate"] == 1].copy()
    raise ValueError(f"unknown universe: {universe}")


def valid_label_mask(df: pd.DataFrame, max_horizon: int) -> pd.Series:
    dates = sorted(df["trade_date"].unique())
    if len(dates) <= max_horizon:
        return pd.Series(False, index=df.index)
    max_label_date = dates[-max_horizon - 1]
    return df["trade_date"] <= max_label_date


def fit_models(train_df: pd.DataFrame, feature_columns: Sequence[str]) -> Dict[str, HistGradientBoostingClassifier]:
    models: Dict[str, HistGradientBoostingClassifier] = {}
    x_train = train_df[list(feature_columns)].to_numpy(dtype=float)
    for target in target_columns():
        y_train = train_df[target].astype(int).to_numpy()
        model = HistGradientBoostingClassifier(
            loss="log_loss",
            learning_rate=0.045,
            max_iter=260,
            max_leaf_nodes=31,
            min_samples_leaf=25,
            l2_regularization=0.08,
            class_weight="balanced",
            random_state=42,
        )
        model.fit(x_train, y_train)
        models[target] = model
    return models


def predict_proba(models: Dict[str, HistGradientBoostingClassifier], df: pd.DataFrame, feature_columns: Sequence[str]) -> pd.DataFrame:
    out = df[["trade_date", "theme_id", "theme_name", "sector_code", "sector_type", "rank_today", "hot_score"]].copy()
    x = df[list(feature_columns)].to_numpy(dtype=float)
    for target, model in models.items():
        out[target] = model.predict_proba(x)[:, 1]
    return out


def precision_at_k(group: pd.DataFrame, target: str, score_col: str, k: int) -> Optional[float]:
    if group.empty:
        return None
    top = group.sort_values(score_col, ascending=False).head(k)
    if top.empty:
        return None
    return float(top[target].mean())


def evaluate_predictions(scored: pd.DataFrame, validation_df: pd.DataFrame) -> Dict[str, Any]:
    merged = scored.merge(
        validation_df[["trade_date", "theme_id"] + target_columns()],
        on=["trade_date", "theme_id"],
        how="inner",
        suffixes=("", "_label"),
    )
    metrics: Dict[str, Any] = {}
    for target in target_columns():
        label_col = f"{target}_label"
        y_true = merged[label_col].astype(int)
        y_score = merged[target].astype(float)
        prevalence = float(y_true.mean()) if len(y_true) else 0.0
        item: Dict[str, Any] = {
            "samples": int(len(y_true)),
            "positive_rate": round(prevalence, 6),
        }
        if len(set(y_true.tolist())) > 1:
            item["roc_auc"] = round(float(roc_auc_score(y_true, y_score)), 6)
            item["pr_auc"] = round(float(average_precision_score(y_true, y_score)), 6)
        by_date = merged.groupby("trade_date", sort=True)
        for k in (5, 10, 20, 30):
            values = [v for v in (precision_at_k(group, label_col, target, k) for _, group in by_date) if v is not None]
            item[f"precision_at_{k}"] = round(float(np.mean(values)), 6) if values else 0.0
            item[f"lift_at_{k}"] = round(item[f"precision_at_{k}"] / prevalence, 3) if prevalence > 0 else None
        metrics[target] = item
    return metrics


def train_validation_split(df: pd.DataFrame, validation_days: int, max_horizon: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(df["trade_date"].unique())
    validation_days = max(max(validation_days, 20), max_horizon + 5)
    if len(dates) <= validation_days + max_horizon + 20:
        raise RuntimeError("not enough dates for a time split")
    validation_dates = dates[-validation_days:]
    train_cutoff = dates[-validation_days - max_horizon - 1]
    train_df = df[df["trade_date"] <= train_cutoff].copy()
    validation_df = df[df["trade_date"].isin(validation_dates)].copy()
    validation_df = validation_df[validation_df[f"future_best_rank_{max_horizon}d"].notna()].copy()
    if train_df.empty or validation_df.empty:
        raise RuntimeError("empty train or validation split")
    return train_df, validation_df


def ensure_forecast_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fine_theme_heat_forecast_predictions (
            trade_date TEXT NOT NULL,
            model_version TEXT NOT NULL,
            target TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            rank_band INTEGER NOT NULL,
            theme_id TEXT NOT NULL,
            theme_name TEXT NOT NULL,
            sector_code TEXT,
            sector_type TEXT,
            current_rank INTEGER NOT NULL,
            current_hot_score REAL NOT NULL,
            probability REAL NOT NULL,
            score_rank INTEGER NOT NULL,
            probability_percentile REAL NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (trade_date, model_version, target, theme_id)
        );
        CREATE INDEX IF NOT EXISTS idx_fine_theme_forecast_latest
          ON fine_theme_heat_forecast_predictions(trade_date, target, score_rank);
        CREATE TABLE IF NOT EXISTS fine_theme_heat_forecast_runs (
            model_version TEXT PRIMARY KEY,
            train_start_date TEXT NOT NULL,
            train_end_date TEXT NOT NULL,
            validation_start_date TEXT,
            validation_end_date TEXT,
            prediction_date TEXT NOT NULL,
            feature_columns_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            model_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )


def target_meta(target: str) -> Tuple[int, int]:
    if target == MAINLINE_EXTENSION_TARGET:
        return 5, 15
    # future_top15_5d
    left, horizon_text = target.replace("future_top", "").split("_")
    return int(horizon_text.replace("d", "")), int(left)


def write_predictions(
    forecast_db: Path,
    model_version: str,
    model_path: Path,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    prediction_df: pd.DataFrame,
    metrics: Dict[str, Any],
    universe: str,
) -> Dict[str, Any]:
    forecast_db.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(str(forecast_db), timeout=60) as conn:
        ensure_forecast_schema(conn)
        conn.execute("DELETE FROM fine_theme_heat_forecast_predictions WHERE trade_date = ? AND model_version = ?", (str(prediction_df["trade_date"].iloc[0]), model_version))
        rows = []
        for target in target_columns():
            horizon, band = target_meta(target)
            ranked = prediction_df.sort_values(target, ascending=False).reset_index(drop=True)
            count = max(len(ranked) - 1, 1)
            for idx, row in ranked.iterrows():
                rows.append(
                    (
                        str(row["trade_date"]),
                        model_version,
                        target,
                        horizon,
                        band,
                        str(row["theme_id"]),
                        str(row["theme_name"]),
                        str(row.get("sector_code") or ""),
                        str(row.get("sector_type") or ""),
                        int(row["rank_today"]),
                        safe_float(row["hot_score"]),
                        safe_float(row[target]),
                        idx + 1,
                        1.0 - (idx / count),
                        created_at,
                    )
                )
        conn.executemany(
            """
            INSERT OR REPLACE INTO fine_theme_heat_forecast_predictions (
                trade_date, model_version, target, horizon_days, rank_band, theme_id, theme_name,
                sector_code, sector_type, current_rank, current_hot_score, probability, score_rank,
                probability_percentile, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO fine_theme_heat_forecast_runs (
                model_version, train_start_date, train_end_date, validation_start_date, validation_end_date,
                prediction_date, feature_columns_json, metrics_json, model_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_version,
                str(train_df["trade_date"].min()),
                str(train_df["trade_date"].max()),
                str(validation_df["trade_date"].min()) if not validation_df.empty else None,
                str(validation_df["trade_date"].max()) if not validation_df.empty else None,
                str(prediction_df["trade_date"].iloc[0]),
                json.dumps(list(FEATURE_COLUMNS), ensure_ascii=False),
                json.dumps({"universe": universe, "metrics": metrics}, ensure_ascii=False),
                str(model_path),
                created_at,
            ),
        )
        conn.commit()
    return {"prediction_rows": len(rows), "forecast_db": str(forecast_db)}


def rows_to_jsonable(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [{k: row[k] for k in row.keys()} for row in rows]


def train_and_predict(
    heat_db: Path,
    forecast_db: Path,
    model_dir: Path,
    prediction_date: Optional[str],
    validation_days: int,
    universe: str,
) -> Dict[str, Any]:
    ensure_market_heat_dir()
    model_dir.mkdir(parents=True, exist_ok=True)
    max_horizon = max(HORIZONS)

    raw = load_heat_frame(heat_db)
    df = add_future_labels(add_engineered_features(raw), HORIZONS, RANK_BANDS)
    df = apply_universe(df, universe)
    labeled_df = df[valid_label_mask(df, max_horizon)].copy()
    train_df, validation_df = train_validation_split(labeled_df, validation_days, max_horizon)

    validation_models = fit_models(train_df, FEATURE_COLUMNS)
    validation_scored = predict_proba(validation_models, validation_df, FEATURE_COLUMNS)
    metrics = evaluate_predictions(validation_scored, validation_df)

    final_train_df = labeled_df.copy()
    final_models = fit_models(final_train_df, FEATURE_COLUMNS)

    latest = prediction_date or latest_trade_date() or str(raw["trade_date"].max())
    predict_df = df[df["trade_date"] == latest].copy()
    if predict_df.empty:
        available = str(raw["trade_date"].max())
        raise RuntimeError(f"prediction date {latest} not found in heat db; latest available is {available}")
    prediction_scored = predict_proba(final_models, predict_df, FEATURE_COLUMNS)

    model_slug = "hgb_focus" if universe != "all" else "hgb"
    model_version = f"fine_theme_heat_{model_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    model_path = model_dir / f"{model_version}.joblib"
    bundle = {
        "model_version": model_version,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "primary_target": PRIMARY_TARGET,
        "feature_columns": list(FEATURE_COLUMNS),
        "targets": target_columns(),
        "horizons": list(HORIZONS),
        "rank_bands": list(RANK_BANDS),
        "universe": universe,
        "models": final_models,
        "metrics": metrics,
        "heat_db": str(heat_db),
        "forecast_db": str(forecast_db),
    }
    joblib.dump(bundle, model_path)
    latest_model_path = model_dir / "fine_theme_heat_forecast_latest.joblib"
    joblib.dump(bundle, latest_model_path)

    write_result = write_predictions(
        forecast_db=forecast_db,
        model_version=model_version,
        model_path=model_path,
        train_df=final_train_df,
        validation_df=validation_df,
        prediction_df=prediction_scored,
        metrics=metrics,
        universe=universe,
    )

    with sqlite3.connect(str(forecast_db), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        top_rows = rows_to_jsonable(
            conn.execute(
                """
                SELECT target, theme_name, current_rank, probability, score_rank
                FROM fine_theme_heat_forecast_predictions
                WHERE trade_date = ? AND model_version = ? AND target = ?
                ORDER BY score_rank
                LIMIT 15
                """,
                (latest, model_version, PRIMARY_TARGET),
            ).fetchall()
        )

    summary = {
        "model_version": model_version,
        "prediction_date": latest,
        "model_path": str(model_path),
        "latest_model_path": str(latest_model_path),
        "heat_db": str(heat_db),
        "forecast_db": str(forecast_db),
        "train_start_date": str(final_train_df["trade_date"].min()),
        "train_end_date": str(final_train_df["trade_date"].max()),
        "validation_start_date": str(validation_df["trade_date"].min()),
        "validation_end_date": str(validation_df["trade_date"].max()),
        "features": len(FEATURE_COLUMNS),
        "universe": universe,
        "train_samples": int(len(final_train_df)),
        "validation_samples": int(len(validation_df)),
        "prediction_candidates": int(len(predict_df)),
        "targets": target_columns(),
        "metrics": metrics,
        "top_primary": top_rows,
        **write_result,
    }
    report_path = model_dir / "fine_theme_heat_forecast_latest.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Train fine-theme heat forecast models and write latest predictions.")
    parser.add_argument("--heat-db", default=str(DEFAULT_HEAT_DB))
    parser.add_argument("--forecast-db", default=str(DEFAULT_FORECAST_DB))
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--prediction-date", default=None)
    parser.add_argument("--validation-days", type=int, default=45)
    parser.add_argument(
        "--universe",
        default=DEFAULT_UNIVERSE,
        choices=["mainline_watch", "mainline_extension", "continuation_reheat", "active_extension", "reheat", "all"],
        help="Candidate universe for training and prediction.",
    )
    args = parser.parse_args()

    result = train_and_predict(
        heat_db=Path(args.heat_db),
        forecast_db=Path(args.forecast_db),
        model_dir=Path(args.model_dir),
        prediction_date=args.prediction_date,
        validation_days=args.validation_days,
        universe=args.universe,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
