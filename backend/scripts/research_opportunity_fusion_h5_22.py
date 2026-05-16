#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import research_opportunity_discovery_model as base
import research_opportunity_short_horizon as short


ROOT = Path(__file__).resolve().parents[2]
MODEL_VERSION = "fusion_h5_22_v0_1"
OPP22_DIR = ROOT / "data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1"
SHORT_DIR = ROOT / "data/selection/opportunity_discovery/short_horizon_v0_1"
OUT_DIR = ROOT / "data/selection/opportunity_discovery" / MODEL_VERSION


@dataclass(frozen=True)
class FusionStrategy:
    name: str
    description: str
    mode: str
    score_col: str
    filter_kind: str = "none"
    rank_22_max: Optional[int] = None
    rank_h5_max: Optional[int] = None


FUSION_STRATEGIES: Tuple[FusionStrategy, ...] = (
    FusionStrategy(
        name="baseline_22_top1",
        description="22日模型Top1基线",
        mode="top1",
        score_col="score_22",
    ),
    FusionStrategy(
        name="baseline_22_top1_top2_conditional",
        description="22日模型Top1+Top2条件买入基线",
        mode="top1_top2_conditional",
        score_col="score_22",
    ),
    FusionStrategy(
        name="fusion_70_30_top1",
        description="22日分数70% + H5同日标准化分数30%，在22日前20候选池内重排Top1",
        mode="top1",
        score_col="fusion_70_30",
    ),
    FusionStrategy(
        name="fusion_50_50_top1",
        description="22日分数50% + H5同日标准化分数50%，在22日前20候选池内重排Top1",
        mode="top1",
        score_col="fusion_50_50",
    ),
    FusionStrategy(
        name="fusion_70_30_top1_top2_conditional",
        description="融合分数Top1+Top2条件买入",
        mode="top1_top2_conditional",
        score_col="fusion_70_30",
    ),
    FusionStrategy(
        name="gate_22top1_h5rank_le5",
        description="只买22日Top1且H5全市场排名前5，否则空仓",
        mode="top1",
        score_col="score_22",
        filter_kind="gate_22_top1",
        rank_h5_max=5,
    ),
    FusionStrategy(
        name="gate_22top1_h5rank_le10",
        description="只买22日Top1且H5全市场排名前10，否则空仓",
        mode="top1",
        score_col="score_22",
        filter_kind="gate_22_top1",
        rank_h5_max=10,
    ),
    FusionStrategy(
        name="gate_22top1_h5rank_le20",
        description="只买22日Top1且H5全市场排名前20，否则空仓",
        mode="top1",
        score_col="score_22",
        filter_kind="gate_22_top1",
        rank_h5_max=20,
    ),
    FusionStrategy(
        name="gate_22top1_h5rank_le50",
        description="只买22日Top1且H5全市场排名前50，否则空仓",
        mode="top1",
        score_col="score_22",
        filter_kind="gate_22_top1",
        rank_h5_max=50,
    ),
    FusionStrategy(
        name="intersection_22top5_h5rank_le20",
        description="22日前5且H5全市场前20的交集里选融合Top1",
        mode="top1",
        score_col="fusion_70_30",
        filter_kind="intersection",
        rank_22_max=5,
        rank_h5_max=20,
    ),
    FusionStrategy(
        name="intersection_22top5_h5rank_le50",
        description="22日前5且H5全市场前50的交集里选融合Top1",
        mode="top1",
        score_col="fusion_70_30",
        filter_kind="intersection",
        rank_22_max=5,
        rank_h5_max=50,
    ),
)


BEST_22_HOLD_POLICY: Dict[str, Any] = {
    "name": "hold_model_tp15_stop12",
    "target_profit_pct": 15.0,
    "hard_stop_pct": -12.0,
    "exit_threshold": 2.0,
    "min_hold_days": 2,
    "max_holding_days": 22,
}

H5_EXIT_POLICY = base.ExitPolicy(
    name="h5_tp8_no_stop",
    target_profit_pct=8.0,
    stop_loss_pct=None,
    time_exit_days=5,
    time_exit_price="atomic_close",
)


