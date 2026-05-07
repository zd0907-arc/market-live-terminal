#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
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
    ATOMIC_DB,
    forward_return,
    is_st_name,
    is_unbuyable_limit_up,
    load_extra_names,
    load_price_and_limit_rows,
    safe_float,
)
from backend.scripts.analyze_new_theme_leader_strategy import intraday_fade, open_gap_bin
from backend.scripts.analyze_strategy_theme_lifecycle import build_rank_history
from backend.scripts.analyze_strategy_theme_resonance import first_indexes, load_or_build_heat_snapshots
from backend.scripts.analyze_hot_theme_low_position_l2_robustness import ma_distance, ma_stickiness, position_n, super_condition


def pct_change(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def tradeable_on_d(symbol: str, d: str, i: int, rows: Dict[str, sqlite3.Row], first_idx: Dict[str, int], name_map: Dict[str, str], min_amount: float, min_history_days: int) -> bool:
    d_row = rows.get(d)
    if not d_row:
        return False
    if first_idx.get(symbol, 10**9) > i - min_history_days:
        return False
    if safe_float(d_row["total_amount"]) < min_amount:
        return False
    if is_st_name(name_map.get(symbol, "")):
        return False
    return True


def market_regime(trade_date: str, trade_dates: Sequence[str], price_rows: Dict[str, Dict[str, sqlite3.Row]], limit_rows: Dict[str, Dict[str, sqlite3.Row]]) -> Dict[str, Any]:
    total_amount = 0.0
    up = down = flat = used = 0
    idx = {d: i for i, d in enumerate(trade_dates)}.get(trade_date)
    prev_date = trade_dates[idx - 1] if idx and idx > 0 else None
    limit_up_count = 0
    for symbol, rows in price_rows.items():
        row = rows.get(trade_date)
        if not row:
            continue
        total_amount += safe_float(row["total_amount"])
        if prev_date and prev_date in rows:
            prev_close = safe_float(rows[prev_date]["close"])
            ret = pct_change(safe_float(row["close"]), prev_close)
            if ret is not None:
                used += 1
                if ret > 0:
                    up += 1
                elif ret < 0:
                    down += 1
                else:
                    flat += 1
        limit_row = limit_rows.get(symbol, {}).get(trade_date)
        if limit_row is not None and int(limit_row["is_limit_up_close"] or 0) == 1:
            limit_up_count += 1
    amount_yi = total_amount / 1e8
    liquidity_label = "流动性充裕" if amount_yi >= 12000 else ("流动性正常" if amount_yi >= 8000 else "市场缩量")
    # Some locally generated limit-state snapshots currently have all limit flags as 0;
    # treat that as unavailable instead of incorrectly saying sentiment is weak.
    sentiment_label = "短线情绪数据未就绪" if limit_up_count == 0 else ("短线情绪强" if limit_up_count >= 80 else ("短线情绪正常" if limit_up_count >= 35 else "短线情绪偏弱"))
    return {
        "total_amount_yi": round(amount_yi, 1),
        "liquidity_label": liquidity_label,
        "limit_up_count": limit_up_count,
        "limit_state_available": limit_up_count > 0,
        "sentiment_label": sentiment_label,
        "advancers": up,
        "decliners": down,
        "flat": flat,
        "advancer_ratio": round(up / used, 4) if used else 0.0,
    }


def shadow_score(rec: Dict[str, Any]) -> float:
    score = 0.0
    score += 25 if rec["super_positive_days_3d"] >= 3 else 20
    score += 18 if 0.8 <= rec["amount_ratio_10d"] <= 1.2 else 14
    score += 16 if rec["position_20d"] <= 0.65 else 10
    score += 14 if rec["ma60_distance_abs_pct"] <= 5 else 10
    if rec.get("ma_stickiness_pct") is not None:
        score += 10 if rec["ma_stickiness_pct"] <= 4 else (6 if rec["ma_stickiness_pct"] <= 6 else 0)
    score += min(12, max(0, rec["l2_main_net_2d_yi"] * 2.0))
    score += max(0, 5 - rec["theme_rank"]) * 1.5
    return round(score, 2)


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    m = report["market_regime"]
    lines = [
        f"# 热点低位补涨影子候选 {meta['trade_date']}",
        "",
        f"市场：{m['liquidity_label']}（成交额 {m['total_amount_yi']} 亿），{m['sentiment_label']}（涨停 {m['limit_up_count']} 家），上涨占比 {m['advancer_ratio']:.1%}。",
        "",
        "这不是买入清单，是前向观察池：看历史有效形态在未来 20~40 个交易日是否继续有效。",
        "",
        f"候选数：{len(report['candidates'])}",
        "",
    ]
    if not report["candidates"]:
        lines.append("今日没有符合主观察口径的候选。")
        return "\n".join(lines)
    lines += [
        "| 排名 | 股票 | 热点板块 | 分数 | 20日位置 | 60日乖离 | 量能比 | L2两日净流入(亿) | 超大单2/3 | D+1状态 | 跟踪 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for idx, c in enumerate(report["candidates"], start=1):
        tracking = []
        for h in ["1", "3", "5"]:
            val = c.get("tracking", {}).get(f"d{h}_return_pct")
            if val is not None:
                tracking.append(f"D+{h} {val:+.2f}%")
        track_text = " / ".join(tracking) if tracking else "待跟踪"
        entry = c.get("entry", {})
        entry_label = entry.get("entry_label") or "无D+1数据"
        lines.append(
            f"| {idx} | {c['symbol']} {c['name']} | {c['theme_name']} | {c['shadow_score']:.1f} | "
            f"{c['position_20d']:.2f} | {c['ma60_distance_pct']:+.1f}% | {c['amount_ratio_10d']:.2f} | "
            f"{c['l2_main_net_2d_yi']:.2f} | {c['super_positive_days_3d']}/3 | {entry_label} | {track_text} |"
        )
    lines += ["", "## 观察口径", "", "```text", meta["strategy_notes"], "```"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump daily shadow candidates for hot-theme low-position L2/super-order accumulation strategy.")
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--min-member-count", type=int, default=5)
    parser.add_argument("--max-member-count", type=int, default=80)
    parser.add_argument("--active-top-k", type=int, default=10)
    parser.add_argument("--hot-lookback", type=int, default=5)
    parser.add_argument("--hot-min-hits", type=int, default=2)
    parser.add_argument("--hot-max-hits", type=int, default=3)
    parser.add_argument("--max-5d-return", type=float, default=5.0)
    parser.add_argument("--min-5d-return", type=float, default=-8.0)
    parser.add_argument("--max-position-20d", type=float, default=0.8)
    parser.add_argument("--max-ma60-abs", type=float, default=8.0)
    parser.add_argument("--min-amount-ratio", type=float, default=0.5)
    parser.add_argument("--max-amount-ratio", type=float, default=1.2)
    parser.add_argument("--super-mode", default="2of3", choices=["2of3", "2d_continuous", "3d_sum_positive", "none"])
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--no-heat-cache", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    latest_date = _trade_dates("9999-12-31", 1)[-1]
    target = args.trade_date or latest_date
    # Price window ends at latest date so historical candidates can include D+1/D+3/D+5 tracking if available.
    all_dates = _trade_dates(latest_date, 140)
    if target not in all_dates:
        raise RuntimeError(f"trade_date {target} not in recent local trade dates")
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], latest_date)
    date_index = {d: idx for idx, d in enumerate(trade_dates)}
    i = date_index[target]
    first_idx = first_indexes(price_rows, date_index)

    rules = load_json(Path(args.fine_rules))
    themes, theme_members, _symbol_themes, name_map = load_fine_sector_themes(Path(args.tradable_theme_db), rules, args.min_member_count, args.max_member_count)
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})

    heat_dates = [d for d in _trade_dates(target, max(20, args.hot_lookback + 12)) if d <= target]
    snapshots = load_or_build_heat_snapshots(
        heat_dates,
        themes,
        args.active_top_k,
        args.min_member_count,
        args.max_member_count,
        MARKET_HEAT_DIR / "cache",
        use_cache=not args.no_heat_cache,
    )
    rank_history = build_rank_history(snapshots, heat_dates, args.active_top_k)
    heat_pos = {d: idx for idx, d in enumerate(heat_dates)}
    extras = load_atomic_extra(all_dates[0], latest_date)
    active = active_hot_themes(target, heat_dates, heat_pos, rank_history, snapshots, args.active_top_k, args.hot_lookback, args.hot_min_hits, args.hot_max_hits)

    by_symbol: Dict[str, Dict[str, Any]] = {}
    for theme in active:
        for symbol in theme_members.get(theme["id"], set()):
            rows = price_rows.get(symbol, {})
            if target not in rows or i < 60 or trade_dates[i - 1] not in rows or trade_dates[i - 5] not in rows:
                continue
            if not tradeable_on_d(symbol, target, i, rows, first_idx, name_map, args.min_amount, args.min_history_days):
                continue
            d_row = rows[target]
            y_row = rows[trade_dates[i - 1]]
            ret5 = pct_change(safe_float(d_row["close"]), safe_float(rows[trade_dates[i - 5]]["close"]))
            if ret5 is None or ret5 < args.min_5d_return or ret5 >= args.max_5d_return:
                continue
            pos20 = position_n(rows, trade_dates, i, 20)
            if pos20 is None or pos20 > args.max_position_20d:
                continue
            ma60 = ma_distance(rows, trade_dates, i, 60)
            if ma60 is None or abs(ma60) > args.max_ma60_abs:
                continue
            avg10 = prior_avg_amount(rows, trade_dates, i, 10)
            if avg10 is None or avg10 <= 0:
                continue
            amount_ratio = safe_float(d_row["total_amount"]) / avg10
            if not (args.min_amount_ratio <= amount_ratio <= args.max_amount_ratio):
                continue
            if safe_float(d_row["l2_main_net_amount"]) <= 0 or safe_float(y_row["l2_main_net_amount"]) <= 0:
                continue
            extra_rows = extras.get(symbol, {})
            if not super_condition(extra_rows, trade_dates, i, args.super_mode):
                continue
            super_vals = [safe_float(extra_rows.get(d, {}).get("l2_super_net_amount")) for d in trade_dates[max(0, i - 2):i + 1]]
            super_days = sum(1 for v in super_vals if v > 0)
            l2_main_2d = safe_float(d_row["l2_main_net_amount"]) + safe_float(y_row["l2_main_net_amount"])
            rec = {
                "symbol": symbol,
                "name": name_map.get(symbol, symbol),
                "trade_date": target,
                "theme_id": theme["id"],
                "theme_name": theme["name"],
                "theme_rank": theme["rank"],
                "theme_recent_hits": theme.get("recent_hits"),
                "close": round(safe_float(d_row["close"]), 3),
                "day_return_pct": round(pct_change(safe_float(d_row["close"]), safe_float(y_row["close"])) or 0.0, 4),
                "return_5d_pct": round(ret5, 4),
                "position_20d": round(pos20, 4),
                "ma60_distance_pct": round(ma60, 4),
                "ma60_distance_abs_pct": round(abs(ma60), 4),
                "ma_stickiness_pct": round(ma_stickiness(rows, trade_dates, i) or 0.0, 4),
                "amount_yi": round(safe_float(d_row["total_amount"]) / 1e8, 4),
                "amount_ratio_10d": round(amount_ratio, 4),
                "l2_main_net_today_yi": round(safe_float(d_row["l2_main_net_amount"]) / 1e8, 4),
                "l2_main_net_yday_yi": round(safe_float(y_row["l2_main_net_amount"]) / 1e8, 4),
                "l2_main_net_2d_yi": round(l2_main_2d / 1e8, 4),
                "l2_super_net_3d_yi": round(sum(super_vals) / 1e8, 4),
                "super_positive_days_3d": super_days,
                "super_mode": args.super_mode,
                "entry": {},
                "tracking": {},
            }
            entry_idx = i + 1
            if entry_idx < len(trade_dates):
                entry_date = trade_dates[entry_idx]
                if entry_date in rows:
                    entry_row = rows[entry_date]
                    gap = pct_change(safe_float(entry_row["open"]), safe_float(d_row["close"])) or 0.0
                    unbuyable = is_unbuyable_limit_up(symbol, d_row, entry_row, limit_rows, entry_date)
                    fade, fade_ratio = intraday_fade(entry_row)
                    if unbuyable:
                        label = "涨停开盘/不可买"
                    elif gap > 5:
                        label = "高开>5%风险"
                    elif gap > 2:
                        label = "高开2~5%"
                    else:
                        label = "低开/平开/温和高开"
                    rec["entry"] = {
                        "entry_date": entry_date,
                        "entry_open": round(safe_float(entry_row["open"]), 3),
                        "open_gap_pct": round(gap, 4),
                        "open_gap_bin": open_gap_bin(gap),
                        "unbuyable_limit_up_open": bool(unbuyable),
                        "intraday_fade": bool(fade),
                        "fade_ratio": round(fade_ratio, 4),
                        "entry_label": label,
                    }
                    for h in [1, 3, 5]:
                        exit_idx = i + h
                        if exit_idx < len(trade_dates):
                            exit_date = trade_dates[exit_idx]
                            if exit_date in rows:
                                ret = forward_return(entry_row, rows[exit_date])
                                if ret is not None:
                                    rec["tracking"][f"d{h}_return_pct"] = round(ret, 4)
                                    rec["tracking"][f"d{h}_exit_date"] = exit_date
            rec["shadow_score"] = shadow_score(rec)
            old = by_symbol.get(symbol)
            if old is None or (rec["theme_rank"], -rec["shadow_score"]) < (old["theme_rank"], -old["shadow_score"]):
                by_symbol[symbol] = rec

    candidates = sorted(by_symbol.values(), key=lambda x: (x["entry"].get("unbuyable_limit_up_open", False), -x["shadow_score"], x["theme_rank"]))[: args.top_n]
    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "trade_date": target,
            "latest_trade_date": latest_date,
            "strategy": "hot_theme_low_position_l2_shadow_v1",
            "strategy_notes": (
                f"热点Top{args.active_top_k}过去{args.hot_lookback}日上榜{args.hot_min_hits}~{args.hot_max_hits}次；"
                f"近5日涨幅{args.min_5d_return}~{args.max_5d_return}%；20日位置<={args.max_position_20d}；"
                f"60日乖离<={args.max_ma60_abs}%；量能比{args.min_amount_ratio}~{args.max_amount_ratio}；"
                f"D/D-1 L2主力净流入；超大单条件={args.super_mode}。"
            ),
        },
        "market_regime": market_regime(target, trade_dates, price_rows, limit_rows),
        "active_themes": active,
        "candidates": candidates,
    }
    ensure_market_heat_dir()
    out_dir = MARKET_HEAT_DIR / "shadow_candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output) if args.output else out_dir / f"hot_theme_low_position_candidates_{target}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
