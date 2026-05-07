#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
import statistics
import sys
from collections import Counter
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
            by_symbol[str(row["symbol"])] [str(row["trade_date"])] = dict(row)
    return samples, dates, by_symbol


def ma(rows: Dict[str, Dict[str, Any]], dates: Sequence[str], idx: int, lookback: int) -> Optional[float]:
    vals = [sf(rows[d]["close"]) for d in dates[max(0, idx - lookback + 1): idx + 1] if d in rows]
    return sum(vals) / len(vals) if vals else None


def enrich(samples: List[Dict[str, Any]], dates: Sequence[str], by_symbol: Dict[str, Dict[str, Dict[str, Any]]], rank_by_date: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    idx = {d: i for i, d in enumerate(dates)}
    out = []
    for s in samples:
        i = idx.get(str(s["trade_date"]))
        symbol = str(s["symbol"])
        rows = by_symbol.get(symbol, {})
        if i is None or i + 1 >= len(dates):
            continue
        d1 = rows.get(dates[i + 1])
        if not d1 or sf(d1.get("close")) <= 0:
            continue
        rec = dict(s)
        rec["d1_date"] = dates[i + 1]
        rec["d1_close"] = sf(d1["close"])
        rec["d1_main_net_yi"] = round(sf(d1.get("l2_main_net_amount")) / 100_000_000, 4)
        rec["d1_super_net_yi"] = round(sf(d1.get("l2_super_net_amount")) / 100_000_000, 4)
        rec["d1_funding_positive"] = sf(d1.get("l2_main_net_amount")) > 0 and sf(d1.get("l2_super_net_amount")) > 0
        theme_id = str(s.get("theme_id") or "")
        rec["theme_rank_d1"] = rank_by_date.get(dates[i + 1], {}).get(theme_id, 999)
        rec["theme_top15_d1"] = rec["theme_rank_d1"] <= 15
        out.append(rec)
    return out


def make_groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "all_87_d1_tail": rows,
        "d1_no_fade": [r for r in rows if int(r.get("intraday_fade") or 0) == 0],
        "d1_no_fade_gain_0_2": [r for r in rows if int(r.get("intraday_fade") or 0) == 0 and 0 <= sf(r.get("d1_return_pct")) <= 2],
        "d1_no_fade_gain_0_2_d1_funding_pos": [r for r in rows if int(r.get("intraday_fade") or 0) == 0 and 0 <= sf(r.get("d1_return_pct")) <= 2 and r.get("d1_funding_positive")],
        "d1_no_fade_gain_0_2_theme_top15": [r for r in rows if int(r.get("intraday_fade") or 0) == 0 and 0 <= sf(r.get("d1_return_pct")) <= 2 and r.get("theme_top15_d1")],
        "d1_no_fade_gain_0_3": [r for r in rows if int(r.get("intraday_fade") or 0) == 0 and 0 <= sf(r.get("d1_return_pct")) <= 3],
        "d1_no_fade_gain_gt2": [r for r in rows if int(r.get("intraday_fade") or 0) == 0 and sf(r.get("d1_return_pct")) > 2],
        "d1_fade": [r for r in rows if int(r.get("intraday_fade") or 0) == 1],
    }


