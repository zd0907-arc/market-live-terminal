#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import ATOMIC_DB, MARKET_HEAT_DIR, ensure_market_heat_dir

DEFAULT_SAMPLE_DB = MARKET_HEAT_DIR / "hot_theme_low_position_l2_samples.db"


def sf(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def pct(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def stat(vals: Sequence[Optional[float]]) -> Dict[str, Any]:
    clean = sorted(sf(v) for v in vals if v is not None)
    if not clean:
        return {"n": 0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "worst": 0.0, "best": 0.0, "p25": 0.0, "p75": 0.0}
    return {
        "n": len(clean),
        "avg": round(sum(clean) / len(clean), 4),
        "median": round(statistics.median(clean), 4),
        "win_rate": round(sum(1 for v in clean if v > 0) / len(clean), 4),
        "worst": round(clean[0], 4),
        "best": round(clean[-1], 4),
        "p25": round(clean[int((len(clean) - 1) * 0.25)], 4),
        "p75": round(clean[int((len(clean) - 1) * 0.75)], 4),
    }


def load_rank_cache() -> Dict[str, Dict[str, int]]:
    cache_dir = MARKET_HEAT_DIR / "cache"
    candidates = sorted(cache_dir.glob("fine_heat_snapshots_*_m5_80.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshots = payload.get("snapshots") or {}
        if len(snapshots) >= 200:
            return {
                str(date): {str(item.get("id")): idx + 1 for idx, item in enumerate((snap.get("hot_top") or [])[:80])}
                for date, snap in snapshots.items()
            }
    return {}


def load_inputs(sample_db: Path) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Dict[str, Dict[str, Any]]]]:
    with sqlite3.connect(str(sample_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        samples = [
            dict(row)
            for row in conn.execute(
                """
                SELECT * FROM samples
                WHERE intraday_fade = 0 AND d1_return_pct <= 2
                ORDER BY trade_date, symbol
                """
            )
        ]
    symbols = sorted({str(r["symbol"]) for r in samples})
    if not symbols:
        return samples, [], {}
    placeholders = ",".join("?" for _ in symbols)
    with sqlite3.connect(str(ATOMIC_DB), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        dates = [str(row[0]) for row in conn.execute("SELECT DISTINCT trade_date FROM atomic_trade_daily ORDER BY trade_date")]
        by_symbol = {s: {} for s in symbols}
        for row in conn.execute(
            f"""
            SELECT symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            FROM atomic_trade_daily
            WHERE symbol IN ({placeholders})
            """,
            symbols,
        ):
            by_symbol[str(row["symbol"])][str(row["trade_date"])] = dict(row)
    return samples, dates, by_symbol


def ma(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], idx: int, lookback: int) -> Optional[float]:
    vals = [sf(rows[d]["close"]) for d in dates[max(0, idx - lookback + 1): idx + 1] if d in rows]
    return sum(vals) / len(vals) if vals else None


def enrich(samples: List[Dict[str, Any]], dates: Sequence[str], by_symbol: Dict[str, Dict[str, Dict[str, Any]]], rank_by_date: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    date_index = {d: i for i, d in enumerate(dates)}
    out: List[Dict[str, Any]] = []
    for s in samples:
        symbol = str(s["symbol"])
        rows = by_symbol.get(symbol, {})
        i = date_index.get(str(s["trade_date"]))
        if i is None or i + 3 >= len(dates):
            continue
        d1 = rows.get(dates[i + 1])
        d3 = rows.get(dates[i + 3])
        if not d1 or not d3 or sf(d1.get("close")) <= 0 or sf(d3.get("close")) <= 0:
            continue
        rec = dict(s)
        rec["d1_tail_date"] = dates[i + 1]
        rec["d1_tail_price"] = sf(d1["close"])
        rec["d3_date"] = dates[i + 3]
        rec["d3_close"] = sf(d3["close"])
        rec["d3_close_tail_ret"] = pct(sf(d3["close"]), sf(d1["close"]))
        rec["d3_confirm"] = sf(rec["d3_close_tail_ret"]) >= 2
        # D1~D3/D2~D3 context for confirmation.
        theme_id = str(s.get("theme_id") or "")
        rec["theme_top15_hits_d1_d3"] = sum(1 for j in range(i + 1, i + 4) if rank_by_date.get(dates[j], {}).get(theme_id, 999) <= 15)
        rec["theme_best_rank_d1_d3"] = min([rank_by_date.get(dates[j], {}).get(theme_id, 999) for j in range(i + 1, i + 4)] or [999])
        period_d2_d3 = [rows.get(dates[j]) for j in range(i + 2, i + 4) if rows.get(dates[j])]
        rec["l2_main_sum_d2_d3_yi"] = round(sum(sf(r.get("l2_main_net_amount")) for r in period_d2_d3) / 100_000_000, 4)
        rec["l2_super_sum_d2_d3_yi"] = round(sum(sf(r.get("l2_super_net_amount")) for r in period_d2_d3) / 100_000_000, 4)
        rec["funding_continue_d2_d3"] = rec["l2_main_sum_d2_d3_yi"] > 0 and rec["l2_super_sum_d2_d3_yi"] > 0
        out.append(rec)
    return out


def simulate(
    sample: Dict[str, Any],
    dates: Sequence[str],
    by_symbol: Dict[str, Dict[str, Dict[str, Any]]],
    rank_by_date: Dict[str, Dict[str, int]],
    entry_offset: int,
    policy: str,
    max_holding: int = 20,
) -> Optional[Dict[str, Any]]:
    date_index = {d: i for i, d in enumerate(dates)}
    d0 = str(sample["trade_date"])
    symbol = str(sample["symbol"])
    rows = by_symbol.get(symbol, {})
    i = date_index.get(d0)
    if i is None or i + entry_offset >= len(dates):
        return None
    entry_date = dates[i + entry_offset]
    entry = rows.get(entry_date)
    if not entry or sf(entry.get("close")) <= 0:
        return None
    entry_price = sf(entry["close"])
    peak_close = entry_price
    peak_ret = 0.0
    cum_super = 0.0
    peak_cum_super = 0.0
    previous_cum_super: Optional[float] = None
    super_decline_streak = 0
    both_neg_streak = 0
    theme_bad_streak = 0
    exit_reason = "max20_observation"
    exit_signal_date = entry_date
    exit_price = entry_price
    mfe = 0.0
    mae = 0.0
    last_close = entry_price

    theme_id = str(sample.get("theme_id") or "")
    for h in range(entry_offset + 1, entry_offset + max_holding + 1):
        if i + h >= len(dates):
            break
        date = dates[i + h]
        row = rows.get(date)
        if not row:
            continue
        close = sf(row["close"])
        high = sf(row["high"])
        low = sf(row["low"])
        last_close = close
        mfe = max(mfe, (high / entry_price - 1) * 100)
        mae = min(mae, (low / entry_price - 1) * 100)
        ret = (close / entry_price - 1) * 100
        peak_close = max(peak_close, close)
        peak_ret = max(peak_ret, (peak_close / entry_price - 1) * 100)
        close_pullback = (peak_close / close - 1) * 100 if close > 0 else 0.0
        daily_main = sf(row.get("l2_main_net_amount"))
        daily_super = sf(row.get("l2_super_net_amount"))
        cum_super += daily_super
        peak_cum_super = max(peak_cum_super, cum_super)
        if previous_cum_super is not None and cum_super < previous_cum_super:
            super_decline_streak += 1
        else:
            super_decline_streak = 0
        previous_cum_super = cum_super
        super_peak_dd = (peak_cum_super - cum_super) / peak_cum_super if peak_cum_super > 0 else 0.0
        both_neg_streak = both_neg_streak + 1 if daily_main < 0 and daily_super < 0 else 0
        theme_rank = rank_by_date.get(date, {}).get(theme_id, 999)
        theme_bad_streak = theme_bad_streak + 1 if theme_rank > 15 else 0
        ma5 = ma(rows, dates, i + h, 5)
        ma10 = ma(rows, dates, i + h, 10)
        below_ma5 = ma5 is not None and close < ma5
        below_ma10 = ma10 is not None and close < ma10

        reason: Optional[str] = None
        if policy == "max20":
            reason = None
        elif policy == "stop5_only":
            if ret <= -5:
                reason = "hard_stop_5"
        elif policy == "price_trail_5_after_8":
            if ret <= -5:
                reason = "hard_stop_5"
            elif peak_ret >= 8 and close_pullback >= 5:
                reason = "price_trail_5_after_8"
        elif policy == "price_trail_3_after_5":
            if ret <= -5:
                reason = "hard_stop_5"
            elif peak_ret >= 5 and close_pullback >= 3:
                reason = "price_trail_3_after_5"
        elif policy == "super_dd25_2d":
            if ret <= -5:
                reason = "hard_stop_5"
            elif peak_cum_super > 0 and super_decline_streak >= 2 and super_peak_dd >= 0.25:
                reason = "super_dd25_2d"
        elif policy == "both_outflow_2d":
            if ret <= -5:
                reason = "hard_stop_5"
            elif both_neg_streak >= 2:
                reason = "both_outflow_2d"
        elif policy == "theme_fade_ma5":
            if ret <= -5:
                reason = "hard_stop_5"
            elif theme_bad_streak >= 2 and below_ma5:
                reason = "theme_fade_ma5"
        elif policy == "theme_fade_ma10":
            if ret <= -5:
                reason = "hard_stop_5"
            elif theme_bad_streak >= 2 and below_ma10:
                reason = "theme_fade_ma10"
        elif policy == "composite_v2_sensitive":
            if ret <= -5:
                reason = "hard_stop_5"
            elif ret <= -3 and both_neg_streak >= 2:
                reason = "loss_and_both_outflow_2d"
            elif peak_ret >= 5 and close_pullback >= 3 and daily_super < 0:
                reason = "profit_pullback_super_negative"
            elif peak_cum_super > 0 and super_decline_streak >= 2 and super_peak_dd >= 0.25 and ret < 3:
                reason = "super_dd25_weak_profit"
            elif theme_bad_streak >= 2 and below_ma5 and ret < 5:
                reason = "theme_fade_below_ma5"
        elif policy == "composite_v3_run_profit":
            if ret <= -5:
                reason = "hard_stop_5"
            elif ret <= -3 and both_neg_streak >= 2:
                reason = "loss_and_both_outflow_2d"
            elif peak_ret >= 8 and close_pullback >= 5 and daily_super < 0:
                reason = "profit_trail_5_after_8_super_negative"
            elif peak_cum_super > 0 and super_decline_streak >= 2 and super_peak_dd >= 0.4 and ret < 5:
                reason = "super_dd40_weak_profit"
            elif theme_bad_streak >= 2 and below_ma5 and ret < 5:
                reason = "theme_fade_below_ma5"
        else:
            raise ValueError(f"unknown policy: {policy}")

        if reason:
            exit_reason = reason
            exit_signal_date = date
            next_date = dates[i + h + 1] if i + h + 1 < len(dates) else None
            next_row = rows.get(next_date) if next_date else None
            exit_price = sf(next_row["open"]) if next_row and sf(next_row.get("open")) > 0 else close
            break
        exit_price = close
        exit_signal_date = date

    return {
        "trade_date": sample["trade_date"],
        "symbol": sample["symbol"],
        "name": sample.get("name"),
        "theme_name": sample.get("theme_name"),
        "entry_date": entry_date,
        "entry_offset": entry_offset,
        "entry_price": entry_price,
        "policy": policy,
        "return_pct": (exit_price / entry_price - 1) * 100 if entry_price > 0 else None,
        "exit_reason": exit_reason,
        "exit_signal_date": exit_signal_date,
        "mfe_pct": mfe,
        "mae_pct": mae,
        "peak_close_ret_pct": peak_ret,
        "last_close_ret_pct": (last_close / entry_price - 1) * 100 if entry_price > 0 else None,
    }


def feature_first_trigger(
    sample: Dict[str, Any], dates: Sequence[str], by_symbol: Dict[str, Dict[str, Dict[str, Any]]], rank_by_date: Dict[str, Dict[str, int]], entry_offset: int, feature: str
) -> Optional[Dict[str, Any]]:
    # Reuse policy simulation for first trigger; then inspect post-trigger MFE/MAE for 5 days from trigger close.
    policy_map = {
        "price_trail_5_after_8": "price_trail_5_after_8",
        "price_trail_3_after_5": "price_trail_3_after_5",
        "super_dd25_2d": "super_dd25_2d",
        "both_outflow_2d": "both_outflow_2d",
        "theme_fade_ma5": "theme_fade_ma5",
        "theme_fade_ma10": "theme_fade_ma10",
    }
    sim = simulate(sample, dates, by_symbol, rank_by_date, entry_offset, policy_map[feature], 20)
    if not sim or sim["exit_reason"] in ("max20_observation", "hard_stop_5"):
        return None
    idx = {d: i for i, d in enumerate(dates)}
    symbol = str(sample["symbol"])
    rows = by_symbol.get(symbol, {})
    k = idx.get(sim["exit_signal_date"])
    trigger_row = rows.get(sim["exit_signal_date"])
    if k is None or not trigger_row or sf(trigger_row.get("close")) <= 0:
        return None
    trigger_close = sf(trigger_row["close"])
    future = [rows.get(dates[j]) for j in range(k + 1, min(k + 6, len(dates))) if rows.get(dates[j])]
    post_mfe = pct(max(sf(r["high"]) for r in future), trigger_close) if future else None
    post_mae = pct(min(sf(r["low"]) for r in future), trigger_close) if future else None
    sim["post_trigger_mfe5_pct"] = post_mfe
    sim["post_trigger_mae5_pct"] = post_mae
    return sim


def summarize_policy(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "n": len(trades),
        "return": stat([t.get("return_pct") for t in trades]),
        "mfe": stat([t.get("mfe_pct") for t in trades]),
        "mae": stat([t.get("mae_pct") for t in trades]),
        "exit_reasons": Counter(str(t.get("exit_reason")) for t in trades).most_common(),
        "examples": [
            {"trade_date": t["trade_date"], "symbol": t["symbol"], "name": t.get("name"), "return_pct": round(sf(t.get("return_pct")), 2), "exit_reason": t.get("exit_reason")}
            for t in sorted(trades, key=lambda x: sf(x.get("return_pct")))[:5]
        ],
    }


def build_report(sample_db: Path) -> Dict[str, Any]:
    samples, dates, by_symbol = load_inputs(sample_db)
    rank_by_date = load_rank_cache()
    samples = enrich(samples, dates, by_symbol, rank_by_date)
    groups = {
        "d1_tail_entry_all_qualified": {"entry_offset": 1, "rows": samples},
        "d3_entry_confirm_close_ge_2": {"entry_offset": 3, "rows": [s for s in samples if s.get("d3_confirm")]},
        "d3_entry_confirm_ge_2_and_theme_or_funding": {
            "entry_offset": 3,
            "rows": [s for s in samples if s.get("d3_confirm") and (sf(s.get("theme_top15_hits_d1_d3")) >= 1 or s.get("funding_continue_d2_d3"))],
        },
    }
    policies = [
        "max20",
        "stop5_only",
        "price_trail_5_after_8",
        "price_trail_3_after_5",
        "super_dd25_2d",
        "both_outflow_2d",
        "theme_fade_ma5",
        "theme_fade_ma10",
        "composite_v2_sensitive",
        "composite_v3_run_profit",
    ]
    policy_summary: Dict[str, Any] = {}
    policy_trades: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for gname, g in groups.items():
        policy_summary[gname] = {"sample_count": len(g["rows"]), "entry_offset": g["entry_offset"], "policies": {}}
        policy_trades[gname] = {}
        for p in policies:
            trades = [x for s in g["rows"] if (x := simulate(s, dates, by_symbol, rank_by_date, g["entry_offset"], p, 20)) is not None]
            policy_summary[gname]["policies"][p] = summarize_policy(trades)
            policy_trades[gname][p] = trades

    matched_d3_confirm = [s for s in samples if s.get("d3_confirm")]
    matched_d3_theme_or_funding = [
        s for s in samples
        if s.get("d3_confirm") and (sf(s.get("theme_top15_hits_d1_d3")) >= 1 or s.get("funding_continue_d2_d3"))
    ]
    matched_entry_comparison: Dict[str, Any] = {}
    for name, rows in {
        "d3_confirm_same_samples": matched_d3_confirm,
        "d3_confirm_theme_or_funding_same_samples": matched_d3_theme_or_funding,
    }.items():
        matched_entry_comparison[name] = {}
        for offset_label, offset in [("d1_tail_entry", 1), ("d3_confirm_entry", 3)]:
            matched_entry_comparison[name][offset_label] = {}
            for p in ["max20", "composite_v3_run_profit"]:
                trades = [x for s in rows if (x := simulate(s, dates, by_symbol, rank_by_date, offset, p, 20)) is not None]
                matched_entry_comparison[name][offset_label][p] = summarize_policy(trades)

    feature_quality: Dict[str, Any] = {}
    for gname, g in groups.items():
        feature_quality[gname] = {}
        for feature in ["price_trail_5_after_8", "price_trail_3_after_5", "super_dd25_2d", "both_outflow_2d", "theme_fade_ma5", "theme_fade_ma10"]:
            hits = [x for s in g["rows"] if (x := feature_first_trigger(s, dates, by_symbol, rank_by_date, g["entry_offset"], feature)) is not None]
            feature_quality[gname][feature] = {
                "trigger_count": len(hits),
                "trigger_rate": round(len(hits) / len(g["rows"]), 4) if g["rows"] else 0.0,
                "exit_return": stat([h.get("return_pct") for h in hits]),
                "post_trigger_mfe5": stat([h.get("post_trigger_mfe5_pct") for h in hits]),
                "post_trigger_mae5": stat([h.get("post_trigger_mae5_pct") for h in hits]),
                "sell_fly_5pct_rate": round(sum(1 for h in hits if sf(h.get("post_trigger_mfe5_pct")) >= 5) / len(hits), 4) if hits else 0.0,
            }

    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sample_scope": "D+1 tail-qualified samples: no fade and open-to-close gain <=2%",
            "sample_count": len(samples),
            "entry_prices": "D+1/D+3 close are used as tail-session proxies. Exits are close-signal, next-open execution when possible.",
        },
        "entry_context": {
            "d3_confirm_count": sum(1 for s in samples if s.get("d3_confirm")),
            "d3_confirm_theme_or_funding_count": sum(1 for s in samples if s.get("d3_confirm") and (sf(s.get("theme_top15_hits_d1_d3")) >= 1 or s.get("funding_continue_d2_d3"))),
        },
        "policy_summary": policy_summary,
        "feature_quality": feature_quality,
        "matched_entry_comparison": matched_entry_comparison,
        "trades": policy_trades,
    }


def fmt_stat(s: Dict[str, Any]) -> str:
    return f"n={s['n']} avg={s['avg']:.2f}% med={s['median']:.2f}% win={s['win_rate']:.1%} worst={s['worst']:.2f}% best={s['best']:.2f}%"


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# 热点低位 L2：D+3 买点与动态卖出特征验证",
        "",
        "## 结论",
        "",
        "```text",
        "D+3 可以作为更保守的二次买点/加仓点，但不是无成本替代 D+1 尾盘买点：它样本更少、胜率更高，但会牺牲前两天利润。",
        "卖点不能固定天数。当前更有效的是组合卖出：硬止损 + 盈利后价格回撤 + 超大单/主力走弱 + 板块退潮破均线。",
        "单独一个卖出特征都不够稳，尤其只看超大单走弱会太敏感；价格回撤和资金转弱需要合在一起看。",
        "```",
        "",
        "## 买点对比",
        "",
        "| 买入口径 | 样本 | Max20观察 | 组合卖出v2敏感 | 组合卖出v3让利润奔跑 |",
        "|---|---:|---|---|---|",
    ]
    labels = {
        "d1_tail_entry_all_qualified": "D+1尾盘买：不回落且涨幅<=2%",
        "d3_entry_confirm_close_ge_2": "D+3买：相对D+1尾盘已浮盈>=2%",
        "d3_entry_confirm_ge_2_and_theme_or_funding": "D+3买：浮盈>=2%且板块/资金至少一个延续",
    }
    for gname, g in report["policy_summary"].items():
        ps = g["policies"]
        lines.append(
            f"| {labels.get(gname, gname)} | {g['sample_count']} | {fmt_stat(ps['max20']['return'])} | "
            f"{fmt_stat(ps['composite_v2_sensitive']['return'])} | {fmt_stat(ps['composite_v3_run_profit']['return'])} |"
        )
    lines += [
        "",
        "## 同一批 D+3 确认样本：D+1买 vs D+3买",
        "",
        "| 样本 | 入口 | Max20观察 | 组合卖出v3 |",
        "|---|---|---|---|",
    ]
    matched_labels = {
        "d3_confirm_same_samples": "D+3浮盈>=2%的同一批样本",
        "d3_confirm_theme_or_funding_same_samples": "D+3浮盈>=2%且板块/资金延续的同一批样本",
    }
    entry_labels = {"d1_tail_entry": "D+1尾盘买", "d3_confirm_entry": "D+3确认后买"}
    for mname, entry_map in report["matched_entry_comparison"].items():
        for ename, pmap in entry_map.items():
            lines.append(
                f"| {matched_labels.get(mname, mname)} | {entry_labels.get(ename, ename)} | "
                f"{fmt_stat(pmap['max20']['return'])} | {fmt_stat(pmap['composite_v3_run_profit']['return'])} |"
            )
    lines += ["", "## 单项卖出特征质量", "", "| 入口 | 特征 | 触发数 | 触发后5日最大反弹 | 触发后5日最大下跌 | 卖飞率>=5% |", "|---|---|---:|---|---|---:|"]
    feature_labels = {
        "price_trail_5_after_8": "盈利>=8%后回撤5%",
        "price_trail_3_after_5": "盈利>=5%后回撤3%",
        "super_dd25_2d": "累计超大单从峰值回撤25%且连降2天",
        "both_outflow_2d": "主力+超大单连续2天净流出",
        "theme_fade_ma5": "板块退潮+破5日线",
        "theme_fade_ma10": "板块退潮+破10日线",
    }
    for gname, fs in report["feature_quality"].items():
        for fname, q in fs.items():
            lines.append(
                f"| {labels.get(gname, gname)} | {feature_labels.get(fname, fname)} | {q['trigger_count']} | "
                f"{fmt_stat(q['post_trigger_mfe5'])} | {fmt_stat(q['post_trigger_mae5'])} | {q['sell_fly_5pct_rate']:.1%} |"
            )
    lines += ["", "## 当前操作解释", "", "```text",
              "如果你想更保守，可以不在 D+1 尾盘买，等 D+3 确认后再买；但这不是免费午餐，会少赚启动段，也会漏掉一些样本。",
              "更合理的结构是：D+1尾盘小仓/观察仓；D+3若浮盈>=2%且板块或资金没熄火，再升级为主仓或继续持有。",
              "卖出先用组合条件，不用固定日期：",
              "1. 收盘亏损 <= -5%：硬风控。",
              "2. 亏损 <= -3% 且主力/超大单连续2天流出：退出。",
              "3. 曾浮盈 >=5%，从高点回撤 >=3%，且超大单当天转负：先减/卖。",
              "4. 累计超大单从峰值回撤 >=25% 且连续2天下降，收益又没打开：退出。",
              "5. 板块连续2天跌出Top15且跌破5日线：退出，不等固定天数。",
              "D+3未确认、板块没延续、资金没继续的票，以上卖出条件要更敏感；D+3已确认的票，可以给更宽的盈利回撤空间。",
              "```"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate D+3 entry and dynamic exit features for hot-theme low-position L2 samples.")
    parser.add_argument("--sample-db", default=str(DEFAULT_SAMPLE_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = build_report(Path(args.sample_db))
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_position_l2_d3_entry_exit_features.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
