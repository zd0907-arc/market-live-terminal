from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import (
    add_trend_features,
    discovery_candidate_ok,
    make_candidate_record,
    rank_discovery,
    row_intent,
    simulate_trade,
    summarize,
)


def ok_discovery(row: pd.Series, intent: Dict[str, Any], variant: str) -> bool:
    if not discovery_candidate_ok(row, intent):
        return False
    latent = float(row.get("latent_chip_score") or 0.0)
    dist = float(intent.get("distribution_score") or 0.0)
    r20 = float(row.get("return_20d_pct") or 0.0)
    attack = float(intent.get("attack_score") or 0.0)
    if variant == "baseline_confirmed":
        return True
    if variant == "balanced_strict":
        return latent >= 60 and dist < 68 and r20 <= 75
    if variant == "repair_only_strict":
        return latent >= 60 and dist < 65 and r20 <= 65
    if variant == "trend_continuation_strict":
        return latent >= 62 and dist < 62 and attack >= 42 and 0 <= r20 <= 75
    raise ValueError(variant)


def find_confirmation_variant(sym_df: pd.DataFrame, discovery_date: str, params: SelectionV2Params, variant: str, max_wait_days: int = 12) -> Tuple[Optional[str], str, Dict[str, Any]]:
    future = sym_df[sym_df["trade_date"] > discovery_date].head(max_wait_days)
    if future.empty:
        return None, "no_future_data", {}
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
        attack = float(intent.get("attack_score") or 0.0)
        repair = float(intent.get("repair_score") or 0.0)
        l2 = float(row.get("l2_main_net_ratio") or 0.0)
        support = float(row.get("support_pressure_spread") or 0.0)
        active = float(row.get("active_buy_strength") or 0.0)
        amt = float(row.get("amount_anomaly_20d") or 0.0)
        r1 = float(row.get("return_1d_pct") or 0.0)
        r20 = float(row.get("return_20d_pct") or 0.0)
        if dist >= 78.0:
            return None, "distribution_before_confirmation", {}

        repair_confirm = (
            had_pullback
            and -22.0 <= pullback_pct <= -3.0
            and repair >= 58.0
            and l2 >= -0.012
            and support >= -0.03
            and float(row.get("close") or 0.0) >= float(row.get("close_ma10") or 0.0) * 0.97
        )
        second_confirm = (
            pullback_pct >= -18.0
            and attack >= 58.0
            and amt >= 1.12
            and active > 0.0
            and l2 > -0.005
            and float(row.get("close") or 0.0) >= float(row.get("close_ma5") or 0.0) * 0.985
        )

        if variant == "balanced_strict":
            repair_confirm = (
                had_pullback
                and -18.0 <= pullback_pct <= -3.5
                and repair >= 62.0
                and l2 >= 0.0
                and support >= -0.01
                and dist < 62.0
                and r1 <= 7.5
                and float(row.get("close") or 0.0) >= float(row.get("close_ma10") or 0.0) * 0.985
            )
            second_confirm = (
                pullback_pct >= -15.0
                and attack >= 62.0
                and amt >= 1.18
                and active >= 0.5
                and l2 >= 0.005
                and dist < 58.0
                and r1 <= 8.5
                and r20 <= 70.0
                and float(row.get("close") or 0.0) >= float(row.get("close_ma5") or 0.0)
            )
        elif variant == "repair_only_strict":
            repair_confirm = (
                had_pullback
                and -18.0 <= pullback_pct <= -4.0
                and repair >= 64.0
                and l2 >= 0.005
                and support >= 0.0
                and dist < 58.0
                and -3.0 <= r1 <= 7.0
                and float(row.get("close") or 0.0) >= float(row.get("close_ma10") or 0.0) * 0.99
            )
            second_confirm = False
        elif variant == "trend_continuation_strict":
            repair_confirm = False
            second_confirm = (
                pullback_pct >= -14.0
                and attack >= 66.0
                and amt >= 1.25
                and active >= 1.0
                and l2 >= 0.01
                and dist < 52.0
                and 0.0 <= r20 <= 70.0
                and 1.0 <= r1 <= 8.5
                and float(row.get("close") or 0.0) >= float(row.get("close_ma5") or 0.0)
            )

        meta = {
            "confirm_return_1d_pct": round(r1, 2),
            "confirm_return_20d_pct": round(r20, 2),
            "confirm_attack_score": round(attack, 2),
            "confirm_repair_score": round(repair, 2),
            "confirm_distribution_score": round(dist, 2),
            "confirm_l2_main_net_ratio": round(l2, 5),
            "confirm_amount_anomaly_20d": round(amt, 3),
            "confirm_pullback_pct": round(pullback_pct, 2),
        }
        if repair_confirm:
            return str(row["trade_date"]), "pullback_repair_confirm", meta
        if second_confirm:
            return str(row["trade_date"]), "second_wave_or_continuation_confirm", meta
    return None, "no_confirmation_within_window", {}