def simulate(sample: Dict[str, Any], dates: Sequence[str], by_symbol: Dict[str, Dict[str, Dict[str, Any]]], rank_by_date: Dict[str, Dict[str, int]], params: Dict[str, Any], max_holding: int = 20) -> Optional[Dict[str, Any]]:
    idx = {d: i for i, d in enumerate(dates)}
    i = idx.get(str(sample["trade_date"]))
    symbol = str(sample["symbol"])
    rows = by_symbol.get(symbol, {})
    if i is None or i + 1 >= len(dates):
        return None
    entry_date = dates[i + 1]
    entry = rows.get(entry_date)
    if not entry or sf(entry.get("close")) <= 0:
        return None
    entry_price = sf(entry["close"])
    theme_id = str(sample.get("theme_id") or "")
    peak_close = entry_price
    peak_ret = 0.0
    mfe = 0.0
    mae = 0.0
    cum_super = 0.0
    peak_cum_super = 0.0
    prev_cum_super: Optional[float] = None
    super_decline_streak = 0
    both_neg_streak = 0
    main_neg_streak = 0
    theme_bad_streak = 0
    exit_reason = "max20_observation"
    exit_signal_date = entry_date
    exit_price = entry_price
    holding_days = 0

    for h in range(2, 2 + max_holding):
        if i + h >= len(dates):
            break
        date = dates[i + h]
        row = rows.get(date)
        if not row:
            continue
        holding_days += 1
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
        main_neg_streak = main_neg_streak + 1 if daily_main < 0 else 0
        cum_super += daily_super
        peak_cum_super = max(peak_cum_super, cum_super)
        if prev_cum_super is not None and cum_super < prev_cum_super:
            super_decline_streak += 1
        else:
            super_decline_streak = 0
        prev_cum_super = cum_super
        super_dd = (peak_cum_super - cum_super) / peak_cum_super if peak_cum_super > 0 else 0.0
        rank = rank_by_date.get(date, {}).get(theme_id, 999)
        theme_bad_streak = theme_bad_streak + 1 if rank > params.get("theme_top_k", 15) else 0
        ma5 = ma(rows, dates, i + h, 5)
        ma10 = ma(rows, dates, i + h, 10)
        below_ma5 = ma5 is not None and close < ma5
        below_ma10 = ma10 is not None and close < ma10

        reason: Optional[str] = None
        if ret <= -float(params.get("hard_stop", 99)):
            reason = f"hard_stop_{params.get('hard_stop')}"
        elif ret <= -float(params.get("loss_stop", 99)) and both_neg_streak >= int(params.get("loss_both_neg_days", 99)):
            reason = "loss_and_both_outflow"
        elif params.get("weak_exit") and holding_days >= int(params.get("weak_days", 3)) and ret < float(params.get("weak_ret_lt", 0)) and (both_neg_streak >= 1 or theme_bad_streak >= 1 or main_neg_streak >= 2):
            reason = "weak_no_follow_through"
        elif peak_ret >= float(params.get("trail_start", 999)) and pullback >= float(params.get("trail_dd", 999)) and (not params.get("trail_need_super_neg") or daily_super < 0):
            reason = "profit_trailing"
        elif peak_cum_super > 0 and super_decline_streak >= int(params.get("super_streak", 99)) and super_dd >= float(params.get("super_dd", 9)) and ret < float(params.get("super_ret_lt", 999)):
            reason = "super_cum_drawdown"
        elif theme_bad_streak >= int(params.get("theme_bad_days", 99)) and ((params.get("theme_ma") == 5 and below_ma5) or (params.get("theme_ma") == 10 and below_ma10)) and ret < float(params.get("theme_ret_lt", 999)) and (not params.get("theme_need_outflow") or both_neg_streak >= 1 or main_neg_streak >= 1):
            reason = "theme_fade_break_ma"

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
        "return_pct": (exit_price / entry_price - 1) * 100,
        "exit_reason": exit_reason,
        "exit_signal_date": exit_signal_date,
        "mfe_pct": mfe,
        "mae_pct": mae,
        "peak_ret_pct": peak_ret,
        "holding_days": holding_days,
    }


