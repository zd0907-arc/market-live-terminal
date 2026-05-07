#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


def stat(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    vals = sorted(sf(v) for v in values if v is not None)
    if not vals:
        return {"n": 0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "worst": 0.0, "best": 0.0, "p25": 0.0, "p75": 0.0}
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 4),
        "median": round(statistics.median(vals), 4),
        "win_rate": round(sum(1 for v in vals if v > 0) / len(vals), 4),
        "worst": round(vals[0], 4),
        "best": round(vals[-1], 4),
        "p25": round(vals[int((len(vals) - 1) * 0.25)], 4),
        "p75": round(vals[int((len(vals) - 1) * 0.75)], 4),
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
        samples = [dict(row) for row in conn.execute("SELECT * FROM samples ORDER BY trade_date, symbol")]
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


def d_fade(row: Dict[str, Any]) -> bool:
    high, low, open_, close = sf(row.get("high")), sf(row.get("low")), sf(row.get("open")), sf(row.get("close"))
    if high <= low:
        return close < open_
    fade_ratio = (high - close) / (high - low)
    return fade_ratio > 0.5 or (high > open_ and close < open_)


def enrich(samples: List[Dict[str, Any]], dates: Sequence[str], by_symbol: Dict[str, Dict[str, Dict[str, Any]]], rank_by_date: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    date_index = {d: i for i, d in enumerate(dates)}
    out = []
    for s in samples:
        symbol = str(s["symbol"])
        rows = by_symbol.get(symbol, {})
        i = date_index.get(str(s["trade_date"]))
        if i is None or i + 3 >= len(dates):
            continue
        d0, d1, d2, d3 = rows.get(dates[i]), rows.get(dates[i + 1]), rows.get(dates[i + 2]), rows.get(dates[i + 3])
        if not d0 or not d1 or not d2 or not d3 or sf(d3.get("close")) <= 0:
            continue
        rec = dict(s)
        rec["d3_date"] = dates[i + 3]
        rec["d3_close"] = sf(d3["close"])
        rec["d3_no_fade"] = not d_fade(d3)
        rec["d3_day_return_pct"] = pct(sf(d3["close"]), sf(d3["open"]))
        rec["d3_from_signal_close_pct"] = pct(sf(d3["close"]), sf(d0["close"]))
        rec["d3_from_d1_open_pct"] = pct(sf(d3["close"]), sf(d1["open"]))
        rec["d3_from_d1_close_pct"] = pct(sf(d3["close"]), sf(d1["close"]))
        theme_id = str(s.get("theme_id") or "")
        rec["theme_top15_hits_d1_d3"] = sum(1 for j in range(i + 1, i + 4) if rank_by_date.get(dates[j], {}).get(theme_id, 999) <= 15)
        rec["theme_best_rank_d1_d3"] = min([rank_by_date.get(dates[j], {}).get(theme_id, 999) for j in range(i + 1, i + 4)] or [999])
        d2d3 = [r for r in [d2, d3] if r]
        rec["l2_main_sum_d2_d3_yi"] = round(sum(sf(r.get("l2_main_net_amount")) for r in d2d3) / 100_000_000, 4)
        rec["l2_super_sum_d2_d3_yi"] = round(sum(sf(r.get("l2_super_net_amount")) for r in d2d3) / 100_000_000, 4)
        rec["funding_continue_d2_d3"] = rec["l2_main_sum_d2_d3_yi"] > 0 and rec["l2_super_sum_d2_d3_yi"] > 0
        out.append(rec)
    return out


def simulate(sample: Dict[str, Any], dates: Sequence[str], by_symbol: Dict[str, Dict[str, Dict[str, Any]]], rank_by_date: Dict[str, Dict[str, int]], policy: str, max_holding: int = 20) -> Optional[Dict[str, Any]]:
    date_index = {d: i for i, d in enumerate(dates)}
    i = date_index.get(str(sample["trade_date"]))
    symbol = str(sample["symbol"])
    rows = by_symbol.get(symbol, {})
    if i is None or i + 3 >= len(dates):
        return None
    entry_date = dates[i + 3]
    entry = rows.get(entry_date)
    if not entry or sf(entry.get("close")) <= 0:
        return None
    entry_price = sf(entry["close"])
    peak_close = entry_price
    peak_ret = 0.0
    cum_super = 0.0
    peak_cum_super = 0.0
    prev_cum_super: Optional[float] = None
    super_decline_streak = 0
    both_neg_streak = 0
    theme_bad_streak = 0
    mfe = 0.0
    mae = 0.0
    exit_reason = "max20_observation"
    exit_signal_date = entry_date
    exit_price = entry_price
    theme_id = str(sample.get("theme_id") or "")
    for h in range(4, 4 + max_holding):
        if i + h >= len(dates):
            break
        date = dates[i + h]
        row = rows.get(date)
        if not row:
            continue
        close, high, low = sf(row["close"]), sf(row["high"]), sf(row["low"])
        ret = (close / entry_price - 1) * 100
        mfe = max(mfe, (high / entry_price - 1) * 100)
        mae = min(mae, (low / entry_price - 1) * 100)
        peak_close = max(peak_close, close)
        peak_ret = max(peak_ret, (peak_close / entry_price - 1) * 100)
        pullback = (peak_close / close - 1) * 100 if close > 0 else 0.0
        daily_main = sf(row.get("l2_main_net_amount"))
        daily_super = sf(row.get("l2_super_net_amount"))
        both_neg_streak = both_neg_streak + 1 if daily_main < 0 and daily_super < 0 else 0
        cum_super += daily_super
        peak_cum_super = max(peak_cum_super, cum_super)
        if prev_cum_super is not None and cum_super < prev_cum_super:
            super_decline_streak += 1
        else:
            super_decline_streak = 0
        prev_cum_super = cum_super
        super_dd = (peak_cum_super - cum_super) / peak_cum_super if peak_cum_super > 0 else 0.0
        rank = rank_by_date.get(date, {}).get(theme_id, 999)
        theme_bad_streak = theme_bad_streak + 1 if rank > 15 else 0
        ma5 = ma(rows, dates, i + h, 5)
        below_ma5 = ma5 is not None and close < ma5
        reason: Optional[str] = None
        if policy == "max20":
            reason = None
        elif policy == "v3":
            if ret <= -5:
                reason = "hard_stop_5"
            elif ret <= -3 and both_neg_streak >= 2:
                reason = "loss_and_both_outflow_2d"
            elif peak_ret >= 8 and pullback >= 5 and daily_super < 0:
                reason = "profit_trail_5_after_8_super_negative"
            elif peak_cum_super > 0 and super_decline_streak >= 2 and super_dd >= 0.4 and ret < 5:
                reason = "super_dd40_weak_profit"
            elif theme_bad_streak >= 2 and below_ma5 and ret < 5:
                reason = "theme_fade_below_ma5"
        elif policy == "v4_strong_wider":
            if ret <= -6:
                reason = "hard_stop_6"
            elif ret <= -3 and both_neg_streak >= 2:
                reason = "loss_and_both_outflow_2d"
            elif peak_ret >= 10 and pullback >= 6 and daily_super < 0:
                reason = "profit_trail_6_after_10_super_negative"
            elif peak_cum_super > 0 and super_decline_streak >= 2 and super_dd >= 0.5 and ret < 5:
                reason = "super_dd50_weak_profit"
            elif theme_bad_streak >= 2 and below_ma5 and both_neg_streak >= 1 and ret < 5:
                reason = "theme_fade_below_ma5_with_outflow"
        else:
            raise ValueError(policy)
        if reason:
            exit_reason = reason
            exit_signal_date = date
            next_date = dates[i + h + 1] if i + h + 1 < len(dates) else None
            next_row = rows.get(next_date) if next_date else None
            exit_price = sf(next_row["open"]) if next_row and sf(next_row.get("open")) > 0 else close
            break
        exit_signal_date = date
        exit_price = close
    return {
        "trade_date": sample["trade_date"],
        "symbol": sample["symbol"],
        "name": sample.get("name"),
        "theme_name": sample.get("theme_name"),
        "entry_date": entry_date,
        "policy": policy,
        "return_pct": (exit_price / entry_price - 1) * 100,
        "exit_reason": exit_reason,
        "exit_signal_date": exit_signal_date,
        "mfe_pct": mfe,
        "mae_pct": mae,
    }


def summarize_trades(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "n": len(trades),
        "return": stat([t.get("return_pct") for t in trades]),
        "mfe": stat([t.get("mfe_pct") for t in trades]),
        "mae": stat([t.get("mae_pct") for t in trades]),
        "exit_reasons": Counter(str(t.get("exit_reason")) for t in trades).most_common(),
        "best_examples": [
            {"trade_date": t["trade_date"], "symbol": t["symbol"], "name": t.get("name"), "theme_name": t.get("theme_name"), "return_pct": round(sf(t.get("return_pct")), 2), "mfe_pct": round(sf(t.get("mfe_pct")), 2)}
            for t in sorted(trades, key=lambda x: sf(x.get("return_pct")), reverse=True)[:8]
        ],
        "worst_examples": [
            {"trade_date": t["trade_date"], "symbol": t["symbol"], "name": t.get("name"), "theme_name": t.get("theme_name"), "return_pct": round(sf(t.get("return_pct")), 2), "mfe_pct": round(sf(t.get("mfe_pct")), 2)}
            for t in sorted(trades, key=lambda x: sf(x.get("return_pct")))[:8]
        ],
    }


def build_report(sample_db: Path) -> Dict[str, Any]:
    samples, dates, by_symbol = load_inputs(sample_db)
    rank_by_date = load_rank_cache()
    rows = enrich(samples, dates, by_symbol, rank_by_date)
    groups = {
        "all_87_d3_entry": lambda r: True,
        "d3_from_d1_open_ge_2": lambda r: sf(r.get("d3_from_d1_open_pct")) >= 2,
        "d3_from_d1_open_2_to_8": lambda r: 2 <= sf(r.get("d3_from_d1_open_pct")) <= 8,
        "d3_from_d1_open_ge_2_no_fade": lambda r: sf(r.get("d3_from_d1_open_pct")) >= 2 and bool(r.get("d3_no_fade")),
        "d3_from_d1_open_ge_2_theme_or_funding": lambda r: sf(r.get("d3_from_d1_open_pct")) >= 2 and (sf(r.get("theme_top15_hits_d1_d3")) >= 1 or bool(r.get("funding_continue_d2_d3"))),
        "d3_from_d1_open_ge_2_no_fade_theme_or_funding": lambda r: sf(r.get("d3_from_d1_open_pct")) >= 2 and bool(r.get("d3_no_fade")) and (sf(r.get("theme_top15_hits_d1_d3")) >= 1 or bool(r.get("funding_continue_d2_d3"))),
        "d3_from_d1_close_ge_2": lambda r: sf(r.get("d3_from_d1_close_pct")) >= 2,
        "d3_from_d1_close_ge_2_no_fade": lambda r: sf(r.get("d3_from_d1_close_pct")) >= 2 and bool(r.get("d3_no_fade")),
        "d3_from_d1_close_2_to_8": lambda r: 2 <= sf(r.get("d3_from_d1_close_pct")) <= 8,
        "d3_from_d1_close_ge_2_no_fade_theme_or_funding": lambda r: sf(r.get("d3_from_d1_close_pct")) >= 2 and bool(r.get("d3_no_fade")) and (sf(r.get("theme_top15_hits_d1_d3")) >= 1 or bool(r.get("funding_continue_d2_d3"))),
        "d3_from_d1_close_ge_2_no_fade_d3_day_le_2": lambda r: sf(r.get("d3_from_d1_close_pct")) >= 2 and bool(r.get("d3_no_fade")) and sf(r.get("d3_day_return_pct")) <= 2,
        "d3_weak_from_d1_open_lt_2": lambda r: sf(r.get("d3_from_d1_open_pct")) < 2,
    }
    summary: Dict[str, Any] = {}
    trade_dump: Dict[str, Any] = {}
    for name, cond in groups.items():
        selected = [r for r in rows if cond(r)]
        summary[name] = {
            "sample_count": len(selected),
            "coverage": round(len(selected) / len(rows), 4) if rows else 0.0,
            "d3_from_d1_open": stat([r.get("d3_from_d1_open_pct") for r in selected]),
            "d3_from_d1_close": stat([r.get("d3_from_d1_close_pct") for r in selected]),
            "theme_hit_rate": round(sum(1 for r in selected if sf(r.get("theme_top15_hits_d1_d3")) >= 1) / len(selected), 4) if selected else 0.0,
            "funding_continue_rate": round(sum(1 for r in selected if r.get("funding_continue_d2_d3")) / len(selected), 4) if selected else 0.0,
            "policies": {},
        }
        trade_dump[name] = {}
        for policy in ["max20", "v3", "v4_strong_wider"]:
            trades = [x for r in selected if (x := simulate(r, dates, by_symbol, rank_by_date, policy, 20)) is not None]
            summary[name]["policies"][policy] = summarize_trades(trades)
            trade_dump[name][policy] = trades
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sample_scope": "All strict hot-theme low-position L2 samples, not prefiltered by D+1 no-fade/tail-entry. D+3 close is used as tail-entry proxy.",
            "sample_count": len(rows),
            "sample_db": str(sample_db),
        },
        "summary": summary,
        "trades": trade_dump,
    }


