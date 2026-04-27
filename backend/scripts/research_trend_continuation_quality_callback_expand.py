from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.research_strong_runup_opportunity_audit import build_all_runups
from backend.scripts.research_trend_continuation_buy_points import add_confirmations, simulate_confirmed_trades
from backend.scripts.research_trend_continuation_strategy import STABLE_TRADES, build_candidates
from backend.scripts.run_strategy_v1_trend_reversal import add_ma

OUT = Path("docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-quality-callback-expand")

CONFIGS = [
    {"name": "top10_score58", "top_n": 10, "min_score": 58.0, "window": 8},
    {"name": "top20_score58", "top_n": 20, "min_score": 58.0, "window": 8},
    {"name": "top30_score58", "top_n": 30, "min_score": 58.0, "window": 8},
    {"name": "top20_score55", "top_n": 20, "min_score": 55.0, "window": 8},
    {"name": "top30_score55", "top_n": 30, "min_score": 55.0, "window": 8},
]


def apply_strict_quality(confirms: pd.DataFrame) -> pd.DataFrame:
    if confirms.empty:
        return confirms
    return confirms[
        (confirms.confirm_cancel_buy_ratio < 0.30)
        & (confirms.confirm_amount_anomaly_20d <= 1.30)
        & (confirms.confirm_return_1d_pct <= 4.0)
    ].copy()


def coverage(mature: pd.DataFrame, runups: pd.DataFrame, stable_syms: set[str]) -> List[Dict[str, Any]]:
    t = set(mature.symbol.astype(str)) if not mature.empty else set()
    rows = []
    for label, strong in [("涨幅>=30%", runups[runups.runup_pct >= 30]), ("涨幅>=50%", runups[runups.runup_pct >= 50]), ("Top50", runups.head(50))]:
        syms = set(str(s) for s in strong.symbol)
        rows.append({
            "sample": label,
            "strong_count": int(len(strong)),
            "trade_hit_count": int(len(syms & t)),
            "stable_trade_hit_count": int(len(syms & stable_syms)),
            "combined_trade_hit_count": int(len(syms & (t | stable_syms))),
            "new_trade_hit_vs_stable": int(len((syms & t) - stable_syms)),
        })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = load_atomic_daily_window("2026-01-01", "2026-04-24")
    metrics = add_ma(compute_v2_metrics(raw))
    runups = build_all_runups(metrics, "2026-03-02", "2026-04-24")
    stable = pd.read_csv(STABLE_TRADES) if STABLE_TRADES.exists() else pd.DataFrame()
    stable_syms = set(stable.symbol.astype(str)) if not stable.empty else set()

    summary_rows = []
    for cfg in CONFIGS:
        out = OUT / cfg["name"]
        out.mkdir(exist_ok=True)
        candidates, by_symbol = build_candidates(metrics, "2026-03-02", "2026-04-24", cfg["top_n"], cfg["min_score"])
        confirms_all = add_confirmations(candidates, by_symbol, cfg["window"], "callback_only", cooldown=5)
        confirms = apply_strict_quality(confirms_all)
        trades = simulate_confirmed_trades(confirms, by_symbol, min_future_days=10)
        mature = trades[trades.is_mature_trade.astype(bool)].copy() if not trades.empty else pd.DataFrame()
        cover = coverage(mature, runups, stable_syms)
        candidates.to_csv(out / "observation_pool.csv", index=False)
        confirms_all.to_csv(out / "all_callback_confirmations.csv", index=False)
        confirms.to_csv(out / "strict_quality_confirmations.csv", index=False)
        trades.to_csv(out / "trades.csv", index=False)
        mature.to_csv(out / "mature_trades.csv", index=False)
        pd.DataFrame(cover).to_csv(out / "strong_coverage.csv", index=False)
        summ = summarize(mature.to_dict("records") if not mature.empty else [])
        row = {**cfg, "observation_count": int(len(candidates)), "confirm_count": int(len(confirms)), **summ}
        for c in cover:
            key = c["sample"]
            row[f"{key}_hit"] = c["trade_hit_count"]
            row[f"{key}_combined"] = c["combined_trade_hit_count"]
        summary_rows.append(row)
        (out / "summary.json").write_text(json.dumps({"config": cfg, "summary": summ, "coverage": cover}, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "variant_summary.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = "# 趋势中继：严格高质量回踩确认扩容实验\n\n" + summary.to_markdown(index=False) + "\n"
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
