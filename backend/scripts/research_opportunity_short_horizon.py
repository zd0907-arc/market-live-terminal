#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

import research_opportunity_discovery_model as base


ROOT = Path(__file__).resolve().parents[2]
MODEL_VERSION = "short_horizon_v0_1"
OUT_DIR = ROOT / "data/selection/opportunity_discovery" / MODEL_VERSION


@dataclass(frozen=True)
class HorizonSpec:
    horizon_days: int
    target_thresholds: Tuple[float, ...]
    speed_half_life: float


@dataclass(frozen=True)
class ShortExitPolicy:
    name: str
    horizon_days: int
    target_profit_pct: float
    stop_loss_pct: Optional[float]


HORIZONS: Tuple[HorizonSpec, ...] = (
    HorizonSpec(horizon_days=2, target_thresholds=(3.0, 5.0, 8.0), speed_half_life=1.0),
    HorizonSpec(horizon_days=3, target_thresholds=(5.0, 8.0), speed_half_life=1.3),
    HorizonSpec(horizon_days=5, target_thresholds=(5.0, 8.0, 10.0), speed_half_life=2.0),
    HorizonSpec(horizon_days=7, target_thresholds=(8.0, 10.0, 12.0), speed_half_life=3.0),
    HorizonSpec(horizon_days=10, target_thresholds=(8.0, 10.0, 12.0, 15.0), speed_half_life=4.0),
)


EXIT_POLICIES: Dict[int, Tuple[ShortExitPolicy, ...]] = {
    2: (
        ShortExitPolicy("h2_tp3_sl5", 2, 3.0, -5.0),
        ShortExitPolicy("h2_tp5_sl7", 2, 5.0, -7.0),
        ShortExitPolicy("h2_tp8_sl7", 2, 8.0, -7.0),
    ),
    3: (
        ShortExitPolicy("h3_tp5_sl6", 3, 5.0, -6.0),
        ShortExitPolicy("h3_tp8_sl8", 3, 8.0, -8.0),
        ShortExitPolicy("h3_tp5_no_stop", 3, 5.0, None),
    ),
    5: (
        ShortExitPolicy("h5_tp8_sl8", 5, 8.0, -8.0),
        ShortExitPolicy("h5_tp10_sl10", 5, 10.0, -10.0),
        ShortExitPolicy("h5_tp8_no_stop", 5, 8.0, None),
    ),
    7: (
        ShortExitPolicy("h7_tp8_sl8", 7, 8.0, -8.0),
        ShortExitPolicy("h7_tp10_sl10", 7, 10.0, -10.0),
        ShortExitPolicy("h7_tp12_sl10", 7, 12.0, -10.0),
    ),
    10: (
        ShortExitPolicy("h10_tp10_sl10", 10, 10.0, -10.0),
        ShortExitPolicy("h10_tp12_sl12", 10, 12.0, -12.0),
        ShortExitPolicy("h10_tp15_sl12", 10, 15.0, -12.0),
    ),
}


