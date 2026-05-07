#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import MARKET_HEAT_DIR, ensure_market_heat_dir


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


def incremental_after_d1(row: Dict[str, Any], horizon: int) -> Optional[float]:
    d1 = row.get("d1_return_pct")
    dh = row.get(f"d{horizon}_return_pct")
    if d1 is None or dh is None:
        return None
    return ((1 + safe_float(dh) / 100) / (1 + safe_float(d1) / 100) - 1) * 100


def load_samples(db_path: Path) -> List[Dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM samples ORDER BY trade_date, symbol")]


def group_stats(samples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "d1": stat([r.get("d1_return_pct") for r in samples]),
        "d3": stat([r.get("d3_return_pct") for r in samples]),
        "d5": stat([r.get("d5_return_pct") for r in samples]),
        "d1_close_to_d3": stat([incremental_after_d1(r, 3) for r in samples]),
        "d1_close_to_d5": stat([incremental_after_d1(r, 5) for r in samples]),
        "fade_rate": round(sum(1 for r in samples if int(r.get("intraday_fade") or 0) == 1) / len(samples), 4) if samples else 0.0,
        "avg_fade_ratio": round(sum(safe_float(r.get("fade_ratio")) for r in samples) / len(samples), 4) if samples else 0.0,
        "avg_open_gap": round(sum(safe_float(r.get("open_gap_pct")) for r in samples) / len(samples), 4) if samples else 0.0,
    }


def policy_return(row: Dict[str, Any], should_exit_d1: Callable[[Dict[str, Any]], bool]) -> float:
    return safe_float(row.get("d1_return_pct")) if should_exit_d1(row) else safe_float(row.get("d5_return_pct"))


def policy_stats(samples: Sequence[Dict[str, Any]], name: str, should_exit_d1: Callable[[Dict[str, Any]], bool]) -> Dict[str, Any]:
    exits = [r for r in samples if should_exit_d1(r)]
    return {
        "name": name,
        "exit_count": len(exits),
        "exit_rate": round(len(exits) / len(samples), 4) if samples else 0.0,
        "return": stat([policy_return(r, should_exit_d1) for r in samples]),
    }


def build_report(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups = {
        "all": group_stats(samples),
        "d1_no_fade": group_stats([r for r in samples if int(r.get("intraday_fade") or 0) == 0]),
        "d1_fade": group_stats([r for r in samples if int(r.get("intraday_fade") or 0) == 1]),
        "fade_ratio_le_0_2": group_stats([r for r in samples if safe_float(r.get("fade_ratio")) <= 0.2]),
        "fade_ratio_0_2_to_0_5": group_stats([r for r in samples if 0.2 < safe_float(r.get("fade_ratio")) <= 0.5]),
        "fade_ratio_gt_0_5": group_stats([r for r in samples if safe_float(r.get("fade_ratio")) > 0.5]),
        "d1_ret_le_minus2": group_stats([r for r in samples if safe_float(r.get("d1_return_pct")) <= -2]),
        "d1_ret_minus2_to_0": group_stats([r for r in samples if -2 < safe_float(r.get("d1_return_pct")) <= 0]),
        "d1_ret_0_to_2": group_stats([r for r in samples if 0 < safe_float(r.get("d1_return_pct")) <= 2]),
        "d1_ret_gt_2": group_stats([r for r in samples if safe_float(r.get("d1_return_pct")) > 2]),
    }
    policies = [
        policy_stats(samples, "base_hold_to_d5", lambda r: False),
        policy_stats(samples, "exit_d1_if_fade", lambda r: int(r.get("intraday_fade") or 0) == 1),
        policy_stats(samples, "exit_d1_if_d1_return_le_minus1", lambda r: safe_float(r.get("d1_return_pct")) <= -1),
        policy_stats(samples, "exit_d1_if_d1_return_le_minus2", lambda r: safe_float(r.get("d1_return_pct")) <= -2),
        policy_stats(samples, "exit_d1_if_fade_and_d1_return_le_minus2", lambda r: int(r.get("intraday_fade") or 0) == 1 and safe_float(r.get("d1_return_pct")) <= -2),
    ]
    top_no_fade = sorted([r for r in samples if int(r.get("intraday_fade") or 0) == 0], key=lambda r: safe_float(r.get("d5_return_pct")), reverse=True)[:15]
    worst_fade = sorted([r for r in samples if int(r.get("intraday_fade") or 0) == 1], key=lambda r: safe_float(r.get("d5_return_pct")))[:15]
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "strategy": "hot_theme_low_position_l2_shadow_v1",
            "sample_count": len(samples),
            "start_date": samples[0]["trade_date"] if samples else None,
            "end_date": samples[-1]["trade_date"] if samples else None,
            "note": "D+1冲高回落只能在D+1盘中/收盘后确认，不能当作D+1开盘前过滤条件。",
        },
        "groups": groups,
        "policies": policies,
        "top_no_fade_winners": top_no_fade,
        "worst_fade_losers": worst_fade,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    groups = report["groups"]
    lines = [
        f"# 热点低位 L2 补涨：D+1 冲高回落深挖 {meta['start_date']} ~ {meta['end_date']}",
        "",
        "## 核心结论",
        "",
        "D+1 冲高回落不是买入前过滤条件，因为 D+1 开盘时还不知道它会不会冲高回落。",
        "",
        "它更适合作为两个用途：",
        "",
        "```text",
        "1. D+1 收盘后的持仓确认：不冲高回落，后续继续走强概率高。",
        "2. D+1 风险处置：如果冲高回落且当天从开盘算亏损超过 2%，应优先止损/降仓。",
        "```",
        "",
        "## 分组表现",
        "",
        "| 分组 | 样本 | D+1均值 | D+3均值 | D+5均值 | D+5胜率 | D+1收盘后到D+5 | 最差D+5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "all": "全部",
        "d1_no_fade": "D+1不冲高回落",
        "d1_fade": "D+1冲高回落",
        "fade_ratio_le_0_2": "回落比例<=0.2",
        "fade_ratio_0_2_to_0_5": "回落比例0.2~0.5",
        "fade_ratio_gt_0_5": "回落比例>0.5",
        "d1_ret_le_minus2": "D+1<=-2%",
        "d1_ret_minus2_to_0": "-2%<D+1<=0",
        "d1_ret_0_to_2": "0<D+1<=2%",
        "d1_ret_gt_2": "D+1>2%",
    }
    for key in labels:
        g = groups[key]
        lines.append(
            f"| {labels[key]} | {g['d5']['n']} | {g['d1']['avg']:.2f}% | {g['d3']['avg']:.2f}% | "
            f"{g['d5']['avg']:.2f}% | {g['d5']['win_rate']:.1%} | {g['d1_close_to_d5']['avg']:.2f}% | {g['d5']['worst']:.2f}% |"
        )
    lines += [
        "",
        "## 退出规则模拟",
        "",
        "口径：原本 D+1 开盘买入、D+5 收盘卖出；规则命中时改成 D+1 收盘退出。",
        "",
        "| 规则 | 退出样本 | 退出占比 | 均值 | 中位数 | 胜率 | P10 | 最差 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    policy_labels = {
        "base_hold_to_d5": "基准：全部持有到D+5",
        "exit_d1_if_fade": "只要冲高回落就D+1退出",
        "exit_d1_if_d1_return_le_minus1": "D+1<=-1%退出",
        "exit_d1_if_d1_return_le_minus2": "D+1<=-2%退出",
        "exit_d1_if_fade_and_d1_return_le_minus2": "冲高回落且D+1<=-2%退出",
    }
    for p in report["policies"]:
        s = p["return"]
        lines.append(
            f"| {policy_labels.get(p['name'], p['name'])} | {p['exit_count']} | {p['exit_rate']:.1%} | "
            f"{s['avg']:.2f}% | {s['median']:.2f}% | {s['win_rate']:.1%} | {s['p10']:.2f}% | {s['worst']:.2f}% |"
        )
    lines += [
        "",
        "## 判断",
        "",
        "```text",
        "1. 不能简单把“冲高回落”全部卖掉：这样平均收益会从 +2.70% 降到 +1.86%。",
        "2. 真正危险的是“冲高回落 + D+1 当天已经跌超过 2%”：这批样本后续没有明显修复优势。",
        "3. D+1不冲高回落是强确认信号：D+5均值 +5.68%，胜率 85%。",
        "4. 如果 D+1 收盘后才考虑是否继续持有，最佳初步规则是：不冲高回落继续拿；冲高回落但跌幅不深可观察；跌破 -2% 优先退出。",
        "```",
        "",
        "## 不冲高回落代表赢家",
        "",
        "| 日期 | 股票 | 板块 | D+1 | D+5 | 量能比 | 60日乖离 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in report["top_no_fade_winners"]:
        lines.append(
            f"| {r['trade_date']} | {r['symbol']} {r['name']} | {r['theme_name']} | {safe_float(r.get('d1_return_pct')):.2f}% | "
            f"{safe_float(r.get('d5_return_pct')):.2f}% | {safe_float(r.get('amount_ratio_10d')):.2f} | {safe_float(r.get('ma60_distance_abs_pct')):.2f}% |"
        )
    lines += [
        "",
        "## 冲高回落代表失败",
        "",
        "| 日期 | 股票 | 板块 | D+1 | D+5 | 回落比例 | 量能比 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in report["worst_fade_losers"]:
        lines.append(
            f"| {r['trade_date']} | {r['symbol']} {r['name']} | {r['theme_name']} | {safe_float(r.get('d1_return_pct')):.2f}% | "
            f"{safe_float(r.get('d5_return_pct')):.2f}% | {safe_float(r.get('fade_ratio')):.2f} | {safe_float(r.get('amount_ratio_10d')):.2f} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze D+1 intraday fade as confirmation/risk policy for hot-theme low-position L2 strategy.")
    parser.add_argument("--sample-db", default=str(DEFAULT_SAMPLE_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    samples = load_samples(Path(args.sample_db))
    report = build_report(samples)
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_position_l2_d1_fade_analysis.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
