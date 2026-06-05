#!/usr/bin/env python3
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.scripts import research_probe_signal_postclose_value as post
from backend.scripts import research_probe_signal_probability_framework as sp


OUT_DIR = ROOT / "docs/strategy-rework/experiments/20260603-probe-lift-research"

TRAIN_START = sp.TRAIN_START
TRAIN_END = sp.TRAIN_END
VALID_START = sp.VALID_START
VALID_END = sp.VALID_END

LIMITUP_BASE_FEATURES = [
    "probe_index",
    "oib_ratio",
    "amount_vs_day_median",
    "same_day_pullback_ratio",
    "day_gap_pct",
    "probe_strength_score",
    "l2_super_net_ratio",
    "l2_main_net_ratio",
    "buy_support_ratio",
    "support_pressure_spread",
    "hot_theme_best_rank",
    "hot_theme_score",
    "hot_theme_is_top10",
    "d1_l2_super_net_ratio",
    "d1_oib_ratio",
    "d3_l2_super_net_ratio",
    "d3_oib_ratio",
]

LIMITUP_STRENGTHENED_FEATURES = LIMITUP_BASE_FEATURES + [
    "close_book_imbalance_ratio",
    "close_bid_ask_amount_ratio",
    "cancel_sell_ratio",
    "price_position_20d",
    "breakout_vs_prev20_high_pct",
    "drawdown_from_20d_high_pct",
    "hot_theme_persistence_score",
    "hot_theme_is_continuing_hot",
    "d1_l2_main_net_ratio",
    "d3_l2_main_net_ratio",
    "d1_cancel_sell_ratio",
    "d3_cancel_sell_ratio",
    "d1_support_pressure_spread",
    "d3_support_pressure_spread",
    "d1_close_book_imbalance_ratio",
    "d3_close_book_imbalance_ratio",
    "d1_hot_theme_score",
    "d3_hot_theme_score",
    "gap_abs_pct",
    "price_mid_20d_score",
    "pullback_mid_score",
    "confirm_oib_strength",
    "confirm_super_strength",
    "confirm_order_score",
    "hot_follow_score",
    "confirm_positive_count_13",
]

TREND_BASE_FEATURES = [
    "probe_index",
    "oib_ratio",
    "amount_vs_day_median",
    "same_day_pullback_ratio",
    "day_gap_pct",
    "probe_strength_score",
    "l2_super_net_ratio",
    "l2_main_net_ratio",
    "buy_support_ratio",
    "support_pressure_spread",
    "price_position_20d",
    "drawdown_from_20d_high_pct",
    "hot_theme_best_rank",
    "hot_theme_score",
    "hot_theme_is_top10",
    "d1_l2_super_net_ratio",
    "d1_oib_ratio",
    "d3_l2_super_net_ratio",
    "d3_oib_ratio",
    "d5_l2_super_net_ratio",
    "d5_oib_ratio",
]

TREND_STRENGTHENED_FEATURES = [
    "probe_index",
    "probe_strength_score",
    "oib_ratio",
    "same_day_pullback_ratio",
    "pullback_mid_score",
    "amount_vs_day_median",
    "amount_log",
    "day_gap_pct",
    "gap_abs_pct",
    "hot_theme_score",
    "hot_theme_best_rank",
    "hot_theme_persistence_score",
    "hot_theme_is_continuing_hot",
    "hot_theme_is_new_hot",
    "hot_follow_score",
    "price_position_20d",
    "price_position_60d",
    "price_mid_20d_score",
    "price_mid_60d_score",
    "drawdown_from_20d_high_pct",
    "breakout_vs_prev20_high_pct",
    "l2_super_net_ratio",
    "l2_main_net_ratio",
    "support_pressure_spread",
    "close_book_imbalance_ratio",
    "cancel_sell_ratio",
    "positive_oib_bar_ratio",
    "positive_l2_bar_ratio",
    "oib_top3_concentration_ratio",
    "d1_oib_ratio",
    "d3_oib_ratio",
    "d5_oib_ratio",
    "d1_l2_super_net_ratio",
    "d3_l2_super_net_ratio",
    "d5_l2_super_net_ratio",
    "d1_l2_main_net_ratio",
    "d3_l2_main_net_ratio",
    "d5_l2_main_net_ratio",
    "d1_support_pressure_spread",
    "d3_support_pressure_spread",
    "d5_support_pressure_spread",
    "d1_cancel_sell_ratio",
    "d3_cancel_sell_ratio",
    "d5_cancel_sell_ratio",
    "confirm_oib_strength",
    "confirm_super_strength",
    "confirm_main_strength",
    "confirm_order_score",
    "confirm_positive_count_13",
    "market_limit_up_count",
    "market_broken_limit_up_ratio",
    "market_advancer_ratio",
    "csi1000_above_ma20",
    "market_trend_score",
]

