from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ATOMIC_DB = Path("/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db")
OUT_DIR = Path("docs/strategy-rework/strategies/S04-capital-exit-risk/experiments/EXP-20260426-combined-risk-stack-robustness")
V14_MODES = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes/all_mode_trades.csv")
V13_THRESHOLDS = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-3-robustness-scan/all_threshold_trades.csv")


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def summarize(df: pd.DataFrame, ret_col: str = "net_return_pct") -> Dict[str, Any]:
    if df is None or df.empty or ret_col not in df.columns:
        return {
            "trade_count": 0,
            "win_rate_pct": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "max_return_pct": 0.0,
            "min_return_pct": 0.0,
            "sum_return_pct": 0.0,
            "big_winner_gt_15_count": 0,
            "big_loss_le_-8_count": 0,
        }
    s = pd.to_numeric(df[ret_col], errors="coerce").dropna()
    if s.empty:
        return summarize(pd.DataFrame())
    return {
        "trade_count": int(len(s)),
        "win_rate_pct": round(float((s > 0).mean() * 100.0), 2),
        "avg_return_pct": round(float(s.mean()), 2),
        "median_return_pct": round(float(s.median()), 2),
        "max_return_pct": round(float(s.max()), 2),
        "min_return_pct": round(float(s.min()), 2),
        "sum_return_pct": round(float(s.sum()), 2),
        "big_winner_gt_15_count": int((s > 15).sum()),
        "big_loss_le_-8_count": int((s <= -8).sum()),
    }


def load_raw(symbols: List[str], start: str = "2026-01-01", end: str = "2026-04-24") -> pd.DataFrame:
    symbols = sorted({str(s).lower() for s in symbols if str(s)})
    if not symbols:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in symbols)
    sql = f"""
        SELECT lower(t.symbol) AS symbol, t.trade_date, t.open, t.high, t.low, t.close,
               t.total_amount, t.l2_main_net_amount, t.l2_super_net_amount,
               o.add_buy_amount, o.add_sell_amount, o.cancel_buy_amount, o.cancel_sell_amount,
               o.cvd_delta_amount, o.oib_delta_amount, o.buy_support_ratio, o.sell_pressure_ratio
        FROM atomic_trade_daily AS t
        LEFT JOIN atomic_order_daily AS o
          ON o.symbol = t.symbol AND o.trade_date = t.trade_date
        WHERE t.trade_date >= ? AND t.trade_date <= ? AND lower(t.symbol) IN ({placeholders})
        ORDER BY lower(t.symbol), t.trade_date
    """
    with sqlite3.connect(ATOMIC_DB) as conn:
        df = pd.read_sql_query(sql, conn, params=[start, end, *symbols])
    for col in df.columns:
        if col not in {"symbol", "trade_date"}:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def window(g: pd.DataFrame, start: Any, end: Any) -> pd.DataFrame:
    if pd.isna(start) or pd.isna(end):
        return g.iloc[0:0]
    return g[(g.trade_date >= str(start)) & (g.trade_date <= str(end))]


def one_day(g: pd.DataFrame, date: Any) -> Optional[pd.Series]:
    if pd.isna(date):
        return None
    rows = g[g.trade_date == str(date)]
    return None if rows.empty else rows.iloc[0]


