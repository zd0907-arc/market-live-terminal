#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import MARKET_HEAT_DIR, _trade_dates, ensure_market_heat_dir
from backend.scripts.analyze_hot_sector_granularity import DEFAULT_FINE_RULES, load_fine_sector_themes, load_json
from backend.scripts.analyze_hot_theme_funding_cross_validation import load_atomic_extra
from backend.scripts.analyze_hot_theme_low_position_l2_strategy import active_hot_themes, prior_avg_amount
from backend.scripts.analyze_hot_theme_winner_lead_lag import (
    DEFAULT_STOCK_SECTOR_DB,
    DEFAULT_TRADABLE_THEME_DB,
    forward_return,
    load_extra_names,
    load_price_and_limit_rows,
    safe_float,
    summarize,
)
from backend.scripts.analyze_strategy_theme_lifecycle import build_rank_history
from backend.scripts.analyze_strategy_theme_resonance import compute_market_returns, first_indexes, is_valid_tradeable, load_or_build_heat_snapshots


def pct_change(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def position_n(rows: Dict[str, sqlite3.Row], trade_dates: Sequence[str], i: int, lookback: int) -> Optional[float]:
    vals = []
    for d in trade_dates[max(0, i - lookback + 1):i + 1]:
        row = rows.get(d)
        if row:
            vals.append(safe_float(row["close"]))
    if len(vals) < max(8, lookback // 2):
        return None
    lo, hi = min(vals), max(vals)
    close = safe_float(rows[trade_dates[i]]["close"])
    if hi <= lo:
        return 0.5
    return (close - lo) / (hi - lo)


def ma_distance(rows: Dict[str, sqlite3.Row], trade_dates: Sequence[str], i: int, lookback: int) -> Optional[float]:
    vals = []
    for d in trade_dates[max(0, i - lookback + 1):i + 1]:
        row = rows.get(d)
        if row:
            vals.append(safe_float(row["close"]))
    if len(vals) < max(10, lookback // 2):
        return None
    ma = sum(vals) / len(vals)
    if ma <= 0:
        return None
    return (safe_float(rows[trade_dates[i]]["close"]) / ma - 1) * 100


def ma_stickiness(rows: Dict[str, sqlite3.Row], trade_dates: Sequence[str], i: int) -> Optional[float]:
    mas = []
    for lb in [5, 10, 20]:
        vals = []
        for d in trade_dates[max(0, i - lb + 1):i + 1]:
            row = rows.get(d)
            if row:
                vals.append(safe_float(row["close"]))
        if len(vals) < max(3, lb // 2):
            return None
        mas.append(sum(vals) / len(vals))
    base = safe_float(rows[trade_dates[i]]["close"])
    if base <= 0:
        return None
    return (max(mas) - min(mas)) / base * 100


def super_condition(extra_rows: Dict[str, Dict[str, Any]], trade_dates: Sequence[str], i: int, mode: str) -> bool:
    vals = []
    for d in trade_dates[max(0, i - 2):i + 1]:
        if d in extra_rows:
            vals.append(safe_float(extra_rows[d].get("l2_super_net_amount")))
    if mode == "2d_continuous":
        if i < 1:
            return False
        return safe_float(extra_rows.get(trade_dates[i], {}).get("l2_super_net_amount")) > 0 and safe_float(extra_rows.get(trade_dates[i - 1], {}).get("l2_super_net_amount")) > 0
    if mode == "2of3":
        return len(vals) >= 3 and sum(1 for v in vals if v > 0) >= 2 and sum(vals) > 0
    if mode == "3d_sum_positive":
        return len(vals) >= 2 and sum(vals) > 0
    return True


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 热点低位 L2 补涨参数稳健性验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        f"- 样本数低于 {meta['min_sample_for_main']} 的组合标记为观察，不作为主参数。",
        "- D 日成交额均值使用 D-10~D-1；量能比设置下限，避免绝对地量。",
        "- 加入 60 日均线乖离和 5/10/20 均线粘合度，避免下跌半山腰。",
        "",
        "## Top 稳定组合（D+5，样本达标）",
        "",
        "| 排名 | 样本 | 均值 | Alpha | 胜率 | 参数 |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for idx, item in enumerate(report.get("top_main", [])[:20], start=1):
        stat = item["stats"].get("5") or item["stats"].get("3") or {}
        lines.append(f"| {idx} | {stat.get('n', 0)} | {stat.get('avg', 0):.2f}% | {stat.get('alpha', 0):.2f}% | {stat.get('win_rate', 0):.1%} | {item['label']} |")
    lines += ["", "## 样本不足但表现突出的观察组合", "", "| 样本 | 均值 | Alpha | 胜率 | 参数 |", "|---:|---:|---:|---:|---|"]
    for item in report.get("top_watch", [])[:15]:
        stat = item["stats"].get("5") or item["stats"].get("3") or {}
        lines.append(f"| {stat.get('n', 0)} | {stat.get('avg', 0):.2f}% | {stat.get('alpha', 0):.2f}% | {stat.get('win_rate', 0):.1%} | {item['label']} |")
    lines += ["", "## 基准组合", ""]
    for item in report.get("baseline", []):
        lines.append(f"- {item['label']}: " + ", ".join([f"D+{h} n={s['n']} avg={s['avg']:.2f}% alpha={s['alpha']:.2f}% win={s['win_rate']:.1%}" for h, s in item["stats"].items()]))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid robustness test for hot-theme low-position L2/super-order accumulation strategy.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--horizons", default="3,5")
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--min-member-count", type=int, default=5)
    parser.add_argument("--max-member-count", type=int, default=80)
    parser.add_argument("--include-unbuyable", action="store_true")
    parser.add_argument("--min-sample-for-main", type=int, default=80)
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--no-heat-cache", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    all_dates = _trade_dates(end_date, args.days + args.min_history_days + max(horizons) + 80)
    analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], end_date)
    date_index = {d: idx for idx, d in enumerate(trade_dates)}
    first_idx = first_indexes(price_rows, date_index)

    rules = load_json(Path(args.fine_rules))
    themes, theme_members, _symbol_themes, name_map = load_fine_sector_themes(Path(args.tradable_theme_db), rules, args.min_member_count, args.max_member_count)
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})

    heat_dates = [d for d in all_dates if d <= analysis_dates[-1]]
    snapshots = load_or_build_heat_snapshots(heat_dates, themes, 15, args.min_member_count, args.max_member_count, MARKET_HEAT_DIR / "cache", use_cache=not args.no_heat_cache)
    rank_history = build_rank_history(snapshots, heat_dates, 15)
    heat_pos = {d: idx for idx, d in enumerate(heat_dates)}
    market = compute_market_returns(analysis_dates, trade_dates, price_rows, limit_rows, name_map, horizons, args.min_amount, args.min_history_days, exclude_unbuyable=not args.include_unbuyable)
    extras = load_atomic_extra(all_dates[0], analysis_dates[-1])

    # Parameter grid. Kept deliberately small to avoid overfitting.
    hot_params = [(10, 5, 2, 3), (15, 5, 2, 4)]  # active_top_k, lookback, min_hits, max_hits
    pos_thresholds = [0.5, 0.65, 0.8]
    ma60_abs_thresholds = [None, 5.0, 8.0]
    ma_sticky_thresholds = [None, 4.0, 6.0]
    amount_ranges = [(0.5, 1.0), (0.5, 1.2), (0.8, 1.2)]
    super_modes = ["none", "2d_continuous", "2of3", "3d_sum_positive"]

    param_results: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    param_labels: Dict[str, str] = {}
    baseline_results: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for d in analysis_dates:
        i = date_index.get(d)
        if i is None or i + max(horizons) >= len(trade_dates) or i < 60 or d not in heat_pos:
            continue
        entry_date = trade_dates[i + 1]
        active_by_key = {
            hp: active_hot_themes(d, heat_dates, heat_pos, rank_history, snapshots, active_top_k=hp[0], lookback=hp[1], min_hits=hp[2], max_hits=hp[3])
            for hp in hot_params
        }
        candidates: Dict[Tuple[str, Tuple[int, int, int, int]], Dict[str, Any]] = {}
        for hp, active in active_by_key.items():
            for theme in active:
                for symbol in theme_members.get(theme["id"], set()):
                    rows = price_rows.get(symbol, {})
                    if d not in rows or entry_date not in rows or trade_dates[i - 1] not in rows or trade_dates[i - 5] not in rows:
                        continue
                    if not is_valid_tradeable(symbol, d, entry_date, i, rows, first_idx, limit_rows, name_map, args.min_amount, args.min_history_days, not args.include_unbuyable):
                        continue
                    ret5 = pct_change(safe_float(rows[d]["close"]), safe_float(rows[trade_dates[i - 5]]["close"]))
                    if ret5 is None or not (-8 <= ret5 < 5):
                        continue
                    if safe_float(rows[d]["l2_main_net_amount"]) <= 0 or safe_float(rows[trade_dates[i - 1]]["l2_main_net_amount"]) <= 0:
                        continue
                    avg10 = prior_avg_amount(rows, trade_dates, i, 10)
                    if avg10 is None or avg10 <= 0:
                        continue
                    rec = {
                        "symbol": symbol,
                        "hp": hp,
                        "rows": rows,
                        "amount_ratio": safe_float(rows[d]["total_amount"]) / avg10,
                        "pos20": position_n(rows, trade_dates, i, 20),
                        "ma60_abs": abs(ma_distance(rows, trade_dates, i, 60) or 999),
                        "ma_stick": ma_stickiness(rows, trade_dates, i),
                        "extra_rows": extras.get(symbol, {}),
                    }
                    old = candidates.get((symbol, hp))
                    if old is None or theme["rank"] < old.get("theme_rank", 999):
                        rec["theme_rank"] = theme["rank"]
                        candidates[(symbol, hp)] = rec

        for (_symbol, hp), rec in candidates.items():
            rows = rec["rows"]
            for h in horizons:
                exit_date = trade_dates[i + h]
                if exit_date not in rows:
                    continue
                ret = forward_return(rows[entry_date], rows[exit_date])
                if ret is None:
                    continue
                # baseline comparable with previous good idea: low/L2 + amount shrink or normal <=1.2
                if rec["pos20"] is not None and rec["pos20"] <= 0.65 and 0.5 <= rec["amount_ratio"] <= 1.2:
                    baseline_results["baseline_pos065_amt05_12"][str(h)].append(ret)
                for pos_max, ma60_max, stick_max, arange, smode in itertools.product(pos_thresholds, ma60_abs_thresholds, ma_sticky_thresholds, amount_ranges, super_modes):
                    if rec["pos20"] is None or rec["pos20"] > pos_max:
                        continue
                    if not (arange[0] <= rec["amount_ratio"] <= arange[1]):
                        continue
                    if ma60_max is not None and rec["ma60_abs"] > ma60_max:
                        continue
                    if stick_max is not None and (rec["ma_stick"] is None or rec["ma_stick"] > stick_max):
                        continue
                    if not super_condition(rec["extra_rows"], trade_dates, i, smode):
                        continue
                    key = f"hot{hp[0]}_{hp[2]}to{hp[3]}_pos{pos_max}_amt{arange[0]}-{arange[1]}_ma60{ma60_max}_stick{stick_max}_super{smode}"
                    param_labels[key] = f"热点Top{hp[0]} {hp[2]}~{hp[3]}/5日, pos20<={pos_max}, amount {arange[0]}~{arange[1]}, ma60<={ma60_max}, stick<={stick_max}, super={smode}"
                    param_results[key][str(h)].append(ret)

    def build_item(key: str, values: Dict[str, List[float]]) -> Dict[str, Any]:
        stats = {}
        for h in map(str, horizons):
            stat = summarize(values.get(h, []))
            stat["alpha"] = round(stat["avg"] - market[h]["avg"], 4)
            stats[h] = stat
        return {"key": key, "label": param_labels.get(key, key), "stats": stats}

    items = [build_item(k, v) for k, v in param_results.items()]
    main_items = [x for x in items if (x["stats"].get("5") or x["stats"].get("3"))["n"] >= args.min_sample_for_main]
    watch_items = [x for x in items if 0 < (x["stats"].get("5") or x["stats"].get("3"))["n"] < args.min_sample_for_main]
    def score_item(item: Dict[str, Any]) -> Tuple[float, float, int]:
        s5 = item["stats"].get("5") or item["stats"].get("3")
        s3 = item["stats"].get("3") or s5
        return (safe_float(s5.get("alpha")), safe_float(s3.get("alpha")), int(s5.get("n", 0)))
    main_items.sort(key=score_item, reverse=True)
    watch_items.sort(key=score_item, reverse=True)

    baseline = []
    for k, v in baseline_results.items():
        item = {"key": k, "label": k, "stats": {}}
        for h in map(str, horizons):
            stat = summarize(v.get(h, []))
            stat["alpha"] = round(stat["avg"] - market[h]["avg"], 4)
            item["stats"][h] = stat
        baseline.append(item)

    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "analysis_days": len(analysis_dates),
            "min_sample_for_main": args.min_sample_for_main,
        },
        "market": market,
        "baseline": baseline,
        "top_main": main_items[:50],
        "top_watch": watch_items[:50],
    }
    ensure_market_heat_dir()
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"hot_theme_low_position_l2_robustness_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
