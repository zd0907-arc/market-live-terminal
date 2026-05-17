#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from sklearn.metrics import mean_absolute_error, roc_auc_score

import research_opportunity_discovery_model as base


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data/selection/opportunity_discovery/walk_forward_old_v0_1"


DEFAULT_WINDOWS: Tuple[Tuple[str, str, str], ...] = (
    ("2026-01", "2026-01-02", "2026-01-31"),
    ("2026-02", "2026-02-01", "2026-02-28"),
    ("2026-03", "2026-03-01", "2026-03-31"),
    ("2026-04-partial", "2026-04-01", "2026-04-30"),
)


def _parse_windows(raw: Optional[str]) -> List[Tuple[str, str, str]]:
    if not raw:
        return list(DEFAULT_WINDOWS)
    windows: List[Tuple[str, str, str]] = []
    for item in raw.split(","):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) != 3:
            raise ValueError(f"bad window spec: {item!r}; expected name:start:end")
        windows.append((parts[0], parts[1], parts[2]))
    return windows


def _score_parts(train_filtered: pd.DataFrame, valid_filtered: pd.DataFrame, feature_cols: Sequence[str], config: base.OpportunityConfig) -> Any:
    model = base._fit_model(train_filtered, feature_cols, config)
    for part in [train_filtered, valid_filtered]:
        part["model_score"] = model.predict(part[list(feature_cols)])
        part["rule_score"] = base._score_rule_baseline(part)
        part["final_score"] = 0.78 * part["model_score"] + 0.22 * part["rule_score"]
    return model


def _top1(summary: Dict[str, Any]) -> Dict[str, Any]:
    for row in summary.get("topk_model", []):
        if int(row.get("top_k", 0)) == 1:
            return row
    return {}


def _rule_top1(summary: Dict[str, Any]) -> Dict[str, Any]:
    for row in summary.get("topk_rule_baseline", []):
        if int(row.get("top_k", 0)) == 1:
            return row
    return {}


def _best_portfolio(holding_summary_df: pd.DataFrame) -> Dict[str, Any]:
    if holding_summary_df.empty or "total_return_pct" not in holding_summary_df.columns:
        return {}
    return (
        holding_summary_df.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False])
        .iloc[0]
        .to_dict()
    )


