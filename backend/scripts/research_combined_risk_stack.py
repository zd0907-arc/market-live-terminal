from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXP_DIR = Path("docs/strategy-rework/strategies/S04-capital-exit-risk/experiments/EXP-20260426-combined-risk-stack")
V14_TRADES = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes/all_mode_trades.csv")
ATOMIC_DB = Path("/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db")

BUY_COST = 1.0 + 15 / 10000 + (20 / 10000) / 2
SELL_COST = 1.0 - 15 / 10000 - (20 / 10000) / 2


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def summarize(df: pd.DataFrame, ret_col: str = "net_return_pct") -> Dict[str, Any]:
    if df is None or df.empty:
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


def load_base_trades() -> pd.DataFrame:
    df = pd.read_csv(V14_TRADES)
    df = df[(df["strategy_mode"] == "v1.4-balanced") & (df["is_mature_trade"].astype(bool))].copy()
    df = df.sort_values(["entry_date", "symbol", "discovery_date"]).reset_index(drop=True)
    return df


def load_raw(symbols: List[str], start: str, end: str) -> pd.DataFrame:
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
        df = pd.read_sql_query(sql, conn, params=[start, end, *[s.lower() for s in symbols]])
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


def sell_pressure_features(g: pd.DataFrame, rec: pd.Series) -> Dict[str, Any]:
    launch = window(g, rec.launch_start_date, rec.launch_end_date)
    confirm = window(g, rec.pullback_confirm_date, rec.pullback_confirm_date)
    hist = g[g.trade_date < str(rec.launch_start_date)].tail(20) if not pd.isna(rec.launch_start_date) else g.iloc[0:0]

    hist_add_sell_day = float(hist.add_sell_amount.mean()) if not hist.empty else 0.0
    hist_add_sell_ratio = float((hist.add_sell_amount / hist.total_amount.replace(0, pd.NA)).dropna().mean()) if not hist.empty else 0.0

    def stage(prefix: str, w: pd.DataFrame) -> Dict[str, Any]:
        days = max(int(len(w)), 1)
        add_sell = float(w.add_sell_amount.sum()) if not w.empty else 0.0
        amount = float(w.total_amount.sum()) if not w.empty else 0.0
        add_sell_ratio = add_sell / amount if amount > 0 else 0.0
        return {
            f"{prefix}_add_sell_amount_vs_hist": round(add_sell / max(hist_add_sell_day * days, 1.0), 4),
            f"{prefix}_add_sell_ratio_vs_hist": round(add_sell_ratio / max(hist_add_sell_ratio, 1e-9), 4) if hist_add_sell_ratio > 0 else 0.0,
            f"{prefix}_sell_pressure_ratio": round(float(w.sell_pressure_ratio.mean()), 6) if not w.empty else 0.0,
            f"{prefix}_buy_support_ratio": round(float(w.buy_support_ratio.mean()), 6) if not w.empty else 0.0,
            f"{prefix}_support_pressure_spread": round(float((w.buy_support_ratio - w.sell_pressure_ratio).mean()), 6) if not w.empty else 0.0,
        }

    out = {**stage("launch3", launch), **stage("confirm", confirm)}
    c = one_day(g, rec.pullback_confirm_date)
    out.update({
        "confirm_day_super_net_amount": round(fnum(c.l2_super_net_amount) if c is not None else 0.0, 2),
        "confirm_day_main_net_amount": round(fnum(c.l2_main_net_amount) if c is not None else 0.0, 2),
    })
    return out


def oib_cvd_features(g: pd.DataFrame, rec: pd.Series) -> Dict[str, Any]:
    launch = window(g, rec.launch_start_date, rec.launch_end_date)
    confirm = window(g, rec.pullback_confirm_date, rec.pullback_confirm_date)
    def calc(prefix: str, w: pd.DataFrame) -> Dict[str, Any]:
        oib = float(w.oib_delta_amount.sum()) if not w.empty else 0.0
        cvd = float(w.cvd_delta_amount.sum()) if not w.empty else 0.0
        return {
            f"{prefix}_oib_sum": round(oib, 2),
            f"{prefix}_cvd_sum": round(cvd, 2),
            f"{prefix}_oib_cvd_diff": round(oib - cvd, 2),
            f"{prefix}_oib_pos_cvd_nonpos": bool(oib > 0 and cvd <= 0),
        }
    return {**calc("launch", launch), **calc("confirm", confirm)}