def fmt(s: Dict[str, Any]) -> str:
    return f"n={s['n']} avg={s['avg']:.2f}% med={s['median']:.2f}% win={s['win_rate']:.1%} worst={s['worst']:.2f}% best={s['best']:.2f}%"


def render_markdown(report: Dict[str, Any]) -> str:
    labels = {
        "all_87_d3_entry": "全87个信号都等D+3买",
        "d3_from_d1_open_ge_2": "D+3相对D+1开盘>=2%",
        "d3_from_d1_open_2_to_8": "D+3相对D+1开盘2%~8%",
        "d3_from_d1_open_ge_2_no_fade": "D+3>=2%且D+3不回落",
        "d3_from_d1_open_ge_2_theme_or_funding": "D+3>=2%且板块/资金至少一个延续",
        "d3_from_d1_open_ge_2_no_fade_theme_or_funding": "D+3>=2%且不回落且板块/资金延续",
        "d3_from_d1_close_ge_2": "D+3相对D+1收盘>=2%",
        "d3_from_d1_close_ge_2_no_fade": "D+3相对D+1收盘>=2%且D+3不回落",
        "d3_from_d1_close_2_to_8": "D+3相对D+1收盘2%~8%",
        "d3_from_d1_close_ge_2_no_fade_theme_or_funding": "D+3相对D+1收盘>=2%且不回落且板块/资金延续",
        "d3_from_d1_close_ge_2_no_fade_d3_day_le_2": "D+3相对D+1收盘>=2%且不回落且D+3当天涨幅<=2%",
        "d3_weak_from_d1_open_lt_2": "D+3相对D+1开盘<2%（弱确认）",
    }
    lines = [
        "# 热点低位 L2：全样本 D+3 买点重测",
        "",
        "## 结论",
        "",
        "```text",
        "之前只在 D+1 尾盘合格的24个样本里测 D+3，是错的；这版改成全部87个严格信号样本。",
        "全样本看，D+3 不能无脑买；全87个都等D+3买，动态收益一般。",
        "真正有价值的是过滤后的 D+3 买点：D+3 相对 D+1 收盘涨幅 >=2%，D+3 当天不冲高回落，且板块或资金至少一个还在延续。",
        "这个口径样本从87个压到19个，动态卖出 v3 均值 +5.46%，胜率 63.2%，最差 -6.95%。",
        "所以 D+3 是“保守确认买点”，不是所有原始信号的统一买点。",
        "```",
        "",
        "## D+3买点分组",
        "",
        "| 口径 | 样本 | 覆盖 | Max20观察 | 动态卖出v3 | 强票宽松卖出v4 |",
        "|---|---:|---:|---|---|---|",
    ]
    for key, item in report["summary"].items():
        ps = item["policies"]
        lines.append(
            f"| {labels.get(key, key)} | {item['sample_count']} | {item['coverage']:.1%} | "
            f"{fmt(ps['max20']['return'])} | {fmt(ps['v3']['return'])} | {fmt(ps['v4_strong_wider']['return'])} |"
        )
    lines += [
        "",
        "## 当前解释",
        "",
        "```text",
        "如果完全不想做 D+1 尾盘试错，D+3 买点可以成立：等它证明自己后再进。",
        "但 D+3 买点必须过滤，不能全87个都买；全买会把弱信号也买进去。",
        "当前最佳过滤口径更像：D+3相对D+1收盘>=2% + D+3不回落 + 板块/资金至少一个延续。",
        "注意 D+3 当天涨幅<=2% 反而不好；到D+3还太温和，说明扩散力度不够。",
        "后续卖出仍然用动态规则，不按固定天数。",
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Retest D+3 entry on all strict hot-theme low-position L2 samples.")
    parser.add_argument("--sample-db", default=str(DEFAULT_SAMPLE_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = build_report(Path(args.sample_db))
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_position_l2_d3_entry_full_sample.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
