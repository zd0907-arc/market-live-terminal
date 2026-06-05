#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from backend.scripts import research_probe_signal_probability_framework as sp


OUT_DIR = ROOT / "docs/strategy-rework/experiments/20260603-probe-lift-research"
MIN_RULE_SAMPLE = 8


def ensure_probability_artifacts() -> None:
    required = [
        OUT_DIR / "probe_limitup_candidate_pool.csv",
        OUT_DIR / "probe_trend_candidate_pool.csv",
    ]
    if any(not path.exists() for path in required):
        sp.main()


def build_base_frame() -> pd.DataFrame:
    probes = sp.load_probe_events()
    feature_df = sp.load_feature_store(probes)
    daily, limit_df = sp.load_daily_and_limit(probes)
    frame = sp.build_feature_frame(probes, feature_df)
    frame = sp.build_confirmation_features(frame, feature_df)
    frame = sp.build_targets(frame, daily, limit_df)
    frame = sp.add_group_flags(frame)
    return frame


def load_probability_pools() -> tuple[pd.DataFrame, pd.DataFrame]:
    limit_pool = pd.read_csv(OUT_DIR / "probe_limitup_candidate_pool.csv")
    trend_pool = pd.read_csv(OUT_DIR / "probe_trend_candidate_pool.csv")
    return limit_pool, trend_pool


def merge_probability_pools(frame: pd.DataFrame, limit_pool: pd.DataFrame, trend_pool: pd.DataFrame) -> pd.DataFrame:
    out = frame.merge(
        limit_pool[["symbol", "trade_date", "limitup_probability", "limitup_probability_sample_split"]],
        on=["symbol", "trade_date"],
        how="left",
    )
    out = out.merge(
        trend_pool[["symbol", "trade_date", "trend20_probability", "trend20_probability_sample_split"]],
        on=["symbol", "trade_date"],
        how="left",
    )
    return out