MODEL_SPECS = [
    {
        "name": "limitup_base",
        "pool": "limitup",
        "features": LIMITUP_BASE_FEATURES,
        "target_col": "target_limitup",
        "extra_col": "target_limitup_extend",
        "clip": False,
    },
    {
        "name": "limitup_strengthened_v2",
        "pool": "limitup",
        "features": LIMITUP_STRENGTHENED_FEATURES,
        "target_col": "target_limitup",
        "extra_col": "target_limitup_extend",
        "clip": True,
    },
    {
        "name": "trend_base",
        "pool": "trend",
        "features": TREND_BASE_FEATURES,
        "target_col": "target_trend20",
        "extra_col": "target_trend40",
        "clip": False,
    },
    {
        "name": "trend_strengthened_v3",
        "pool": "trend",
        "features": TREND_STRENGTHENED_FEATURES,
        "target_col": "target_trend20",
        "extra_col": "target_trend40",
        "clip": True,
    },
]


def add_derived_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    numeric_cols = [
        "price_position_20d",
        "price_position_60d",
        "same_day_pullback_ratio",
        "day_gap_pct",
        "amount_vs_day_median",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["gap_abs_pct"] = out["day_gap_pct"].abs()
    out["price_mid_20d_score"] = -(out["price_position_20d"] - 0.5).abs()
    out["price_mid_60d_score"] = -(out["price_position_60d"] - 0.5).abs()
    out["pullback_mid_score"] = -(out["same_day_pullback_ratio"] - 0.575).abs()
    out["amount_log"] = np.log1p(out["amount_vs_day_median"].clip(lower=0))
    out["confirm_oib_strength"] = out[["d1_oib_ratio", "d3_oib_ratio", "d5_oib_ratio"]].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    out["confirm_super_strength"] = out[
        ["d1_l2_super_net_ratio", "d3_l2_super_net_ratio", "d5_l2_super_net_ratio"]
    ].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    out["confirm_main_strength"] = out[
        ["d1_l2_main_net_ratio", "d3_l2_main_net_ratio", "d5_l2_main_net_ratio"]
    ].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    out["confirm_order_score"] = out[
        [
            "d1_cancel_sell_ratio",
            "d3_cancel_sell_ratio",
            "d1_support_pressure_spread",
            "d3_support_pressure_spread",
            "d1_close_book_imbalance_ratio",
            "d3_close_book_imbalance_ratio",
        ]
    ].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    out["hot_follow_score"] = out[["hot_theme_score", "d1_hot_theme_score", "d3_hot_theme_score"]].apply(
        pd.to_numeric,
        errors="coerce",
    ).mean(axis=1)
    out["market_trend_score"] = out[
        ["csi1000_return_5d_pct", "csi500_return_5d_pct", "hs300_return_5d_pct", "gem_index_return_5d_pct"]
    ].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    out["confirm_positive_count_13"] = (
        (pd.to_numeric(out["d1_oib_ratio"], errors="coerce") > 0).astype(float)
        + (pd.to_numeric(out["d3_oib_ratio"], errors="coerce") > 0).astype(float)
        + (pd.to_numeric(out["d1_l2_super_net_ratio"], errors="coerce") > 0).astype(float)
        + (pd.to_numeric(out["d3_l2_super_net_ratio"], errors="coerce") > 0).astype(float)
    )
    return out


def build_research_frame() -> pd.DataFrame:
    probes = sp.load_probe_events()
    feature_df = sp.load_feature_store(probes)
    daily, limit_df = sp.load_daily_and_limit(probes)
    frame = sp.build_feature_frame(probes, feature_df)
    frame = sp.build_confirmation_features(frame, feature_df)
    frame = sp.build_targets(frame, daily, limit_df)
    frame = sp.add_group_flags(frame)
    entry_metrics = post.build_entry_metrics(frame, daily)
    frame = frame.merge(entry_metrics, on=["symbol", "trade_date"], how="left")
    frame = add_derived_features(frame)
    return frame


def fit_model_variant(
    frame: pd.DataFrame,
    feature_cols: Sequence[str],
    target_col: str,
    model_name: str,
    clip: bool,
) -> tuple[pd.DataFrame, Dict[str, float]]:
    use = frame[(frame["trade_date"] >= TRAIN_START) & (frame["trade_date"] <= VALID_END)].copy()
    for col in feature_cols:
        use[col] = pd.to_numeric(use[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    use[target_col] = pd.to_numeric(use[target_col], errors="coerce").fillna(0).astype(int)
    use = use.dropna(subset=feature_cols)
    train = use[(use["trade_date"] >= TRAIN_START) & (use["trade_date"] <= TRAIN_END)].copy()
    valid = use[(use["trade_date"] >= VALID_START) & (use["trade_date"] <= VALID_END)].copy()
    if clip:
        for col in feature_cols:
            lo = train[col].quantile(0.02)
            hi = train[col].quantile(0.98)
            train[col] = train[col].clip(lo, hi)
            valid[col] = valid[col].clip(lo, hi)
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=4000, class_weight="balanced")),
        ]
    )
    model.fit(train[feature_cols], train[target_col])
    train_score = model.predict_proba(train[feature_cols])[:, 1]
    valid_score = model.predict_proba(valid[feature_cols])[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(train_score, train[target_col].astype(float))
    train_prob = iso.transform(train_score)
    valid_prob = iso.transform(valid_score)
    scored = pd.concat(
        [
            train.assign(score_raw=train_score, prob=train_prob, split="train", model_name=model_name),
            valid.assign(score_raw=valid_score, prob=valid_prob, split="valid", model_name=model_name),
        ],
        ignore_index=True,
    )
    metrics = {
        "train_auc": float(roc_auc_score(train[target_col], train_score)),
        "valid_auc": float(roc_auc_score(valid[target_col], valid_score)),
        "train_n": int(len(train)),
        "valid_n": int(len(valid)),
        "valid_base_rate": float(valid[target_col].mean()),
    }
    return scored, metrics


def summarize_buckets(
    frame: pd.DataFrame,
    scored: pd.DataFrame,
    model_name: str,
    pool: str,
    target_col: str,
    extra_col: str,
) -> tuple[pd.DataFrame, Dict[str, float], pd.DataFrame]:
    valid = scored[scored["split"] == "valid"][["symbol", "trade_date", "prob"]].copy()
    merged = frame.merge(valid, on=["symbol", "trade_date"], how="inner")
    merged["prob_bucket"] = pd.qcut(merged["prob"].rank(method="first"), q=3, labels=["low", "mid", "high"])
    bucket_rows: List[Dict[str, float]] = []
    for bucket, group in merged.groupby("prob_bucket"):
        bucket_rows.append(
            {
                "model_name": model_name,
                "pool": pool,
                "bucket": str(bucket),
                "sample_count": len(group),
                "avg_probability": group["prob"].mean(),
                "hit_rate": group[target_col].mean(),
                "extra_rate": group[extra_col].mean(),
                "entry_5d_avg_pct": group["entry_close_5d_pct"].mean(),
                "entry_10d_avg_pct": group["entry_close_10d_pct"].mean(),
                "entry_5d_win_rate": (group["entry_close_5d_pct"] > 0).mean(),
                "entry_5d_low_le_-5_rate": (group["entry_low_5d_pct"] <= -5).mean(),
                "entry_10d_high_ge_5_rate": (group["entry_high_10d_pct"] >= 5).mean(),
            }
        )
    bucket_df = pd.DataFrame(bucket_rows)
    high = merged[merged["prob_bucket"] == "high"].copy()
    high_summary = {
        "model_name": model_name,
        "pool": pool,
        "high_n": int(len(high)),
        "high_avg_prob": float(high["prob"].mean()),
        "high_hit_rate": float(high[target_col].mean()),
        "high_extra_rate": float(high[extra_col].mean()),
        "high_5d_avg": float(high["entry_close_5d_pct"].mean()),
        "high_10d_avg": float(high["entry_close_10d_pct"].mean()),
        "high_5d_win": float((high["entry_close_5d_pct"] > 0).mean()),
        "high_5d_low_-5": float((high["entry_low_5d_pct"] <= -5).mean()),
        "high_10d_high_5": float((high["entry_high_10d_pct"] >= 5).mean()),
    }
    return bucket_df, high_summary, high


def high_bucket_quantiles(df: pd.DataFrame, cols: Iterable[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for col in cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series):
            out[col] = {"p40": float(series.quantile(0.4)), "p60": float(series.quantile(0.6)), "p70": float(series.quantile(0.7))}
    return out


def overlay_row(
    model_name: str,
    overlay_name: str,
    pool: str,
    df: pd.DataFrame,
    target_col: str,
    extra_col: str,
) -> Dict[str, float]:
    return {
        "model_name": model_name,
        "pool": pool,
        "overlay_name": overlay_name,
        "sample_count": len(df),
        "hit_rate": df[target_col].mean(),
        "extra_rate": df[extra_col].mean(),
        "entry_5d_avg_pct": df["entry_close_5d_pct"].mean(),
        "entry_10d_avg_pct": df["entry_close_10d_pct"].mean(),
        "entry_5d_win_rate": (df["entry_close_5d_pct"] > 0).mean(),
        "entry_5d_low_le_-5_rate": (df["entry_low_5d_pct"] <= -5).mean(),
        "entry_10d_high_ge_5_rate": (df["entry_high_10d_pct"] >= 5).mean(),
    }


def build_overlay_compare(
    trend_base_high: pd.DataFrame,
    limitup_strength_high: pd.DataFrame,
) -> pd.DataFrame:
    rows: List[Dict[str, float]] = []

    trend_q = high_bucket_quantiles(trend_base_high, ["d3_oib_ratio", "price_position_20d", "amount_vs_day_median"])
    trend_overlays = {
        "base_high_bucket": pd.Series(True, index=trend_base_high.index),
        "confirm_d3_pos": trend_base_high["confirm_d3_pos"] == 1,
        "d3_oib_high": pd.to_numeric(trend_base_high["d3_oib_ratio"], errors="coerce") >= trend_q["d3_oib_ratio"]["p60"],
        "price_position_mid_band": pd.to_numeric(trend_base_high["price_position_20d"], errors="coerce").between(
            trend_q["price_position_20d"]["p40"],
            trend_q["price_position_20d"]["p70"],
        ),
        "amount_not_extreme": pd.to_numeric(trend_base_high["amount_vs_day_median"], errors="coerce")
        <= trend_q["amount_vs_day_median"]["p60"],
    }
    trend_overlays["confirm_d3_and_price_mid_band"] = trend_overlays["confirm_d3_pos"] & trend_overlays["price_position_mid_band"]
    for name, mask in trend_overlays.items():
        group = trend_base_high[mask].copy()
        if len(group) >= 8:
            rows.append(overlay_row("trend_base", name, "trend", group, "target_trend20", "target_trend40"))

    limit_q = high_bucket_quantiles(limitup_strength_high, ["d3_oib_ratio", "d3_l2_super_net_ratio", "d1_oib_ratio"])
    limit_overlays = {
        "base_high_bucket": pd.Series(True, index=limitup_strength_high.index),
        "confirm_d3_pos": limitup_strength_high["confirm_d3_pos"] == 1,
        "d3_super_high": pd.to_numeric(limitup_strength_high["d3_l2_super_net_ratio"], errors="coerce")
        >= limit_q["d3_l2_super_net_ratio"]["p60"],
        "d3_oib_high": pd.to_numeric(limitup_strength_high["d3_oib_ratio"], errors="coerce") >= limit_q["d3_oib_ratio"]["p60"],
        "d1_oib_high": pd.to_numeric(limitup_strength_high["d1_oib_ratio"], errors="coerce") >= limit_q["d1_oib_ratio"]["p60"],
    }
    for name, mask in limit_overlays.items():
        group = limitup_strength_high[mask].copy()
        if len(group) >= 8:
            rows.append(overlay_row("limitup_strengthened_v2", name, "limitup", group, "target_limitup", "target_limitup_extend"))
    return pd.DataFrame(rows)


def write_markdown(model_df: pd.DataFrame, overlay_df: pd.DataFrame) -> None:
    model_df = model_df.copy()
    lookup = {row["model_name"]: row for _, row in model_df.iterrows()}
    limit_base = lookup["limitup_base"]
    limit_v2 = lookup["limitup_strengthened_v2"]
    trend_base = lookup["trend_base"]
    trend_v3 = lookup["trend_strengthened_v3"]

    trend_overlay = overlay_df[(overlay_df["model_name"] == "trend_base") & (overlay_df["overlay_name"] == "confirm_d3_pos")]
    trend_price_overlay = overlay_df[
        (overlay_df["model_name"] == "trend_base") & (overlay_df["overlay_name"] == "price_position_mid_band")
    ]
    trend_overlay = trend_overlay.iloc[0] if not trend_overlay.empty else None
    trend_price_overlay = trend_price_overlay.iloc[0] if not trend_price_overlay.empty else None

    lines = [
        "# 试盘信号强化对比结论",
        "",
        "## 结论",
        "",
        "- `首板线` 强化有效，应该升级成增强版。",
        "- `趋势线` 直接塞更多特征并不划算，当前更优解是保留原主模型，再叠加确认型过滤。",
        "",
        "## 1. 首板线：强化后提升多少",
        "",
        f"- 基线验证 AUC：`{limit_base['valid_auc']:.4f}`",
        f"- 强化版验证 AUC：`{limit_v2['valid_auc']:.4f}`",
        f"- AUC 提升：`{limit_v2['valid_auc'] - limit_base['valid_auc']:+.4f}`",
        f"- 高分池首板命中率：`{limit_base['high_hit_rate']:.1%}` -> `{limit_v2['high_hit_rate']:.1%}`",
        f"- 高分池二三板延续率：`{limit_base['high_extra_rate']:.1%}` -> `{limit_v2['high_extra_rate']:.1%}`",
        f"- 高分池 5 日平均收益：`{limit_base['high_5d_avg']:+.2f}%` -> `{limit_v2['high_5d_avg']:+.2f}%`",
        f"- 高分池 10 日平均收益：`{limit_base['high_10d_avg']:+.2f}%` -> `{limit_v2['high_10d_avg']:+.2f}%`",
        "",
        "业务解释：",
        "",
        "- 首板线这次强化，主要是把 `D1/D3` 资金确认、盘口撤卖、热点延续、位置结构一起纳进来，所以对“后面会不会被正式点板”这件事，区分度明显变强了。",
        "",
        "## 2. 趋势线：强化后有没有提升",
        "",
        f"- 基线验证 AUC：`{trend_base['valid_auc']:.4f}`",
        f"- 强化版验证 AUC：`{trend_v3['valid_auc']:.4f}`",
        f"- AUC 变化：`{trend_v3['valid_auc'] - trend_base['valid_auc']:+.4f}`",
        f"- 但高分池 20 日走到 `+20%` 的比例：`{trend_base['high_hit_rate']:.1%}` -> `{trend_v3['high_hit_rate']:.1%}`",
        f"- 高分池 5 日平均收益：`{trend_base['high_5d_avg']:+.2f}%` -> `{trend_v3['high_5d_avg']:+.2f}%`",
        f"- 高分池 10 日平均收益：`{trend_base['high_10d_avg']:+.2f}%` -> `{trend_v3['high_10d_avg']:+.2f}%`",
        "",
        "业务解释：",
        "",
        "- 趋势线当前已经不弱，再硬塞更多字段，AUC 虽然略涨，但高分池的真实交易体验反而变差了，这更像过拟合，不像有效强化。",
        "",
        "## 3. 趋势线更合理的强化方式",
        "",
        "- 不是重做主模型，而是在原趋势高分池上再叠加确认型过滤。",
    ]

    if trend_overlay is not None:
        lines.extend(
            [
                f"- `趋势高分池 + D3 资金确认为正`：样本 `{int(trend_overlay['sample_count'])}`，`20` 日走到 `+20%` 的比例 `{trend_overlay['hit_rate']:.1%}`，`5` 日平均收益 `{trend_overlay['entry_5d_avg_pct']:+.2f}%`。",
            ]
        )
    if trend_price_overlay is not None:
        lines.extend(
            [
                f"- `趋势高分池 + 20日位置中间带`：样本 `{int(trend_price_overlay['sample_count'])}`，`20` 日走到 `+20%` 的比例 `{trend_price_overlay['hit_rate']:.1%}`，`5` 日内打到 `-5%` 的概率 `{trend_price_overlay['entry_5d_low_le_-5_rate']:.1%}`，`10` 日平均收益 `{trend_price_overlay['entry_10d_avg_pct']:+.2f}%`。",
            ]
        )

    lines.extend(
        [
            "",
            "这说明：",
            "",
            "- 趋势线的下一步不是再堆更多特征，而是保留原趋势打分，外面再做一层 `确认过滤器`。",
            "",
            "## 4. 现在建议采用的版本",
            "",
            "- `首板线`：采用 `limitup_strengthened_v2`。",
            "- `趋势线`：保留 `trend_base` 做主模型。",
            "- `趋势聚焦池`：在 `trend_base` 高分池上，再看 `D3` 资金确认或位置中间带，做更激进或更稳健的二次筛选。",
            "",
            "## 5. 对应产物",
            "",
            "- [probe_signal_strengthening_model_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_model_compare.csv)",
            "- [probe_signal_strengthening_bucket_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_bucket_compare.csv)",
            "- [probe_signal_strengthening_overlay_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_overlay_compare.csv)",
        ]
    )
    (OUT_DIR / "probe_signal_strengthening_compare.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = build_research_frame()

    model_rows: List[Dict[str, float]] = []
    bucket_frames: List[pd.DataFrame] = []
    high_pools: Dict[str, pd.DataFrame] = {}

    for spec in MODEL_SPECS:
        scored, metrics = fit_model_variant(frame, spec["features"], spec["target_col"], spec["name"], spec["clip"])
        bucket_df, high_summary, high_pool = summarize_buckets(
            frame,
            scored,
            spec["name"],
            spec["pool"],
            spec["target_col"],
            spec["extra_col"],
        )
        row = {
            "name": spec["name"],
            "pool": spec["pool"],
            "feature_count": len(spec["features"]),
            **metrics,
            **high_summary,
        }
        model_rows.append(row)
        bucket_frames.append(bucket_df)
        high_pools[spec["name"]] = high_pool

    model_df = pd.DataFrame(model_rows)
    bucket_df = pd.concat(bucket_frames, ignore_index=True)
    overlay_df = build_overlay_compare(
        trend_base_high=high_pools["trend_base"],
        limitup_strength_high=high_pools["limitup_strengthened_v2"],
    )

    model_df.to_csv(OUT_DIR / "probe_signal_strengthening_model_compare.csv", index=False)
    bucket_df.to_csv(OUT_DIR / "probe_signal_strengthening_bucket_compare.csv", index=False)
    overlay_df.to_csv(OUT_DIR / "probe_signal_strengthening_overlay_compare.csv", index=False)
    write_markdown(model_df, overlay_df)

    print(model_df.round(4).to_string(index=False))
    print()
    print(overlay_df.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