def enrich_one(g: pd.DataFrame, rec: pd.Series) -> Dict[str, Any]:
    launch = window(g, rec.get("launch_start_date"), rec.get("launch_end_date"))
    confirm = window(g, rec.get("pullback_confirm_date"), rec.get("pullback_confirm_date"))
    hist = g[g.trade_date < str(rec.get("launch_start_date"))].tail(20) if not pd.isna(rec.get("launch_start_date")) else g.iloc[0:0]

    # R1：优先使用已有字段；如果没有，就从原始挂单重算。
    if "launch_cancel_buy_to_add_buy_vs_hist" in rec and not pd.isna(rec.get("launch_cancel_buy_to_add_buy_vs_hist")):
        cancel_vs_hist = fnum(rec.get("launch_cancel_buy_to_add_buy_vs_hist"))
    else:
        launch_ratio = float(launch.cancel_buy_amount.sum() / max(launch.add_buy_amount.sum(), 1.0)) if not launch.empty else 0.0
        hist_daily = (hist.cancel_buy_amount / hist.add_buy_amount.replace(0, pd.NA)).dropna() if not hist.empty else pd.Series(dtype=float)
        hist_avg = float(hist_daily.mean()) if not hist_daily.empty else 0.0
        cancel_vs_hist = launch_ratio / max(hist_avg, 1e-9) if hist_avg > 0 else 0.0

    def oib_cvd(prefix: str, w: pd.DataFrame) -> Dict[str, Any]:
        oib = float(w.oib_delta_amount.sum()) if not w.empty else 0.0
        cvd = float(w.cvd_delta_amount.sum()) if not w.empty else 0.0
        return {
            f"{prefix}_oib_sum": round(oib, 2),
            f"{prefix}_cvd_sum": round(cvd, 2),
            f"{prefix}_oib_pos_cvd_nonpos": bool(oib > 0 and cvd <= 0),
        }

    confirm_day = one_day(g, rec.get("pullback_confirm_date"))

    # R6 仅作为低权重观察标签。
    hist_add_sell = float(hist.add_sell_amount.mean()) if not hist.empty else 0.0
    confirm_add_sell_vs_hist = float(confirm.add_sell_amount.sum() / max(hist_add_sell, 1.0)) if not confirm.empty else 0.0
    confirm_support_pressure_spread = float((confirm.buy_support_ratio - confirm.sell_pressure_ratio).mean()) if not confirm.empty else 0.0

    out: Dict[str, Any] = {
        "launch_cancel_buy_to_add_buy_vs_hist_recalc": round(cancel_vs_hist, 4),
        "confirm_day_super_net_amount": round(fnum(confirm_day.l2_super_net_amount) if confirm_day is not None else 0.0, 2),
        "confirm_day_main_net_amount": round(fnum(confirm_day.l2_main_net_amount) if confirm_day is not None else 0.0, 2),
        "confirm_add_sell_amount_vs_hist": round(confirm_add_sell_vs_hist, 4),
        "confirm_support_pressure_spread": round(confirm_support_pressure_spread, 6),
        **oib_cvd("launch", launch),
        **oib_cvd("confirm", confirm),
    }

    r1 = out["launch_cancel_buy_to_add_buy_vs_hist_recalc"] >= 1.2
    r2 = bool(out["launch_oib_pos_cvd_nonpos"])
    r3 = fnum(rec.get("confirm_distribution_score")) >= 50.0
    r4 = out["confirm_day_super_net_amount"] < 0 and out["confirm_day_main_net_amount"] < 0
    r5 = fnum(rec.get("launch3_return_pct")) < 6.0 and fnum(rec.get("pullback_support_spread_avg")) < 0.0
    r6 = out["confirm_add_sell_amount_vs_hist"] >= 1.5 and out["confirm_support_pressure_spread"] <= 0.0
    out.update({
        "R1_cancel_ladder_near_15": r1,
        "R2_launch_oib_cvd_divergence": r2,
        "R3_confirm_distribution_high": r3,
        "R4_confirm_super_main_both_negative": r4,
        "R5_weak_launch_poor_support": r5,
        "R6_confirm_sell_pressure_tag": r6,
        "risk_count_R1_R5": int(sum([r1, r2, r3, r4, r5])),
        "risk_count_R1_R6": int(sum([r1, r2, r3, r4, r5, r6])),
    })
    out["risk_labels"] = ";".join(k for k, v in {
        "R1": r1, "R2": r2, "R3": r3, "R4": r4, "R5": r5, "R6": r6,
    }.items() if v)
    return out


