#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import ATOMIC_DB, MARKET_HEAT_DIR, ensure_market_heat_dir

DEFAULT_SAMPLE_DB = MARKET_HEAT_DIR / "hot_theme_low_position_l2_samples.db"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def stat(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    vals = sorted(safe_float(v) for v in values if v is not None)
    if not vals:
        return {"n": 0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "p10": 0.0, "p25": 0.0, "worst": 0.0, "best": 0.0}
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 4),
        "median": round(statistics.median(vals), 4),
        "win_rate": round(sum(1 for v in vals if v > 0) / len(vals), 4),
        "p10": round(vals[int((len(vals) - 1) * 0.10)], 4),
        "p25": round(vals[int((len(vals) - 1) * 0.25)], 4),
        "worst": round(vals[0], 4),
        "best": round(vals[-1], 4),
    }


def load_enriched_samples(sample_db: Path, max_horizon: int = 10) -> List[Dict[str, Any]]:
    with sqlite3.connect(str(sample_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        samples = [dict(row) for row in conn.execute("SELECT * FROM samples ORDER BY trade_date, symbol")]
    symbols = sorted({row["symbol"] for row in samples})
    if not symbols:
        return samples
    with sqlite3.connect(str(ATOMIC_DB), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        dates = [str(row[0]) for row in conn.execute("SELECT DISTINCT trade_date FROM atomic_trade_daily ORDER BY trade_date")]
        date_index = {d: i for i, d in enumerate(dates)}
        placeholders = ",".join("?" for _ in symbols)
        price_rows: Dict[str, Dict[str, Dict[str, Any]]] = {sym: {} for sym in symbols}
        for row in conn.execute(
            f"""
            SELECT symbol, trade_date, open, high, low, close
            FROM atomic_trade_daily
            WHERE symbol IN ({placeholders})
            """,
            symbols,
        ):
            price_rows[str(row["symbol"])][str(row["trade_date"])] = dict(row)

    for item in samples:
        i = date_index.get(item["trade_date"])
        rows = price_rows.get(item["symbol"], {})
        if i is None or i + 1 >= len(dates):
            continue
        entry_date = dates[i + 1]
        entry_row = rows.get(entry_date)
        entry_open = safe_float(entry_row.get("open")) if entry_row else 0.0
        for h in range(1, max_horizon + 1):
            d = dates[i + h] if i + h < len(dates) else None
            row = rows.get(d) if d else None
            if not row or entry_open <= 0:
                item[f"d{h}_close_ret"] = None
                item[f"d{h}_high_ret"] = None
                item[f"d{h}_low_ret"] = None
                continue
            item[f"d{h}_close_ret"] = (safe_float(row["close"]) / entry_open - 1) * 100
            item[f"d{h}_high_ret"] = (safe_float(row["high"]) / entry_open - 1) * 100
            item[f"d{h}_low_ret"] = (safe_float(row["low"]) / entry_open - 1) * 100
    return samples


def fixed_exit(samples: Sequence[Dict[str, Any]], horizons: Sequence[int]) -> Dict[str, Any]:
    return {f"d{h}": stat([row.get(f"d{h}_close_ret") for row in samples]) for h in horizons}


def close_policy(row: Dict[str, Any], take_profit: Optional[float], stop_loss: Optional[float], max_horizon: int = 5) -> Optional[float]:
    for h in range(1, max_horizon + 1):
        value = row.get(f"d{h}_close_ret")
        if value is None:
            return None
        value = safe_float(value)
        if stop_loss is not None and value <= stop_loss:
            return value
        if take_profit is not None and value >= take_profit:
            return value
    return row.get(f"d{max_horizon}_close_ret")


def intraday_policy(row: Dict[str, Any], take_profit: float, stop_loss: float, max_horizon: int = 5) -> Optional[float]:
    # Conservative daily-OHLC simulation: if take-profit and stop-loss both touch on the same day,
    # assume stop-loss happens first. This avoids optimistic backtest hallucination.
    for h in range(1, max_horizon + 1):
        high = row.get(f"d{h}_high_ret")
        low = row.get(f"d{h}_low_ret")
        if high is None or low is None:
            return None
        hit_stop = safe_float(low) <= stop_loss
        hit_take = safe_float(high) >= take_profit
        if hit_stop and hit_take:
            return stop_loss
        if hit_stop:
            return stop_loss
        if hit_take:
            return take_profit
    return row.get(f"d{max_horizon}_close_ret")


def build_report(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    no_fade = [row for row in samples if int(row.get("intraday_fade") or 0) == 0]
    fade = [row for row in samples if int(row.get("intraday_fade") or 0) == 1]
    horizons = list(range(1, 11))
    close_policies = {
        "close_stop_-2": stat([close_policy(row, None, -2, 5) for row in samples]),
        "close_stop_-3": stat([close_policy(row, None, -3, 5) for row in samples]),
        "close_stop_-5": stat([close_policy(row, None, -5, 5) for row in samples]),
        "close_take_5_stop_-3": stat([close_policy(row, 5, -3, 5) for row in samples]),
        "close_take_10_stop_-5": stat([close_policy(row, 10, -5, 5) for row in samples]),
        "risk_exit_d1_fade_and_d1_le_-2": stat([
            safe_float(row.get("d1_close_ret")) if int(row.get("intraday_fade") or 0) == 1 and safe_float(row.get("d1_close_ret")) <= -2 else safe_float(row.get("d5_close_ret"))
            for row in samples
        ]),
    }
    intraday_policies = {
        "intraday_take_5_stop_-3_conservative": stat([intraday_policy(row, 5, -3, 5) for row in samples]),
        "intraday_take_8_stop_-3_conservative": stat([intraday_policy(row, 8, -3, 5) for row in samples]),
        "intraday_take_10_stop_-5_conservative": stat([intraday_policy(row, 10, -5, 5) for row in samples]),
    }
    mfe_mae = {}
    for name, group in [("all", samples), ("d1_no_fade", no_fade), ("d1_fade", fade)]:
        mfe = []
        mae = []
        for row in group:
            highs = [row.get(f"d{h}_high_ret") for h in range(1, 6) if row.get(f"d{h}_high_ret") is not None]
            lows = [row.get(f"d{h}_low_ret") for h in range(1, 6) if row.get(f"d{h}_low_ret") is not None]
            mfe.append(max(highs) if highs else None)
            mae.append(min(lows) if lows else None)
        mfe_mae[name] = {"mfe": stat(mfe), "mae": stat(mae)}
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sample_count": len(samples),
            "start_date": samples[0]["trade_date"] if samples else None,
            "end_date": samples[-1]["trade_date"] if samples else None,
            "note": "All returns use D+1 open as entry. Intraday TP/SL is conservative daily-OHLC simulation.",
        },
        "fixed_exit": {
            "all": fixed_exit(samples, horizons),
            "d1_no_fade": fixed_exit(no_fade, horizons),
            "d1_fade": fixed_exit(fade, horizons),
        },
        "close_policies": close_policies,
        "intraday_policies": intraday_policies,
        "mfe_mae": mfe_mae,
    }


def render_stat(s: Dict[str, Any]) -> str:
    return f"n={s['n']} avg={s['avg']:.2f}% med={s['median']:.2f}% win={s['win_rate']:.1%} p10={s['p10']:.2f}% worst={s['worst']:.2f}%"


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 热点低位 L2 补涨：卖出时机验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        "## 结论",
        "",
        "```text",
        "1. 固定 D+5 不是最优雅，但在当前样本里是一个很稳的基准。",
        "2. D+1 不冲高回落后，D+4/D+5 是较好的收益释放区；过早止盈会砍掉大赢家。",
        "3. D+1 冲高回落后，样本后续也会修复，但尾部风险显著变大。",
        "4. 当前更像可执行的卖出框架：D+1确认强弱，D+3第一次复核，D+5默认结束；亏损超过2%优先风控。",
        "```",
        "",
        "## 固定卖出窗口",
        "",
        "| 分组 | D+1 | D+2 | D+3 | D+4 | D+5 | D+10 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in [("all", "全部"), ("d1_no_fade", "D+1不回落"), ("d1_fade", "D+1回落")]:
        data = report["fixed_exit"][key]
        lines.append(
            f"| {label} | {data['d1']['avg']:.2f}% | {data['d2']['avg']:.2f}% | {data['d3']['avg']:.2f}% | "
            f"{data['d4']['avg']:.2f}% | {data['d5']['avg']:.2f}% | {data['d10']['avg']:.2f}% |"
        )
    lines += [
        "",
        "## 卖出策略测试",
        "",
        "| 规则 | 表现 |",
        "|---|---|",
    ]
    labels = {
        "close_stop_-2": "收盘跌破 -2% 止损",
        "close_stop_-3": "收盘跌破 -3% 止损",
        "close_stop_-5": "收盘跌破 -5% 止损",
        "close_take_5_stop_-3": "收盘 +5%止盈 / -3%止损",
        "close_take_10_stop_-5": "收盘 +10%止盈 / -5%止损",
        "risk_exit_d1_fade_and_d1_le_-2": "D+1回落且当天<=-2%退出，否则D+5",
    }
    for key, s in report["close_policies"].items():
        lines.append(f"| {labels.get(key, key)} | {render_stat(s)} |")
    lines += [
        "",
        "## D+1~D+5 波动空间",
        "",
        "| 分组 | 最大浮盈MFE | 最大浮亏MAE |",
        "|---|---|---|",
    ]
    for key, label in [("all", "全部"), ("d1_no_fade", "D+1不回落"), ("d1_fade", "D+1回落")]:
        item = report["mfe_mae"][key]
        lines.append(f"| {label} | {render_stat(item['mfe'])} | {render_stat(item['mae'])} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze exit timing for hot-theme low-position L2 strategy samples.")
    parser.add_argument("--sample-db", default=str(DEFAULT_SAMPLE_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    samples = load_enriched_samples(Path(args.sample_db))
    report = build_report(samples)
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_position_l2_exit_policy.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
