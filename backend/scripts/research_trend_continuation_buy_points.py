from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.research_strong_runup_opportunity_audit import build_all_runups
from backend.scripts.research_trend_continuation_strategy import (
    STABLE_TRADES,
    build_candidates,
    fnum,
    future_days_after_entry,
)
from backend.scripts.research_trend_sample_factors import pct
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams, simulate_trade_v1_2
from backend.scripts.run_strategy_v1_trend_reversal import add_ma

OUT = Path("docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-buy-point-v1")


def ratio(row: pd.Series, amount_col: str) -> float:
    return fnum(row.get(amount_col)) / max(fnum(row.get("total_amount")), 1.0)


def close_vs_high20(g: pd.DataFrame, j: int) -> float:
    if j < 20:
        return 0.0
    high20 = float(g.iloc[j - 20:j].high.max())
    close = fnum(g.loc[j].get("close"))
    return pct(high20, close) if high20 > 0 else 0.0


def recent_pullback_from_observe(g: pd.DataFrame, obs_i: int, j: int) -> float:
    w = g.iloc[obs_i:j + 1]
    if w.empty:
        return 0.0
    peak = float(w.high.max())
    low = float(w.low.min())
    return pct(peak, low) if peak > 0 else 0.0


def prior_shrink(g: pd.DataFrame, j: int, n: int = 3) -> Tuple[float, float]:
    w = g.iloc[max(0, j - n):j]
    if w.empty:
        return 1.0, 0.0
    return float(w.amount_anomaly_20d.mean()), float(w.return_1d_pct.max())


def hard_danger(row: pd.Series) -> Optional[str]:
    day_ret = fnum(row.get("return_1d_pct"))
    super_r = fnum(row.get("l2_super_net_ratio"))
    main_r = fnum(row.get("l2_main_net_ratio"))
    support = fnum(row.get("support_pressure_spread"))
    cancel_buy_r = ratio(row, "cancel_buy_amount")
    add_sell_r = ratio(row, "add_sell_amount")
    active = fnum(row.get("active_buy_strength"))
    if day_ret > 7.5:
        return "确认日过热，容易追高"
    if super_r <= -0.008 and main_r <= -0.006:
        return "确认日超大单和主力同时明显流出"
    if cancel_buy_r > 0.65 and add_sell_r > 0.50:
        return "撤买单和新增卖压共振"
    if support < -0.35 and active < -3:
        return "盘口承接和主动买入同时弱"
    return None