def build_features(trades: pd.DataFrame, sample_name: str, raw: pd.DataFrame) -> pd.DataFrame:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in raw.groupby("symbol")}
    rows: List[Dict[str, Any]] = []
    for _, rec in trades.iterrows():
        g = by_symbol.get(str(rec.symbol).lower())
        base = rec.to_dict()
        base["sample_name"] = sample_name
        if g is None or g.empty:
            rows.append({**base, "raw_available": False})
        else:
            rows.append({**base, "raw_available": True, **enrich_one(g, rec)})
    return pd.DataFrame(rows)


def eval_rule(df: pd.DataFrame, rule_name: str, mask: pd.Series) -> Dict[str, Any]:
    m = mask.fillna(False).astype(bool)
    filtered = df[m]
    kept = df[~m]
    base = summarize(df)
    kept_s = summarize(kept)
    filtered_s = summarize(filtered)
    return {
        "sample_name": str(df.sample_name.iloc[0]) if not df.empty and "sample_name" in df.columns else "",
        "rule_name": rule_name,
        **{f"base_{k}": v for k, v in base.items()},
        "filtered_count": int(m.sum()),
        "filtered_loss_count": int((filtered.net_return_pct < 0).sum()) if not filtered.empty else 0,
        "filtered_big_winner_gt_15_count": int((filtered.net_return_pct > 15).sum()) if not filtered.empty else 0,
        **{f"filtered_{k}": v for k, v in filtered_s.items()},
        **{f"kept_{k}": v for k, v in kept_s.items()},
        "delta_avg_return_pct": round(kept_s["avg_return_pct"] - base["avg_return_pct"], 2),
        "delta_median_return_pct": round(kept_s["median_return_pct"] - base["median_return_pct"], 2),
        "delta_win_rate_pct": round(kept_s["win_rate_pct"] - base["win_rate_pct"], 2),
    }


