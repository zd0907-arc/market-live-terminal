from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, _apply_buy_costs, _apply_sell_costs, _is_limit_up_day, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams, build_v1_candidates
from backend.scripts.run_strategy_v1_3_orderbook_filter import launch_cancel_buy_vs_hist
from backend.scripts.run_strategy_v1_4_modes import filter_reason as v14_filter_reason
from backend.scripts.run_strategy_v1_trend_reversal import add_ma


def fetch_tencent_snapshot(symbols: List[str], cache_path: Path) -> Dict[str, Dict[str, Any]]:
    """Fetch current name/share snapshot from Tencent quote API.

    用途：
    - name：当前名称，用于 ST 过滤。
    - float_shares：当前流通股本；回测时用 `当日收盘价 * float_shares` 近似当日流通市值。

    注意：如果历史期间发生股本变化，这不是严格历史流通股本；当前先作为可执行近似。
    """
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and cached:
                return cached
        except Exception:
            pass

    out: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(symbols), 80):
        batch = symbols[i : i + 80]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=30).read().decode("gbk", "ignore")
        for sym, body in re.findall(r"v_(\w+)=\"([^\"]*)\";", text):
            parts = body.split("~")
            if len(parts) < 74:
                continue
            name = parts[1].strip()
            try:
                total_shares = float(parts[72] or 0.0)
                float_shares = float(parts[73] or 0.0)
            except Exception:
                total_shares = 0.0
                float_shares = 0.0
            out[sym] = {
                "name": name,
                "total_shares": total_shares,
                "float_shares": float_shares,
                "source": "tencent_quote_current_snapshot",
            }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def enrich_candidates(candidates: List[Dict[str, Any]], by_symbol: Dict[str, pd.DataFrame], snapshot: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rec in candidates:
        sym = str(rec["symbol"])
        snap = snapshot.get(sym, {})
        name = str(snap.get("name") or "")
        float_shares = float(snap.get("float_shares") or 0.0)
        g = by_symbol[sym]
        discovery_rows = g[g.trade_date == rec.get("discovery_date")]
        discovery_close = float(discovery_rows.iloc[0].close) if not discovery_rows.empty else 0.0
        float_mcap = discovery_close * float_shares if float_shares > 0 and discovery_close > 0 else 0.0

        if rec.get("launch_start_date") and rec.get("launch_end_date"):
            ob = launch_cancel_buy_vs_hist(g, str(rec["launch_start_date"]), str(rec["launch_end_date"]))
        else:
            ob = {"order_filter_available": False, "orderbook_filter_reason": "no_launch"}

        out.append({
            **rec,
            **ob,
            "name": name,
            "float_shares_current": round(float_shares, 2),
            "float_mcap_on_discovery": round(float_mcap, 2),
        })
    return out


def next_row_after(sym_df: pd.DataFrame, date: str) -> Optional[pd.Series]:
    rows = sym_df[sym_df.trade_date > date]
    return None if rows.empty else rows.iloc[0]


def simulate_trade_v1_5(sym_df: pd.DataFrame, signal_date: str, p: V12ExitParams, params: SelectionV2Params) -> Optional[Dict[str, Any]]:
    entry_row = next_row_after(sym_df, signal_date)
    if entry_row is None:
        return None
    if _is_limit_up_day(entry_row, params):
        return {"skipped": True, "skip_reason": "entry_blocked_limit_up", "entry_signal_date": signal_date}
    gross_entry = float(entry_row.open)
    if gross_entry <= 0:
        return None

    entry_price = _apply_buy_costs(gross_entry, params)
    entry_date = str(entry_row.trade_date)
    entry_i = int(sym_df.index[sym_df.trade_date == entry_date][0])
    rows = sym_df.loc[entry_i:].copy()

    cum_super = 0.0
    cum_main = 0.0
    cum_amount = 0.0
    cum_super_peak = 0.0
    prev_cum_super: Optional[float] = None
    decline_streak = 0
    max_runup = -999.0
    max_drawdown = 999.0
    exit_signal_date: Optional[str] = None
    exit_reason = "window_end"
    holding_days = 0

    final_meta: Dict[str, Any] = {}
    for _, row in rows.iterrows():
        holding_days += 1
        amount = float(row.total_amount or 0.0)
        daily_super = float(row.l2_super_net_amount or 0.0)
        daily_main = float(row.l2_main_net_amount or 0.0)
        cum_amount += amount
        cum_super += daily_super
        cum_main += daily_main

        if prev_cum_super is not None and cum_super < prev_cum_super:
            decline_streak += 1
        else:
            decline_streak = 0
        prev_cum_super = cum_super
        cum_super_peak = max(cum_super_peak, cum_super)
        peak_dd = (cum_super_peak - cum_super) / cum_super_peak if cum_super_peak > 0 else 0.0

        high = float(row.high)
        low = float(row.low)
        close = float(row.close)
        close_ret = (close / gross_entry - 1) * 100
        max_runup = max(max_runup, (high / gross_entry - 1) * 100)
        max_drawdown = min(max_drawdown, (low / gross_entry - 1) * 100)

        final_meta = {
            "final_cum_super_ratio": round(cum_super / max(cum_amount, 1.0), 5),
            "final_cum_main_ratio": round(cum_main / max(cum_amount, 1.0), 5),
            "final_super_peak_drawdown_pct": round(peak_dd * 100, 2),
            "final_super_decline_streak": int(decline_streak),
        }

        # v1.5：买入后如果资金马上撤退，不等 -8%。
        early_flow_failure = (
            holding_days <= 3
            and holding_days >= 2
            and cum_super < 0
            and cum_main < 0
            and close_ret < 0
        )
        if early_flow_failure:
            exit_signal_date = str(row.trade_date)
            exit_reason = "early_flow_failure"
            break

        if close_ret <= p.stop_loss_pct:
            exit_signal_date = str(row.trade_date)
            exit_reason = f"hard_stop_{abs(p.stop_loss_pct):g}pct"
            break
        daily_outflow_cum_amount_ratio = max(0.0, -daily_super) / max(cum_amount, 1.0)
        if cum_super_peak > 0 and decline_streak >= p.super_decline_days and peak_dd >= p.super_peak_drawdown_pct:
            exit_signal_date = str(row.trade_date)
            exit_reason = f"cum_super_peak_dd_{int(p.super_peak_drawdown_pct * 100)}pct_{p.super_decline_days}d"
            break
        if cum_super_peak > 0 and daily_super < 0 and daily_outflow_cum_amount_ratio >= p.daily_super_outflow_cum_amount_ratio and peak_dd >= min(0.15, p.super_peak_drawdown_pct):
            exit_signal_date = str(row.trade_date)
            exit_reason = "violent_super_outflow"
            break
        if holding_days >= p.max_holding_days:
            exit_signal_date = str(row.trade_date)
            exit_reason = "max_holding_days"
            break

    if exit_signal_date:
        exit_row = next_row_after(sym_df, exit_signal_date)
        if exit_row is None:
            exit_row = sym_df[sym_df.trade_date == exit_signal_date].iloc[0]
            gross_exit = float(exit_row.close)
        else:
            gross_exit = float(exit_row.open)
    else:
        exit_row = rows.iloc[-1]
        gross_exit = float(exit_row.close)
        exit_signal_date = str(exit_row.trade_date)

    exit_price = _apply_sell_costs(gross_exit, params)
    return {
        "entry_signal_date": signal_date,
        "entry_date": entry_date,
        "gross_entry_price": round(gross_entry, 4),
        "entry_price": round(entry_price, 4),
        "exit_signal_date": exit_signal_date,
        "exit_date": str(exit_row.trade_date),
        "gross_exit_price": round(gross_exit, 4),
        "exit_price": round(exit_price, 4),
        "return_pct": round((gross_exit / gross_entry - 1) * 100, 2),
        "net_return_pct": round((exit_price / entry_price - 1) * 100, 2),
        "max_runup_pct": round(max_runup, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "holding_days": int(holding_days),
        "exit_reason": exit_reason,
        **final_meta,
    }


def candidate_filter_reason(rec: Dict[str, Any], min_float_mcap: float, max_float_mcap: float) -> str:
    name = str(rec.get("name") or "")
    if "ST" in name.upper():
        return "st_stock"
    cap = float(rec.get("float_mcap_on_discovery") or 0.0)
    if cap <= 0:
        return "missing_float_mcap"
    if cap < min_float_mcap:
        return "float_mcap_too_small"
    if cap > max_float_mcap:
        return "float_mcap_too_large"
    # 沿用 v1.4-balanced：撤梯子 + 弱启动/坏回调组合。
    reason = v14_filter_reason(rec, "v1.4-balanced")
    return reason


def date_index_map(metrics: pd.DataFrame) -> Dict[str, int]:
    days = sorted(metrics.trade_date.unique().tolist())
    return {str(d): i for i, d in enumerate(days)}


def run_v1_5(args: argparse.Namespace) -> Dict[str, Any]:
    t0 = time.perf_counter()
    raw = load_atomic_daily_window("2026-01-01", args.replay_end)
    metrics = add_ma(compute_v2_metrics(raw))
    candidates, by_symbol = build_v1_candidates(metrics, args.start, args.end, args.top_n)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    snapshot = fetch_tencent_snapshot(sorted(metrics.symbol.unique().tolist()), out / "tencent_snapshot_cache.json")
    enriched = enrich_candidates(candidates, by_symbol, snapshot)
    pd.DataFrame(enriched).to_csv(out / "enriched_candidates.csv", index=False)

    dindex = date_index_map(metrics)
    exit_params = V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    trade_params = SelectionV2Params()

    filtered: List[Dict[str, Any]] = []
    accepted: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    blocked_until: Dict[str, int] = {}

    signal_candidates = [c for c in enriched if c.get("pullback_confirm_date")]
    signal_candidates.sort(key=lambda c: (str(c.get("pullback_confirm_date")), str(c.get("symbol")), str(c.get("discovery_date"))))
    for rec in signal_candidates:
        sym = str(rec["symbol"])
        signal_date = str(rec["pullback_confirm_date"])
        sig_idx = dindex.get(signal_date, -1)
        reason = candidate_filter_reason(rec, args.min_float_mcap, args.max_float_mcap)
        if not reason and sig_idx >= 0 and sig_idx <= blocked_until.get(sym, -999):
            reason = "cooldown_or_open_position"
        tagged = {**rec, "strategy_mode": "v1.5-business-guards", "filter_reason": reason}
        if reason:
            filtered.append(tagged)
            continue
        trade = simulate_trade_v1_5(by_symbol[sym], signal_date, exit_params, trade_params)
        if not trade or trade.get("skipped"):
            filtered.append({**tagged, "filter_reason": trade.get("skip_reason", "no_trade") if trade else "no_trade"})
            continue
        future_days = int((by_symbol[sym].trade_date >= str(trade["entry_date"])).sum())
        row = {
            **tagged,
            **trade,
            "future_days_available": future_days,
            "is_mature_trade": future_days >= args.min_future_days,
        }
        accepted.append(tagged)
        trades.append(row)
        exit_idx = dindex.get(str(trade["exit_signal_date"]), sig_idx)
        blocked_until[sym] = max(exit_idx, sig_idx) + args.cooldown_days

    pd.DataFrame(filtered).to_csv(out / "filtered_candidates.csv", index=False)
    pd.DataFrame(accepted).to_csv(out / "accepted_candidates.csv", index=False)
    pd.DataFrame(trades).to_csv(out / "v1_5_trades.csv", index=False)

    mature = [t for t in trades if t.get("is_mature_trade")]
    summary = {
        "range": {"start": args.start, "end": args.end, "replay_end": args.replay_end, "top_n": args.top_n},
        "rules": {
            "base": "v1.4-balanced",
            "st_filter": "current name contains ST/*ST",
            "float_mcap": f"{args.min_float_mcap:.0f}~{args.max_float_mcap:.0f}, computed as discovery close * current float shares",
            "cooldown_days": args.cooldown_days,
            "early_exit": "holding_days<=3 and cum_super<0 and cum_main<0 and close_return<0",
        },
        "raw_candidate_count": len(candidates),
        "signal_candidate_count": len(signal_candidates),
        "accepted_candidate_count": len(accepted),
        "filtered_candidate_count": len(filtered),
        "filter_reason_counts": pd.Series([f.get("filter_reason") for f in filtered]).value_counts().to_dict() if filtered else {},
        "full_summary": summarize(trades),
        "mature_summary": summarize(mature),
        "timing_seconds": round(time.perf_counter() - t0, 2),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# v1.5 业务防线与资金连续性验证",
        "",
        "## 规则",
        "",
        "- 基础沿用 v1.4-balanced。",
        "- 剔除当前名称包含 ST/*ST 的股票。",
        "- 流通市值过滤：发现日收盘价 × 当前流通股本，范围 50亿~500亿。",
        "- 同股信号冷却/持仓互斥：一次买入信号后，到卖出信号后再冷却 5 个交易日。",
        "- 买入后早期资金失败：前 3 个持仓日内，累计超大单和主力都转负且股价亏损，提前退出。",
        "",
        "## 汇总",
        "",
        pd.DataFrame([
            {"scope": "full", **summary["full_summary"]},
            {"scope": "mature", **summary["mature_summary"]},
        ]).to_markdown(index=False),
        "",
        "## 过滤原因",
        "",
        pd.Series(summary["filter_reason_counts"]).to_frame("count").to_markdown(),
        "",
        "## 文件",
        "",
        "- enriched_candidates.csv",
        "- filtered_candidates.csv",
        "- accepted_candidates.csv",
        "- v1_5_trades.csv",
        "- tencent_snapshot_cache.json",
        "- summary.json",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--replay-end", default="2026-04-24")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-future-days", type=int, default=10)
    parser.add_argument("--cooldown-days", type=int, default=5)
    parser.add_argument("--min-float-mcap", type=float, default=5_000_000_000)
    parser.add_argument("--max-float-mcap", type=float, default=50_000_000_000)
    parser.add_argument("--out", default="docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-5-business-guards")
    args = parser.parse_args()
    summary = run_v1_5(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