def confirm_buy_point(g: pd.DataFrame, obs_i: int, j: int, mode: str) -> Tuple[bool, str, Dict[str, Any]]:
    row = g.loc[j]
    danger = hard_danger(row)
    if danger:
        return False, danger, {}

    close = fnum(row.get("close"))
    low = fnum(row.get("low"))
    ma5 = fnum(row.get("close_ma5"))
    ma10 = fnum(row.get("close_ma10"))
    day_ret = fnum(row.get("return_1d_pct"))
    amount_anom = fnum(row.get("amount_anomaly_20d"))
    super_r = fnum(row.get("l2_super_net_ratio"))
    main_r = fnum(row.get("l2_main_net_ratio"))
    super3 = fnum(row.get("super_net_3d")) / max(fnum(row.get("total_amount")), 1.0)
    main3 = fnum(row.get("main_net_3d")) / max(fnum(row.get("total_amount")), 1.0)
    support = fnum(row.get("support_pressure_spread"))
    active = fnum(row.get("active_buy_strength"))
    c20h = close_vs_high20(g, j)
    pullback = recent_pullback_from_observe(g, obs_i, j)
    shrink_amt, prior_max_ret = prior_shrink(g, j, 3)
    cancel_buy_r = ratio(row, "cancel_buy_amount")
    add_sell_r = ratio(row, "add_sell_amount")

    fund_ok_loose = max(super_r, main_r, super3, main3) > -0.001 and min(super_r, main_r) > -0.010
    fund_ok_strict = max(super_r, main_r) > 0.002 or max(super3, main3) > 0.006
    fund_ok = fund_ok_strict if mode in {"strict", "callback_strict"} else fund_ok_loose

    base_meta = {
        "confirm_date": str(row.trade_date),
        "confirm_return_1d_pct": round(day_ret, 2),
        "confirm_amount_anomaly_20d": round(amount_anom, 3),
        "confirm_super_net_ratio": round(super_r, 5),
        "confirm_main_net_ratio": round(main_r, 5),
        "confirm_super3_ratio": round(super3, 5),
        "confirm_main3_ratio": round(main3, 5),
        "confirm_support_pressure_spread": round(support, 5),
        "confirm_active_buy_strength": round(active, 5),
        "confirm_close_vs_20d_high_pct": round(c20h, 2),
        "confirm_pullback_from_observe_peak_pct": round(pullback, 2),
        "confirm_cancel_buy_ratio": round(cancel_buy_r, 5),
        "confirm_add_sell_ratio": round(add_sell_r, 5),
        "prior3_amount_anomaly_avg": round(shrink_amt, 3),
    }

    touch_ma = ((ma5 > 0 and low <= ma5 * 1.015) or (ma10 > 0 and low <= ma10 * 1.025))
    callback_ma = (
        ma10 > 0
        and -15 <= pullback <= -3
        and touch_ma
        and close >= ma10 * 0.985
        and -3.5 <= day_ret <= 4.5
        and support > -0.18
        and fund_ok
    )

    shrink_bull = (
        shrink_amt <= 1.05
        and prior_max_ret <= 4.5
        and 2.0 <= day_ret <= 7.0
        and amount_anom >= 1.05
        and close >= max(ma5, ma10 * 0.995 if ma10 > 0 else 0)
        and c20h >= -12
        and fund_ok_strict
    )

    prior3 = g.iloc[max(0, j - 3):j]
    prior_min_ret = float(prior3.return_1d_pct.min()) if not prior3.empty else 0.0
    close_repaired = ma5 > 0 and close >= ma5 * 0.995
    repair = (
        prior_min_ret <= -4.0
        and 2.0 <= day_ret <= 6.5
        and close_repaired
        and fund_ok_strict
        and support > -0.12
    )

    near_high_no_distribution = (
        mode in {"loose", "all"}
        and c20h >= -5
        and -1.0 <= day_ret <= 4.5
        and 0.75 <= amount_anom <= 1.9
        and max(super_r, main_r) >= 0
        and support > -0.15
        and cancel_buy_r < 0.55
        and add_sell_r < 0.62
    )

    allowed = {
        "callback_only": [callback_ma],
        "callback_strict": [callback_ma and fund_ok_strict],
        "callback_bull": [callback_ma, shrink_bull],
        "strict": [callback_ma, shrink_bull, repair],
        "loose": [callback_ma, shrink_bull, repair, near_high_no_distribution],
        "all": [callback_ma, shrink_bull, repair, near_high_no_distribution],
    }.get(mode, [callback_ma, shrink_bull, repair])

    if not any(allowed):
        return False, "未出现二次买点", {}

    if callback_ma:
        typ = "回踩均线承接"
    elif shrink_bull:
        typ = "缩量震荡后放量阳线"
    elif repair:
        typ = "强分歧后修复"
    else:
        typ = "前高附近不出货"
    return True, typ, {**base_meta, "buy_point_type": typ}


def add_confirmations(candidates: pd.DataFrame, by_symbol: Dict[str, pd.DataFrame], window: int, mode: str, cooldown: int) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    last_confirm_idx: Dict[str, int] = {}
    if candidates.empty:
        return pd.DataFrame()
    ordered = candidates.sort_values(["signal_date", "rank", "symbol"]).reset_index(drop=True)
    for _, rec in ordered.iterrows():
        sym = str(rec.symbol)
        g = by_symbol[sym]
        idxs = g.index[g.trade_date == rec.signal_date].tolist()
        if not idxs:
            continue
        obs_i = int(idxs[0])
        if sym in last_confirm_idx and obs_i <= last_confirm_idx[sym] + cooldown:
            continue
        found = None
        for j in range(obs_i + 1, min(len(g), obs_i + window + 1)):
            ok, reason, meta = confirm_buy_point(g, obs_i, j, mode)
            if ok:
                found = (j, reason, meta)
                break
        if not found:
            continue
        j, reason, meta = found
        last_confirm_idx[sym] = j
        rows.append({**rec.to_dict(), "observe_date": rec.signal_date, "entry_signal_date": str(g.loc[j].trade_date), "buy_point_reason": reason, **meta})
    return pd.DataFrame(rows)


def simulate_confirmed_trades(confirms: pd.DataFrame, by_symbol: Dict[str, pd.DataFrame], min_future_days: int) -> pd.DataFrame:
    exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    cost_params = SelectionV2Params()
    rows = []
    for _, rec in confirms.iterrows():
        g = by_symbol[str(rec.symbol)]
        trade = simulate_trade_v1_2(g, str(rec.entry_signal_date), exit_params, cost_params)
        if not trade or trade.get("skipped"):
            continue
        fdays = future_days_after_entry(g, str(trade["entry_date"]))
        rows.append({**rec.to_dict(), **trade, "future_days_available": fdays, "is_mature_trade": fdays >= min_future_days})
    return pd.DataFrame(rows)