def _json_dump(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _month_key(date: str) -> str:
    return str(date)[:7]


def _zscore_by_day(df: pd.DataFrame, col: str) -> pd.Series:
    values = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    mean = values.groupby(df["trade_date"]).transform("mean")
    std = values.groupby(df["trade_date"]).transform("std").replace(0.0, np.nan).fillna(1.0)
    return ((values - mean) / std).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def _build_fusion_base(opp22_dir: Path, short_dir: Path) -> pd.DataFrame:
    v22 = pd.read_csv(opp22_dir / "validation_topk.csv")
    h5 = pd.read_csv(short_dir / "short_horizon_labels.csv.gz")
    h5 = h5[pd.to_numeric(h5["horizon_days"], errors="coerce").fillna(0).astype(int).eq(5)].copy()
    if v22.empty or h5.empty:
        raise RuntimeError("22日验证候选或H5验证标签为空")

    v22 = v22.sort_values(["trade_date", "final_score", "symbol"], ascending=[True, False, True]).copy()
    v22["rank_22_pool"] = v22.groupby("trade_date").cumcount() + 1
    h5 = h5.sort_values(["trade_date", "final_score", "symbol"], ascending=[True, False, True]).copy()
    h5["rank_h5_full"] = h5.groupby("trade_date").cumcount() + 1

    h5_keep = [
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
        "rank_h5_full",
    ]
    merged = v22.merge(
        h5[[col for col in h5_keep if col in h5.columns]],
        on=["symbol", "trade_date"],
        how="inner",
        suffixes=("_22", "_h5"),
    )
    if merged.empty:
        raise RuntimeError("22日验证候选与H5验证标签无交集")

    merged["score_22"] = pd.to_numeric(merged["final_score_22"], errors="coerce").fillna(0.0)
    merged["score_h5"] = pd.to_numeric(merged["final_score_h5"], errors="coerce").fillna(0.0)
    merged["z22_pool"] = _zscore_by_day(merged, "score_22")
    merged["zh5_in_22_pool"] = _zscore_by_day(merged, "score_h5")
    day_22_mean = merged["score_22"].groupby(merged["trade_date"]).transform("mean")
    day_22_std = merged["score_22"].groupby(merged["trade_date"]).transform("std").replace(0.0, np.nan).fillna(1.0)
    merged["score_h5_on_22_scale"] = day_22_mean + merged["zh5_in_22_pool"] * day_22_std
    merged["fusion_70_30"] = 0.70 * merged["score_22"] + 0.30 * merged["score_h5_on_22_scale"]
    merged["fusion_50_50"] = 0.50 * merged["score_22"] + 0.50 * merged["score_h5_on_22_scale"]
    merged["fusion_40_60"] = 0.40 * merged["score_22"] + 0.60 * merged["score_h5_on_22_scale"]
    merged["h5_confirm_top5"] = (pd.to_numeric(merged["rank_h5_full"], errors="coerce").fillna(999999) <= 5).astype(int)
    merged["h5_confirm_top10"] = (pd.to_numeric(merged["rank_h5_full"], errors="coerce").fillna(999999) <= 10).astype(int)
    merged["h5_confirm_top20"] = (pd.to_numeric(merged["rank_h5_full"], errors="coerce").fillna(999999) <= 20).astype(int)
    merged["h5_confirm_top50"] = (pd.to_numeric(merged["rank_h5_full"], errors="coerce").fillna(999999) <= 50).astype(int)
    return merged


def _strategy_scored(base_df: pd.DataFrame, strategy: FusionStrategy) -> pd.DataFrame:
    scored = base_df.copy()
    if strategy.filter_kind == "gate_22_top1":
        scored = scored[
            (pd.to_numeric(scored["rank_22_pool"], errors="coerce").fillna(999999).astype(int) == 1)
            & (pd.to_numeric(scored["rank_h5_full"], errors="coerce").fillna(999999) <= float(strategy.rank_h5_max or 0))
        ].copy()
    elif strategy.filter_kind == "intersection":
        scored = scored[
            (pd.to_numeric(scored["rank_22_pool"], errors="coerce").fillna(999999) <= float(strategy.rank_22_max or 0))
            & (pd.to_numeric(scored["rank_h5_full"], errors="coerce").fillna(999999) <= float(strategy.rank_h5_max or 0))
        ].copy()
    if scored.empty:
        return scored
    scored["final_score"] = pd.to_numeric(scored[strategy.score_col], errors="coerce").fillna(0.0)
    scored["fusion_strategy"] = strategy.name
    return scored


def _ranked_entries(scored: pd.DataFrame, mode: str) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame()
    ranked = scored.sort_values(["trade_date", "final_score", "symbol"], ascending=[True, False, True]).copy()
    rows: List[pd.DataFrame] = []
    for _, day in ranked.groupby("trade_date", sort=True):
        if mode == "top1":
            pick = day.head(1).copy()
            pick["weight"] = 0.80
            rows.append(pick)
        elif mode == "top1_top2_conditional":
            pick = day.head(2).copy()
            if pick.empty:
                continue
            if len(pick) >= 2:
                top1_score = base._to_float(pick.iloc[0].get("final_score"))
                top2_score = base._to_float(pick.iloc[1].get("final_score"))
                if top2_score < top1_score - 6.0:
                    pick = pick.head(1).copy()
                    pick["weight"] = 0.70
                else:
                    pick["weight"] = [0.55, 0.35]
            else:
                pick["weight"] = 0.70
            rows.append(pick)
        else:
            raise ValueError(f"unknown mode: {mode}")
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _build_h5_exit_orders(
    scored: pd.DataFrame,
    atomic: pd.DataFrame,
    config: base.OpportunityConfig,
    *,
    strategy_name: str,
    mode: str,
) -> Tuple[List[Dict[str, Any]], int, pd.DataFrame]:
    entries = _ranked_entries(scored, mode)
    if entries.empty:
        return [], 0, entries
    keys = [(str(row["symbol"]), str(row["trade_date"])) for _, row in entries.iterrows()]
    path_map = base._future_path_map(atomic, config, keys=keys)
    orders: List[Dict[str, Any]] = []
    skipped_no_path = 0
    for _, row in entries.iterrows():
        symbol = str(row["symbol"])
        trade_date = str(row["trade_date"])
        future = path_map.get((symbol, trade_date))
        if future is None or future.empty:
            skipped_no_path += 1
            continue
        sim = base._simulate_exit_policy(future, H5_EXIT_POLICY, config)
        gross_entry = base._to_float(sim.get("gross_entry_price"))
        gross_exit = base._to_float(sim.get("gross_exit_price"))
        exit_date = str(sim.get("exit_date", ""))
        if gross_entry <= 0 or gross_exit <= 0 or not exit_date:
            skipped_no_path += 1
            continue
        orders.append(
            {
                "fusion_strategy": strategy_name,
                "mode": mode,
                "exit_shell": "h5_tp8_no_stop_day5",
                "trade_date": trade_date,
                "entry_date": str(future.iloc[0]["trade_date"]),
                "symbol": symbol,
                "weight": float(row.get("weight", 0.80)),
                "final_score": round(base._to_float(row.get("final_score")), 4),
                "score_22": round(base._to_float(row.get("score_22")), 4),
                "score_h5": round(base._to_float(row.get("score_h5")), 4),
                "rank_22_pool": int(base._to_float(row.get("rank_22_pool"), 0)),
                "rank_h5_full": int(base._to_float(row.get("rank_h5_full"), 0)),
                "max_runup_22d_pct": round(base._to_float(row.get("max_runup_22d_pct")), 4),
                "mfe_h_pct": round(base._to_float(row.get("mfe_h_pct")), 4),
                "close_return_h_pct": round(base._to_float(row.get("close_return_h_pct")), 4),
                "net_entry_price": base._apply_buy_cost(gross_entry, config),
                "net_exit_price": base._apply_sell_cost(gross_exit, config),
                **sim,
            }
        )
    return orders, skipped_no_path, entries


def _add_strategy_context(trades: pd.DataFrame, strategy: FusionStrategy, exit_shell: str, signal_month: str) -> pd.DataFrame:
    if trades.empty:
        return trades
    out = trades.copy()
    out["fusion_strategy"] = strategy.name
    out["strategy_description"] = strategy.description
    out["mode"] = strategy.mode
    out["exit_shell"] = exit_shell
    out["signal_month"] = signal_month
    return out


def _summarize_entries(scored: pd.DataFrame, strategy: FusionStrategy) -> Dict[str, Any]:
    if scored.empty:
        return {
            "fusion_strategy": strategy.name,
            "mode": strategy.mode,
            "signal_days": 0,
            "picked_rows": 0,
        }
    entries = _ranked_entries(scored, strategy.mode)
    if entries.empty:
        return {
            "fusion_strategy": strategy.name,
            "mode": strategy.mode,
            "signal_days": 0,
            "picked_rows": 0,
        }
    mfe22 = pd.to_numeric(entries["max_runup_22d_pct"], errors="coerce").fillna(0.0)
    mfe5 = pd.to_numeric(entries["mfe_h_pct"], errors="coerce").fillna(0.0)
    return {
        "fusion_strategy": strategy.name,
        "mode": strategy.mode,
        "signal_days": int(entries["trade_date"].nunique()),
        "picked_rows": int(len(entries)),
        "hit15_22d_rate": round(float((mfe22 >= 15.0).mean()), 4),
        "hit8_5d_rate": round(float((mfe5 >= 8.0).mean()), 4),
        "avg_mfe_22d_pct": round(float(mfe22.mean()), 4),
        "avg_mfe_5d_pct": round(float(mfe5.mean()), 4),
        "avg_rank_h5_full": round(float(pd.to_numeric(entries["rank_h5_full"], errors="coerce").fillna(0.0).mean()), 2),
        "symbols": ",".join(entries["symbol"].astype(str).head(12).tolist()),
    }


def _build_feature_panel_without_labels(
    config: base.OpportunityConfig,
    atomic_db: Path,
    selection_db: Path,
    heat_db: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    selection = base.load_selection_features(config.start_date, config.end_date, selection_db)
    atomic = base.add_atomic_features(base.load_atomic_daily(config.start_date, config.end_date, atomic_db))
    atomic_market = base.add_market_features(atomic)
    heat = base.load_heat_features(config.start_date, config.end_date, heat_db)
    panel = selection.merge(atomic_market, on=["symbol", "trade_date"], how="inner", suffixes=("", "_atomic_dup"))
    if not heat.empty:
        panel = panel.merge(heat, on=["symbol", "trade_date"], how="left")
    defaults = {
        "hot_theme_best_rank": 999.0,
        "hot_theme_score": 0.0,
        "hot_theme_persistence_score": 0.0,
        "hot_theme_member_count": 0.0,
        "hot_theme_is_top10": 0.0,
        "hot_theme_is_new_hot": 0.0,
        "hot_theme_is_continuing_hot": 0.0,
        "hot_theme_is_climax_hot": 0.0,
        "hot_theme_is_fading": 0.0,
        "board_type": "",
        "risk_flag_type": "normal",
    }
    for col, default in defaults.items():
        if col not in panel.columns:
            panel[col] = default
        else:
            panel[col] = panel[col].fillna(default)

    prev_for_limit = pd.to_numeric(panel.get("limit_prev_close", 0.0), errors="coerce")
    fallback_prev = pd.to_numeric(panel.get("prev_close", 0.0), errors="coerce")
    prev_for_limit = prev_for_limit.where(prev_for_limit > 0, fallback_prev).fillna(0.0)
    close_for_limit = pd.to_numeric(panel.get("atomic_close", panel.get("close", 0.0)), errors="coerce").fillna(0.0)
    high_for_limit = pd.to_numeric(panel.get("high", close_for_limit), errors="coerce").fillna(0.0)
    low_for_limit = pd.to_numeric(panel.get("low", close_for_limit), errors="coerce").fillna(0.0)
    open_for_limit = pd.to_numeric(panel.get("open", close_for_limit), errors="coerce").fillna(0.0)
    up_limit_price = pd.to_numeric(panel.get("up_limit_price", 0.0), errors="coerce").fillna(0.0)
    inferred_up_limit = np.where(up_limit_price > 0, up_limit_price, prev_for_limit * 1.10)
    inferred_limit_return = np.where(prev_for_limit > 0, (close_for_limit / prev_for_limit - 1.0) * 100.0, 0.0)
    signal_limit_up_like = (
        (prev_for_limit > 0)
        & (
            (pd.to_numeric(panel.get("is_limit_up_close", 0), errors="coerce").fillna(0.0) > 0)
            | (close_for_limit >= inferred_up_limit * 0.995)
            | (inferred_limit_return >= 9.85)
        )
    )
    signal_locked_limit_up_like = (
        signal_limit_up_like & (open_for_limit >= inferred_up_limit * 0.995) & (low_for_limit >= inferred_up_limit * 0.995)
    )
    panel["signal_is_limit_up_close"] = signal_limit_up_like.astype(float)
    panel["signal_limit_up_like"] = signal_limit_up_like.astype(float)
    panel["signal_locked_limit_up_like"] = signal_locked_limit_up_like.astype(float)
    panel["signal_touch_limit_up"] = (
        (pd.to_numeric(panel.get("touch_limit_up", 0), errors="coerce").fillna(0.0) > 0)
        | (high_for_limit >= inferred_up_limit * 0.995)
    ).astype(float)
    panel["signal_broken_limit_up"] = pd.to_numeric(panel.get("broken_limit_up", 0), errors="coerce").fillna(0.0)
    return panel, atomic


def _latest_fusion_candidates(
    panel: pd.DataFrame,
    opp22_dir: Path,
    short_dir: Path,
    config: base.OpportunityConfig,
) -> pd.DataFrame:
    feature_22 = _load_json(opp22_dir / "feature_columns.json")["features"]
    feature_h = _load_json(short_dir / "feature_columns.json")["features"]
    model_22 = base._read_model(opp22_dir / "model.joblib")
    model_h5 = base._read_model(short_dir / "model_h5.joblib")

    latest_date = str(panel["trade_date"].max())
    latest = panel[panel["trade_date"].eq(latest_date)].copy()
    latest = latest[latest["risk_flag_type"].fillna("normal").eq("normal")].copy()
    latest = latest[pd.to_numeric(latest["total_amount"], errors="coerce").fillna(0.0) >= float(config.min_signal_amount)].copy()
    latest = latest[pd.to_numeric(latest["return_20d_pct"], errors="coerce").fillna(0.0) <= float(config.max_signal_return_20d_pct)].copy()
    latest = latest[pd.to_numeric(latest["distribution_score"], errors="coerce").fillna(0.0) <= float(config.max_signal_distribution_score)].copy()
    if latest.empty:
        return latest

    for col in set(feature_22).union(feature_h):
        if col not in latest.columns:
            latest[col] = 0.0
    latest["model_score_22"] = model_22.predict(latest[list(feature_22)])
    latest["model_score_h5"] = model_h5.predict(latest[list(feature_h)])
    latest["rule_score"] = base._score_rule_baseline(latest)
    latest["score_22"] = 0.78 * latest["model_score_22"] + 0.22 * latest["rule_score"]
    latest["score_h5"] = 0.78 * latest["model_score_h5"] + 0.22 * latest["rule_score"]
    latest = latest.sort_values(["score_22", "symbol"], ascending=[False, True]).copy()
    latest["rank_22_full"] = np.arange(1, len(latest) + 1)
    latest = latest.sort_values(["score_h5", "symbol"], ascending=[False, True]).copy()
    latest["rank_h5_full"] = np.arange(1, len(latest) + 1)

    pool = latest[pd.to_numeric(latest["rank_22_full"], errors="coerce").fillna(999999) <= 80].copy()
    pool["z22_pool"] = (pool["score_22"] - pool["score_22"].mean()) / (pool["score_22"].std() or 1.0)
    pool["zh5_in_22_pool"] = (pool["score_h5"] - pool["score_h5"].mean()) / (pool["score_h5"].std() or 1.0)
    pool["score_h5_on_22_scale"] = pool["score_22"].mean() + pool["zh5_in_22_pool"] * (pool["score_22"].std() or 1.0)
    pool["fusion_70_30"] = 0.70 * pool["score_22"] + 0.30 * pool["score_h5_on_22_scale"]
    pool["fusion_50_50"] = 0.50 * pool["score_22"] + 0.50 * pool["score_h5_on_22_scale"]
    pool["operability_penalty"] = (
        pool.get("signal_locked_limit_up_like", 0).astype(float) * 24.0
        + pool.get("signal_limit_up_like", 0).astype(float) * 9.0
        + np.clip((pool["return_20d_pct"].astype(float) - 70.0) / 25.0, 0.0, 1.0) * 7.0
        + np.clip((pool["distribution_score"].astype(float) - 65.0) / 20.0, 0.0, 1.0) * 8.0
    )
    pool["fusion_action_score"] = pool["fusion_70_30"] - pool["operability_penalty"]
    pool["h5_confirm"] = np.select(
        [
            pool["rank_h5_full"].astype(float) <= 5,
            pool["rank_h5_full"].astype(float) <= 20,
            pool["rank_h5_full"].astype(float) <= 50,
        ],
        ["h5_top5", "h5_top20", "h5_top50"],
        default="h5_weak",
    )
    pool["tomorrow_buy_rule"] = "D+1开盘高开不超过6.8%、不接近涨停/一字板才考虑"
    keep = [
        "trade_date",
        "symbol",
        "name",
        "fusion_action_score",
        "fusion_70_30",
        "fusion_50_50",
        "score_22",
        "score_h5",
        "rank_22_full",
        "rank_h5_full",
        "h5_confirm",
        "operability_penalty",
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
        "tomorrow_buy_rule",
    ]
    return pool[[col for col in keep if col in pool.columns]].sort_values(["fusion_action_score", "symbol"], ascending=[False, True])


def _evaluate(
    fusion_base: pd.DataFrame,
    atomic: pd.DataFrame,
    feature_panel: pd.DataFrame,
    config22: base.OpportunityConfig,
    out_dir: Path,
    opp22_dir: Path,
    short_dir: Path,
) -> Dict[str, Any]:
    hold_model = base._read_model(opp22_dir / "holding_model.joblib")
    hold_features = _load_json(opp22_dir / "holding_feature_columns.json")["features"]
    config_h5 = base.OpportunityConfig(
        start_date=config22.start_date,
        end_date=config22.end_date,
        validation_start=config22.validation_start,
        horizon_days=5,
    )

    entry_summary_rows: List[Dict[str, Any]] = []
    hold_summary_rows: List[Dict[str, Any]] = []
    h5_summary_rows: List[Dict[str, Any]] = []
    monthly_rows: List[Dict[str, Any]] = []
    hold_trades_parts: List[pd.DataFrame] = []
    h5_trades_parts: List[pd.DataFrame] = []
    pick_parts: List[pd.DataFrame] = []
    months = sorted({_month_key(d) for d in fusion_base["trade_date"].astype(str).unique()})

    for strategy in FUSION_STRATEGIES:
        scored_all = _strategy_scored(fusion_base, strategy)
        entry_summary_rows.append(_summarize_entries(scored_all, strategy))
        picks = _ranked_entries(scored_all, strategy.mode)
        if not picks.empty:
            picks["fusion_strategy"] = strategy.name
            picks["mode"] = strategy.mode
            pick_parts.append(picks)

        for signal_month in ["ALL", *months]:
            scored = scored_all
            if signal_month != "ALL":
                scored = scored[scored["trade_date"].astype(str).str.startswith(signal_month)].copy()
            if scored.empty:
                continue

            hold_trades, hold_summary = base._simulate_portfolio(
                scored,
                atomic,
                feature_panel,
                hold_model,
                hold_features,
                config22,
                mode=strategy.mode,
                policy=BEST_22_HOLD_POLICY,
            )
            hold_summary.update(
                {
                    "fusion_strategy": strategy.name,
                    "strategy_description": strategy.description,
                    "mode": strategy.mode,
                    "exit_shell": "22_hold_model_tp15_stop12",
                    "signal_month": signal_month,
                }
            )
            if signal_month == "ALL":
                hold_summary_rows.append(hold_summary)
            else:
                monthly_rows.append(hold_summary)
            hold_trades = _add_strategy_context(hold_trades, strategy, "22_hold_model_tp15_stop12", signal_month)
            if not hold_trades.empty:
                hold_trades_parts.append(hold_trades)

            orders, skipped_no_path, _ = _build_h5_exit_orders(
                scored,
                atomic,
                config_h5,
                strategy_name=strategy.name,
                mode=strategy.mode,
            )
            h5_trades, _, h5_summary = short._simulate_orders_account(orders, atomic, config_h5)
            h5_summary.update(
                {
                    "fusion_strategy": strategy.name,
                    "strategy_description": strategy.description,
                    "mode": strategy.mode,
                    "exit_shell": "h5_tp8_no_stop_day5",
                    "signal_month": signal_month,
                    "skipped_no_path": int(skipped_no_path),
                }
            )
            if signal_month == "ALL":
                h5_summary_rows.append(h5_summary)
            else:
                monthly_rows.append(h5_summary)
            if not h5_trades.empty:
                h5_trades["fusion_strategy"] = strategy.name
                h5_trades["strategy_description"] = strategy.description
                h5_trades["mode"] = strategy.mode
                h5_trades["exit_shell"] = "h5_tp8_no_stop_day5"
                h5_trades["signal_month"] = signal_month
                h5_trades_parts.append(h5_trades)

    # Common-window H5 standalone baseline. This is not a 22日候选池策略;
    # it is included so the fusion result can be compared on the same dates.
    h5_labels = pd.read_csv(short_dir / "short_horizon_labels.csv.gz")
    h5_labels = h5_labels[pd.to_numeric(h5_labels["horizon_days"], errors="coerce").fillna(0).astype(int).eq(5)].copy()
    h5_labels = h5_labels[
        (h5_labels["trade_date"].astype(str) >= str(fusion_base["trade_date"].min()))
        & (h5_labels["trade_date"].astype(str) <= str(fusion_base["trade_date"].max()))
    ].copy()
    h5_labels["score_h5"] = pd.to_numeric(h5_labels["final_score"], errors="coerce").fillna(0.0)
    h5_labels["score_22"] = np.nan
    h5_labels["rank_22_pool"] = np.nan
    h5_labels = h5_labels.sort_values(["trade_date", "score_h5", "symbol"], ascending=[True, False, True]).copy()
    h5_labels["rank_h5_full"] = h5_labels.groupby("trade_date").cumcount() + 1
    h5_labels["final_score"] = h5_labels["score_h5"]
    orders, skipped_no_path, h5_entries = _build_h5_exit_orders(
        h5_labels,
        atomic,
        config_h5,
        strategy_name="baseline_h5_top1_common_window",
        mode="top1",
    )
    h5_trades, _, h5_summary = short._simulate_orders_account(orders, atomic, config_h5)
    h5_summary.update(
        {
            "fusion_strategy": "baseline_h5_top1_common_window",
            "strategy_description": "H5独立模型Top1，信号日期限制在22日验证窗口内",
            "mode": "top1",
            "exit_shell": "h5_tp8_no_stop_day5",
            "signal_month": "ALL",
            "skipped_no_path": int(skipped_no_path),
        }
    )
    h5_summary_rows.append(h5_summary)
    if not h5_trades.empty:
        h5_trades["fusion_strategy"] = "baseline_h5_top1_common_window"
        h5_trades["strategy_description"] = "H5独立模型Top1，信号日期限制在22日验证窗口内"
        h5_trades["mode"] = "top1"
        h5_trades["exit_shell"] = "h5_tp8_no_stop_day5"
        h5_trades["signal_month"] = "ALL"
        h5_trades_parts.append(h5_trades)
    if not h5_entries.empty:
        h5_entries["fusion_strategy"] = "baseline_h5_top1_common_window"
        h5_entries["mode"] = "top1"
        pick_parts.append(h5_entries)

    entry_summary = pd.DataFrame(entry_summary_rows)
    hold_summary = pd.DataFrame(hold_summary_rows)
    h5_summary = pd.DataFrame(h5_summary_rows)
    monthly_summary = pd.DataFrame(monthly_rows)
    hold_trades_df = pd.concat(hold_trades_parts, ignore_index=True) if hold_trades_parts else pd.DataFrame()
    h5_trades_df = pd.concat(h5_trades_parts, ignore_index=True) if h5_trades_parts else pd.DataFrame()
    picks_df = pd.concat(pick_parts, ignore_index=True) if pick_parts else pd.DataFrame()
    all_trades = pd.concat([hold_trades_df, h5_trades_df], ignore_index=True, sort=False) if not (hold_trades_df.empty and h5_trades_df.empty) else pd.DataFrame()

    entry_summary.to_csv(out_dir / "fusion_entry_summary.csv", index=False)
    hold_summary.to_csv(out_dir / "fusion_holding_portfolio_summary.csv", index=False)
    h5_summary.to_csv(out_dir / "fusion_h5_exit_portfolio_summary.csv", index=False)
    monthly_summary.to_csv(out_dir / "fusion_monthly_summary.csv", index=False)
    hold_trades_df.to_csv(out_dir / "fusion_holding_trades.csv", index=False)
    h5_trades_df.to_csv(out_dir / "fusion_h5_exit_trades.csv", index=False)
    all_trades.to_csv(out_dir / "fusion_trades.csv", index=False)
    picks_df.to_csv(out_dir / "fusion_picks.csv", index=False)

    def _top(df: pd.DataFrame, n: int = 10) -> List[Dict[str, Any]]:
        if df.empty or "total_return_pct" not in df.columns:
            return []
        return (
            df.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False])
            .head(n)
            .to_dict(orient="records")
        )

    return {
        "entry_summary_top": entry_summary.to_dict(orient="records"),
        "best_22_hold_shell": _top(hold_summary, 12),
        "best_h5_exit_shell": _top(h5_summary, 12),
        "files": {
            "entry_summary": str(out_dir / "fusion_entry_summary.csv"),
            "holding_summary": str(out_dir / "fusion_holding_portfolio_summary.csv"),
            "h5_exit_summary": str(out_dir / "fusion_h5_exit_portfolio_summary.csv"),
            "monthly_summary": str(out_dir / "fusion_monthly_summary.csv"),
            "trades": str(out_dir / "fusion_trades.csv"),
            "picks": str(out_dir / "fusion_picks.csv"),
        },
    }