def early_path_features(g: pd.DataFrame, rec: pd.Series) -> Dict[str, Any]:
    rows = g[g.trade_date >= str(rec.entry_date)].head(5).reset_index(drop=True)
    cum_super = 0.0
    cum_main = 0.0
    cum_super_peak = 0.0
    out: Dict[str, Any] = {}
    gross_entry = fnum(rec.gross_entry_price)
    for i, row in rows.iterrows():
        day = i + 1
        cum_super += fnum(row.l2_super_net_amount)
        cum_main += fnum(row.l2_main_net_amount)
        cum_super_peak = max(cum_super_peak, cum_super)
        close_ret = (fnum(row.close) / gross_entry - 1.0) * 100 if gross_entry > 0 else 0.0
        dd = (cum_super_peak - cum_super) / cum_super_peak * 100 if cum_super_peak > 0 else 0.0
        out.update({
            f"d{day}_date": str(row.trade_date),
            f"d{day}_cum_super_amount": round(cum_super, 2),
            f"d{day}_cum_main_amount": round(cum_main, 2),
            f"d{day}_cum_super_peak_dd_pct": round(dd, 2),
            f"d{day}_close_return_pct": round(close_ret, 2),
        })
    return out


def build_features(trades: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in raw.groupby("symbol")}
    rows = []
    for _, rec in trades.iterrows():
        g = by_symbol.get(str(rec.symbol).lower())
        base = rec.to_dict()
        if g is None:
            rows.append({**base, "raw_available": False})
            continue
        enriched = {**base, "raw_available": True, **sell_pressure_features(g, rec), **oib_cvd_features(g, rec), **early_path_features(g, rec)}
        # 固定风险因子：R1 用 1.2 作为 M04B 样本内的“接近 1.5 撤梯子防线”观察阈值；1.5 已是上游硬过滤。
        r1 = fnum(enriched.get("launch_cancel_buy_to_add_buy_vs_hist")) >= 1.2
        r2 = bool(enriched.get("launch_oib_pos_cvd_nonpos"))
        r3 = fnum(enriched.get("confirm_distribution_score")) >= 50.0
        r4 = fnum(enriched.get("confirm_day_super_net_amount")) < 0 and fnum(enriched.get("confirm_day_main_net_amount")) < 0
        r5 = fnum(enriched.get("launch3_return_pct")) < 6.0 and fnum(enriched.get("pullback_support_spread_avg")) < 0.0
        r6 = fnum(enriched.get("confirm_add_sell_amount_vs_hist")) >= 1.5 and fnum(enriched.get("confirm_support_pressure_spread")) <= 0.0
        rcols = {
            "R1_cancel_ladder_near_15": r1,
            "R2_launch_oib_cvd_divergence": r2,
            "R3_confirm_distribution_high": r3,
            "R4_confirm_super_main_both_negative": r4,
            "R5_weak_launch_poor_support": r5,
            "R6_confirm_sell_pressure_tag": r6,
        }
        enriched.update(rcols)
        enriched["risk_count_R1_R5"] = int(sum(bool(v) for k, v in rcols.items() if k != "R6_confirm_sell_pressure_tag"))
        enriched["risk_count_R1_R6"] = int(sum(bool(v) for v in rcols.values()))
        enriched["risk_labels"] = ";".join(k[:2] for k, v in rcols.items() if v)
        rows.append(enriched)
    return pd.DataFrame(rows)


def eval_entry_rule(df: pd.DataFrame, rule_name: str, mask: pd.Series) -> Dict[str, Any]:
    m = mask.fillna(False).astype(bool)
    kept = df[~m]
    filtered = df[m]
    return {
        "rule_name": rule_name,
        "total_trades": int(len(df)),
        "filtered_count": int(m.sum()),
        "filtered_return_avg_pct": summarize(filtered)["avg_return_pct"],
        "filtered_return_median_pct": summarize(filtered)["median_return_pct"],
        "filtered_sum_return_pct": summarize(filtered)["sum_return_pct"],
        "filtered_big_winner_gt_15_count": int((filtered.net_return_pct > 15).sum()),
        "filtered_loss_count": int((filtered.net_return_pct < 0).sum()),
        "filtered_big_loss_le_-8_count": int((filtered.net_return_pct <= -8).sum()),
        **{f"kept_{k}": v for k, v in summarize(kept).items()},
    }