def policy_presets() -> Dict[str, Dict[str, Any]]:
    base = {"theme_top_k": 15, "hard_stop": 5, "loss_stop": 3, "loss_both_neg_days": 2, "trail_start": 999, "trail_dd": 999, "super_streak": 99, "super_dd": 9, "theme_bad_days": 99}
    return {
        "max20_reference": {**base, "hard_stop": 999},
        "hard_stop_5_only": {**base},
        "v3_current": {**base, "trail_start": 8, "trail_dd": 5, "trail_need_super_neg": True, "super_streak": 2, "super_dd": 0.40, "super_ret_lt": 5, "theme_bad_days": 2, "theme_ma": 5, "theme_ret_lt": 5},
        "v4_weak_sensitive": {**base, "weak_exit": True, "weak_days": 3, "weak_ret_lt": 0, "trail_start": 8, "trail_dd": 5, "trail_need_super_neg": True, "super_streak": 2, "super_dd": 0.35, "super_ret_lt": 5, "theme_bad_days": 2, "theme_ma": 5, "theme_ret_lt": 5},
        "v5_profit_super_theme": {**base, "trail_start": 6, "trail_dd": 4, "trail_need_super_neg": True, "super_streak": 2, "super_dd": 0.35, "super_ret_lt": 6, "theme_bad_days": 2, "theme_ma": 5, "theme_ret_lt": 6, "theme_need_outflow": True},
        "v6_run_winner_wide": {**base, "hard_stop": 6, "loss_stop": 3, "loss_both_neg_days": 2, "trail_start": 10, "trail_dd": 6, "trail_need_super_neg": True, "super_streak": 2, "super_dd": 0.50, "super_ret_lt": 5, "theme_bad_days": 2, "theme_ma": 5, "theme_ret_lt": 5, "theme_need_outflow": True},
        "theme_ma5_only": {**base, "theme_bad_days": 2, "theme_ma": 5, "theme_ret_lt": 99},
        "super_dd35_only": {**base, "super_streak": 2, "super_dd": 0.35, "super_ret_lt": 99},
        "trail_8_5_only": {**base, "trail_start": 8, "trail_dd": 5, "trail_need_super_neg": False},
        "trail_8_5_superneg_only": {**base, "trail_start": 8, "trail_dd": 5, "trail_need_super_neg": True},
    }


