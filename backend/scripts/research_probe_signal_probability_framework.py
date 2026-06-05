#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts import research_probe_lift_events as base


OUT_DIR = ROOT / "docs/strategy-rework/experiments/20260603-probe-lift-research"

TRAIN_START = "2024-09-02"
TRAIN_END = "2025-09-30"
VALID_START = "2025-10-01"
VALID_END = "2025-12-31"
FULL_SCAN_START = "2024-09-02"
FULL_SCAN_END = "2025-12-31"
FORWARD_END = "2026-06-03"


def safe_float(v: object, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path.expanduser().resolve()), timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def load_probe_events() -> pd.DataFrame:
    base.SCAN_START = FULL_SCAN_START
    base.SCAN_END = FULL_SCAN_END
    base.load_trade_date_index.cache_clear()
    conn = connect(base.DEFAULT_ATOMIC_DB)
    try:
        all_events = base.build_event_frame(conn)
        train_events = all_events[(all_events["trade_date"] >= TRAIN_START) & (all_events["trade_date"] <= TRAIN_END)].copy()
        thresholds = base.derive_thresholds(train_events)
        classified = base.classify_events(all_events, thresholds)
        tagged = base.tag_sequences(classified)
        probes = tagged[tagged["event_kind"] == "probe_candidate"].copy().reset_index(drop=True)
        return probes
    finally:
        conn.close()


def load_feature_store(probes: pd.DataFrame) -> pd.DataFrame:
    symbols = sorted(probes["symbol"].dropna().unique().tolist())
    conn = connect(base.DEFAULT_FEATURE_DB)
    try:
        conn.execute("DROP TABLE IF EXISTS temp_probe_symbols")
        conn.execute("CREATE TEMP TABLE temp_probe_symbols(symbol TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO temp_probe_symbols(symbol) VALUES (?)", [(symbol,) for symbol in symbols])
        df = pd.read_sql_query(
            f"""
            SELECT *
            FROM model_feature_daily_v1
            WHERE symbol IN (SELECT symbol FROM temp_probe_symbols)
              AND trade_date >= '{FULL_SCAN_START}' AND trade_date <= '{FORWARD_END}'
            """,
            conn,
        )
        return df
    finally:
        conn.close()