def scan_entry_rules(df: pd.DataFrame) -> pd.DataFrame:
    rules: Dict[str, pd.Series] = {}
    rules["risk_count_R1_R5>=2"] = df.risk_count_R1_R5 >= 2
    rules["risk_count_R1_R5>=3"] = df.risk_count_R1_R5 >= 3
    rules["risk_count_R1_R6>=2"] = df.risk_count_R1_R6 >= 2
    rules["risk_count_R1_R6>=3"] = df.risk_count_R1_R6 >= 3
    rules["R2_and_any_R3_R4_R5"] = df.R2_launch_oib_cvd_divergence & (df.R3_confirm_distribution_high | df.R4_confirm_super_main_both_negative | df.R5_weak_launch_poor_support)
    rules["R3_and_R5"] = df.R3_confirm_distribution_high & df.R5_weak_launch_poor_support
    rules["R4_and_price_weak_nextday"] = df.R4_confirm_super_main_both_negative & (pd.to_numeric(df.get("d2_close_return_pct"), errors="coerce") < 0)
    rules["R6_plus_any_core"] = df.R6_confirm_sell_pressure_tag & (df.risk_count_R1_R5 >= 1)
    out = pd.DataFrame([eval_entry_rule(df, name, mask) for name, mask in rules.items()])
    return out.sort_values(["kept_avg_return_pct", "filtered_count"], ascending=[False, True])


def next_open_after(g: pd.DataFrame, date: str) -> tuple[str, float]:
    fut = g[g.trade_date > date]
    if fut.empty:
        row = g[g.trade_date == date].iloc[0]
        return str(row.trade_date), fnum(row.close)
    row = fut.iloc[0]
    return str(row.trade_date), fnum(row.open)


def first_early_signal(row: pd.Series, rule: str) -> Optional[str]:
    max_day = 3
    for d in range(1, max_day + 1):
        date = row.get(f"d{d}_date")
        if pd.isna(date) or not date:
            continue
        cum_super = fnum(row.get(f"d{d}_cum_super_amount"))
        cum_main = fnum(row.get(f"d{d}_cum_main_amount"))
        close_ret = fnum(row.get(f"d{d}_close_return_pct"))
        dd = fnum(row.get(f"d{d}_cum_super_peak_dd_pct"))
        if rule == "D2_3_cum_super_main_neg_and_loss" and d >= 2 and cum_super < 0 and cum_main < 0 and close_ret < 0:
            return str(date)
        if rule == "D1_3_cum_super_neg_and_loss" and cum_super < 0 and close_ret < 0:
            return str(date)
        if rule == "D2_3_super_peak_dd20_and_loss" and d >= 2 and dd >= 20 and close_ret < 0:
            return str(date)
        if rule == "D2_3_super_or_main_neg_and_loss_gt2" and d >= 2 and (cum_super < 0 or cum_main < 0) and close_ret <= -2:
            return str(date)
    return None


def eval_early_exit_rule(df: pd.DataFrame, raw: pd.DataFrame, rule: str) -> tuple[Dict[str, Any], pd.DataFrame]:
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in raw.groupby("symbol")}
    rows = []
    for _, rec in df.iterrows():
        sig = first_early_signal(rec, rule)
        new = rec.to_dict()
        new["early_exit_rule"] = rule
        new["early_exit_triggered"] = False
        new["new_net_return_pct"] = fnum(rec.net_return_pct)
        if sig and str(sig) < str(rec.exit_signal_date):
            g = by_symbol[str(rec.symbol).lower()]
            exit_date, gross_exit = next_open_after(g[g.trade_date >= str(rec.entry_date)], sig)
            if gross_exit > 0:
                exit_price = gross_exit * SELL_COST
                entry_price = fnum(rec.entry_price)
                new.update({
                    "early_exit_triggered": True,
                    "early_exit_signal_date": sig,
                    "early_exit_date": exit_date,
                    "early_exit_gross_exit_price": round(gross_exit, 4),
                    "new_net_return_pct": round((exit_price / entry_price - 1.0) * 100.0, 2) if entry_price > 0 else fnum(rec.net_return_pct),
                })
        rows.append(new)
    out = pd.DataFrame(rows)
    changed = out[out.early_exit_triggered]
    summary = {
        "rule_name": rule,
        "total_trades": int(len(out)),
        "early_exit_count": int(len(changed)),
        "early_exit_original_avg_return_pct": summarize(changed)["avg_return_pct"],
        "early_exit_original_median_return_pct": summarize(changed)["median_return_pct"],
        "early_exit_new_avg_return_pct": summarize(changed, "new_net_return_pct")["avg_return_pct"],
        "early_exit_new_median_return_pct": summarize(changed, "new_net_return_pct")["median_return_pct"],
        "early_exit_delta_sum_pct": round(float((changed.new_net_return_pct - changed.net_return_pct).sum()), 2) if not changed.empty else 0.0,
        "early_exit_big_winner_gt_15_count": int((changed.net_return_pct > 15).sum()) if not changed.empty else 0,
        **{f"final_{k}": v for k, v in summarize(out, "new_net_return_pct").items()},
    }
    return summary, out