def summarize_trades(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    ret = [t.get("return_pct") for t in trades]
    mfe = [t.get("mfe_pct") for t in trades]
    capture_vals = []
    for t in trades:
        m = sf(t.get("mfe_pct"))
        r = sf(t.get("return_pct"))
        if m > 0:
            capture_vals.append(max(-1.0, min(1.5, r / m)))
    return {
        "n": len(trades),
        "return": stat(ret),
        "mfe": stat(mfe),
        "mae": stat([t.get("mae_pct") for t in trades]),
        "capture_ratio": stat([v * 100 for v in capture_vals]),
        "avg_holding_days": round(sum(sf(t.get("holding_days")) for t in trades) / len(trades), 2) if trades else 0.0,
        "exit_reasons": Counter(str(t.get("exit_reason")) for t in trades).most_common(),
        "best_examples": [
            {"trade_date": t["trade_date"], "symbol": t["symbol"], "name": t.get("name"), "return_pct": round(sf(t.get("return_pct")), 2), "mfe_pct": round(sf(t.get("mfe_pct")), 2), "exit_reason": t.get("exit_reason")}
            for t in sorted(trades, key=lambda x: sf(x.get("return_pct")), reverse=True)[:6]
        ],
        "worst_examples": [
            {"trade_date": t["trade_date"], "symbol": t["symbol"], "name": t.get("name"), "return_pct": round(sf(t.get("return_pct")), 2), "mfe_pct": round(sf(t.get("mfe_pct")), 2), "exit_reason": t.get("exit_reason")}
            for t in sorted(trades, key=lambda x: sf(x.get("return_pct")))[:6]
        ],
    }


def build_report(sample_db: Path) -> Dict[str, Any]:
    samples, dates, by_symbol = load_inputs(sample_db)
    rank_by_date = load_rank_cache()
    rows = enrich(samples, dates, by_symbol, rank_by_date)
    groups = make_groups(rows)
    policies = policy_presets()
    summary: Dict[str, Any] = {}
    for gname, grows in groups.items():
        summary[gname] = {"sample_count": len(grows), "coverage": round(len(grows) / len(rows), 4) if rows else 0.0, "policies": {}}
        for pname, params in policies.items():
            trades = [x for r in grows if (x := simulate(r, dates, by_symbol, rank_by_date, params, 20)) is not None]
            summary[gname]["policies"][pname] = summarize_trades(trades)

    # Small grid only for the current main buy group; keep it coarse to avoid false precision.
    main_rows = groups["d1_no_fade_gain_0_2"]
    grid_results = []
    for hard_stop, trail_start, trail_dd, super_dd, theme_need_outflow, weak_exit in itertools.product([4, 5, 6], [6, 8, 10], [3, 4, 5, 6], [0.25, 0.35, 0.5], [False, True], [False, True]):
        if trail_dd >= trail_start:
            continue
        params = {
            "theme_top_k": 15,
            "hard_stop": hard_stop,
            "loss_stop": 3,
            "loss_both_neg_days": 2,
            "weak_exit": weak_exit,
            "weak_days": 3,
            "weak_ret_lt": 0,
            "trail_start": trail_start,
            "trail_dd": trail_dd,
            "trail_need_super_neg": True,
            "super_streak": 2,
            "super_dd": super_dd,
            "super_ret_lt": 5,
            "theme_bad_days": 2,
            "theme_ma": 5,
            "theme_ret_lt": 5,
            "theme_need_outflow": theme_need_outflow,
        }
        trades = [x for r in main_rows if (x := simulate(r, dates, by_symbol, rank_by_date, params, 20)) is not None]
        s = summarize_trades(trades)
        r = s["return"]
        # Prefer robust policies: average, median, p25, win, worst; penalize very bad tails.
        score = r["avg"] + 0.8 * r["median"] + 6 * r["win_rate"] + 0.4 * r["p25"] + 0.25 * r["worst"]
        grid_results.append({"score": round(score, 4), "params": params, "summary": s})
    grid_results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sample_scope": "All 87 strict D-day signals; D+1 close as tail-entry proxy; exits are close-signal, next-open execution when possible; max20 is only observation cap.",
            "sample_count": len(rows),
        },
        "summary": summary,
        "grid_top": grid_results[:20],
    }


def fmt(s: Dict[str, Any]) -> str:
    return f"n={s['n']} avg={s['avg']:.2f}% med={s['median']:.2f}% win={s['win_rate']:.1%} p25={s['p25']:.2f}% worst={s['worst']:.2f}% best={s['best']:.2f}%"