def load_daily_and_limit(probes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbols = sorted(probes["symbol"].dropna().unique().tolist())
    conn = connect(base.DEFAULT_ATOMIC_DB)
    try:
        conn.execute("DROP TABLE IF EXISTS temp_probe_symbols_2")
        conn.execute("CREATE TEMP TABLE temp_probe_symbols_2(symbol TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO temp_probe_symbols_2(symbol) VALUES (?)", [(symbol,) for symbol in symbols])
        daily = pd.read_sql_query(
            f"""
            SELECT symbol, trade_date, open, high, low, close
            FROM atomic_trade_daily
            WHERE symbol IN (SELECT symbol FROM temp_probe_symbols_2)
              AND trade_date >= '{FULL_SCAN_START}' AND trade_date <= '{FORWARD_END}'
            """,
            conn,
        )
        limit_df = pd.read_sql_query(
            f"""
            SELECT symbol, trade_date, touch_limit_up, is_limit_up_close, broken_limit_up, limit_state_label
            FROM atomic_limit_state_daily
            WHERE symbol IN (SELECT symbol FROM temp_probe_symbols_2)
              AND trade_date >= '{FULL_SCAN_START}' AND trade_date <= '{FORWARD_END}'
            """,
            conn,
        )
        return daily, limit_df
    finally:
        conn.close()


def build_feature_frame(probes: pd.DataFrame, feature_df: pd.DataFrame) -> pd.DataFrame:
    feature_df["trade_date"] = feature_df["trade_date"].astype(str)
    probes["trade_date"] = probes["trade_date"].astype(str)
    merged = probes.merge(feature_df, on=["symbol", "trade_date"], how="left", suffixes=("", "_mf"))
    feature_cols = [
        "probe_index",
        "bar_high_ret_pct",
        "bar_close_ret_pct",
        "amount_vs_day_median",
        "same_day_pullback_ratio",
        "same_day_later_high_pct",
        "oib_ratio",
        "cvd_ratio",
        "day_gap_pct",
        "day_return_pct",
        "probe_strength_score",
        "l2_super_net_ratio",
        "l2_main_net_ratio",
        "l1_super_net_ratio",
        "l1_main_net_ratio",
        "add_buy_ratio",
        "add_sell_ratio",
        "cancel_buy_ratio",
        "cancel_sell_ratio",
        "buy_support_ratio",
        "sell_pressure_ratio",
        "support_pressure_spread",
        "avg_book_imbalance_ratio",
        "close_book_imbalance_ratio",
        "close_bid_ask_amount_ratio",
        "positive_l2_bar_ratio",
        "positive_oib_bar_ratio",
        "positive_cvd_bar_ratio",
        "oib_top3_concentration_ratio",
        "price_position_20d",
        "price_position_60d",
        "breakout_vs_prev20_high_pct",
        "drawdown_from_20d_high_pct",
        "return_1d_pct",
        "return_3d_pct",
        "return_5d_pct",
        "amount_ratio_20d",
        "hot_theme_best_rank",
        "hot_theme_score",
        "hot_theme_is_top10",
        "hot_theme_is_new_hot",
        "hot_theme_is_continuing_hot",
        "hot_theme_is_climax_hot",
        "hot_theme_is_fading",
        "hot_theme_concentration_top3",
        "hot_theme_member_count",
        "market_limit_up_count",
        "market_broken_limit_up_ratio",
        "market_advancer_ratio",
        "csi1000_above_ma20",
        "csi1000_return_5d_pct",
        "csi500_return_5d_pct",
        "hs300_return_5d_pct",
        "gem_index_return_5d_pct",
    ]
    for col in feature_cols:
        if col not in merged.columns:
            merged[col] = np.nan
    return merged


def build_confirmation_features(frame: pd.DataFrame, feature_df: pd.DataFrame) -> pd.DataFrame:
    feature_df = feature_df.sort_values(["symbol", "trade_date"]).copy()
    use_cols = [
        "symbol",
        "trade_date",
        "l2_super_net_ratio",
        "l2_main_net_ratio",
        "oib_ratio",
        "cvd_ratio",
        "add_buy_ratio",
        "cancel_sell_ratio",
        "buy_support_ratio",
        "support_pressure_spread",
        "close_book_imbalance_ratio",
        "hot_theme_best_rank",
        "hot_theme_score",
        "hot_theme_is_top10",
        "hot_theme_is_new_hot",
        "hot_theme_is_continuing_hot",
        "hot_theme_is_fading",
        "market_limit_up_count",
        "market_broken_limit_up_ratio",
    ]
    feat = feature_df[use_cols].copy()
    feat["trade_date"] = feat["trade_date"].astype(str)
    by_symbol = {sym: g.reset_index(drop=True) for sym, g in feat.groupby("symbol", sort=False)}
    rows: List[Dict[str, float]] = []
    for rec in frame[["symbol", "trade_date"]].itertuples(index=False):
        g = by_symbol.get(rec.symbol)
        row: Dict[str, float] = {"symbol": rec.symbol, "trade_date": rec.trade_date}
        if g is None:
            rows.append(row)
            continue
        pos = g.index[g["trade_date"] == rec.trade_date].tolist()
        if not pos:
            rows.append(row)
            continue
        i = pos[0]
        for d in [1, 3, 5]:
            j = i + d
            prefix = f"d{d}_"
            if j < len(g):
                rec2 = g.loc[j]
                for col in use_cols[2:]:
                    row[prefix + col] = safe_float(rec2[col], np.nan)
            else:
                for col in use_cols[2:]:
                    row[prefix + col] = np.nan
        rows.append(row)
    confirm = pd.DataFrame(rows)
    return frame.merge(confirm, on=["symbol", "trade_date"], how="left")


def build_targets(frame: pd.DataFrame, daily: pd.DataFrame, limit_df: pd.DataFrame) -> pd.DataFrame:
    daily["trade_date"] = daily["trade_date"].astype(str)
    limit_df["trade_date"] = limit_df["trade_date"].astype(str)
    daily = daily.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    limit_df = limit_df.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    daily_by_symbol = {sym: g.reset_index(drop=True) for sym, g in daily.groupby("symbol", sort=False)}
    limit_by_symbol = {sym: g.reset_index(drop=True) for sym, g in limit_df.groupby("symbol", sort=False)}
    rows: List[Dict[str, float]] = []
    for rec in frame[["symbol", "trade_date"]].itertuples(index=False):
        d = daily_by_symbol.get(rec.symbol)
        l = limit_by_symbol.get(rec.symbol)
        row: Dict[str, float] = {"symbol": rec.symbol, "trade_date": rec.trade_date}
        if d is None or l is None:
            rows.append(row)
            continue
        pos_d = d.index[d["trade_date"] == rec.trade_date].tolist()
        pos_l = l.index[l["trade_date"] == rec.trade_date].tolist()
        if not pos_d or not pos_l:
            rows.append(row)
            continue
        i = pos_d[0]
        j = pos_l[0]
        base_close = safe_float(d.loc[i, "close"], np.nan)
        dwin20 = d.iloc[i + 1 : i + 21].copy().reset_index(drop=True)
        dwin40 = d.iloc[i + 1 : i + 41].copy().reset_index(drop=True)
        lwin20 = l.iloc[j + 1 : j + 21].copy().reset_index(drop=True)
        if base_close > 0 and not dwin20.empty:
            row["high_20d_pct"] = (safe_float(dwin20["high"].max()) / base_close - 1.0) * 100.0
        else:
            row["high_20d_pct"] = np.nan
        if base_close > 0 and not dwin40.empty:
            row["high_40d_pct"] = (safe_float(dwin40["high"].max()) / base_close - 1.0) * 100.0
        else:
            row["high_40d_pct"] = np.nan
        row["limit_close_20d"] = int((lwin20["is_limit_up_close"].fillna(0).astype(int) == 1).any()) if not lwin20.empty else 0
        row["touch_up_20d"] = int((lwin20["touch_limit_up"].fillna(0).astype(int) == 1).any()) if not lwin20.empty else 0
        close_hits = np.where(lwin20["is_limit_up_close"].fillna(0).astype(int).values == 1)[0] if not lwin20.empty else np.array([])
        touch_hits = np.where(lwin20["touch_limit_up"].fillna(0).astype(int).values == 1)[0] if not lwin20.empty else np.array([])
        row["days_to_first_limit_close"] = int(close_hits[0] + 1) if len(close_hits) else np.nan
        row["days_to_first_touch_up"] = int(touch_hits[0] + 1) if len(touch_hits) else np.nan
        streak = 0
        if len(close_hits):
            start = close_hits[0]
            k = start
            while k < len(lwin20) and int(lwin20.loc[k, "is_limit_up_close"]) == 1:
                streak += 1
                k += 1
        row["first_limit_close_streak"] = streak
        row["has_2board_from_first_close"] = int(streak >= 2)
        row["has_3board_from_first_close"] = int(streak >= 3)
        row["trend20_15"] = int(safe_float(row["high_20d_pct"], -999) >= 15)
        row["trend20_20"] = int(safe_float(row["high_20d_pct"], -999) >= 20)
        row["trend40_30"] = int(safe_float(row["high_40d_pct"], -999) >= 30)
        row["target_limitup"] = int(row["limit_close_20d"] == 1)
        row["target_limitup_extend"] = int((row["has_2board_from_first_close"] == 1) or (row["has_3board_from_first_close"] == 1))
        row["target_trend20"] = int(row["trend20_20"] == 1)
        row["target_trend40"] = int(row["trend40_30"] == 1)
        rows.append(row)
    target_df = pd.DataFrame(rows)
    return frame.merge(target_df, on=["symbol", "trade_date"], how="left")


def add_group_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["probe_1"] = (out["probe_index"] == 1).astype(int)
    out["probe_2_3"] = out["probe_index"].isin([2, 3]).astype(int)
    out["oib_top20"] = (out["oib_ratio"] >= out["oib_ratio"].quantile(0.8)).astype(int)
    out["oib_top30"] = (out["oib_ratio"] >= out["oib_ratio"].quantile(0.7)).astype(int)
    out["pullback_mid"] = out["same_day_pullback_ratio"].between(0.35, 0.8).astype(int)
    out["hot_top10"] = (pd.to_numeric(out["hot_theme_best_rank"], errors="coerce") <= 10).astype(int)
    out["confirm_d1_pos"] = (
        (pd.to_numeric(out["d1_l2_super_net_ratio"], errors="coerce") > 0)
        & (pd.to_numeric(out["d1_oib_ratio"], errors="coerce") > 0)
    ).astype(int)
    out["confirm_d3_pos"] = (
        (pd.to_numeric(out["d3_l2_super_net_ratio"], errors="coerce") > 0)
        & (pd.to_numeric(out["d3_oib_ratio"], errors="coerce") > 0)
    ).astype(int)
    out["confirm_d5_pos"] = (
        (pd.to_numeric(out["d5_l2_super_net_ratio"], errors="coerce") > 0)
        & (pd.to_numeric(out["d5_oib_ratio"], errors="coerce") > 0)
    ).astype(int)
    return out


def fit_probability_model(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    name: str,
) -> tuple[pd.DataFrame, Dict[str, float], pd.DataFrame]:
    use = df.copy()
    use = use[(use["trade_date"] >= TRAIN_START) & (use["trade_date"] <= VALID_END)].copy()
    for col in feature_cols:
        use[col] = pd.to_numeric(use[col], errors="coerce")
        use[col] = use[col].replace([np.inf, -np.inf], np.nan)
    use[target_col] = pd.to_numeric(use[target_col], errors="coerce").fillna(0).astype(int)
    use = use.dropna(subset=feature_cols)
    train = use[(use["trade_date"] >= TRAIN_START) & (use["trade_date"] <= TRAIN_END)].copy()
    valid = use[(use["trade_date"] >= VALID_START) & (use["trade_date"] <= VALID_END)].copy()
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
    train = train.assign(score_raw=train_score, prob=train_prob, split="train", model_name=name)
    valid = valid.assign(score_raw=valid_score, prob=valid_prob, split="valid", model_name=name)
    metrics = {
        "train_auc": round(roc_auc_score(train[target_col], train_score), 4) if train[target_col].nunique() > 1 else np.nan,
        "valid_auc": round(roc_auc_score(valid[target_col], valid_score), 4) if valid[target_col].nunique() > 1 else np.nan,
        "train_base_rate": round(train[target_col].mean(), 4),
        "valid_base_rate": round(valid[target_col].mean(), 4),
        "train_n": int(len(train)),
        "valid_n": int(len(valid)),
    }
    coef = pd.DataFrame(
        {
            "feature": feature_cols,
            "coef": model.named_steps["clf"].coef_[0],
            "abs_coef": np.abs(model.named_steps["clf"].coef_[0]),
            "model_name": name,
            "target": target_col,
        }
    ).sort_values("abs_coef", ascending=False)
    scored = pd.concat([train, valid], ignore_index=True)
    return scored, metrics, coef


def build_probability_table(scored: pd.DataFrame, target_col: str) -> pd.DataFrame:
    valid = scored[scored["split"] == "valid"].copy()
    valid["prob_bucket"] = pd.qcut(valid["prob"], q=min(5, valid["prob"].nunique()), duplicates="drop")
    out = (
        valid.groupby("prob_bucket", as_index=False)
        .agg(
            sample_count=("symbol", "count"),
            avg_probability=("prob", "mean"),
            realized_rate=(target_col, "mean"),
        )
    )
    out["avg_probability"] = out["avg_probability"].round(4)
    out["realized_rate"] = out["realized_rate"].round(4)
    return out


def build_candidate_pool(df: pd.DataFrame, scored: pd.DataFrame, model_name: str, prob_col_name: str) -> pd.DataFrame:
    core = df.copy()
    part = scored[scored["model_name"] == model_name][["symbol", "trade_date", "prob", "split"]].copy()
    out = core.merge(part, on=["symbol", "trade_date"], how="left")
    out = out.rename(columns={"prob": prob_col_name, "split": f"{prob_col_name}_sample_split"})
    return out


def build_feature_dictionary() -> pd.DataFrame:
    rows = [
        ("probe_index", "试盘序号", "第一次、第二次、第三次试盘。"),
        ("oib_ratio", "订单失衡强度", "试盘当日 OIB / 成交额，反映主动推动是否明显。"),
        ("l2_super_net_ratio", "超大单净流入强度", "试盘当日超大单净额 / 成交额。"),
        ("l2_main_net_ratio", "主力净流入强度", "试盘当日主力净额 / 成交额。"),
        ("same_day_pullback_ratio", "同日回吐比例", "试盘拉升后，当天回吐了多少。"),
        ("amount_vs_day_median", "放量倍数", "试盘 5 分钟成交额相对当日中位 5 分钟成交额的倍数。"),
        ("buy_support_ratio", "买盘托举强度", "盘口买方承接是否明显。"),
        ("support_pressure_spread", "托举减抛压差", "买盘托举相对卖盘压力的净差。"),
        ("hot_theme_best_rank", "热点题材排名", "试盘发生日，该票归属热点的最好排名。"),
        ("hot_theme_is_top10", "是否属于前排热点", "试盘发生日是否属于热点前十。"),
        ("d1_l2_super_net_ratio", "试盘后 1 日超大单确认", "试盘后第 1 日超大单是否继续流入。"),
        ("d1_oib_ratio", "试盘后 1 日 OIB 确认", "试盘后第 1 日订单失衡是否继续为正。"),
        ("d3_l2_super_net_ratio", "试盘后 3 日超大单确认", "试盘后第 3 日超大单是否继续流入。"),
        ("d3_oib_ratio", "试盘后 3 日 OIB 确认", "试盘后第 3 日订单失衡是否继续为正。"),
        ("d5_l2_super_net_ratio", "试盘后 5 日超大单确认", "试盘后第 5 日超大单是否继续流入。"),
        ("d5_oib_ratio", "试盘后 5 日 OIB 确认", "试盘后第 5 日订单失衡是否继续为正。"),
    ]
    return pd.DataFrame(rows, columns=["feature_name", "business_name", "business_meaning"])


def build_review_samples(df: pd.DataFrame, prob_col: str, target_col: str, limit: int = 30) -> pd.DataFrame:
    ok = df[df[target_col] == 1].sort_values(prob_col, ascending=False).head(limit)
    bad = df[df[target_col] == 0].sort_values(prob_col, ascending=False).head(limit)
    out = pd.concat([ok.assign(review_group="success"), bad.assign(review_group="failure")], ignore_index=True)
    cols = [
        "review_group",
        "symbol",
        "trade_date",
        "probe_index",
        "oib_ratio",
        "same_day_pullback_ratio",
        "day_gap_pct",
        "hot_theme_best_rank",
        "confirm_d1_pos",
        "confirm_d3_pos",
        "confirm_d5_pos",
        prob_col,
        target_col,
    ]
    return out[cols]


def write_scoring_blueprint(metrics: Dict[str, Dict[str, float]]) -> None:
    lines = [
        "# 试盘信号评分蓝图",
        "",
        "## 目标",
        "- 不是看到试盘就给买卖结论，而是把试盘翻译成一个条件概率框架。",
        "- 输出分成两条线：首板线和趋势线。",
        "",
        "## 实盘流程",
        "1. 盘后先识别试盘事件。",
        "2. 提取试盘当日特征：试盘序号、OIB、超大单、回吐结构、盘口托举、热点位置。",
        "3. 再提取试盘后确认特征：第 1/3/5 日超大单是否继续流入，OIB 是否继续为正，热点是否继续回流。",
        "4. 分别计算：",
        "   - 首板概率",
        "   - 首板延续概率",
        "   - 20 日冲高概率",
        "   - 40 日趋势概率",
        "5. 给出原因摘要，而不是只报一个分数。",
        "",
        "## 当前原型",
        f"- 首板概率验证 AUC：{metrics['limitup']['valid_auc']}",
        f"- 趋势概率验证 AUC：{metrics['trend']['valid_auc']}",
        "",
        "## 使用方式",
        "- 对于首板型票，优先看第一次试盘且试盘后 1 到 3 日资金继续确认的样本。",
        "- 对于趋势型票，优先看第二次或第三次试盘、强 OIB、热点仍在、试盘后资金没有撤退的样本。",
        "- 盘后候选池里每只票都要给：概率、原因摘要、等待窗口。",
        "",
    ]
    (OUT_DIR / "probe_signal_scoring_blueprint.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    probes = load_probe_events()
    feature_df = load_feature_store(probes)
    daily, limit_df = load_daily_and_limit(probes)
    frame = build_feature_frame(probes, feature_df)
    frame = build_confirmation_features(frame, feature_df)
    frame = build_targets(frame, daily, limit_df)
    frame = add_group_flags(frame)

    feature_dict = build_feature_dictionary()
    feature_dict.to_csv(OUT_DIR / "probe_feature_dictionary.csv", index=False)

    limitup_features = [
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
    trend_features = [
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

    limitup_scored, limitup_metrics, limitup_coef = fit_probability_model(frame, limitup_features, "target_limitup", "limitup")
    trend_scored, trend_metrics, trend_coef = fit_probability_model(frame, trend_features, "target_trend20", "trend20")

    limitup_table = build_probability_table(limitup_scored, "target_limitup")
    trend_table = build_probability_table(trend_scored, "target_trend20")
    limitup_table.to_csv(OUT_DIR / "probe_limitup_probability_table.csv", index=False)
    trend_table.to_csv(OUT_DIR / "probe_trend_probability_table.csv", index=False)
    limitup_coef.to_csv(OUT_DIR / "probe_limitup_feature_importance.csv", index=False)
    trend_coef.to_csv(OUT_DIR / "probe_trend_feature_importance.csv", index=False)

    all_scored = frame.copy()
    all_scored = build_candidate_pool(all_scored, limitup_scored, "limitup", "limitup_probability")
    all_scored = build_candidate_pool(all_scored, trend_scored, "trend20", "trend20_probability")
    limitup_pool_cols = [
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
        "target_limitup",
        "target_limitup_extend",
        "days_to_first_limit_close",
        "has_2board_from_first_close",
        "has_3board_from_first_close",
    ]
    trend_pool_cols = [
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
        "trend20_probability",
        "trend20_probability_sample_split",
        "target_trend20",
        "target_trend40",
        "high_20d_pct",
        "high_40d_pct",
    ]
    all_scored[limitup_pool_cols].to_csv(OUT_DIR / "probe_limitup_candidate_pool.csv", index=False)
    all_scored[trend_pool_cols].to_csv(OUT_DIR / "probe_trend_candidate_pool.csv", index=False)

    limitup_review = build_review_samples(
        all_scored[
            [
                "symbol",
                "trade_date",
                "probe_index",
                "oib_ratio",
                "same_day_pullback_ratio",
                "day_gap_pct",
                "hot_theme_best_rank",
                "confirm_d1_pos",
                "confirm_d3_pos",
                "confirm_d5_pos",
                "limitup_probability",
                "target_limitup",
            ]
        ].copy(),
        "limitup_probability",
        "target_limitup",
    )
    trend_review = build_review_samples(
        all_scored[
            [
                "symbol",
                "trade_date",
                "probe_index",
                "oib_ratio",
                "same_day_pullback_ratio",
                "day_gap_pct",
                "hot_theme_best_rank",
                "confirm_d1_pos",
                "confirm_d3_pos",
                "confirm_d5_pos",
                "trend20_probability",
                "target_trend20",
            ]
        ].copy(),
        "trend20_probability",
        "target_trend20",
    )
    limitup_review.to_csv(OUT_DIR / "probe_limitup_success_failure_review.csv", index=False)
    trend_review.to_csv(OUT_DIR / "probe_trend_success_failure_review.csv", index=False)

    (OUT_DIR / "probe_limitup_target_definition.md").write_text(
        "\n".join(
            [
                "# 首板 / 连板目标定义",
                "",
                "- `target_limitup`：试盘后 20 个交易日内，至少出现一次涨停收盘。",
                "- `target_limitup_extend`：第一次涨停收盘之后，还能继续走成 2 连板或 3 连板。",
                "- 这条线主要回答：什么样的试盘更像后面会被正式点成首板。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (OUT_DIR / "probe_trend_target_definition.md").write_text(
        "\n".join(
            [
                "# 趋势目标定义",
                "",
                "- `target_trend20`：试盘后 20 个交易日内，最高涨幅达到 20%。",
                "- `target_trend40`：试盘后 40 个交易日内，最高涨幅达到 30%。",
                "- 这条线主要回答：什么样的试盘不一定马上板，但更容易走出一波趋势拉升。",
                "",
            ]
        ),
        encoding="utf-8",
    )

    metrics = {"limitup": limitup_metrics, "trend": trend_metrics}
    write_scoring_blueprint(metrics)
    summary = {
        "range": {"train_start": TRAIN_START, "train_end": TRAIN_END, "valid_start": VALID_START, "valid_end": VALID_END},
        "probe_count": int(len(frame)),
        "targets": {
            "limitup_rate": round(float(pd.to_numeric(frame["target_limitup"], errors="coerce").mean()), 4),
            "trend20_rate": round(float(pd.to_numeric(frame["target_trend20"], errors="coerce").mean()), 4),
        },
        "metrics": metrics,
    }
    (OUT_DIR / "probe_signal_probability_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