def run_variant(
    metrics: pd.DataFrame,
    day_list: List[str],
    variant: str,
    params: SelectionV2Params,
    top_n: int,
    *,
    stop_loss_pct: float = -8.0,
    max_holding_days: int = 40,
) -> Dict[str, Any]:
    by_symbol = {sym: g.sort_values("trade_date").reset_index(drop=True) for sym, g in metrics.groupby("symbol", sort=False)}
    candidates: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    for day in day_list:
        ranked: List[Dict[str, Any]] = []
        for _, row in metrics[metrics["trade_date"] == day].iterrows():
            intent = row_intent(row, params)
            if not ok_discovery(row, intent, variant):
                continue
            score = rank_discovery(row, intent)
            ranked.append({"row": row, "intent": intent, "record": make_candidate_record(row, intent, score, variant)})
        ranked = sorted(ranked, key=lambda x: (-x["record"]["score"], x["record"]["symbol"]))[:top_n]
        for rank, item in enumerate(ranked, start=1):
            rec = {**item["record"], "rank": rank}
            sym_df = by_symbol[rec["symbol"]]
            confirm_date, confirm_reason, confirm_meta = find_confirmation_variant(sym_df, day, params, variant)
            rec = {**rec, "confirmation_date": confirm_date, "confirmation_reason": confirm_reason, **confirm_meta}
            candidates.append(rec)
            if confirm_date:
                trade = simulate_trade(sym_df, confirm_date, params, stop_loss_pct=stop_loss_pct, max_holding_days=max_holding_days)
                if trade:
                    trades.append({**rec, **trade})
    summary = summarize(trades)
    summary.update({
        "discovery_count": len(candidates),
        "confirmed_count": sum(1 for c in candidates if c.get("confirmation_date")),
        "confirmation_rate": round(100.0 * sum(1 for c in candidates if c.get("confirmation_date")) / max(len(candidates), 1), 2),
    })
    return {"summary": summary, "candidates": candidates, "trades": trades}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--stop-loss", type=float, default=-8.0)
    parser.add_argument("--max-holding-days", type=int, default=40)
    parser.add_argument("--out", default="docs/strategy-rework/experiments/20260426-variant-validation")
    args = parser.parse_args()
    params = SelectionV2Params(attack_score_min=65.0, repair_score_min=60.0, distribution_score_warn=70.0, panic_distribution_score_exit=80.0, entry_attack_cvd_floor=-0.08, entry_return_20d_cap=80.0)
    lookback = (pd.Timestamp(args.start) - pd.Timedelta(days=110)).strftime("%Y-%m-%d")
    raw = load_atomic_daily_window(lookback, args.replay_end)
    metrics = add_trend_features(compute_v2_metrics(raw), params)
    day_list = sorted(metrics[(metrics["trade_date"] >= args.start) & (metrics["trade_date"] <= args.end)]["trade_date"].unique().tolist())
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    variants = ["baseline_confirmed", "balanced_strict", "repair_only_strict", "trend_continuation_strict"]
    summary: Dict[str, Any] = {"range": {"start": args.start, "end": args.end, "replay_end": args.replay_end, "top_n": args.top_n}, "variants": {}}
    for variant in variants:
        result = run_variant(metrics, day_list, variant, params, args.top_n, stop_loss_pct=args.stop_loss, max_holding_days=args.max_holding_days)
        summary["variants"][variant] = result["summary"]
        pd.DataFrame(result["candidates"]).to_csv(out_dir / f"{variant}_candidates.csv", index=False)
        pd.DataFrame(result["trades"]).to_csv(out_dir / f"{variant}_trades.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    rows=[]
    for k,v in summary['variants'].items():
        rows.append({'variant':k, **v})
    table=pd.DataFrame(rows)
    table.to_csv(out_dir / 'summary_table.csv', index=False)
    print(table.to_string(index=False))

if __name__ == "__main__":
    main()