def _run_window(
    *,
    name: str,
    validation_start: str,
    validation_end: str,
    data: pd.DataFrame,
    panel: pd.DataFrame,
    atomic_for_exit: pd.DataFrame,
    feature_cols: Sequence[str],
    base_config: base.OpportunityConfig,
    out_dir: Path,
    write_details: bool,
) -> Dict[str, Any]:
    config = base.OpportunityConfig(
        start_date=base_config.start_date,
        end_date=base_config.end_date,
        validation_start=validation_start,
        validation_end=validation_end,
        horizon_days=base_config.horizon_days,
    )
    split_dir = out_dir / name
    split_dir.mkdir(parents=True, exist_ok=True)

    train = data[pd.to_datetime(data["label_complete_asof_date"]) < pd.to_datetime(validation_start)].copy()
    valid = data[(data["trade_date"] >= validation_start) & (data["trade_date"] <= validation_end)].copy()
    train_filtered = base._apply_historical_entry_filter(train, config)
    valid_filtered = base._apply_historical_entry_filter(valid, config)
    if train_filtered.empty or valid_filtered.empty:
        raise RuntimeError(f"{name}: train/validation split is empty after entry filters")

    model = _score_parts(train_filtered, valid_filtered, feature_cols, config)
    valid_eval = base._evaluate_topk(valid_filtered, "final_score")
    baseline_eval = base._evaluate_topk(valid_filtered.assign(rule_score=base._score_rule_baseline(valid_filtered)), "rule_score")
    trades_df, exit_summary_df, mfe_bucket_df = base._evaluate_exit_policies(
        valid_filtered,
        atomic_for_exit,
        config,
        score_col="final_score",
        top_ks=(1, 3, 5),
    )

    hold_samples = base._build_holding_training_samples(
        train_filtered,
        atomic_for_exit,
        panel,
        config,
        score_col="final_score",
        top_k=2,
    )
    hold_model, hold_feature_cols = base._fit_holding_model(hold_samples, config)
    holding_portfolio_trades: List[pd.DataFrame] = []
    holding_portfolio_summary: List[Dict[str, Any]] = []
    for policy in base.HOLDING_MODEL_POLICIES:
        for mode in ["top1", "top1_top2_conditional"]:
            portfolio_trades, portfolio_summary = base._simulate_portfolio(
                valid_filtered,
                atomic_for_exit,
                panel,
                hold_model,
                hold_feature_cols,
                config,
                mode=mode,
                policy=policy,
            )
            holding_portfolio_summary.append(portfolio_summary)
            if not portfolio_trades.empty:
                holding_portfolio_trades.append(portfolio_trades)
    holding_trades_df = pd.concat(holding_portfolio_trades, ignore_index=True) if holding_portfolio_trades else pd.DataFrame()
    holding_summary_df = pd.DataFrame(holding_portfolio_summary)

    y_valid = pd.to_numeric(valid_filtered["opportunity_score"], errors="coerce").fillna(0.0)
    pred_valid = pd.to_numeric(valid_filtered["model_score"], errors="coerce").fillna(0.0)
    auc_payload: Dict[str, Any] = {}
    for threshold in [10.0, 15.0, 20.0]:
        y_bin = (pd.to_numeric(valid_filtered["max_runup_22d_pct"], errors="coerce").fillna(0.0) >= threshold).astype(int)
        if int(y_bin.nunique()) > 1:
            auc_payload[f"hit{int(threshold)}_auc"] = round(float(roc_auc_score(y_bin, pred_valid)), 4)

    summary = {
        "name": name,
        "config": asdict(config),
        "data": {
            "train_rows": int(len(train_filtered)),
            "validation_rows": int(len(valid_filtered)),
            "train_dates": [str(train_filtered["trade_date"].min()), str(train_filtered["trade_date"].max())],
            "validation_dates": [str(valid_filtered["trade_date"].min()), str(valid_filtered["trade_date"].max())],
            "feature_count": int(len(feature_cols)),
            "holding_sample_rows": int(len(hold_samples)),
            "holding_feature_count": int(len(hold_feature_cols)),
        },
        "metrics": {
            "validation_mae_opportunity_score": round(float(mean_absolute_error(y_valid, pred_valid)), 4),
            **auc_payload,
            "topk_model": valid_eval["summary"],
            "topk_rule_baseline": baseline_eval["summary"],
            "mfe_bucket_summary": mfe_bucket_df.to_dict(orient="records"),
            "exit_policy_summary": exit_summary_df.to_dict(orient="records"),
            "holding_model_portfolio_summary": holding_summary_df.to_dict(orient="records"),
        },
    }

    if write_details:
        valid_filtered.sort_values(["trade_date", "final_score"], ascending=[True, False]).groupby("trade_date").head(20).to_csv(
            split_dir / "validation_topk.csv", index=False
        )
        trades_df.to_csv(split_dir / "validation_exit_trades.csv", index=False)
        exit_summary_df.to_csv(split_dir / "validation_exit_policy_summary.csv", index=False)
        mfe_bucket_df.to_csv(split_dir / "validation_mfe_bucket_summary.csv", index=False)
        holding_trades_df.to_csv(split_dir / "holding_model_portfolio_trades.csv", index=False)
        holding_summary_df.to_csv(split_dir / "holding_model_portfolio_summary.csv", index=False)
        base._write_model(split_dir / "model.joblib", model)
        base._write_model(split_dir / "holding_model.joblib", hold_model)
    base._json_dump(split_dir / "summary.json", summary)

    top1 = _top1(summary["metrics"])
    rule1 = _rule_top1(summary["metrics"])
    best = _best_portfolio(holding_summary_df)
    return {
        "window": name,
        "validation_start": validation_start,
        "validation_end_requested": validation_end,
        "validation_dates": " ~ ".join(summary["data"]["validation_dates"]),
        "train_dates": " ~ ".join(summary["data"]["train_dates"]),
        "validation_days": int(top1.get("days", 0)),
        "top1_picks": int(top1.get("picks", 0)),
        "top1_hit15_rate": float(top1.get("hit15_rate", 0.0)),
        "top1_hit20_rate": float(top1.get("hit20_rate", 0.0)),
        "top1_avg_mfe_pct": float(top1.get("avg_max_runup_22d_pct", 0.0)),
        "top1_median_mfe_pct": float(top1.get("median_max_runup_22d_pct", 0.0)),
        "rule_top1_hit15_rate": float(rule1.get("hit15_rate", 0.0)),
        "best_mode": best.get("mode"),
        "best_policy": best.get("policy"),
        "best_trades": int(best.get("trades", 0)) if best else 0,
        "best_total_return_pct": float(best.get("total_return_pct", 0.0)) if best else 0.0,
        "best_max_drawdown_pct": float(best.get("max_drawdown_pct", 0.0)) if best else 0.0,
        "best_win_rate": float(best.get("win_rate", 0.0)) if best else 0.0,
    }


