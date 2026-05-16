#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.train_fine_theme_heat_forecast_model import (
    DEFAULT_HEAT_DB,
    FEATURE_COLUMNS,
    HORIZONS,
    RANK_BANDS,
    add_engineered_features,
    add_future_labels,
    apply_universe,
    fit_models,
    load_heat_frame,
    predict_proba,
    valid_label_mask,
)


def walk_forward_topk(
    top_k: int,
    validation_start_index: int,
    universe: str,
    score_target: str,
) -> Dict[str, Any]:
    max_horizon = max(HORIZONS)
    raw = load_heat_frame(DEFAULT_HEAT_DB)
    df = add_future_labels(add_engineered_features(raw), HORIZONS, RANK_BANDS)
    df = apply_universe(df, universe)
    dates = sorted(df.trade_date.unique())
    valid_dates = sorted(df[valid_label_mask(df, max_horizon)].trade_date.unique())
    eval_dates = [d for d in valid_dates if dates.index(d) >= validation_start_index + max_horizon + 1]
    months: List[str] = []
    for d in eval_dates:
        month = d[:7]
        if not months or months[-1] != month:
            months.append(month)

    rows: List[Dict[str, Any]] = []
    for month in months:
        month_dates = [d for d in eval_dates if d.startswith(month)]
        if not month_dates:
            continue
        first_pos = dates.index(month_dates[0])
        train_cutoff_pos = first_pos - max_horizon - 1
        if train_cutoff_pos < 40:
            continue
        train_cutoff = dates[train_cutoff_pos]
        train = df[(df.trade_date <= train_cutoff) & (df[f"future_best_rank_{max_horizon}d"].notna())].copy()
        if train.empty or train.theme_id.nunique() < 20:
            continue
        models = fit_models(train, FEATURE_COLUMNS)
        for trade_date in month_dates:
            day = df[df.trade_date == trade_date].copy()
            if day.empty:
                continue
            scored = predict_proba(models, day, FEATURE_COLUMNS)
            merged = scored.merge(
                day[[
                    "trade_date",
                    "theme_id",
                    "theme_name",
                    "rank_today",
                    "future_mainline_extension_5d",
                    "future_top10_5d",
                    "future_top15_5d",
                    "future_top30_5d",
                ]],
                on=["trade_date", "theme_id"],
                suffixes=("", "_label"),
            )
            def label_col(name: str) -> str:
                suffixed = f"{name}_label"
                return suffixed if suffixed in merged.columns else name

            mainline_col = label_col("future_mainline_extension_5d")
            top10_col = label_col("future_top10_5d")
            top15_col = label_col("future_top15_5d")
            top30_col = label_col("future_top30_5d")
            universe_base = float(merged[mainline_col].mean()) if len(merged) else 0.0
            top = merged.sort_values(score_target, ascending=False).head(top_k)
            for _, row in top.iterrows():
                rows.append({
                    "trade_date": trade_date,
                    "month": month,
                    "theme_id": row["theme_id"],
                    "theme_name": row.get("theme_name_label") or row.get("theme_name"),
                    "current_rank": int(row.get("rank_today_label") or row.get("rank_today")),
                    "score": float(row[score_target]),
                    "hit_mainline_extension_5d": int(row[mainline_col]),
                    "hit_top10_5d": int(row[top10_col]),
                    "hit_top15_5d": int(row[top15_col]),
                    "hit_top30_5d": int(row[top30_col]),
                    "universe_count": int(len(merged)),
                    "universe_base_mainline_extension_5d": universe_base,
                })
    result = pd.DataFrame(rows)
    if result.empty:
        raise RuntimeError("walk-forward produced no rows")
    daily = result.groupby("trade_date").agg(
        any_mainline_extension_5d=("hit_mainline_extension_5d", lambda x: int(np.any(x))),
        any_top15_5d=("hit_top15_5d", lambda x: int(np.any(x))),
        any_top30_5d=("hit_top30_5d", lambda x: int(np.any(x))),
        universe_count=("universe_count", "first"),
        universe_base_mainline_extension_5d=("universe_base_mainline_extension_5d", "first"),
    ).reset_index()
    monthly = result.groupby("month").agg(
        days=("trade_date", "nunique"),
        picks=("theme_id", "count"),
        hit_mainline_extension_5d=("hit_mainline_extension_5d", "mean"),
        hit_top10_5d=("hit_top10_5d", "mean"),
        hit_top15_5d=("hit_top15_5d", "mean"),
        hit_top30_5d=("hit_top30_5d", "mean"),
    ).reset_index()
    summary = {
        "start_date": str(daily.trade_date.min()),
        "end_date": str(daily.trade_date.max()),
        "days": int(len(daily)),
        "picks": int(len(result)),
        "top_k": int(top_k),
        "universe": universe,
        "score_target": score_target,
        "avg_universe_count": round(float(daily.universe_count.mean()), 2),
        "universe_base_mainline_extension_5d": round(float(daily.universe_base_mainline_extension_5d.mean()), 6),
        "pick_hit_mainline_extension_5d": round(float(result.hit_mainline_extension_5d.mean()), 6),
        "pick_hit_top10_5d": round(float(result.hit_top10_5d.mean()), 6),
        "pick_hit_top15_5d": round(float(result.hit_top15_5d.mean()), 6),
        "pick_hit_top30_5d": round(float(result.hit_top30_5d.mean()), 6),
        "daily_any_mainline_extension_5d": round(float(daily.any_mainline_extension_5d.mean()), 6),
        "daily_any_top15_5d": round(float(daily.any_top15_5d.mean()), 6),
        "daily_any_top30_5d": round(float(daily.any_top30_5d.mean()), 6),
        "monthly": monthly.to_dict(orient="records"),
    }
    return {"summary": summary, "picks": result, "daily": daily}


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward backtest for focused fine-theme heat forecast.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--validation-start-index", type=int, default=70)
    parser.add_argument("--universe", default="mainline_watch", choices=["mainline_watch", "mainline_extension", "continuation_reheat", "active_extension", "reheat", "all"])
    parser.add_argument("--score-target", default="future_mainline_extension_5d")
    parser.add_argument("--output-dir", default=str(ROOT / "data/selection/market_heat/backtests"))
    args = parser.parse_args()

    result = walk_forward_topk(args.top_k, args.validation_start_index, args.universe, args.score_target)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"fine_theme_forecast_{args.universe}_walkforward_top{args.top_k}"
    csv_path = out_dir / f"{stem}.csv"
    json_path = out_dir / f"{stem}.json"
    result["picks"].to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(result["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**result["summary"], "csv_path": str(csv_path), "json_path": str(json_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