def run_command(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    config22 = base.OpportunityConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        validation_start=args.validation_start,
        horizon_days=22,
    )
    fusion_base = _build_fusion_base(Path(args.opp22_dir), Path(args.short_dir))
    fusion_base.to_csv(out_dir / "fusion_scores.csv.gz", index=False, compression="gzip")

    feature_panel, atomic = _build_feature_panel_without_labels(
        config22,
        Path(args.atomic_db),
        Path(args.selection_db),
        Path(args.heat_db),
    )
    evaluation = _evaluate(fusion_base, atomic, feature_panel, config22, out_dir, Path(args.opp22_dir), Path(args.short_dir))
    latest = _latest_fusion_candidates(feature_panel, Path(args.opp22_dir), Path(args.short_dir), config22)
    latest.to_csv(out_dir / "latest_fusion_candidates.csv", index=False)

    existing_22_summary = pd.read_csv(Path(args.opp22_dir) / "holding_model_portfolio_summary.csv")
    existing_h5_summary = pd.read_csv(Path(args.short_dir) / "portfolio_summary_by_horizon.csv")
    best_22_existing = (
        existing_22_summary.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False])
        .head(5)
        .to_dict(orient="records")
    )
    best_h5_existing = (
        existing_h5_summary.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False])
        .head(5)
        .to_dict(orient="records")
    )
    summary = {
        "model_version": MODEL_VERSION,
        "config": asdict(config22),
        "source_dirs": {
            "opp22_dir": str(Path(args.opp22_dir)),
            "short_dir": str(Path(args.short_dir)),
        },
        "data": {
            "fusion_rows": int(len(fusion_base)),
            "signal_dates": [str(fusion_base["trade_date"].min()), str(fusion_base["trade_date"].max())],
            "signal_days": int(fusion_base["trade_date"].nunique()),
            "candidate_pool": "22日validation_topk每日前20名，与H5全市场验证得分按symbol/trade_date合并",
            "latest_date": str(feature_panel["trade_date"].max()) if not feature_panel.empty else None,
        },
        "strategies": [asdict(s) for s in FUSION_STRATEGIES],
        "evaluation": evaluation,
        "existing_baselines": {
            "best_22_existing": best_22_existing,
            "best_h5_existing_full_window": best_h5_existing,
        },
        "latest_fusion_top10": latest.head(10).to_dict(orient="records") if not latest.empty else [],
        "files": {
            "fusion_scores": str(out_dir / "fusion_scores.csv.gz"),
            "latest_fusion_candidates": str(out_dir / "latest_fusion_candidates.csv"),
            **evaluation["files"],
        },
        "caveats": [
            "融合回测没有重新训练模型，使用已落盘的22日验证Top20候选和H5验证得分。",
            "22日候选池只有每日前20名，因此重排结论只代表候选池内融合，不代表H5+22全市场联合排序。",
            "22日持仓模型仍是评估壳，不是成熟离场模型。",
        ],
    }
    _json_dump(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:14000])


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate H5 + 22d opportunity model fusion")
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
    run.add_argument("--out", default=str(OUT_DIR))
    run.set_defaults(func=run_command)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
