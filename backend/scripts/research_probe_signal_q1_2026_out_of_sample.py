#!/usr/bin/env python3
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.scripts import research_probe_lift_events as base
from backend.scripts import research_probe_signal_postclose_value as post
from backend.scripts import research_probe_signal_probability_framework as sp
from backend.scripts import research_probe_signal_strengthening_compare as cmp


OUT_DIR = ROOT / "docs/strategy-rework/experiments/20260603-probe-lift-research"

TRAIN_START = "2024-09-02"
TRAIN_END = "2025-12-31"
TEST_START = "2026-01-01"
TEST_END = "2026-03-31"
SCAN_START = "2024-09-02"
SCAN_END = "2026-03-31"
FORWARD_END = "2026-06-03"


MODEL_SPECS = [
    {
        "name": "limitup_base_q1_2026",
        "pool": "limitup",
        "features": cmp.LIMITUP_BASE_FEATURES,
        "target_col": "target_limitup",
        "extra_col": "target_limitup_extend",
        "clip": False,
    },
    {
        "name": "limitup_strengthened_v2_q1_2026",
        "pool": "limitup",
        "features": cmp.LIMITUP_STRENGTHENED_FEATURES,
        "target_col": "target_limitup",
        "extra_col": "target_limitup_extend",
        "clip": True,
    },
    {
        "name": "trend_base_q1_2026",
        "pool": "trend",
        "features": cmp.TREND_BASE_FEATURES,
        "target_col": "target_trend20",
        "extra_col": "target_trend40",
        "clip": False,
    },
    {
        "name": "trend_strengthened_v3_q1_2026",
        "pool": "trend",
        "features": cmp.TREND_STRENGTHENED_FEATURES,
        "target_col": "target_trend20",
        "extra_col": "target_trend40",
        "clip": True,
    },
]


def load_probe_events_for_q1_2026() -> pd.DataFrame:
    base.SCAN_START = SCAN_START
    base.SCAN_END = SCAN_END
    base.load_trade_date_index.cache_clear()
    conn = sp.connect(base.DEFAULT_ATOMIC_DB)
    try:
        all_events = base.build_event_frame(conn)
        train_events = all_events[(all_events["trade_date"] >= TRAIN_START) & (all_events["trade_date"] <= TRAIN_END)].copy()
        thresholds = base.derive_thresholds(train_events)
        classified = base.classify_events(all_events, thresholds)
        tagged = base.tag_sequences(classified)
        return tagged[tagged["event_kind"] == "probe_candidate"].copy().reset_index(drop=True)
    finally:
        conn.close()


def build_frame() -> pd.DataFrame:
    probes = load_probe_events_for_q1_2026()
    original_scan_start = sp.FULL_SCAN_START
    original_scan_end = sp.FULL_SCAN_END
    original_forward_end = sp.FORWARD_END
    try:
        sp.FULL_SCAN_START = SCAN_START
        sp.FULL_SCAN_END = SCAN_END
        sp.FORWARD_END = FORWARD_END
        feature_df = sp.load_feature_store(probes)
        daily, limit_df = sp.load_daily_and_limit(probes)
        frame = sp.build_feature_frame(probes, feature_df)
        frame = sp.build_confirmation_features(frame, feature_df)
        frame = sp.build_targets(frame, daily, limit_df)
        frame = sp.add_group_flags(frame)
        entry_metrics = post.build_entry_metrics(frame, daily)
        frame = frame.merge(entry_metrics, on=["symbol", "trade_date"], how="left")
        frame = cmp.add_derived_features(frame)
        return frame
    finally:
        sp.FULL_SCAN_START = original_scan_start
        sp.FULL_SCAN_END = original_scan_end
        sp.FORWARD_END = original_forward_end