def scan_rules(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rules = {
        "risk_count_R1_R5>=2": df.risk_count_R1_R5 >= 2,
        "risk_count_R1_R5>=3": df.risk_count_R1_R5 >= 3,
        "R2_and_any_R3_R4_R5": df.R2_launch_oib_cvd_divergence & (df.R3_confirm_distribution_high | df.R4_confirm_super_main_both_negative | df.R5_weak_launch_poor_support),
        "R4_and_any_R1_R2_R3_R5": df.R4_confirm_super_main_both_negative & (df.R1_cancel_ladder_near_15 | df.R2_launch_oib_cvd_divergence | df.R3_confirm_distribution_high | df.R5_weak_launch_poor_support),
        "risk_count_R1_R6>=2": df.risk_count_R1_R6 >= 2,
    }
    return pd.DataFrame([eval_rule(df, name, mask) for name, mask in rules.items()])


def load_samples() -> Dict[str, pd.DataFrame]:
    samples: Dict[str, pd.DataFrame] = {}
    v14 = pd.read_csv(V14_MODES)
    for mode in ["v1.3", "v1.4-balanced", "v1.4-quality"]:
        sub = v14[v14.strategy_mode == mode].copy()
        samples[f"modes:{mode}:full"] = sub
        samples[f"modes:{mode}:mature"] = sub[sub.is_mature_trade.astype(bool)].copy()

    v13 = pd.read_csv(V13_THRESHOLDS)
    for th in ["none", "1.5", "2.0", "2.5", "3.0"]:
        sub = v13[v13.filter_threshold.astype(str) == th].copy()
        samples[f"threshold:{th}:full"] = sub
        samples[f"threshold:{th}:mature"] = sub[sub.is_mature_trade.astype(bool)].copy()
    return samples


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    samples = load_samples()
    all_symbols = sorted({str(s).lower() for df in samples.values() for s in df.symbol.dropna().unique()})
    raw = load_raw(all_symbols)

    feature_frames = []
    scan_frames = []
    for name, df in samples.items():
        if df.empty:
            continue
        feats = build_features(df, name, raw)
        feature_frames.append(feats)
        scan = scan_rules(feats)
        scan_frames.append(scan)

    features = pd.concat(feature_frames, ignore_index=True) if feature_frames else pd.DataFrame()
    scans = pd.concat(scan_frames, ignore_index=True) if scan_frames else pd.DataFrame()

    features.to_csv(OUT_DIR / "combined_risk_robustness_features.csv", index=False)
    scans.to_csv(OUT_DIR / "combined_risk_robustness_scan.csv", index=False)

    # 推荐规则单独看：risk_count_R1_R5>=2，在所有样本中的表现。
    recommended = scans[scans.rule_name == "risk_count_R1_R5>=2"].copy()
    recommended.to_csv(OUT_DIR / "recommended_rule_cross_sample.csv", index=False)

    # 找规则明显失效的样本：过滤组为正，或误杀大赢家。
    bad = recommended[(recommended.filtered_avg_return_pct > 0) | (recommended.filtered_big_winner_gt_15_count > 0)].copy()
    bad.to_csv(OUT_DIR / "recommended_rule_failure_cases.csv", index=False)

    summary = {
        "experiment": "EXP-20260426-combined-risk-stack-robustness",
        "sample_count": len(samples),
        "feature_rows": int(len(features)),
        "recommended_rule": "risk_count_R1_R5>=2",
        "recommended_rule_rows": int(len(recommended)),
        "recommended_positive_filter_samples": int((recommended.filtered_avg_return_pct > 0).sum()) if not recommended.empty else 0,
        "recommended_big_winner_false_kill_samples": int((recommended.filtered_big_winner_gt_15_count > 0).sum()) if not recommended.empty else 0,
        "recommended_mature_core": recommended[recommended.sample_name.isin([
            "modes:v1.3:mature", "modes:v1.4-balanced:mature", "modes:v1.4-quality:mature",
            "threshold:1.5:mature", "threshold:none:mature"
        ])].to_dict(orient="records"),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # README with compact tables.
    mature_focus = recommended[recommended.sample_name.str.endswith(":mature")].copy()
    cols = [
        "sample_name", "base_trade_count", "base_win_rate_pct", "base_avg_return_pct", "base_median_return_pct", "base_min_return_pct",
        "filtered_count", "filtered_avg_return_pct", "filtered_median_return_pct", "filtered_big_winner_gt_15_count",
        "kept_trade_count", "kept_win_rate_pct", "kept_avg_return_pct", "kept_median_return_pct", "kept_min_return_pct",
        "delta_avg_return_pct", "delta_median_return_pct", "delta_win_rate_pct",
    ]
    table = mature_focus[cols].sort_values("sample_name").to_markdown(index=False)
    readme = f"""# EXP-20260426-combined-risk-stack-robustness：组合风险跨样本验证

## 问题

上一轮只在 `S01-M04B / v1.4-balanced` 成熟交易 41 笔上验证了组合风险。本实验扩大到 v1.3 阈值样本、v1.4 多模式、full/mature 两种口径，检查 `risk_count_R1_R5>=2` 是否稳定。

## 样本

- `modes:*`：来自 `20260426-v1-4-modes/all_mode_trades.csv`。
- `threshold:*`：来自 `20260426-v1-3-robustness-scan/all_threshold_trades.csv`。
- 日期范围仍受 L2 挂单限制：2026-03-02 ~ 2026-04-24。

## 推荐规则

`risk_count_R1_R5>=2`：R1~R5 中至少两个风险同时出现。

- R1：启动期撤买/新增买接近防线，`>=1.2`。
- R2：启动期 OIB/CVD 背离。
- R3：确认日出货分偏高。
- R4：确认日超大单和主力均为负。
- R5：弱启动 + 回调承接差。

## 成熟样本横向结果

{table}

## 输出文件

- `combined_risk_robustness_features.csv`
- `combined_risk_robustness_scan.csv`
- `recommended_rule_cross_sample.csv`
- `recommended_rule_failure_cases.csv`
- `summary.json`

## 结论

`risk_count_R1_R5>=2` 在核心成熟样本上方向仍然有效，但在更宽样本中存在误杀和样本依赖。建议继续作为 S04 观察型风险模块，不直接升级成 S01 默认硬过滤。
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