def coverage(trades: pd.DataFrame, runups: pd.DataFrame, stable_syms: set[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    trade_syms = set(str(s) for s in trades.symbol.unique()) if not trades.empty else set()
    for label, strong in [("涨幅>=30%", runups[runups.runup_pct >= 30]), ("涨幅>=50%", runups[runups.runup_pct >= 50]), ("Top50", runups.head(50))]:
        syms = set(str(s) for s in strong.symbol)
        rows.append({
            "sample": label,
            "strong_count": int(len(strong)),
            "trade_hit_count": int(len(syms & trade_syms)),
            "stable_trade_hit_count": int(len(syms & stable_syms)),
            "combined_trade_hit_count": int(len(syms & (trade_syms | stable_syms))),
            "new_trade_hit_vs_stable": int(len((syms & trade_syms) - stable_syms)),
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-score", type=float, default=58.0)
    parser.add_argument("--window", type=int, default=8)
    parser.add_argument("--cooldown", type=int, default=5)
    parser.add_argument("--min-future-days", type=int, default=10)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    raw = load_atomic_daily_window("2026-01-01", args.replay_end)
    metrics = add_ma(compute_v2_metrics(raw))
    runups = build_all_runups(metrics, args.start, args.end)
    obs_candidates, by_symbol = build_candidates(metrics, args.start, args.end, args.top_n, args.min_score)
    stable = pd.read_csv(STABLE_TRADES) if STABLE_TRADES.exists() else pd.DataFrame()
    stable_syms = set(str(s) for s in stable.symbol.unique()) if not stable.empty else set()

    variant_rows: List[Dict[str, Any]] = []
    for mode in ["callback_only", "callback_strict", "callback_bull", "strict", "loose"]:
        vout = out / mode
        vout.mkdir(exist_ok=True)
        confirms = add_confirmations(obs_candidates, by_symbol, args.window, mode, args.cooldown)
        trades = simulate_confirmed_trades(confirms, by_symbol, args.min_future_days)
        mature = trades[trades.is_mature_trade.astype(bool)].copy() if not trades.empty else pd.DataFrame()
        cover = coverage(mature, runups, stable_syms)
        confirms.to_csv(vout / "confirmed_buy_points.csv", index=False)
        trades.to_csv(vout / "trades.csv", index=False)
        mature.to_csv(vout / "mature_trades.csv", index=False)
        cover.to_csv(vout / "strong_coverage.csv", index=False)
        summ = summarize(mature.to_dict("records") if not mature.empty else [])
        type_counts = mature.buy_point_type.value_counts().to_dict() if not mature.empty and "buy_point_type" in mature else {}
        row = {"mode": mode, "confirm_count": int(len(confirms)), "mature_trade_count": int(len(mature)), **summ, "buy_point_type_counts": type_counts}
        variant_rows.append(row)
        (vout / "summary.json").write_text(json.dumps({"summary": row, "coverage": cover.to_dict("records")}, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_df = pd.DataFrame(variant_rows)
    summary_df.to_csv(out / "variant_summary.csv", index=False)
    obs_candidates.to_csv(out / "observation_pool.csv", index=False)
    runups.to_csv(out / "all_runup_opportunities.csv", index=False)
    (out / "summary.json").write_text(json.dumps({
        "range": vars(args),
        "observation_count": int(len(obs_candidates)),
        "variants": variant_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# 趋势中继二次买点实验 v1

## 问题

趋势中继第一版能覆盖强势股，但入池后直接买胜率低。本实验把它拆成：

```text
强趋势观察池
+ 二次买点确认
```

## 二次买点类型

- 回踩均线承接
- 缩量震荡后放量阳线
- 强分歧后修复
- 前高附近不出货（只在宽松模式启用）

## 核心防线

确认日如果出现以下情况，不买：

```text
确认日过热
确认日超大单和主力同时明显流出
撤买单和新增卖压共振
盘口承接和主动买入同时弱
```

## 结果摘要

{summary_df.to_markdown(index=False)}

## 初步结论

看 `variant_summary.csv` 和各模式子目录的 `strong_coverage.csv`。
本实验先用于判断二次买点是否能明显降低硬止损和改善中位收益。
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps({"out": str(out), "variant_summary": variant_rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
