from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import (
    SelectionV2Params,
    _apply_buy_costs,
    _apply_sell_costs,
    _compute_intent_profile,
    _is_limit_up_day,
    compute_v2_metrics,
    load_atomic_daily_window,
)


def clip01(v: float) -> float:
    if pd.isna(v):
        return 0.0
    return max(0.0, min(1.0, float(v)))


def score_linear(v: float, lo: float, hi: float) -> float:
    if hi == lo or pd.isna(v):
        return 0.0
    return 100.0 * clip01((float(v) - lo) / (hi - lo))


def controlled_return_score(r20: float) -> float:
    """潜伏期不希望已经涨太多，也不希望仍在明显破位下跌。"""
    if pd.isna(r20):
        return 0.0
    r20 = float(r20)
    if -8.0 <= r20 <= 25.0:
        return 100.0
    if 25.0 < r20 <= 50.0:
        return score_linear(50.0 - r20, 0.0, 25.0)
    if -25.0 <= r20 < -8.0:
        return score_linear(r20, -25.0, -8.0)
    return 0.0


def add_trend_features(metrics_df: pd.DataFrame, params: SelectionV2Params) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for _, group in metrics_df.groupby("symbol", sort=False):
        g = group.sort_values("trade_date").copy()
        amount_20 = g["total_amount"].rolling(20, min_periods=8).sum()
        amount_40 = g["total_amount"].rolling(40, min_periods=12).sum()
        g["main_net_20d_sum"] = g["l2_main_net_amount"].rolling(20, min_periods=8).sum()
        g["super_net_20d_sum"] = g["l2_super_net_amount"].rolling(20, min_periods=8).sum()
        g["main_net_40d_sum"] = g["l2_main_net_amount"].rolling(40, min_periods=12).sum()
        g["super_net_40d_sum"] = g["l2_super_net_amount"].rolling(40, min_periods=12).sum()
        g["main_net_20d_ratio"] = (g["main_net_20d_sum"] / amount_20.replace(0, pd.NA)).fillna(0.0)
        g["super_net_20d_ratio"] = (g["super_net_20d_sum"] / amount_20.replace(0, pd.NA)).fillna(0.0)
        g["main_net_40d_ratio"] = (g["main_net_40d_sum"] / amount_40.replace(0, pd.NA)).fillna(0.0)
        g["super_net_40d_ratio"] = (g["super_net_40d_sum"] / amount_40.replace(0, pd.NA)).fillna(0.0)
        g["positive_l2_net_day_ratio_20d"] = (g["l2_main_net_amount"].gt(0).rolling(20, min_periods=8).sum() / 20.0).fillna(0.0)
        g["close_ma5"] = g["close"].rolling(5, min_periods=3).mean()
        g["close_ma10"] = g["close"].rolling(10, min_periods=5).mean()
        g["close_ma20"] = g["close"].rolling(20, min_periods=8).mean()
        g["volatility_20d"] = g["return_1d_pct"].rolling(20, min_periods=8).std().fillna(0.0)
        low_40 = g["low"].rolling(40, min_periods=12).min()
        low_20 = g["low"].rolling(20, min_periods=8).min()
        high_40 = g["high"].rolling(40, min_periods=12).max()
        g["low_lift_20v40_pct"] = ((low_20 / low_40.replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
        g["drawdown_from_40d_high_pct"] = ((g["close"] / high_40.replace(0, pd.NA)) - 1.0).fillna(0.0) * 100.0
        frames.append(g)
    out = pd.concat(frames, ignore_index=True)

    latent_scores: List[float] = []
    for _, row in out.iterrows():
        # 核心：资金慢进 + 股价没有严重过热 + 结构没有破坏。
        score = (
            0.22 * score_linear(row.get("main_net_20d_ratio", 0.0), 0.00, 0.045)
            + 0.16 * score_linear(row.get("main_net_40d_ratio", 0.0), 0.00, 0.035)
            + 0.14 * score_linear(row.get("super_net_20d_ratio", 0.0), 0.00, 0.022)
            + 0.12 * score_linear(row.get("positive_l2_net_day_ratio_20d", 0.0), 0.45, 0.70)
            + 0.12 * score_linear(row.get("price_position_60d", 0.0), 0.30, 0.82)
            + 0.10 * score_linear(row.get("low_lift_20v40_pct", 0.0), -2.0, 8.0)
            + 0.08 * controlled_return_score(row.get("return_20d_pct", 0.0))
            + 0.06 * score_linear(9.0 - float(row.get("volatility_20d", 0.0) or 0.0), 0.0, 7.0)
        )
        latent_scores.append(round(max(0.0, min(100.0, score)), 2))
    out["latent_chip_score"] = latent_scores
    return out


def row_intent(row: pd.Series, params: SelectionV2Params) -> Dict[str, Any]:
    return _compute_intent_profile(row, params)


def rank_direct(row: pd.Series, intent: Dict[str, Any]) -> float:
    latent = float(row.get("latent_chip_score") or 0.0)
    attack = float(intent.get("attack_score") or 0.0)
    repair = float(intent.get("repair_score") or 0.0)
    dist = float(intent.get("distribution_score") or 0.0)
    amount = score_linear(row.get("amount_anomaly_20d", 0.0), 1.0, 2.4)
    breakout = score_linear(row.get("breakout_vs_prev20_high_pct", 0.0), -1.0, 4.0)
    overheat_penalty = score_linear(row.get("return_20d_pct", 0.0), 35.0, 90.0)
    score = 0.36 * latent + 0.24 * attack + 0.14 * amount + 0.10 * breakout + 0.08 * repair - 0.20 * dist - 0.10 * overheat_penalty
    return round(max(0.0, min(100.0, score)), 2)


def rank_discovery(row: pd.Series, intent: Dict[str, Any]) -> float:
    latent = float(row.get("latent_chip_score") or 0.0)
    attack = float(intent.get("attack_score") or 0.0)
    dist = float(intent.get("distribution_score") or 0.0)
    amount = score_linear(row.get("amount_anomaly_20d", 0.0), 0.9, 2.0)
    breakout = score_linear(row.get("breakout_vs_prev20_high_pct", 0.0), -2.0, 3.0)
    score = 0.52 * latent + 0.18 * attack + 0.12 * amount + 0.08 * breakout - 0.18 * dist
    return round(max(0.0, min(100.0, score)), 2)


def direct_candidate_ok(row: pd.Series, intent: Dict[str, Any]) -> bool:
    if float(row.get("total_amount") or 0.0) < 300_000_000:
        return False
    if float(row.get("latent_chip_score") or 0.0) < 52.0:
        return False
    if float(intent.get("distribution_score") or 0.0) >= 72.0:
        return False
    if float(row.get("return_20d_pct") or 0.0) > 80.0:
        return False
    # 必须既有潜伏，又已经开始异动；避免纯潜伏不动的票。
    attack = float(intent.get("attack_score") or 0.0)
    return (
        attack >= 48.0
        or float(row.get("return_1d_pct") or 0.0) >= 3.0
        or (float(row.get("breakout_vs_prev20_high_pct") or 0.0) >= 0.5 and float(row.get("amount_anomaly_20d") or 0.0) >= 1.15)
    )


def discovery_candidate_ok(row: pd.Series, intent: Dict[str, Any]) -> bool:
    if float(row.get("total_amount") or 0.0) < 300_000_000:
        return False
    if float(row.get("latent_chip_score") or 0.0) < 55.0:
        return False
    if float(intent.get("distribution_score") or 0.0) >= 78.0:
        return False
    if float(row.get("return_20d_pct") or 0.0) > 90.0:
        return False
    # 观察池允许“有潜伏 + 轻微异动”，不要求当天追击。
    return (
        float(intent.get("attack_score") or 0.0) >= 38.0
        or float(row.get("amount_anomaly_20d") or 0.0) >= 1.15
        or float(row.get("breakout_vs_prev20_high_pct") or 0.0) >= -0.5
        or float(row.get("return_1d_pct") or 0.0) >= 2.0
    )


def make_candidate_record(row: pd.Series, intent: Dict[str, Any], score: float, mode: str) -> Dict[str, Any]:
    return {
        "signal_date": str(row["trade_date"]),
        "symbol": str(row["symbol"]),
        "mode": mode,
        "score": score,
        "latent_chip_score": round(float(row.get("latent_chip_score") or 0.0), 2),
        "attack_score": round(float(intent.get("attack_score") or 0.0), 2),
        "distribution_score": round(float(intent.get("distribution_score") or 0.0), 2),
        "repair_score": round(float(intent.get("repair_score") or 0.0), 2),
        "return_1d_pct": round(float(row.get("return_1d_pct") or 0.0), 2),
        "return_20d_pct": round(float(row.get("return_20d_pct") or 0.0), 2),
        "amount_anomaly_20d": round(float(row.get("amount_anomaly_20d") or 0.0), 3),
        "l2_main_net_ratio": round(float(row.get("l2_main_net_ratio") or 0.0), 5),
        "main_net_20d_ratio": round(float(row.get("main_net_20d_ratio") or 0.0), 5),
        "breakout_vs_prev20_high_pct": round(float(row.get("breakout_vs_prev20_high_pct") or 0.0), 2),
        "close": round(float(row.get("close") or 0.0), 3),
    }


def next_row_after(sym_df: pd.DataFrame, date: str) -> Optional[pd.Series]:
    rows = sym_df[sym_df["trade_date"] > date]
    if rows.empty:
        return None
    return rows.iloc[0]


def find_confirmation(sym_df: pd.DataFrame, discovery_date: str, params: SelectionV2Params, max_wait_days: int = 12) -> Tuple[Optional[str], str]:
    future = sym_df[sym_df["trade_date"] > discovery_date].head(max_wait_days)
    if future.empty:
        return None, "no_future_data"
    disc_row = sym_df[sym_df["trade_date"] == discovery_date].iloc[0]
    discovery_close = float(disc_row["close"])
    min_low_since = discovery_close
    had_pullback = False
    for _, row in future.iterrows():
        min_low_since = min(min_low_since, float(row.get("low") or row["close"]))
        pullback_pct = ((min_low_since / discovery_close) - 1.0) * 100.0 if discovery_close > 0 else 0.0
        if pullback_pct <= -3.0:
            had_pullback = True
        intent = row_intent(row, params)
        dist = float(intent.get("distribution_score") or 0.0)
        if dist >= 78.0:
            return None, "distribution_before_confirmation"
        # 回踩修复：先跌过，随后承接修复。
        repair_confirm = (
            had_pullback
            and pullback_pct >= -22.0
            and float(intent.get("repair_score") or 0.0) >= 58.0
            and float(row.get("l2_main_net_ratio") or 0.0) >= -0.012
            and float(row.get("support_pressure_spread") or 0.0) >= -0.03
            and float(row.get("close") or 0.0) >= float(row.get("close_ma10") or 0.0) * 0.97
        )
        # 二波/趋势延续：回调不深或短暂震荡后，再次放量主动买。
        second_wave_confirm = (
            pullback_pct >= -18.0
            and float(intent.get("attack_score") or 0.0) >= 58.0
            and float(row.get("amount_anomaly_20d") or 0.0) >= 1.12
            and float(row.get("active_buy_strength") or 0.0) > 0.0
            and float(row.get("l2_main_net_ratio") or 0.0) > -0.005
            and float(row.get("close") or 0.0) >= float(row.get("close_ma5") or 0.0) * 0.985
        )
        if repair_confirm:
            return str(row["trade_date"]), "pullback_repair_confirm"
        if second_wave_confirm:
            return str(row["trade_date"]), "second_wave_or_continuation_confirm"
    return None, "no_confirmation_within_window"


def simulate_trade(
    sym_df: pd.DataFrame,
    signal_date: str,
    params: SelectionV2Params,
    *,
    max_holding_days: int = 40,
    stop_loss_pct: float = -8.0,
) -> Optional[Dict[str, Any]]:
    entry_row = next_row_after(sym_df, signal_date)
    if entry_row is None:
        return None
    if _is_limit_up_day(entry_row, params):
        return {"skipped": True, "skip_reason": "entry_blocked_limit_up", "entry_signal_date": signal_date}
    gross_entry = float(entry_row["open"])
    if gross_entry <= 0:
        return None
    entry_price = _apply_buy_costs(gross_entry, params)
    entry_date = str(entry_row["trade_date"])
    max_runup = ((float(entry_row["high"]) / gross_entry) - 1.0) * 100.0
    max_drawdown = ((float(entry_row["low"]) / gross_entry) - 1.0) * 100.0
    distribution_streak = 0
    holding_days = 0
    rows = sym_df[sym_df["trade_date"] >= entry_date]
    exit_signal_date: Optional[str] = None
    exit_reason = "window_end"
    for _, row in rows.iterrows():
        holding_days += 1
        max_runup = max(max_runup, ((float(row["high"]) / gross_entry) - 1.0) * 100.0)
        max_drawdown = min(max_drawdown, ((float(row["low"]) / gross_entry) - 1.0) * 100.0)
        close_return = ((float(row["close"]) / gross_entry) - 1.0) * 100.0
        intent = row_intent(row, params)
        dist = float(intent.get("distribution_score") or 0.0)
        weak_funding = float(row.get("l2_main_net_ratio") or 0.0) <= -0.012 or float(row.get("active_buy_strength") or 0.0) < -1.0
        distribution_day = dist >= 72.0 and (weak_funding or float(row.get("support_pressure_spread") or 0.0) < -0.025)
        distribution_streak = distribution_streak + 1 if distribution_day else 0
        if close_return <= stop_loss_pct:
            exit_signal_date = str(row["trade_date"])
            exit_reason = f"stop_loss_{abs(stop_loss_pct):g}pct"
            break
        if dist >= 82.0 and weak_funding:
            exit_signal_date = str(row["trade_date"])
            exit_reason = "panic_distribution"
            break
        if distribution_streak >= 2:
            exit_signal_date = str(row["trade_date"])
            exit_reason = "distribution_confirmed_2d"
            break
        if holding_days >= max_holding_days:
            exit_signal_date = str(row["trade_date"])
            exit_reason = "max_holding_days"
            break
    if exit_signal_date is None:
        last = rows.iloc[-1]
        gross_exit = float(last["close"])
        exit_date = str(last["trade_date"])
        exit_signal_date = exit_date
    else:
        exit_row = next_row_after(sym_df, exit_signal_date)
        if exit_row is None:
            exit_row = sym_df[sym_df["trade_date"] == exit_signal_date].iloc[0]
            gross_exit = float(exit_row["close"])
        else:
            gross_exit = float(exit_row["open"])
        exit_date = str(exit_row["trade_date"])
    exit_price = _apply_sell_costs(gross_exit, params)
    return {
        "entry_signal_date": signal_date,
        "entry_date": entry_date,
        "gross_entry_price": round(gross_entry, 4),
        "entry_price": round(entry_price, 4),
        "exit_signal_date": exit_signal_date,
        "exit_date": exit_date,
        "gross_exit_price": round(gross_exit, 4),
        "exit_price": round(exit_price, 4),
        "return_pct": round(((gross_exit / gross_entry) - 1.0) * 100.0, 2),
        "net_return_pct": round(((exit_price / entry_price) - 1.0) * 100.0, 2),
        "max_runup_pct": round(max_runup, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "holding_days": int(holding_days),
        "exit_reason": exit_reason,
    }


def summarize(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [t for t in trades if not t.get("skipped") and t.get("net_return_pct") is not None]
    if not valid:
        return {"trade_count": 0, "win_rate": 0, "avg_return_pct": 0, "median_return_pct": 0}
    s = pd.Series([float(t["net_return_pct"]) for t in valid])
    gross = pd.Series([float(t["return_pct"]) for t in valid])
    return {
        "trade_count": int(len(valid)),
        "win_rate": round(float((s > 0).mean() * 100.0), 2),
        "avg_return_pct": round(float(s.mean()), 2),
        "avg_gross_return_pct": round(float(gross.mean()), 2),
        "median_return_pct": round(float(s.median()), 2),
        "max_return_pct": round(float(s.max()), 2),
        "min_return_pct": round(float(s.min()), 2),
        "avg_holding_days": round(float(pd.Series([int(t["holding_days"]) for t in valid]).mean()), 2),
        "total_return_pct_signal_sum": round(float(s.sum()), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--out", default="docs/strategy-rework/experiments/20260426-quick-validation")
    args = parser.parse_args()

    params = SelectionV2Params(
        attack_score_min=65.0,
        repair_score_min=60.0,
        distribution_score_warn=70.0,
        panic_distribution_score_exit=80.0,
        entry_attack_cvd_floor=-0.08,
        entry_return_20d_cap=80.0,
    )
    lookback = (pd.Timestamp(args.start) - pd.Timedelta(days=110)).strftime("%Y-%m-%d")
    raw = load_atomic_daily_window(lookback, args.replay_end)
    metrics = add_trend_features(compute_v2_metrics(raw), params)
    day_list = sorted(metrics[(metrics["trade_date"] >= args.start) & (metrics["trade_date"] <= args.end)]["trade_date"].unique().tolist())
    by_symbol = {sym: g.sort_values("trade_date").reset_index(drop=True) for sym, g in metrics.groupby("symbol", sort=False)}

    direct_candidates: List[Dict[str, Any]] = []
    confirmed_candidates: List[Dict[str, Any]] = []
    direct_trades: List[Dict[str, Any]] = []
    confirmed_trades: List[Dict[str, Any]] = []

    for day in day_list:
        day_df = metrics[metrics["trade_date"] == day]
        direct_ranked: List[Dict[str, Any]] = []
        confirmed_ranked: List[Dict[str, Any]] = []
        for _, row in day_df.iterrows():
            intent = row_intent(row, params)
            if direct_candidate_ok(row, intent):
                score = rank_direct(row, intent)
                direct_ranked.append({"row": row, "intent": intent, "record": make_candidate_record(row, intent, score, "direct_entry")})
            if discovery_candidate_ok(row, intent):
                score = rank_discovery(row, intent)
                confirmed_ranked.append({"row": row, "intent": intent, "record": make_candidate_record(row, intent, score, "confirmed_entry_discovery")})
        direct_ranked = sorted(direct_ranked, key=lambda x: (-x["record"]["score"], x["record"]["symbol"]))[: args.top_n]
        confirmed_ranked = sorted(confirmed_ranked, key=lambda x: (-x["record"]["score"], x["record"]["symbol"]))[: args.top_n]

        for rank, item in enumerate(direct_ranked, start=1):
            rec = {**item["record"], "rank": rank}
            direct_candidates.append(rec)
            sym_df = by_symbol[rec["symbol"]]
            trade = simulate_trade(sym_df, day, params)
            if trade:
                direct_trades.append({**rec, **trade})

        for rank, item in enumerate(confirmed_ranked, start=1):
            rec = {**item["record"], "rank": rank}
            sym_df = by_symbol[rec["symbol"]]
            confirm_date, confirm_reason = find_confirmation(sym_df, day, params)
            rec = {**rec, "confirmation_date": confirm_date, "confirmation_reason": confirm_reason}
            confirmed_candidates.append(rec)
            if confirm_date:
                trade = simulate_trade(sym_df, confirm_date, params)
                if trade:
                    confirmed_trades.append({**rec, **trade})

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(direct_candidates).to_csv(out_dir / "direct_daily_candidates.csv", index=False)
    pd.DataFrame(confirmed_candidates).to_csv(out_dir / "confirmed_daily_candidates.csv", index=False)
    pd.DataFrame(direct_trades).to_csv(out_dir / "direct_trades.csv", index=False)
    pd.DataFrame(confirmed_trades).to_csv(out_dir / "confirmed_trades.csv", index=False)

    summary = {
        "range": {"start": args.start, "end": args.end, "replay_end": args.replay_end, "top_n": args.top_n},
        "params": asdict(params),
        "strategy_notes": {
            "direct_entry": "目标日T综合潜伏分+异动分入选，T+1开盘买入。",
            "confirmed_entry": "目标日T只进入观察池，未来最多12个交易日等待回踩修复/二波延续确认，确认日+1开盘买入。",
        },
        "direct_entry": summarize(direct_trades),
        "confirmed_entry": {
            **summarize(confirmed_trades),
            "discovery_count": len(confirmed_candidates),
            "confirmed_count": sum(1 for c in confirmed_candidates if c.get("confirmation_date")),
            "confirmation_rate": round(100.0 * sum(1 for c in confirmed_candidates if c.get("confirmation_date")) / max(len(confirmed_candidates), 1), 2),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# 趋势波段策略快速验证", "", f"区间：{args.start} ~ {args.end}，回放到 {args.replay_end}，每日 Top{args.top_n}", ""]
    for key, title in [("direct_entry", "策略一：信号次日进场"), ("confirmed_entry", "策略二：二次确认进场")]:
        s = summary[key]
        md.extend([
            f"## {title}",
            "",
            f"- 交易数：{s.get('trade_count')}",
            f"- 胜率：{s.get('win_rate')}%",
            f"- 平均净收益：{s.get('avg_return_pct')}%",
            f"- 中位净收益：{s.get('median_return_pct')}%",
            f"- 最大单笔：{s.get('max_return_pct')}%",
            f"- 最小单笔：{s.get('min_return_pct')}%",
            f"- 平均持有：{s.get('avg_holding_days')} 天",
            "",
        ])
        if key == "confirmed_entry":
            md.extend([f"- 观察候选数：{s.get('discovery_count')}", f"- 触发确认数：{s.get('confirmed_count')}", f"- 确认率：{s.get('confirmation_rate')}%", ""])
    md.extend(["## 输出文件", "", "- direct_daily_candidates.csv", "- direct_trades.csv", "- confirmed_daily_candidates.csv", "- confirmed_trades.csv", "- summary.json", ""])
    (out_dir / "README.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