def run_command(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    windows = _parse_windows(args.windows)
    config = base.OpportunityConfig(start_date=args.start_date, end_date=args.end_date, horizon_days=int(args.horizon_days))

    data, panel = base.build_dataset(config, Path(args.atomic_db), Path(args.selection_db), Path(args.heat_db))
    if data.empty:
        raise RuntimeError("No labeled opportunity dataset was built")
    feature_cols = base.available_feature_columns(data, include_orderbook=False)
    if not feature_cols:
        raise RuntimeError("No feature columns are available")
    atomic_for_exit = base.add_atomic_features(base.load_atomic_daily(config.start_date, config.end_date, Path(args.atomic_db)))

    rows = []
    for name, validation_start, validation_end in windows:
        print(f"running {name} {validation_start}..{validation_end}", flush=True)
        rows.append(
            _run_window(
                name=name,
                validation_start=validation_start,
                validation_end=validation_end,
                data=data,
                panel=panel,
                atomic_for_exit=atomic_for_exit,
                feature_cols=feature_cols,
                base_config=config,
                out_dir=out_dir,
                write_details=not args.summary_only,
            )
        )
    summary_df = pd.DataFrame(rows)
    summary_df.to_csv(out_dir / "walk_forward_summary.csv", index=False)
    payload = {
        "model_version": "walk_forward_old_v0_1",
        "base_model_version": base.MODEL_VERSION,
        "config": asdict(config),
        "windows": rows,
        "files": {"summary_csv": str(out_dir / "walk_forward_summary.csv")},
    }
    base._json_dump(out_dir / "summary.json", payload)
    print(summary_df.to_string(index=False))


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Walk-forward validation for opportunity discovery model")
    parser.add_argument("--atomic-db", default=str(base.DEFAULT_ATOMIC_DB))
    parser.add_argument("--selection-db", default=str(base.DEFAULT_SELECTION_DB))
    parser.add_argument("--heat-db", default=str(base.DEFAULT_HEAT_DB))
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run monthly walk-forward validation")
    run.add_argument("--start-date", default="2025-01-02")
    run.add_argument("--end-date", default="2026-05-14")
    run.add_argument("--horizon-days", type=int, default=22)
    run.add_argument("--windows", default=None, help="Comma list: name:start:end,name:start:end")
    run.add_argument("--summary-only", action="store_true")
    run.add_argument("--out", default=str(OUT_DIR))
    run.set_defaults(func=run_command)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