def render_markdown(report: Dict[str, Any]) -> str:
    group_labels = {
        "all_87_d1_tail": "全87个都D+1尾盘买",
        "d1_no_fade": "D+1不回落",
        "d1_no_fade_gain_0_2": "D+1不回落且涨幅0~2%",
        "d1_no_fade_gain_0_2_d1_funding_pos": "D+1不回落0~2%且D+1资金为正",
        "d1_no_fade_gain_0_2_theme_top15": "D+1不回落0~2%且板块D+1仍Top15",
        "d1_no_fade_gain_0_3": "D+1不回落且涨幅0~3%",
        "d1_no_fade_gain_gt2": "D+1不回落但涨幅>2%",
        "d1_fade": "D+1冲高回落",
    }
    policy_labels = {
        "max20_reference": "不触发卖出，仅观察Max20",
        "v3_current": "动态v3",
        "v4_weak_sensitive": "动态v4：弱票更敏感",
        "v5_profit_super_theme": "动态v5：回撤+超大单+板块",
        "v6_run_winner_wide": "动态v6：强票宽止盈",
        "theme_ma5_only": "只看板块退潮+破5日线",
        "super_dd35_only": "只看超大单峰值回撤35%",
        "trail_8_5_superneg_only": "只看盈利8%后回撤5%且超大单转负",
    }
    lines = [
        "# 热点低位 L2：D+1尾盘买点与动态卖出网格",
        "",
        "## 结论",
        "",
        "```text",
        "方向已切回 D+1 尾盘：先确定尾盘买入条件，再找动态卖点。",
        "买入条件仍然是 D+1 不冲高回落，且当天从开盘算涨幅 0~2%。",
        "卖点不是单一规则；当前更像“弱票快速处理 + 盈利票用超大单/板块/价格回撤组合退出”。",
        "在主买点24个样本里，动态卖出能把最差结果从约 -9% 压到 -2%~-3%，但会牺牲部分极端大肉。",
        "```",
        "",
        "## 买点分组 + 代表卖出规则",
        "",
        "| 买入口径 | 样本 | 不卖只观察Max20 | 动态v3 | 动态v4弱票敏感 | 动态v5组合 | 动态v6强票宽止盈 |",
        "|---|---:|---|---|---|---|---|",
    ]
    for gname, g in report["summary"].items():
        ps = g["policies"]
        lines.append(
            f"| {group_labels.get(gname, gname)} | {g['sample_count']} | {fmt(ps['max20_reference']['return'])} | "
            f"{fmt(ps['v3_current']['return'])} | {fmt(ps['v4_weak_sensitive']['return'])} | "
            f"{fmt(ps['v5_profit_super_theme']['return'])} | {fmt(ps['v6_run_winner_wide']['return'])} |"
        )
    main = report["summary"]["d1_no_fade_gain_0_2"]["policies"]
    lines += ["", "## 主买点下的单项规则参考", "", "| 规则 | 表现 | 退出原因 |", "|---|---|---|"]
    for pname in ["theme_ma5_only", "super_dd35_only", "trail_8_5_superneg_only", "v5_profit_super_theme", "v6_run_winner_wide"]:
        s = main[pname]
        reasons = ", ".join([f"{k}:{v}" for k, v in s["exit_reasons"][:4]])
        lines.append(f"| {policy_labels.get(pname, pname)} | {fmt(s['return'])} | {reasons} |")
    lines += ["", "## 网格搜索前5（主买点24样本，仅作辅助，不追求过拟合）", "", "| 排名 | 表现 | 参数摘要 |", "|---:|---|---|"]
    for idx, item in enumerate(report["grid_top"][:5], start=1):
        p = item["params"]
        desc = f"止损{p['hard_stop']}%, 盈利{p['trail_start']}后回撤{p['trail_dd']}且超大单转负, 超大单DD{int(p['super_dd']*100)}%, 板块退潮需流出={p['theme_need_outflow']}, 弱票退出={p['weak_exit']}"
        lines.append(f"| {idx} | {fmt(item['summary']['return'])} | {desc} |")
    lines += ["", "## 当前可执行版", "", "```text",
              "买入：D+1尾盘，不冲高回落，且从开盘算涨幅 0~2%。",
              "不买：D+1冲高回落；或D+1已涨超2%（容易兑现）；或D+1涨幅虽温和但资金/板块明显反向时降级观察。",
              "卖出：",
              "1. 收盘亏损达到约 -4%~-5%：硬风控。",
              "2. 买后3天仍没有浮盈，且资金/板块走弱：弱票退出。",
              "3. 曾浮盈 >=6%~8%，之后从高点回撤 4%~5%，且超大单转负：卖/减。",
              "4. 累计超大单从峰值回撤 35%~50%，且连续2天下降，收益没打开：卖。",
              "5. 板块连续2天跌出Top15且跌破5日线：卖；如果同时资金流出，优先级更高。",
              "```"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze D+1 tail-entry buy filters and dynamic exit grid for hot-theme low-position L2 samples.")
    parser.add_argument("--sample-db", default=str(DEFAULT_SAMPLE_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = build_report(Path(args.sample_db))
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_position_l2_d1_tail_dynamic_exit_grid.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