def build_entry_metrics(frame: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["trade_date"] = daily["trade_date"].astype(str)
    daily = daily.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    by_symbol = {symbol: group.reset_index(drop=True) for symbol, group in daily.groupby("symbol", sort=False)}
    rows: List[Dict[str, float]] = []
    for rec in frame[["symbol", "trade_date"]].itertuples(index=False):
        row: Dict[str, float] = {"symbol": rec.symbol, "trade_date": rec.trade_date}
        group = by_symbol.get(rec.symbol)
        if group is None:
            rows.append(row)
            continue
        pos = group.index[group["trade_date"].eq(rec.trade_date)].tolist()
        if not pos:
            rows.append(row)
            continue
        i = pos[0]
        if i + 1 >= len(group):
            rows.append(row)
            continue
        entry_open = pd.to_numeric(group.loc[i + 1, "open"], errors="coerce")
        row["entry_open_d1"] = entry_open
        for horizon in (1, 3, 5, 10):
            window = group.iloc[i + 1 : i + 1 + horizon].copy().reset_index(drop=True)
            eligible = len(window) == horizon and pd.notna(entry_open) and entry_open > 0
            row[f"eligible_entry_{horizon}d"] = int(eligible)
            if eligible:
                row[f"entry_close_{horizon}d_pct"] = (pd.to_numeric(window.iloc[-1]["close"], errors="coerce") / entry_open - 1.0) * 100.0
                row[f"entry_high_{horizon}d_pct"] = (pd.to_numeric(window["high"], errors="coerce").max() / entry_open - 1.0) * 100.0
                row[f"entry_low_{horizon}d_pct"] = (pd.to_numeric(window["low"], errors="coerce").min() / entry_open - 1.0) * 100.0
            else:
                row[f"entry_close_{horizon}d_pct"] = np.nan
                row[f"entry_high_{horizon}d_pct"] = np.nan
                row[f"entry_low_{horizon}d_pct"] = np.nan
        window10 = group.iloc[i + 1 : i + 11].copy().reset_index(drop=True)
        if len(window10) and pd.notna(entry_open) and entry_open > 0:
            up5 = np.nan
            down5 = np.nan
            up8 = np.nan
            down8 = np.nan
            for j, bar in window10.iterrows():
                high_ret = (pd.to_numeric(bar["high"], errors="coerce") / entry_open - 1.0) * 100.0
                low_ret = (pd.to_numeric(bar["low"], errors="coerce") / entry_open - 1.0) * 100.0
                if pd.isna(up5) and high_ret >= 5:
                    up5 = j + 1
                if pd.isna(down5) and low_ret <= -5:
                    down5 = j + 1
                if pd.isna(up8) and high_ret >= 8:
                    up8 = j + 1
                if pd.isna(down8) and low_ret <= -8:
                    down8 = j + 1
            row["days_to_entry_up5_10d"] = up5
            row["days_to_entry_down5_10d"] = down5
            row["days_to_entry_up8_10d"] = up8
            row["days_to_entry_down8_10d"] = down8
            row["entry_t5s5"] = first_barrier_score(up5, down5, 5, -5)
            row["entry_t8s8"] = first_barrier_score(up8, down8, 8, -8)
        rows.append(row)
    return pd.DataFrame(rows)


def first_barrier_score(up_day: float, down_day: float, up_value: int, down_value: int) -> int:
    if pd.isna(up_day) and pd.isna(down_day):
        return 0
    if pd.isna(down_day):
        return up_value
    if pd.isna(up_day):
        return down_value
    return up_value if up_day <= down_day else down_value


def build_enriched_pool(frame: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    entry_metrics = build_entry_metrics(frame, daily)
    out = frame.merge(entry_metrics, on=["symbol", "trade_date"], how="left")
    keep_cols = [
        "symbol",
        "trade_date",
        "probe_index",
        "oib_ratio",
        "same_day_pullback_ratio",
        "day_gap_pct",
        "probe_strength_score",
        "hot_theme_best_rank",
        "hot_theme_score",
        "hot_theme_is_top10",
        "confirm_d1_pos",
        "confirm_d3_pos",
        "confirm_d5_pos",
        "limitup_probability",
        "limitup_probability_sample_split",
        "trend20_probability",
        "trend20_probability_sample_split",
        "target_limitup",
        "target_limitup_extend",
        "target_trend20",
        "target_trend40",
        "high_20d_pct",
        "high_40d_pct",
        "entry_close_1d_pct",
        "entry_close_3d_pct",
        "entry_close_5d_pct",
        "entry_close_10d_pct",
        "entry_high_10d_pct",
        "entry_low_5d_pct",
        "entry_t5s5",
        "entry_t8s8",
        "d1_oib_ratio",
        "d3_oib_ratio",
        "d5_oib_ratio",
        "d1_l2_super_net_ratio",
        "d3_l2_super_net_ratio",
        "d5_l2_super_net_ratio",
        "d1_l2_main_net_ratio",
        "d3_l2_main_net_ratio",
        "d5_l2_main_net_ratio",
        "buy_support_ratio",
        "sell_pressure_ratio",
        "support_pressure_spread",
        "add_buy_ratio",
        "cancel_sell_ratio",
        "close_book_imbalance_ratio",
        "avg_book_imbalance_ratio",
        "close_bid_ask_amount_ratio",
        "price_position_20d",
        "price_position_60d",
        "breakout_vs_prev20_high_pct",
        "drawdown_from_20d_high_pct",
        "amount_vs_day_median",
        "positive_oib_bar_ratio",
        "positive_l2_bar_ratio",
        "oib_top3_concentration_ratio",
        "market_limit_up_count",
        "market_broken_limit_up_ratio",
        "market_advancer_ratio",
        "hot_theme_is_new_hot",
        "hot_theme_is_continuing_hot",
        "hot_theme_is_fading",
        "csi1000_above_ma20",
        "csi1000_return_5d_pct",
        "csi500_return_5d_pct",
        "hs300_return_5d_pct",
        "gem_index_return_5d_pct",
    ]
    for col in keep_cols:
        if col not in out.columns:
            out[col] = np.nan
    return out[keep_cols].copy()


def assign_prob_bucket(df: pd.DataFrame, prob_col: str) -> pd.DataFrame:
    out = df.copy()
    out["prob_bucket"] = pd.qcut(out[prob_col].rank(method="first"), q=3, labels=["low", "mid", "high"])
    return out


def build_bucket_trade_metrics(valid_limit: pd.DataFrame, valid_trend: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, float]] = []
    specs = [
        ("limitup", valid_limit, "limitup_probability", "target_limitup", "target_limitup_extend"),
        ("trend", valid_trend, "trend20_probability", "target_trend20", "target_trend40"),
    ]
    for pool, df, prob_col, target_col, extra_col in specs:
        for bucket, group in df.groupby("prob_bucket"):
            rows.append(
                {
                    "pool": pool,
                    "bucket": str(bucket),
                    "sample_count": len(group),
                    "avg_probability": group[prob_col].mean(),
                    "hit_rate": group[target_col].mean(),
                    "extra_rate": group[extra_col].mean(),
                    "avg_high20_pct": group["high_20d_pct"].mean(),
                    "avg_high40_pct": group["high_40d_pct"].mean(),
                    "entry_1d_win_rate": (group["entry_close_1d_pct"] > 0).mean(),
                    "entry_1d_avg_pct": group["entry_close_1d_pct"].mean(),
                    "entry_3d_win_rate": (group["entry_close_3d_pct"] > 0).mean(),
                    "entry_3d_avg_pct": group["entry_close_3d_pct"].mean(),
                    "entry_5d_win_rate": (group["entry_close_5d_pct"] > 0).mean(),
                    "entry_5d_avg_pct": group["entry_close_5d_pct"].mean(),
                    "entry_10d_win_rate": (group["entry_close_10d_pct"] > 0).mean(),
                    "entry_10d_avg_pct": group["entry_close_10d_pct"].mean(),
                    "entry_5d_low_le_-5_rate": (group["entry_low_5d_pct"] <= -5).mean(),
                    "entry_10d_high_ge_5_rate": (group["entry_high_10d_pct"] >= 5).mean(),
                    "entry_t5s5_avg": group["entry_t5s5"].mean(),
                    "entry_t5s5_win_rate": (group["entry_t5s5"] > 0).mean(),
                    "entry_t8s8_avg": group["entry_t8s8"].mean(),
                    "entry_t8s8_win_rate": (group["entry_t8s8"] > 0).mean(),
                }
            )
    return pd.DataFrame(rows)


def build_rule_exploration(valid_limit: pd.DataFrame, valid_trend: pd.DataFrame) -> pd.DataFrame:
    rules: List[Dict[str, float]] = []
    for pool, df in (
        ("limitup", valid_limit[valid_limit["prob_bucket"] == "high"].copy()),
        ("trend", valid_trend[valid_trend["prob_bucket"] == "high"].copy()),
    ):
        q = high_bucket_quantiles(
            df,
            [
                "d1_oib_ratio",
                "d3_oib_ratio",
                "d1_l2_super_net_ratio",
                "d3_l2_super_net_ratio",
                "buy_support_ratio",
                "support_pressure_spread",
                "cancel_sell_ratio",
                "add_buy_ratio",
                "close_book_imbalance_ratio",
                "price_position_20d",
                "drawdown_from_20d_high_pct",
                "amount_vs_day_median",
                "hot_theme_score",
                "positive_oib_bar_ratio",
                "positive_l2_bar_ratio",
                "oib_top3_concentration_ratio",
                "market_limit_up_count",
                "market_advancer_ratio",
            ],
        )
        add_rule(rules, df, pool, "base_high_bucket", pd.Series(True, index=df.index))
        add_rule(rules, df, pool, "confirm_d1_pos", df["confirm_d1_pos"] == 1)
        add_rule(rules, df, pool, "confirm_d3_pos", df["confirm_d3_pos"] == 1)
        add_rule(rules, df, pool, "confirm_d1_d3_both_pos", (df["confirm_d1_pos"] == 1) & (df["confirm_d3_pos"] == 1))
        add_rule(rules, df, pool, "hot_theme_top10", pd.to_numeric(df["hot_theme_best_rank"], errors="coerce") <= 10)
        add_rule(rules, df, pool, "hot_theme_top5", pd.to_numeric(df["hot_theme_best_rank"], errors="coerce") <= 5)

        if "d3_oib_ratio" in q:
            add_rule(rules, df, pool, "d3_oib_high", pd.to_numeric(df["d3_oib_ratio"], errors="coerce") >= q["d3_oib_ratio"]["p60"])
        if "d1_oib_ratio" in q:
            add_rule(rules, df, pool, "d1_oib_high", pd.to_numeric(df["d1_oib_ratio"], errors="coerce") >= q["d1_oib_ratio"]["p60"])
        if "d1_l2_super_net_ratio" in q:
            add_rule(rules, df, pool, "d1_super_high", pd.to_numeric(df["d1_l2_super_net_ratio"], errors="coerce") >= q["d1_l2_super_net_ratio"]["p60"])
        if "d3_l2_super_net_ratio" in q:
            add_rule(rules, df, pool, "d3_super_high", pd.to_numeric(df["d3_l2_super_net_ratio"], errors="coerce") >= q["d3_l2_super_net_ratio"]["p60"])
        if "support_pressure_spread" in q:
            add_rule(rules, df, pool, "support_spread_high", pd.to_numeric(df["support_pressure_spread"], errors="coerce") >= q["support_pressure_spread"]["p60"])
        if "cancel_sell_ratio" in q:
            add_rule(rules, df, pool, "cancel_sell_high", pd.to_numeric(df["cancel_sell_ratio"], errors="coerce") >= q["cancel_sell_ratio"]["p60"])
        if "buy_support_ratio" in q:
            add_rule(rules, df, pool, "buy_support_high", pd.to_numeric(df["buy_support_ratio"], errors="coerce") >= q["buy_support_ratio"]["p60"])
        if "price_position_20d" in q:
            pos = pd.to_numeric(df["price_position_20d"], errors="coerce")
            add_rule(rules, df, pool, "price_position_lowmid", pos <= q["price_position_20d"]["p60"])
            add_rule(rules, df, pool, "price_position_mid_band", pos.between(q["price_position_20d"]["p40"], q["price_position_20d"]["p70"]))
        if "amount_vs_day_median" in q:
            add_rule(rules, df, pool, "amount_not_extreme", pd.to_numeric(df["amount_vs_day_median"], errors="coerce") <= q["amount_vs_day_median"]["p60"])

        add_rule(
            rules,
            df,
            pool,
            "confirm_d1_d3_and_hot_top10",
            (df["confirm_d1_pos"] == 1) & (df["confirm_d3_pos"] == 1) & (pd.to_numeric(df["hot_theme_best_rank"], errors="coerce") <= 10),
        )
        if "price_position_20d" in q:
            add_rule(
                rules,
                df,
                pool,
                "confirm_d1_d3_and_price_lowmid",
                (df["confirm_d1_pos"] == 1)
                & (df["confirm_d3_pos"] == 1)
                & (pd.to_numeric(df["price_position_20d"], errors="coerce") <= q["price_position_20d"]["p60"]),
            )
        if "support_pressure_spread" in q:
            add_rule(
                rules,
                df,
                pool,
                "confirm_d1_d3_and_support_spread",
                (df["confirm_d1_pos"] == 1)
                & (df["confirm_d3_pos"] == 1)
                & (pd.to_numeric(df["support_pressure_spread"], errors="coerce") >= q["support_pressure_spread"]["p60"]),
            )
        if "cancel_sell_ratio" in q:
            add_rule(
                rules,
                df,
                pool,
                "confirm_d1_d3_and_cancel_sell",
                (df["confirm_d1_pos"] == 1)
                & (df["confirm_d3_pos"] == 1)
                & (pd.to_numeric(df["cancel_sell_ratio"], errors="coerce") >= q["cancel_sell_ratio"]["p60"]),
            )
        if "amount_vs_day_median" in q and "price_position_20d" in q:
            add_rule(
                rules,
                df,
                pool,
                "confirm_d1_d3_and_not_extreme_and_lowmid",
                (df["confirm_d1_pos"] == 1)
                & (df["confirm_d3_pos"] == 1)
                & (pd.to_numeric(df["amount_vs_day_median"], errors="coerce") <= q["amount_vs_day_median"]["p60"])
                & (pd.to_numeric(df["price_position_20d"], errors="coerce") <= q["price_position_20d"]["p60"]),
            )
        if "support_pressure_spread" in q:
            add_rule(
                rules,
                df,
                pool,
                "hot_top10_and_support_spread",
                (pd.to_numeric(df["hot_theme_best_rank"], errors="coerce") <= 10)
                & (pd.to_numeric(df["support_pressure_spread"], errors="coerce") >= q["support_pressure_spread"]["p60"]),
            )
    return pd.DataFrame(rules).sort_values(
        ["pool", "hit_rate", "entry_5d_avg_pct", "entry_5d_low_le_-5_rate"],
        ascending=[True, False, False, True],
    )


def high_bucket_quantiles(df: pd.DataFrame, cols: Iterable[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for col in cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series):
            out[col] = {"p40": float(series.quantile(0.4)), "p60": float(series.quantile(0.6)), "p70": float(series.quantile(0.7))}
    return out


def add_rule(rules: List[Dict[str, float]], df: pd.DataFrame, pool: str, name: str, mask: pd.Series) -> None:
    group = df[mask].copy()
    if len(group) < MIN_RULE_SAMPLE:
        return
    target_col = "target_limitup" if pool == "limitup" else "target_trend20"
    extra_col = "target_limitup_extend" if pool == "limitup" else "target_trend40"
    rules.append(
        {
            "pool": pool,
            "rule_name": name,
            "sample_count": len(group),
            "hit_rate": group[target_col].mean(),
            "extra_rate": group[extra_col].mean(),
            "avg_high20_pct": group["high_20d_pct"].mean(),
            "entry_5d_avg_pct": group["entry_close_5d_pct"].mean(),
            "entry_5d_win_rate": (group["entry_close_5d_pct"] > 0).mean(),
            "entry_10d_avg_pct": group["entry_close_10d_pct"].mean(),
            "entry_10d_win_rate": (group["entry_close_10d_pct"] > 0).mean(),
            "entry_5d_low_le_-5_rate": (group["entry_low_5d_pct"] <= -5).mean(),
            "entry_10d_high_ge_5_rate": (group["entry_high_10d_pct"] >= 5).mean(),
            "entry_t5s5_avg": group["entry_t5s5"].mean(),
            "entry_t5s5_win_rate": (group["entry_t5s5"] > 0).mean(),
        }
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_probability_artifacts()
    base_frame = build_base_frame()
    daily, _ = sp.load_daily_and_limit(base_frame)
    limit_pool, trend_pool = load_probability_pools()
    merged = merge_probability_pools(base_frame, limit_pool, trend_pool)
    enriched = build_enriched_pool(merged, daily)
    valid_limit = assign_prob_bucket(enriched[enriched["limitup_probability_sample_split"] == "valid"].copy(), "limitup_probability")
    valid_trend = assign_prob_bucket(enriched[enriched["trend20_probability_sample_split"] == "valid"].copy(), "trend20_probability")
    bucket_metrics = build_bucket_trade_metrics(valid_limit, valid_trend)
    rule_metrics = build_rule_exploration(valid_limit, valid_trend)
    enriched.to_csv(OUT_DIR / "probe_signal_enriched_candidate_pool.csv", index=False)
    bucket_metrics.to_csv(OUT_DIR / "probe_signal_bucket_trade_metrics.csv", index=False)
    rule_metrics.to_csv(OUT_DIR / "probe_signal_rule_exploration.csv", index=False)
    print(bucket_metrics.round(4).to_string(index=False))
    print()
    print(rule_metrics.head(20).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