def fit_model(frame: pd.DataFrame, feature_cols: Sequence[str], target_col: str, clip: bool) -> tuple[pd.DataFrame, Dict[str, float]]:
    use = frame[(frame["trade_date"] >= TRAIN_START) & (frame["trade_date"] <= TEST_END)].copy()
    for col in feature_cols:
        use[col] = pd.to_numeric(use[col], errors="coerce").replace([float("inf"), float("-inf")], pd.NA)
    use[target_col] = pd.to_numeric(use[target_col], errors="coerce").fillna(0).astype(int)
    use = use.dropna(subset=feature_cols)
    train = use[(use["trade_date"] >= TRAIN_START) & (use["trade_date"] <= TRAIN_END)].copy()
    test = use[(use["trade_date"] >= TEST_START) & (use["trade_date"] <= TEST_END)].copy()
    if clip:
        for col in feature_cols:
            lo = train[col].quantile(0.02)
            hi = train[col].quantile(0.98)
            train[col] = train[col].clip(lo, hi)
            test[col] = test[col].clip(lo, hi)
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=4000, class_weight="balanced")),
        ]
    )
    model.fit(train[feature_cols], train[target_col])
    train_score = model.predict_proba(train[feature_cols])[:, 1]
    test_score = model.predict_proba(test[feature_cols])[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(train_score, train[target_col].astype(float))
    train_prob = iso.transform(train_score)
    test_prob = iso.transform(test_score)
    scored = pd.concat(
        [
            train.assign(prob=train_prob, split="train"),
            test.assign(prob=test_prob, split="test"),
        ],
        ignore_index=True,
    )
    metrics = {
        "train_auc": float(roc_auc_score(train[target_col], train_score)),
        "test_auc": float(roc_auc_score(test[target_col], test_score)),
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "test_base_rate": float(test[target_col].mean()),
    }
    return scored, metrics


def summarize_test(
    scored: pd.DataFrame,
    model_name: str,
    pool: str,
    target_col: str,
    extra_col: str,
) -> tuple[pd.DataFrame, Dict[str, float], pd.DataFrame]:
    test = scored[scored["split"] == "test"].copy()
    test["prob_bucket"] = pd.qcut(test["prob"].rank(method="first"), q=3, labels=["low", "mid", "high"])
    bucket_rows: List[Dict[str, float]] = []
    for bucket, group in test.groupby("prob_bucket"):
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
    high = test[test["prob_bucket"] == "high"].copy()
    summary = {
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
    return bucket_df, summary, high


def build_overlay_compare(high_pools: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: List[Dict[str, float]] = []
    trend_base_high = high_pools["trend_base_q1_2026"]
    limitup_strength_high = high_pools["limitup_strengthened_v2_q1_2026"]

    trend_q = cmp.high_bucket_quantiles(trend_base_high, ["d3_oib_ratio", "price_position_20d", "amount_vs_day_median"])
    trend_overlays = {
        "base_high_bucket": pd.Series(True, index=trend_base_high.index),
        "confirm_d3_pos": trend_base_high["confirm_d3_pos"] == 1,
        "d3_oib_high": pd.to_numeric(trend_base_high["d3_oib_ratio"], errors="coerce") >= trend_q["d3_oib_ratio"]["p60"],
        "price_position_mid_band": pd.to_numeric(trend_base_high["price_position_20d"], errors="coerce").between(
            trend_q["price_position_20d"]["p40"],
            trend_q["price_position_20d"]["p70"],
        ),
    }
    trend_overlays["confirm_d3_and_price_mid_band"] = trend_overlays["confirm_d3_pos"] & trend_overlays["price_position_mid_band"]
    for name, mask in trend_overlays.items():
        group = trend_base_high[mask].copy()
        if len(group) >= 8:
            rows.append(cmp.overlay_row("trend_base_q1_2026", name, "trend", group, "target_trend20", "target_trend40"))

    limit_q = cmp.high_bucket_quantiles(limitup_strength_high, ["d3_oib_ratio", "d3_l2_super_net_ratio", "d1_oib_ratio"])
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
            rows.append(cmp.overlay_row("limitup_strengthened_v2_q1_2026", name, "limitup", group, "target_limitup", "target_limitup_extend"))
    return pd.DataFrame(rows)


def write_markdown(model_df: pd.DataFrame, overlay_df: pd.DataFrame) -> None:
    lookup = {row["model_name"]: row for _, row in model_df.iterrows()}
    limit_base = lookup["limitup_base_q1_2026"]
    limit_v2 = lookup["limitup_strengthened_v2_q1_2026"]
    trend_base = lookup["trend_base_q1_2026"]
    trend_v3 = lookup["trend_strengthened_v3_q1_2026"]

    trend_overlay = overlay_df[(overlay_df["model_name"] == "trend_base_q1_2026") & (overlay_df["overlay_name"] == "confirm_d3_pos")]
    trend_pos_overlay = overlay_df[
        (overlay_df["model_name"] == "trend_base_q1_2026") & (overlay_df["overlay_name"] == "price_position_mid_band")
    ]
    trend_overlay = trend_overlay.iloc[0] if not trend_overlay.empty else None
    trend_pos_overlay = trend_pos_overlay.iloc[0] if not trend_pos_overlay.empty else None

    lines = [
        "# 2026Q1 样本外检验",
        "",
        "## 强化版分别做了什么",
        "",
        "### 首板强化版 `limitup_strengthened_v2`",
        "",
        "- 在原来 17 个基础特征上，加了 26 个增强特征。",
        "- 主要新增四层：",
        "  - `盘口层`：收盘盘口失衡、收盘买卖盘金额比、撤卖强度。",
        "  - `确认层`：D1/D3 的主力净流入、撤卖、托举减抛压差、盘口失衡。",
        "  - `热点层`：热点持续性、D1/D3 热点分数延续。",
        "  - `位置层`：20日位置、距前高距离、绝对跳空、回吐是否居中。",
        "",
        "### 趋势强化版 `trend_strengthened_v3`",
        "",
        "- 在原来 21 个基础特征上，加到了 54 个特征。",
        "- 比首板版额外多加了：",
        "  - `更长确认层`：D5 的 OIB、超大单、主力净流入、撤卖、托举。",
        "  - `节奏层`：OIB 连续性、L2 连续性、OIB 集中度。",
        "  - `市场层`：涨停数量、炸板率、市场涨跌家数比、指数状态。",
        "  - `位置层`：60日位置、中间带评分、放量对数化。",
        "",
        "## 2026-01-01 ~ 2026-03-31 样本外结果",
        "",
        f"- 测试样本量：`{int(limit_base['test_n'])}` 次试盘事件",
        "",
        "### 首板线",
        "",
        f"- 基线测试 AUC：`{limit_base['test_auc']:.4f}`",
        f"- 强化版测试 AUC：`{limit_v2['test_auc']:.4f}`",
        f"- 高分池首板命中率：`{limit_base['high_hit_rate']:.1%}` -> `{limit_v2['high_hit_rate']:.1%}`",
        f"- 高分池二三板延续率：`{limit_base['high_extra_rate']:.1%}` -> `{limit_v2['high_extra_rate']:.1%}`",
        f"- 高分池 5 日平均收益：`{limit_base['high_5d_avg']:+.2f}%` -> `{limit_v2['high_5d_avg']:+.2f}%`",
        f"- 高分池 10 日平均收益：`{limit_base['high_10d_avg']:+.2f}%` -> `{limit_v2['high_10d_avg']:+.2f}%`",
        "",
        "结论：",
        "",
        "- 如果这轮样本外里，首板强化版还能保持比基线更好的 AUC 和高分池表现，就说明它不是只在旧验证窗里有效。",
        "",
        "### 趋势线",
        "",
        f"- 基线测试 AUC：`{trend_base['test_auc']:.4f}`",
        f"- 强化版测试 AUC：`{trend_v3['test_auc']:.4f}`",
        f"- 高分池 20 日到 `+20%` 的比例：`{trend_base['high_hit_rate']:.1%}` -> `{trend_v3['high_hit_rate']:.1%}`",
        f"- 高分池 5 日平均收益：`{trend_base['high_5d_avg']:+.2f}%` -> `{trend_v3['high_5d_avg']:+.2f}%`",
        f"- 高分池 10 日平均收益：`{trend_base['high_10d_avg']:+.2f}%` -> `{trend_v3['high_10d_avg']:+.2f}%`",
        "",
        "结论：",
        "",
        "- 趋势线重点不是看 AUC 一点点变化，而是看高分池的真实持有体验有没有变好。",
        "",
        "## 趋势过滤版",
        "",
    ]
    if trend_overlay is not None:
        lines.append(
            f"- `趋势基线高分池 + D3 资金确认为正`：样本 `{int(trend_overlay['sample_count'])}`，命中率 `{trend_overlay['hit_rate']:.1%}`，5日收益 `{trend_overlay['entry_5d_avg_pct']:+.2f}%`。"
        )
    if trend_pos_overlay is not None:
        lines.append(
            f"- `趋势基线高分池 + 20日位置中间带`：样本 `{int(trend_pos_overlay['sample_count'])}`，命中率 `{trend_pos_overlay['hit_rate']:.1%}`，5日内打到 -5% 概率 `{trend_pos_overlay['entry_5d_low_le_-5_rate']:.1%}`，10日收益 `{trend_pos_overlay['entry_10d_avg_pct']:+.2f}%`。"
        )
    lines.extend(
        [
            "",
            "## 对应产物",
            "",
            "- [probe_signal_q1_2026_model_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_q1_2026_model_compare.csv)",
            "- [probe_signal_q1_2026_bucket_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_q1_2026_bucket_compare.csv)",
            "- [probe_signal_q1_2026_overlay_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_q1_2026_overlay_compare.csv)",
        ]
    )
    (OUT_DIR / "probe_signal_q1_2026_out_of_sample.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    frame = build_frame()
    model_rows: List[Dict[str, float]] = []
    bucket_frames: List[pd.DataFrame] = []
    high_pools: Dict[str, pd.DataFrame] = {}
    for spec in MODEL_SPECS:
        scored, metrics = fit_model(frame, spec["features"], spec["target_col"], spec["clip"])
        bucket_df, summary, high = summarize_test(scored, spec["name"], spec["pool"], spec["target_col"], spec["extra_col"])
        model_rows.append(
            {
                "model_name": spec["name"],
                "pool": spec["pool"],
                "feature_count": len(spec["features"]),
                **metrics,
                **summary,
            }
        )
        bucket_frames.append(bucket_df)
        high_pools[spec["name"]] = high

    model_df = pd.DataFrame(model_rows)
    bucket_df = pd.concat(bucket_frames, ignore_index=True)
    overlay_df = build_overlay_compare(high_pools)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model_df.to_csv(OUT_DIR / "probe_signal_q1_2026_model_compare.csv", index=False)
    bucket_df.to_csv(OUT_DIR / "probe_signal_q1_2026_bucket_compare.csv", index=False)
    overlay_df.to_csv(OUT_DIR / "probe_signal_q1_2026_overlay_compare.csv", index=False)
    write_markdown(model_df, overlay_df)

    print(model_df.round(4).to_string(index=False))
    print()
    print(bucket_df.round(4).to_string(index=False))
    print()
    print(overlay_df.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