def scan_early_exit(df: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    rules = [
        "D2_3_cum_super_main_neg_and_loss",
        "D1_3_cum_super_neg_and_loss",
        "D2_3_super_peak_dd20_and_loss",
        "D2_3_super_or_main_neg_and_loss_gt2",
    ]
    summaries = []
    details: Dict[str, pd.DataFrame] = {}
    for rule in rules:
        s, d = eval_early_exit_rule(df, raw, rule)
        summaries.append(s)
        details[rule] = d
    return pd.DataFrame(summaries).sort_values(["final_avg_return_pct", "early_exit_big_winner_gt_15_count"], ascending=[False, True]), details


def write_readme(summary: Dict[str, Any], entry_scan: pd.DataFrame, early_scan: pd.DataFrame) -> None:
    lines = [
        "# EXP-20260426-combined-risk-stack：组合风险因子实验",
        "",
        "## 1. 问题",
        "单个压单/OIB-CVD/撤梯子信号都有误杀，验证多个风险因子同时出现时，是否能更稳定过滤亏损且少误杀大赢家。",
        "",
        "## 2. 假设",
        "不让任一单因子主导；只有风险堆叠或买入后早期资金失败同时伴随价格亏损时，才作为 S04 风险模块候选。",
        "",
        "## 3. 数据范围",
        "- 成熟交易样本：旧 `v1.4-balanced` / S01-M04B，买入后至少 10 个交易日，41 笔。",
        "- 发现日：2026-03-02 ~ 2026-04-24；回放到 2026-04-24。",
        "- 原子日线补充：2026-01-01 ~ 2026-04-24。",
        "",
        "## 4. 样本口径",
        f"基准：{summary['base_summary']}",
        "",
        "## 5. 规则/参数",
        "- R1：`launch_cancel_buy_to_add_buy_vs_hist >= 1.2`，M04B 已硬过滤 1.5，这里作为接近防线的观察标签。",
        "- R2：启动期 `OIB > 0 且 CVD <= 0`。",
        "- R3：确认日 `confirm_distribution_score >= 50`。",
        "- R4：确认日超大单和主力净额均为负。",
        "- R5：`launch3_return_pct < 6 且 pullback_support_spread_avg < 0`。",
        "- R6：确认日新增卖挂单相对历史 >=1.5 且支撑压力差 <=0；只作附加标签。",
        "- 早退：买入后 1~3 日累计资金转弱且价格亏损时模拟次日开盘卖出。",
        "",
        "## 6. 输出文件",
        "- `combined_risk_trade_features.csv`",
        "- `entry_filter_rule_scan.csv`",
        "- `early_exit_rule_scan.csv`",
        "- `recommended_rule_trades.csv`",
        "- `summary.json`",
        "",
        "## 7. 核心结果",
        "",
        "### 入场前过滤扫描",
        entry_scan.to_markdown(index=False),
        "",
        "### 买入后早期退出扫描",
        early_scan.to_markdown(index=False),
        "",
        "## 8. 结论：采纳为 S04 观察型风险模块，不建议直接接入 S01 默认硬过滤",
        "组合风险堆叠有解释力，但当前 41 笔样本太小；推荐先沉淀 S04 风险标签和人工复盘字段。早期退出规则改善不稳定，暂不接入 S01 默认策略。",
        "",
    ]
    (EXP_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> Dict[str, Any]:
    t0 = time.perf_counter()
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    trades = load_base_trades()
    symbols = sorted(trades.symbol.str.lower().unique().tolist())
    raw = load_raw(symbols, args.raw_start, args.replay_end)
    features = build_features(trades, raw)
    features.to_csv(EXP_DIR / "combined_risk_trade_features.csv", index=False)

    entry_scan = scan_entry_rules(features)
    entry_scan.to_csv(EXP_DIR / "entry_filter_rule_scan.csv", index=False)

    early_scan, early_details = scan_early_exit(features, raw)
    early_scan.to_csv(EXP_DIR / "early_exit_rule_scan.csv", index=False)

    recommended_entry_rule = "risk_count_R1_R5>=2"
    recommended_early_rule = "none"
    recommended_mask = features.risk_count_R1_R5 >= 2
    # 早退扫描整体伤害收益，所以推荐明细不应用任何早退出场，只保留扫描字段供复盘。
    rec_detail = features.copy()
    rec_detail["early_exit_rule"] = recommended_early_rule
    rec_detail["early_exit_triggered"] = False
    rec_detail["new_net_return_pct"] = rec_detail["net_return_pct"]
    rec_detail["recommended_entry_filter"] = recommended_mask.values
    rec_detail["recommended_action"] = rec_detail.apply(
        lambda r: "entry_filter" if bool(r["recommended_entry_filter"]) else ("early_exit" if bool(r["early_exit_triggered"]) else "keep"), axis=1
    )
    rec_detail.to_csv(EXP_DIR / "recommended_rule_trades.csv", index=False)

    recommended_kept = rec_detail[~rec_detail.recommended_entry_filter].copy()
    # entry filtered trades are skipped; early exit return is in new_net_return_pct.
    summary = {
        "experiment": "EXP-20260426-combined-risk-stack",
        "inputs": {"v1_4_balanced_trades": str(V14_TRADES), "atomic_db": str(ATOMIC_DB)},
        "range": {"raw_start": args.raw_start, "replay_end": args.replay_end},
        "base_summary": summarize(features),
        "risk_factor_counts": {
            "R1_cancel_ladder_near_15": int(features.R1_cancel_ladder_near_15.sum()),
            "R2_launch_oib_cvd_divergence": int(features.R2_launch_oib_cvd_divergence.sum()),
            "R3_confirm_distribution_high": int(features.R3_confirm_distribution_high.sum()),
            "R4_confirm_super_main_both_negative": int(features.R4_confirm_super_main_both_negative.sum()),
            "R5_weak_launch_poor_support": int(features.R5_weak_launch_poor_support.sum()),
            "R6_confirm_sell_pressure_tag": int(features.R6_confirm_sell_pressure_tag.sum()),
            "risk_count_R1_R5_ge_2": int((features.risk_count_R1_R5 >= 2).sum()),
            "risk_count_R1_R5_ge_3": int((features.risk_count_R1_R5 >= 3).sum()),
        },
        "best_entry_rules": entry_scan.head(5).to_dict("records"),
        "best_early_exit_rules": early_scan.head(4).to_dict("records"),
        "recommended_rule": {
            "entry_filter": recommended_entry_rule,
            "early_exit": recommended_early_rule,
            "recommended_summary_after_entry_filter_and_early_exit": summarize(recommended_kept, "new_net_return_pct"),
            "entry_filtered_summary": summarize(rec_detail[rec_detail.recommended_entry_filter]),
            "early_exited_summary_original": summarize(rec_detail[rec_detail.early_exit_triggered]),
            "early_exited_summary_new": summarize(rec_detail[rec_detail.early_exit_triggered], "new_net_return_pct"),
            "false_killed_big_winners_gt_15": int(((rec_detail.recommended_entry_filter) & (rec_detail.net_return_pct > 15)).sum()),
        },
        "recommendation": {
            "form_s04_module": True,
            "connect_to_s01_default": False,
            "reason": "风险堆叠可作为 S04 标签；样本小且硬过滤会减少交易，早退改善不稳定，暂不进入 S01 默认策略。",
        },
        "timing_seconds": round(time.perf_counter() - t0, 2),
    }
    (EXP_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(summary, entry_scan, early_scan)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-start", default="2026-01-01")
    parser.add_argument("--replay-end", default="2026-04-24")
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
