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
from typing import Any, Dict, List, Optional, Sequence

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


def stat(vals: Sequence[Optional[float]]) -> Dict[str, Any]:
    clean = sorted(sf(v) for v in vals if v is not None)
    if not clean:
        return {"n": 0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "worst": 0.0, "best": 0.0}
    return {
        "n": len(clean),
        "avg": round(sum(clean) / len(clean), 4),
        "median": round(statistics.median(clean), 4),
        "win_rate": round(sum(1 for v in clean if v > 0) / len(clean), 4),
        "worst": round(clean[0], 4),
        "best": round(clean[-1], 4),
    }


def load_rank_cache() -> Dict[str, Dict[str, int]]:
    cache_dir = MARKET_HEAT_DIR / "cache"
    candidates = sorted(cache_dir.glob("fine_heat_snapshots_*_m5_80.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshots = payload.get("snapshots") or {}
        if len(snapshots) >= 200:
            return {
                date: {str(item.get("id")): idx + 1 for idx, item in enumerate(snapshot.get("hot_top", [])[:50])}
                for date, snapshot in snapshots.items()
            }
    return {}


def load_inputs(sample_db: Path) -> tuple[List[Dict[str, Any]], List[str], Dict[str, Dict[str, Dict[str, Any]]]]:
    with sqlite3.connect(str(sample_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        # Tail-entry only studies samples that pass D+1 no-fade confirmation.
        samples = [dict(row) for row in conn.execute("SELECT * FROM samples WHERE intraday_fade = 0 ORDER BY trade_date, symbol")]
    symbols = sorted({row["symbol"] for row in samples})
    if not symbols:
        return samples, [], {}
    placeholders = ",".join("?" for _ in symbols)
    with sqlite3.connect(str(ATOMIC_DB), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        dates = [str(row[0]) for row in conn.execute("SELECT DISTINCT trade_date FROM atomic_trade_daily ORDER BY trade_date")]
        by_symbol = {symbol: {} for symbol in symbols}
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


def ma(by_symbol: Dict[str, Dict[str, Dict[str, Any]]], dates: Sequence[str], date_index: Dict[str, int], symbol: str, date: str, lookback: int) -> Optional[float]:
    i = date_index.get(date)
    if i is None:
        return None
    vals = [sf(by_symbol[symbol][d]["close"]) for d in dates[max(0, i - lookback + 1): i + 1] if d in by_symbol.get(symbol, {})]
    return sum(vals) / len(vals) if vals else None


def fixed_tail_return(sample: Dict[str, Any], dates: Sequence[str], date_index: Dict[str, int], by_symbol: Dict[str, Dict[str, Dict[str, Any]]], horizon: int) -> Optional[float]:
    i = date_index.get(sample["trade_date"])
    if i is None or i + 1 >= len(dates) or i + horizon >= len(dates):
        return None
    entry = by_symbol[sample["symbol"]].get(dates[i + 1])
    exit_row = by_symbol[sample["symbol"]].get(dates[i + horizon])
    if not entry or not exit_row or sf(entry.get("close")) <= 0:
        return None
    return (sf(exit_row["close"]) / sf(entry["close"]) - 1) * 100


def simulate_dynamic(sample: Dict[str, Any], dates: Sequence[str], date_index: Dict[str, int], by_symbol: Dict[str, Dict[str, Dict[str, Any]]], rank_by_date: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    i = date_index.get(sample["trade_date"])
    symbol = sample["symbol"]
    if i is None or i + 1 >= len(dates):
        return {"return_pct": None, "exit_reason": "missing"}
    entry_date = dates[i + 1]
    entry = by_symbol[symbol].get(entry_date)
    if not entry:
        return {"return_pct": None, "exit_reason": "missing"}
    entry_price = sf(entry["close"])
    cum_super = 0.0
    cum_amount = 0.0
    peak_super = 0.0
    previous_super: Optional[float] = None
    super_decline_streak = 0
    both_negative_streak = 0
    theme_bad_streak = 0
    peak_close = entry_price
    exit_price = entry_price
    exit_reason = "max20"
    exit_signal_date = entry_date
    holding_days = 0
    for h in range(2, 31):
        if i + h >= len(dates):
            break
        date = dates[i + h]
        row = by_symbol[symbol].get(date)
        if not row:
            continue
        holding_days += 1
        close = sf(row["close"])
        daily_super = sf(row.get("l2_super_net_amount"))
        daily_main = sf(row.get("l2_main_net_amount"))
        amount = sf(row.get("total_amount"))
        cum_amount += amount
        cum_super += daily_super
        if previous_super is not None and cum_super < previous_super:
            super_decline_streak += 1
        else:
            super_decline_streak = 0
        previous_super = cum_super
        peak_super = max(peak_super, cum_super)
        peak_super_drawdown = (peak_super - cum_super) / peak_super if peak_super > 0 else 0.0
        daily_super_out_ratio = max(0.0, -daily_super) / max(cum_amount, 1.0)
        both_negative_streak = both_negative_streak + 1 if daily_super < 0 and daily_main < 0 else 0
        ret = (close / entry_price - 1) * 100 if entry_price > 0 else 0.0
        theme_rank = rank_by_date.get(date, {}).get(str(sample.get("theme_id")), 999)
        theme_bad_streak = theme_bad_streak + 1 if theme_rank > 15 else 0
        ma5 = ma(by_symbol, dates, date_index, symbol, date, 5)
        below_ma5 = ma5 is not None and close < ma5
        peak_close = max(peak_close, close)
        peak_ret = (peak_close / entry_price - 1) * 100 if entry_price > 0 else 0.0
        trail_drawdown = (peak_close - close) / peak_close * 100 if peak_close > 0 else 0.0

        reason: Optional[str] = None
        if ret <= -5:
            reason = "hard_stop_5"
        elif ret <= -3 and both_negative_streak >= 2:
            reason = "price_loss_fund_neg2d"
        elif peak_super > 0 and super_decline_streak >= 2 and peak_super_drawdown >= 0.25 and ret < 3:
            reason = "super_peak_dd25_2d"
        elif peak_super > 0 and daily_super < 0 and daily_main < 0 and daily_super_out_ratio >= 0.018 and ret < 5:
            reason = "violent_main_super_outflow"
        elif theme_bad_streak >= 2 and below_ma5 and ret < 5:
            reason = "theme_fade_below_ma5"
        elif peak_ret >= 8 and trail_drawdown >= 5 and both_negative_streak >= 1:
            reason = "profit_trailing_fund_turn"

        if reason:
            exit_reason = reason
            exit_signal_date = date
            next_date = dates[i + h + 1] if i + h + 1 < len(dates) else None
            next_row = by_symbol[symbol].get(next_date) if next_date else None
            exit_price = sf(next_row["open"]) if next_row else close
            break
        if holding_days >= 20:
            exit_signal_date = date
            exit_price = close
            break
    return {
        "return_pct": (exit_price / entry_price - 1) * 100 if entry_price > 0 else None,
        "exit_reason": exit_reason,
        "exit_signal_date": exit_signal_date,
        "holding_days": holding_days,
    }


def build_report(sample_db: Path) -> Dict[str, Any]:
    samples, dates, by_symbol = load_inputs(sample_db)
    date_index = {date: idx for idx, date in enumerate(dates)}
    rank_by_date = load_rank_cache()
    groups = {
        "tail_all_no_fade": samples,
        "tail_confirm_d1_le_2": [row for row in samples if sf(row.get("d1_return_pct")) <= 2],
        "tail_confirm_0_lt_d1_le_2": [row for row in samples if 0 < sf(row.get("d1_return_pct")) <= 2],
        "tail_confirm_d1_gt_2": [row for row in samples if sf(row.get("d1_return_pct")) > 2],
    }
    out_groups: Dict[str, Any] = {}
    trades_by_group: Dict[str, List[Dict[str, Any]]] = {}
    for key, rows in groups.items():
        dynamic = [{**row, **simulate_dynamic(row, dates, date_index, by_symbol, rank_by_date)} for row in rows]
        trades_by_group[key] = dynamic
        out_groups[key] = {
            "sample_count": len(rows),
            "fixed_tail_d3": stat([fixed_tail_return(row, dates, date_index, by_symbol, 3) for row in rows]),
            "fixed_tail_d5": stat([fixed_tail_return(row, dates, date_index, by_symbol, 5) for row in rows]),
            "fixed_tail_d10": stat([fixed_tail_return(row, dates, date_index, by_symbol, 10) for row in rows]),
            "dynamic_exit": stat([row.get("return_pct") for row in dynamic]),
            "avg_holding_days": round(sum(sf(row.get("holding_days")) for row in dynamic) / len(dynamic), 2) if dynamic else 0.0,
            "exit_reasons": Counter(str(row.get("exit_reason")) for row in dynamic).most_common(),
        }
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "strategy": "hot_theme_low_position_l2_tail_entry_trade_management_v1",
            "entry_proxy": "D+1 close; intended as next-day tail-session buy after no-fade confirmation",
            "sample_count": len(samples),
        },
        "groups": out_groups,
        "trades": trades_by_group,
    }


def render_stat(s: Dict[str, Any]) -> str:
    return f"n={s['n']} avg={s['avg']:.2f}% med={s['median']:.2f}% win={s['win_rate']:.1%} worst={s['worst']:.2f}% best={s['best']:.2f}%"


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# 热点低位 L2：尾盘确认买入 + 动态卖出验证",
        "",
        "## 结论",
        "",
        "```text",
        "D+1 尾盘买入不能只看“不冲高回落”，还要避免当天已经涨太多。",
        "当前更好的尾盘买入口径是：D+1 不冲高回落，且从 D+1 开盘算涨幅 <= 2%。",
        "卖出不使用固定天数；动态退出看资金撤退、价格转弱、板块退潮、盈利回撤。",
        "```",
        "",
        "## 分组结果",
        "",
        "| 组别 | 样本 | 固定D+5参考 | 动态卖出 | 平均持有 | 主要退出原因 |",
        "|---|---:|---|---|---:|---|",
    ]
    labels = {
        "tail_all_no_fade": "D+1不回落全部",
        "tail_confirm_d1_le_2": "D+1不回落且涨幅<=2%",
        "tail_confirm_0_lt_d1_le_2": "D+1不回落且0~2%",
        "tail_confirm_d1_gt_2": "D+1不回落但涨幅>2%",
    }
    for key, item in report["groups"].items():
        reasons = ", ".join([f"{name}:{count}" for name, count in item["exit_reasons"][:3]])
        lines.append(
            f"| {labels.get(key, key)} | {item['sample_count']} | {render_stat(item['fixed_tail_d5'])} | "
            f"{render_stat(item['dynamic_exit'])} | {item['avg_holding_days']:.1f} | {reasons} |"
        )
    lines += [
        "",
        "## 当前尾盘买入判定",
        "",
        "```text",
        "D 日：策略产生热点低位 L2 信号。",
        "D+1 尾盘：",
        "1. 收盘/当前价位于全天振幅上半区： (最高价 - 当前价) / (最高价 - 最低价) <= 0.5；",
        "2. 当前价 >= 开盘价，不能冲高后收绿；",
        "3. 从 D+1 开盘价算涨幅最好在 0%~2%，<=2% 可接受；",
        "4. 如果已经涨超 2%，不作为主买点，除非有额外强逻辑；",
        "5. 如果涨超 5%，原则上不追。",
        "```",
        "",
        "## 当前动态卖出信号",
        "",
        "```text",
        "硬风控：买入后收盘亏损 <= -5%。",
        "价格+资金：亏损 <= -3%，且主力/超大单连续 2 天同时净流出。",
        "超大单撤退：累计超大单从峰值回撤 >=25%，且连续 2 天下降，且收益未明显打开。",
        "暴力流出：当日主力和超大单同时净流出，超大单流出占持仓期累计成交额 >=1.8%。",
        "板块退潮：所属热点连续 2 天跌出 Top15，且个股跌破 5 日线。",
        "盈利回撤：浮盈曾 >=8%，随后从高点回撤 >=5%，且资金转负。",
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tail-entry and dynamic trade management for hot-theme low-position L2 samples.")
    parser.add_argument("--sample-db", default=str(DEFAULT_SAMPLE_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = build_report(Path(args.sample_db))
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_position_l2_tail_entry_trade_management.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