def _json_dump(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _month_key(date: str) -> str:
    return str(date)[:7]


def _build_feature_panel(config: base.OpportunityConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # build_dataset already applies the same joins/defaults/signal-limit features
    # used by the 22-day model. The returned panel is label-independent.
    max_horizon_config = base.OpportunityConfig(
        start_date=config.start_date,
        end_date=config.end_date,
        validation_start=config.validation_start,
        horizon_days=max(spec.horizon_days for spec in HORIZONS),
    )
    _, panel = base.build_dataset(max_horizon_config, base.DEFAULT_ATOMIC_DB, base.DEFAULT_SELECTION_DB, base.DEFAULT_HEAT_DB)
    atomic = base.add_atomic_features(base.load_atomic_daily(config.start_date, config.end_date, base.DEFAULT_ATOMIC_DB))
    return panel, atomic


def _short_score(labels: pd.DataFrame, spec: HorizonSpec) -> pd.Series:
    mfe = pd.to_numeric(labels["max_runup_22d_pct"], errors="coerce").fillna(0.0)
    mdd_to_mfe = pd.to_numeric(labels["mdd_to_mfe_pct"], errors="coerce").fillna(0.0)
    max_dd = pd.to_numeric(labels["max_drawdown_22d_pct"], errors="coerce").fillna(0.0)
    entry_gap = pd.to_numeric(labels["entry_gap_pct"], errors="coerce").fillna(0.0)
    days_to_mfe = pd.to_numeric(labels["days_to_mfe"], errors="coerce").fillna(float(spec.horizon_days))
    locked = pd.to_numeric(labels["entry_locked_limit_up"], errors="coerce").fillna(0.0)
    near = pd.to_numeric(labels["entry_near_limit_up"], errors="coerce").fillna(0.0)

    path_penalty = np.maximum(0.0, -mdd_to_mfe - 4.0) * 1.05 + np.maximum(0.0, -max_dd - 8.0) * 0.25
    high_gap_penalty = np.maximum(0.0, entry_gap - 2.8) * 1.55
    block_penalty = locked * 20.0 + np.maximum(0.0, near - locked) * 8.0
    speed_penalty = np.maximum(0.0, days_to_mfe - float(spec.speed_half_life)) * (1.7 if spec.horizon_days <= 3 else 1.0)
    return (mfe - path_penalty - high_gap_penalty - block_penalty - speed_penalty).clip(-35.0, 60.0)


def _build_horizon_dataset(
    panel: pd.DataFrame,
    atomic: pd.DataFrame,
    base_config: base.OpportunityConfig,
    spec: HorizonSpec,
) -> pd.DataFrame:
    config = base.OpportunityConfig(
        start_date=base_config.start_date,
        end_date=base_config.end_date,
        validation_start=base_config.validation_start,
        horizon_days=spec.horizon_days,
    )
    labels = base.build_labels(atomic, config)
    if labels.empty:
        return labels
    labels = labels.rename(
        columns={
            "max_runup_22d_pct": "mfe_h_pct",
            "max_drawdown_22d_pct": "max_drawdown_h_pct",
            "close_return_22d_pct": "close_return_h_pct",
        }
    )
    labels_for_score = labels.rename(
        columns={
            "mfe_h_pct": "max_runup_22d_pct",
            "max_drawdown_h_pct": "max_drawdown_22d_pct",
            "close_return_h_pct": "close_return_22d_pct",
        }
    )
    labels["short_opportunity_score"] = _short_score(labels_for_score, spec)
    labels["horizon_days"] = int(spec.horizon_days)
    for threshold in spec.target_thresholds:
        labels[f"hit{int(threshold)}_h"] = (pd.to_numeric(labels["mfe_h_pct"], errors="coerce").fillna(0.0) >= threshold).astype(int)

    data = panel.merge(labels, on=["symbol", "trade_date"], how="inner")
    data = data[data["risk_flag_type"].fillna("normal").eq("normal")].copy()
    data = data[pd.to_numeric(data["total_amount"], errors="coerce").fillna(0.0) >= float(base_config.min_train_amount)].copy()
    data = data[pd.to_numeric(data["return_20d_pct"], errors="coerce").fillna(0.0) <= float(base_config.max_signal_return_20d_pct)].copy()
    data = data[pd.to_numeric(data["distribution_score"], errors="coerce").fillna(0.0) <= float(base_config.max_signal_distribution_score)].copy()
    data["opportunity_score"] = data["short_opportunity_score"]
    # Reuse the 22-day model trainer, which expects these canonical label names
    # for sample weighting and downstream utilities.
    data["max_runup_22d_pct"] = data["mfe_h_pct"]
    data["max_drawdown_22d_pct"] = data["max_drawdown_h_pct"]
    data["close_return_22d_pct"] = data["close_return_h_pct"]
    return data


def _evaluate_topk_short(df: pd.DataFrame, spec: HorizonSpec, top_ks: Sequence[int] = (1, 3, 5)) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if df.empty:
        return rows
    ranked = df.sort_values(["trade_date", "final_score", "symbol"], ascending=[True, False, True])
    for top_k in top_ks:
        picks = ranked.groupby("trade_date", as_index=False).head(int(top_k)).copy()
        if picks.empty:
            continue
        mfe = pd.to_numeric(picks["mfe_h_pct"], errors="coerce").fillna(0.0)
        close_ret = pd.to_numeric(picks["close_return_h_pct"], errors="coerce").fillna(0.0)
        row: Dict[str, Any] = {
            "horizon_days": int(spec.horizon_days),
            "top_k": int(top_k),
            "days": int(picks["trade_date"].nunique()),
            "picks": int(len(picks)),
            "avg_mfe_pct": round(float(mfe.mean()), 4),
            "median_mfe_pct": round(float(mfe.median()), 4),
            "avg_close_return_pct": round(float(close_ret.mean()), 4),
            "median_close_return_pct": round(float(close_ret.median()), 4),
            "avg_days_to_mfe": round(float(pd.to_numeric(picks["days_to_mfe"], errors="coerce").fillna(0.0).mean()), 2),
            "avg_mdd_to_mfe_pct": round(float(pd.to_numeric(picks["mdd_to_mfe_pct"], errors="coerce").fillna(0.0).mean()), 4),
            "avg_entry_gap_pct": round(float(pd.to_numeric(picks["entry_gap_pct"], errors="coerce").fillna(0.0).mean()), 4),
        }
        for threshold in spec.target_thresholds:
            key = f"hit{int(threshold)}_rate"
            row[key] = round(float((mfe >= threshold).mean()), 4)
            misses = picks[mfe < threshold]
            row[f"miss{int(threshold)}_avg_close_return_pct"] = (
                round(float(pd.to_numeric(misses["close_return_h_pct"], errors="coerce").fillna(0.0).mean()), 4)
                if not misses.empty
                else 0.0
            )
        rows.append(row)
    return rows


def _policy_to_exit_policy(policy: ShortExitPolicy) -> base.ExitPolicy:
    return base.ExitPolicy(
        name=policy.name,
        target_profit_pct=policy.target_profit_pct,
        stop_loss_pct=policy.stop_loss_pct,
        time_exit_days=policy.horizon_days,
        time_exit_price="atomic_close",
    )


def _top1_orders(
    scored: pd.DataFrame,
    atomic: pd.DataFrame,
    config: base.OpportunityConfig,
    policy: ShortExitPolicy,
    signal_month: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    if signal_month:
        scored = scored[scored["trade_date"].astype(str).str.startswith(signal_month)].copy()
    if scored.empty:
        return [], 0
    ranked = scored.sort_values(["trade_date", "final_score", "symbol"], ascending=[True, False, True])
    top = ranked.groupby("trade_date", as_index=False).head(1).copy()
    keys = [(str(row["symbol"]), str(row["trade_date"])) for _, row in top.iterrows()]
    path_map = base._future_path_map(atomic, config, keys=keys)
    orders: List[Dict[str, Any]] = []
    skipped = 0
    for _, row in top.iterrows():
        symbol = str(row["symbol"])
        trade_date = str(row["trade_date"])
        future = path_map.get((symbol, trade_date))
        if future is None or future.empty:
            skipped += 1
            continue
        sim = base._simulate_exit_policy(future, _policy_to_exit_policy(policy), config)
        gross_entry = base._to_float(sim.get("gross_entry_price"))
        gross_exit = base._to_float(sim.get("gross_exit_price"))
        exit_date = str(sim.get("exit_date", ""))
        if gross_entry <= 0 or gross_exit <= 0 or not exit_date:
            skipped += 1
            continue
        orders.append(
            {
                "horizon_days": int(policy.horizon_days),
                "policy": policy.name,
                "trade_date": trade_date,
                "entry_date": str(future.iloc[0]["trade_date"]),
                "symbol": symbol,
                "weight": 0.80,
                "final_score": round(base._to_float(row.get("final_score")), 4),
                "mfe_h_pct": round(base._to_float(row.get("mfe_h_pct")), 4),
                "close_return_h_pct": round(base._to_float(row.get("close_return_h_pct")), 4),
                "net_entry_price": base._apply_buy_cost(gross_entry, config),
                "net_exit_price": base._apply_sell_cost(gross_exit, config),
                **sim,
            }
        )
    return orders, skipped


def _simulate_orders_account(
    orders: List[Dict[str, Any]],
    atomic: pd.DataFrame,
    config: base.OpportunityConfig,
    *,
    initial_capital: float = 1_000_000.0,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    if not orders:
        return pd.DataFrame(), pd.DataFrame(), {"trades": 0}
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

    def mark_position(pos: Dict[str, Any], trade_date: str) -> float:
        rec = record_at(str(pos["symbol"]), trade_date)
        if rec is None:
            return float(pos["cost_cash"])
        price = base._to_float(rec.get("atomic_close"))
        return float(pos["shares"]) * base._apply_sell_cost(price, config) if price > 0 else float(pos["cost_cash"])

    min_position_cash = max(20_000.0, initial_capital * 0.02)
    cash = float(initial_capital)
    positions: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    curve: List[Dict[str, Any]] = []
    skipped_cash = 0
    skipped_duplicate = 0

    for current_date in calendar:
        equity_for_sizing = cash + sum(mark_position(pos, current_date) for pos in positions)
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
                        "net_return_pct": round(float(pnl / float(pos["cost_cash"]) * 100.0), 4),
                    }
                )
                trades.append(record)
            else:
                still_open.append(pos)
        positions = still_open
        equity = cash + sum(mark_position(pos, current_date) for pos in positions)
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
        return trades_df, curve_df, {"trades": 0}
    equity_curve = pd.Series([float(initial_capital)] + curve_df["equity"].astype(float).tolist())
    peak = equity_curve.cummax()
    dd = equity_curve / peak - 1.0
    returns = trades_df["net_return_pct"].astype(float) if not trades_df.empty else pd.Series(dtype=float)
    summary = {
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
        "max_open_positions": int(curve_df["open_positions"].max()) if "open_positions" in curve_df else 0,
        "avg_cash_pct": round(float((curve_df["cash"].astype(float) / curve_df["equity"].replace(0, np.nan).astype(float)).mean() * 100.0), 4),
    }
    return trades_df, curve_df, summary


def _latest_candidates(
    panel: pd.DataFrame,
    models: Dict[int, Any],
    feature_cols: Sequence[str],
    config: base.OpportunityConfig,
) -> pd.DataFrame:
    latest_date = str(panel["trade_date"].max())
    latest0 = panel[panel["trade_date"] == latest_date].copy()
    latest0 = latest0[latest0["risk_flag_type"].fillna("normal").eq("normal")].copy()
    latest0 = latest0[pd.to_numeric(latest0["total_amount"], errors="coerce").fillna(0.0) >= float(config.min_signal_amount)].copy()
    latest0 = latest0[pd.to_numeric(latest0["return_20d_pct"], errors="coerce").fillna(0.0) <= float(config.max_signal_return_20d_pct)].copy()
    latest0 = latest0[pd.to_numeric(latest0["distribution_score"], errors="coerce").fillna(0.0) <= float(config.max_signal_distribution_score)].copy()
    rows: List[pd.DataFrame] = []
    for horizon, model in models.items():
        latest = latest0.copy()
        if latest.empty:
            continue
        missing = [col for col in feature_cols if col not in latest.columns]
        for col in missing:
            latest[col] = 0.0
        latest["model_score"] = model.predict(latest[list(feature_cols)])
        latest["rule_score"] = base._score_rule_baseline(latest)
        latest["final_score"] = 0.78 * latest["model_score"] + 0.22 * latest["rule_score"]
        latest["operability_penalty"] = (
            latest.get("signal_locked_limit_up_like", 0).astype(float) * 24.0
            + latest.get("signal_limit_up_like", 0).astype(float) * 9.0
            + np.clip((latest["return_20d_pct"].astype(float) - 70.0) / 25.0, 0.0, 1.0) * 7.0
            + np.clip((latest["distribution_score"].astype(float) - 65.0) / 20.0, 0.0, 1.0) * 8.0
        )
        latest["action_score"] = latest["final_score"] - latest["operability_penalty"]
        latest["horizon_days"] = int(horizon)
        latest["rank"] = latest.sort_values(["action_score", "symbol"], ascending=[False, True]).groupby("horizon_days").cumcount() + 1
        rows.append(latest.sort_values(["action_score", "symbol"], ascending=[False, True]).head(10))
    if not rows:
        return pd.DataFrame()
    keep = [
        "horizon_days",
        "rank",
        "trade_date",
        "symbol",
        "action_score",
        "final_score",
        "model_score",
        "rule_score",
        "close",
        "daily_return_pct",
        "return_5d_pct",
        "return_20d_pct",
        "total_amount",
        "breakout_score",
        "stealth_score",
        "distribution_score",
        "l2_main_net_ratio",
        "active_buy_strength",
        "signal_limit_up_like",
        "signal_locked_limit_up_like",
    ]
    out = pd.concat(rows, ignore_index=True)
    return out[[col for col in keep if col in out.columns]].sort_values(["horizon_days", "rank"])


def train_command(args: argparse.Namespace) -> None:
    config = base.OpportunityConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        validation_start=args.validation_start,
        horizon_days=max(spec.horizon_days for spec in HORIZONS),
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    panel, atomic = _build_feature_panel(config)
    all_label_parts: List[pd.DataFrame] = []
    topk_rows: List[Dict[str, Any]] = []
    policy_rows: List[Dict[str, Any]] = []
    monthly_rows: List[Dict[str, Any]] = []
    trade_parts: List[pd.DataFrame] = []
    model_payload: Dict[int, Any] = {}
    feature_cols: List[str] = []

    for spec in HORIZONS:
        print(f"=== horizon {spec.horizon_days}d ===", flush=True)
        data = _build_horizon_dataset(panel, atomic, config, spec)
        if data.empty:
            continue
        if not feature_cols:
            feature_cols = base.available_feature_columns(data, include_orderbook=False)
        train = data[pd.to_datetime(data["label_complete_asof_date"]) < pd.to_datetime(str(config.validation_start))].copy()
        valid = data[data["trade_date"] >= str(config.validation_start)].copy()
        train_filtered = base._apply_historical_entry_filter(train, config)
        valid_filtered = base._apply_historical_entry_filter(valid, config)
        if train_filtered.empty or valid_filtered.empty:
            continue
        model = base._fit_model(train_filtered, feature_cols, config)
        model_payload[int(spec.horizon_days)] = model
        for part in [train_filtered, valid_filtered]:
            part["model_score"] = model.predict(part[feature_cols])
            part["rule_score"] = base._score_rule_baseline(part)
            part["final_score"] = 0.78 * part["model_score"] + 0.22 * part["rule_score"]

        valid_scored = valid_filtered.copy()
        valid_scored["split"] = "validation"
        valid_scored["horizon_days"] = int(spec.horizon_days)
        all_label_parts.append(
            valid_scored[
                [
                    "horizon_days",
                    "symbol",
                    "trade_date",
                    "entry_date",
                    "label_end_date",
                    "entry_open",
                    "entry_gap_pct",
                    "mfe_h_pct",
                    "mdd_to_mfe_pct",
                    "max_drawdown_h_pct",
                    "close_return_h_pct",
                    "days_to_mfe",
                    "short_opportunity_score",
                    "model_score",
                    "rule_score",
                    "final_score",
                ]
            ].copy()
        )
        topk_rows.extend(_evaluate_topk_short(valid_scored, spec, top_ks=(1, 3, 5)))

        months = sorted({_month_key(d) for d in valid_scored["trade_date"].astype(str).unique()})
        horizon_config = base.OpportunityConfig(
            start_date=config.start_date,
            end_date=config.end_date,
            validation_start=config.validation_start,
            horizon_days=spec.horizon_days,
        )
        for policy in EXIT_POLICIES[int(spec.horizon_days)]:
            orders, skipped_no_path = _top1_orders(valid_scored, atomic, horizon_config, policy)
            trades_df, _, summary = _simulate_orders_account(orders, atomic, horizon_config)
            summary.update(
                {
                    "horizon_days": int(spec.horizon_days),
                    "policy": policy.name,
                    "signal_month": "ALL",
                    "skipped_no_path": int(skipped_no_path),
                }
            )
            policy_rows.append(summary)
            if not trades_df.empty:
                trades_df["signal_month"] = "ALL"
                trade_parts.append(trades_df)
            for month in months:
                month_orders, month_skipped = _top1_orders(valid_scored, atomic, horizon_config, policy, signal_month=month)
                month_trades, _, month_summary = _simulate_orders_account(month_orders, atomic, horizon_config)
                month_summary.update(
                    {
                        "horizon_days": int(spec.horizon_days),
                        "policy": policy.name,
                        "signal_month": month,
                        "skipped_no_path": int(month_skipped),
                    }
                )
                monthly_rows.append(month_summary)

        if args.save_train_labels:
            train_sample = train_filtered.sample(n=min(80_000, len(train_filtered)), random_state=42).copy()
            train_sample["split"] = "train_sample"
            train_sample["horizon_days"] = int(spec.horizon_days)
            all_label_parts.append(
                train_sample[
                    [
                        "horizon_days",
                        "symbol",
                        "trade_date",
                        "entry_date",
                        "label_end_date",
                        "entry_open",
                        "entry_gap_pct",
                        "mfe_h_pct",
                        "mdd_to_mfe_pct",
                        "max_drawdown_h_pct",
                        "close_return_h_pct",
                        "days_to_mfe",
                        "short_opportunity_score",
                        "split",
                    ]
                ].copy()
            )

    if not model_payload:
        raise RuntimeError("No short-horizon models were trained")

    for horizon, model in model_payload.items():
        base._write_model(out_dir / f"model_h{horizon}.joblib", model)
    _json_dump(out_dir / "feature_columns.json", {"model_version": MODEL_VERSION, "features": feature_cols})

    labels_df = pd.concat(all_label_parts, ignore_index=True) if all_label_parts else pd.DataFrame()
    topk_df = pd.DataFrame(topk_rows)
    policy_df = pd.DataFrame(policy_rows)
    monthly_df = pd.DataFrame(monthly_rows)
    trades_df = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    latest_df = _latest_candidates(panel, model_payload, feature_cols, config)

    labels_df.to_csv(out_dir / "short_horizon_labels.csv.gz", index=False, compression="gzip")
    topk_df.to_csv(out_dir / "topk_summary_by_horizon.csv", index=False)
    policy_df.to_csv(out_dir / "portfolio_summary_by_horizon.csv", index=False)
    monthly_df.to_csv(out_dir / "monthly_portfolio_summary.csv", index=False)
    trades_df.to_csv(out_dir / "portfolio_trades.csv", index=False)
    latest_df.to_csv(out_dir / "latest_short_candidates.csv", index=False)

    best = (
        policy_df.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).head(20).to_dict(orient="records")
        if not policy_df.empty
        else []
    )
    monthly_best = (
        monthly_df.sort_values(["signal_month", "total_return_pct"], ascending=[True, False])
        .groupby("signal_month", as_index=False)
        .head(5)
        .to_dict(orient="records")
        if not monthly_df.empty
        else []
    )
    summary = {
        "model_version": MODEL_VERSION,
        "config": asdict(config),
        "horizons": [asdict(spec) for spec in HORIZONS],
        "exit_policies": {str(k): [asdict(p) for p in v] for k, v in EXIT_POLICIES.items()},
        "data": {
            "latest_date": str(panel["trade_date"].max()) if not panel.empty else None,
            "feature_count": int(len(feature_cols)),
            "validation_label_rows": int(len(labels_df[labels_df.get("split", "validation").eq("validation")])) if "split" in labels_df else int(len(labels_df)),
        },
        "best_overall": best,
        "monthly_best": monthly_best,
        "files": {
            "labels": str(out_dir / "short_horizon_labels.csv.gz"),
            "topk": str(out_dir / "topk_summary_by_horizon.csv"),
            "portfolio_summary": str(out_dir / "portfolio_summary_by_horizon.csv"),
            "monthly_summary": str(out_dir / "monthly_portfolio_summary.csv"),
            "trades": str(out_dir / "portfolio_trades.csv"),
            "latest": str(out_dir / "latest_short_candidates.csv"),
        },
    }
    _json_dump(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:12000])


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Train short-horizon opportunity discovery models")
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--start-date", default="2025-01-02")
    train.add_argument("--end-date", default="2026-05-14")
    train.add_argument("--validation-start", default="2026-03-02")
    train.add_argument("--out", default=str(OUT_DIR))
    train.add_argument("--save-train-labels", action="store_true")
    train.set_defaults(func=train_command)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
