#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
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
from backend.scripts.analyze_hot_theme_low_position_l2_robustness import ma_distance, ma_stickiness, position_n, super_condition
from backend.scripts.analyze_hot_theme_winner_lead_lag import (
    DEFAULT_STOCK_SECTOR_DB,
    DEFAULT_TRADABLE_THEME_DB,
    forward_return,
    is_st_name,
    is_unbuyable_limit_up,
    load_extra_names,
    load_price_and_limit_rows,
    safe_float,
    summarize,
)
from backend.scripts.analyze_new_theme_leader_strategy import intraday_fade, open_gap_bin
from backend.scripts.analyze_strategy_theme_lifecycle import build_rank_history
from backend.scripts.analyze_strategy_theme_resonance import compute_market_returns, first_indexes, load_or_build_heat_snapshots
from backend.scripts.dump_hot_theme_low_position_candidates import market_regime, shadow_score


DEFAULT_OUTPUT_DB = MARKET_HEAT_DIR / "hot_theme_low_position_l2_samples.db"


def pct_change(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def tradeable_on_d(
    symbol: str,
    d: str,
    entry_date: str,
    i: int,
    rows: Dict[str, sqlite3.Row],
    first_idx: Dict[str, int],
    name_map: Dict[str, str],
    min_amount: float,
    min_history_days: int,
) -> bool:
    d_row = rows.get(d)
    entry_row = rows.get(entry_date)
    if not d_row or not entry_row:
        return False
    if first_idx.get(symbol, 10**9) > i - min_history_days:
        return False
    if safe_float(d_row["total_amount"]) < min_amount:
        return False
    if is_st_name(name_map.get(symbol, "")):
        return False
    return True


def outcome_bucket(ret: Optional[float]) -> str:
    if ret is None:
        return "unknown"
    if ret >= 8:
        return "big_winner"
    if ret >= 3:
        return "winner"
    if ret > 0:
        return "small_win"
    if ret <= -8:
        return "big_loser"
    if ret <= -3:
        return "loser"
    return "small_loss"


def _round(value: Any, digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    return round(safe_float(value), digits)


def _avg(records: Sequence[Dict[str, Any]], field: str) -> Optional[float]:
    vals = [safe_float(r.get(field)) for r in records if r.get(field) is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def _corr(records: Sequence[Dict[str, Any]], x: str, y: str) -> Optional[float]:
    pairs = [(safe_float(r.get(x)), safe_float(r.get(y))) for r in records if r.get(x) is not None and r.get(y) is not None]
    if len(pairs) < 3:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    vx = sum((v - mx) ** 2 for v in xs)
    vy = sum((v - my) ** 2 for v in ys)
    if vx <= 0 or vy <= 0:
        return None
    cov = sum((a - mx) * (b - my) for a, b in pairs)
    return round(cov / (vx * vy) ** 0.5, 4)


def _entry_fields(symbol: str, rows: Dict[str, sqlite3.Row], d_row: sqlite3.Row, i: int, trade_dates: Sequence[str], limit_rows: Dict[str, Dict[str, sqlite3.Row]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "entry_date": None,
        "entry_open": None,
        "open_gap_pct": None,
        "open_gap_bin": "unknown",
        "unbuyable_limit_up_open": 0,
        "intraday_fade": 0,
        "fade_ratio": None,
        "entry_label": "无D+1数据",
    }
    entry_idx = i + 1
    if entry_idx >= len(trade_dates):
        return out
    entry_date = trade_dates[entry_idx]
    entry_row = rows.get(entry_date)
    if not entry_row:
        return out
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
    out.update(
        {
            "entry_date": entry_date,
            "entry_open": round(safe_float(entry_row["open"]), 3),
            "open_gap_pct": round(gap, 4),
            "open_gap_bin": open_gap_bin(gap),
            "unbuyable_limit_up_open": 1 if unbuyable else 0,
            "intraday_fade": 1 if fade else 0,
            "fade_ratio": round(fade_ratio, 4),
            "entry_label": label,
        }
    )
    return out


def _tracking_fields(rows: Dict[str, sqlite3.Row], i: int, trade_dates: Sequence[str], horizons: Sequence[int]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    entry_idx = i + 1
    if entry_idx >= len(trade_dates):
        return out
    entry_date = trade_dates[entry_idx]
    entry_row = rows.get(entry_date)
    if not entry_row:
        return out
    for h in horizons:
        exit_idx = i + h
        ret: Optional[float] = None
        exit_date: Optional[str] = None
        if exit_idx < len(trade_dates):
            exit_date = trade_dates[exit_idx]
            if exit_date in rows:
                ret = forward_return(entry_row, rows[exit_date])
        out[f"d{h}_return_pct"] = round(ret, 4) if ret is not None else None
        out[f"d{h}_exit_date"] = exit_date
        out[f"d{h}_outcome"] = outcome_bucket(ret)
    return out


def generate_samples(args: argparse.Namespace) -> Dict[str, Any]:
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    all_dates = _trade_dates(end_date, args.days + args.min_history_days + max(args.horizons) + 90)
    analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    start_date = analysis_dates[0]
    latest_date = _trade_dates("9999-12-31", 1)[-1]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], latest_date)
    date_index = {d: idx for idx, d in enumerate(trade_dates)}
    first_idx = first_indexes(price_rows, date_index)

    rules = load_json(Path(args.fine_rules))
    themes, theme_members, _symbol_themes, name_map = load_fine_sector_themes(
        Path(args.tradable_theme_db),
        rules,
        args.min_member_count,
        args.max_member_count,
    )
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})

    heat_dates = [d for d in all_dates if d <= analysis_dates[-1]]
    snapshots = load_or_build_heat_snapshots(
        heat_dates,
        themes,
        max(15, args.active_top_k),
        args.min_member_count,
        args.max_member_count,
        MARKET_HEAT_DIR / "cache",
        use_cache=not args.no_heat_cache,
    )
    rank_history = build_rank_history(snapshots, heat_dates, max(15, args.active_top_k))
    heat_pos = {d: idx for idx, d in enumerate(heat_dates)}
    extras = load_atomic_extra(all_dates[0], latest_date)
    market = compute_market_returns(
        analysis_dates,
        trade_dates,
        price_rows,
        limit_rows,
        name_map,
        args.horizons,
        args.min_amount,
        args.min_history_days,
        exclude_unbuyable=True,
    )
    market_by_date = {d: market_regime(d, trade_dates, price_rows, limit_rows) for d in analysis_dates}

    sample_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for d in analysis_dates:
        i = date_index.get(d)
        if i is None or i < 60 or i + max(args.horizons) >= len(trade_dates) or d not in heat_pos:
            continue
        entry_date = trade_dates[i + 1]
        active = active_hot_themes(
            d,
            heat_dates,
            heat_pos,
            rank_history,
            snapshots,
            active_top_k=args.active_top_k,
            lookback=args.hot_lookback,
            min_hits=args.hot_min_hits,
            max_hits=args.hot_max_hits,
        )
        for theme in active:
            for symbol in theme_members.get(theme["id"], set()):
                rows = price_rows.get(symbol, {})
                if d not in rows or entry_date not in rows or trade_dates[i - 1] not in rows or trade_dates[i - 5] not in rows:
                    continue
                if not tradeable_on_d(symbol, d, entry_date, i, rows, first_idx, name_map, args.min_amount, args.min_history_days):
                    continue
                d_row = rows[d]
                y_row = rows[trade_dates[i - 1]]
                if is_unbuyable_limit_up(symbol, d_row, rows[entry_date], limit_rows, entry_date):
                    continue
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
                super_vals = [safe_float(extra_rows.get(td, {}).get("l2_super_net_amount")) for td in trade_dates[max(0, i - 2): i + 1]]
                super_days = sum(1 for v in super_vals if v > 0)
                tracking = _tracking_fields(rows, i, trade_dates, args.horizons)
                rec: Dict[str, Any] = {
                    "trade_date": d,
                    "symbol": symbol,
                    "name": name_map.get(symbol, symbol),
                    "theme_id": theme["id"],
                    "theme_name": theme["name"],
                    "theme_rank": int(theme["rank"]),
                    "theme_recent_hits": int(theme.get("recent_hits") or 0),
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
                    "l2_main_net_2d_yi": round((safe_float(d_row["l2_main_net_amount"]) + safe_float(y_row["l2_main_net_amount"])) / 1e8, 4),
                    "l2_super_net_3d_yi": round(sum(super_vals) / 1e8, 4),
                    "super_positive_days_3d": int(super_days),
                    "super_mode": args.super_mode,
                    **_entry_fields(symbol, rows, d_row, i, trade_dates, limit_rows),
                    **tracking,
                    "market_total_amount_yi": market_by_date[d]["total_amount_yi"],
                    "market_advancer_ratio": market_by_date[d]["advancer_ratio"],
                    "market_liquidity_label": market_by_date[d]["liquidity_label"],
                    "market_sentiment_label": market_by_date[d]["sentiment_label"],
                }
                rec["shadow_score"] = shadow_score(
                    {
                        **rec,
                        "entry": {
                            "unbuyable_limit_up_open": bool(rec["unbuyable_limit_up_open"]),
                        },
                    }
                )
                for h in args.horizons:
                    ret = rec.get(f"d{h}_return_pct")
                    stat = market.get(str(h), {})
                    rec[f"d{h}_alpha_pct"] = round(safe_float(ret) - safe_float(stat.get("avg")), 4) if ret is not None else None
                key = (d, symbol)
                old = sample_map.get(key)
                if old is None or (rec["theme_rank"], -rec["shadow_score"]) < (old["theme_rank"], -old["shadow_score"]):
                    sample_map[key] = rec

    samples = sorted(sample_map.values(), key=lambda r: (r["trade_date"], -safe_float(r.get("shadow_score")), r["symbol"]))
    summary = build_summary(samples, market, args)
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "strategy": "hot_theme_low_position_l2_shadow_v1",
            "start_date": start_date,
            "end_date": analysis_dates[-1],
            "latest_trade_date": latest_date,
            "days": args.days,
            "sample_count": len(samples),
            "horizons": args.horizons,
            "params": {
                "active_top_k": args.active_top_k,
                "hot_lookback": args.hot_lookback,
                "hot_min_hits": args.hot_min_hits,
                "hot_max_hits": args.hot_max_hits,
                "min_5d_return": args.min_5d_return,
                "max_5d_return": args.max_5d_return,
                "max_position_20d": args.max_position_20d,
                "max_ma60_abs": args.max_ma60_abs,
                "min_amount_ratio": args.min_amount_ratio,
                "max_amount_ratio": args.max_amount_ratio,
                "super_mode": args.super_mode,
            },
        },
        "market": market,
        "summary": summary,
        "samples": samples,
    }


def build_summary(samples: Sequence[Dict[str, Any]], market: Dict[str, Dict[str, Any]], args: argparse.Namespace) -> Dict[str, Any]:
    horizon_stats: Dict[str, Any] = {}
    for h in args.horizons:
        vals = [r.get(f"d{h}_return_pct") for r in samples if r.get(f"d{h}_return_pct") is not None]
        stat = summarize(vals)
        market_avg = safe_float(market.get(str(h), {}).get("avg"))
        stat["alpha"] = round(safe_float(stat["avg"]) - market_avg, 4)
        stat["market_avg"] = round(market_avg, 4)
        stat["market_win_rate"] = market.get(str(h), {}).get("win_rate", 0.0)
        horizon_stats[str(h)] = stat

    winners = [r for r in samples if safe_float(r.get("d5_return_pct")) >= 3]
    losers = [r for r in samples if safe_float(r.get("d5_return_pct")) <= -3]
    small = [r for r in samples if -3 < safe_float(r.get("d5_return_pct")) < 3]

    def group_stats(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "n": len(records),
            "avg_d5": _avg(records, "d5_return_pct"),
            "avg_d3": _avg(records, "d3_return_pct"),
            "d5_win_rate": round(sum(1 for r in records if safe_float(r.get("d5_return_pct")) > 0) / len(records), 4) if records else 0.0,
            "avg_open_gap": _avg(records, "open_gap_pct"),
            "fade_ratio": round(sum(1 for r in records if int(r.get("intraday_fade") or 0) == 1) / len(records), 4) if records else 0.0,
            "avg_amount_ratio": _avg(records, "amount_ratio_10d"),
            "avg_pos20": _avg(records, "position_20d"),
            "avg_ma60_abs": _avg(records, "ma60_distance_abs_pct"),
            "avg_super_3d_yi": _avg(records, "l2_super_net_3d_yi"),
            "avg_l2_main_2d_yi": _avg(records, "l2_main_net_2d_yi"),
            "avg_market_advancer_ratio": _avg(records, "market_advancer_ratio"),
        }

    theme_counts = Counter(r["theme_name"] for r in samples)
    month_counts = Counter(str(r["trade_date"])[:7] for r in samples)
    entry_bins = defaultdict(list)
    for r in samples:
        entry_bins[str(r.get("open_gap_bin") or "unknown")].append(r)
    amount_bins = {
        "0.5~0.8": [r for r in samples if 0.5 <= safe_float(r.get("amount_ratio_10d")) < 0.8],
        "0.8~1.0": [r for r in samples if 0.8 <= safe_float(r.get("amount_ratio_10d")) < 1.0],
        "1.0~1.2": [r for r in samples if 1.0 <= safe_float(r.get("amount_ratio_10d")) <= 1.2],
    }
    ma_bins = {
        "<=5%": [r for r in samples if safe_float(r.get("ma60_distance_abs_pct")) <= 5],
        "5~8%": [r for r in samples if 5 < safe_float(r.get("ma60_distance_abs_pct")) <= 8],
    }
    score_bins = {
        "score>=75": [r for r in samples if safe_float(r.get("shadow_score")) >= 75],
        "65<=score<75": [r for r in samples if 65 <= safe_float(r.get("shadow_score")) < 75],
        "score<65": [r for r in samples if safe_float(r.get("shadow_score")) < 65],
    }
    fade_bins = {
        "d1_no_fade": [r for r in samples if int(r.get("intraday_fade") or 0) == 0],
        "d1_fade": [r for r in samples if int(r.get("intraday_fade") or 0) == 1],
    }

    return {
        "horizon_stats": horizon_stats,
        "groups": {
            "d5_winner_ge3": group_stats(winners),
            "d5_loser_le_minus3": group_stats(losers),
            "d5_middle": group_stats(small),
        },
        "entry_gap_bins": {k: group_stats(v) for k, v in sorted(entry_bins.items())},
        "amount_ratio_bins": {k: group_stats(v) for k, v in amount_bins.items()},
        "ma60_abs_bins": {k: group_stats(v) for k, v in ma_bins.items()},
        "score_bins": {k: group_stats(v) for k, v in score_bins.items()},
        "d1_fade_bins": {k: group_stats(v) for k, v in fade_bins.items()},
        "correlations_to_d5": {
            "open_gap_pct": _corr(samples, "open_gap_pct", "d5_return_pct"),
            "amount_ratio_10d": _corr(samples, "amount_ratio_10d", "d5_return_pct"),
            "position_20d": _corr(samples, "position_20d", "d5_return_pct"),
            "ma60_distance_abs_pct": _corr(samples, "ma60_distance_abs_pct", "d5_return_pct"),
            "l2_super_net_3d_yi": _corr(samples, "l2_super_net_3d_yi", "d5_return_pct"),
            "l2_main_net_2d_yi": _corr(samples, "l2_main_net_2d_yi", "d5_return_pct"),
            "market_advancer_ratio": _corr(samples, "market_advancer_ratio", "d5_return_pct"),
            "shadow_score": _corr(samples, "shadow_score", "d5_return_pct"),
        },
        "top_themes": theme_counts.most_common(20),
        "month_counts": sorted(month_counts.items()),
        "top_winners_d5": sorted(samples, key=lambda r: safe_float(r.get("d5_return_pct")), reverse=True)[:20],
        "top_losers_d5": sorted(samples, key=lambda r: safe_float(r.get("d5_return_pct")))[:20],
    }


def save_report(report: Dict[str, Any], output_db: Path) -> Dict[str, Path]:
    ensure_market_heat_dir()
    output_db.parent.mkdir(parents=True, exist_ok=True)
    samples = report["samples"]
    meta = report["meta"]
    start, end = meta["start_date"], meta["end_date"]
    json_path = output_db.with_suffix(".json")
    csv_path = output_db.with_name(f"hot_theme_low_position_l2_samples_{start}_{end}.csv")
    md_path = output_db.with_name(f"hot_theme_low_position_l2_samples_{start}_{end}_summary.md")

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if samples:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(samples[0].keys()))
            writer.writeheader()
            writer.writerows(samples)

    with sqlite3.connect(str(output_db), timeout=60) as conn:
        conn.execute("DROP TABLE IF EXISTS samples")
        conn.execute("DROP TABLE IF EXISTS meta")
        conn.execute("DROP TABLE IF EXISTS summary_json")
        conn.execute(
            """
            CREATE TABLE samples (
              trade_date TEXT NOT NULL,
              symbol TEXT NOT NULL,
              name TEXT,
              theme_id TEXT,
              theme_name TEXT,
              theme_rank INTEGER,
              theme_recent_hits INTEGER,
              close REAL,
              day_return_pct REAL,
              return_5d_pct REAL,
              position_20d REAL,
              ma60_distance_pct REAL,
              ma60_distance_abs_pct REAL,
              ma_stickiness_pct REAL,
              amount_yi REAL,
              amount_ratio_10d REAL,
              l2_main_net_today_yi REAL,
              l2_main_net_yday_yi REAL,
              l2_main_net_2d_yi REAL,
              l2_super_net_3d_yi REAL,
              super_positive_days_3d INTEGER,
              super_mode TEXT,
              entry_date TEXT,
              entry_open REAL,
              open_gap_pct REAL,
              open_gap_bin TEXT,
              unbuyable_limit_up_open INTEGER,
              intraday_fade INTEGER,
              fade_ratio REAL,
              entry_label TEXT,
              d1_return_pct REAL,
              d1_exit_date TEXT,
              d1_outcome TEXT,
              d3_return_pct REAL,
              d3_exit_date TEXT,
              d3_outcome TEXT,
              d5_return_pct REAL,
              d5_exit_date TEXT,
              d5_outcome TEXT,
              market_total_amount_yi REAL,
              market_advancer_ratio REAL,
              market_liquidity_label TEXT,
              market_sentiment_label TEXT,
              shadow_score REAL,
              d1_alpha_pct REAL,
              d3_alpha_pct REAL,
              d5_alpha_pct REAL,
              PRIMARY KEY (trade_date, symbol)
            )
            """
        )
        if samples:
            keys = list(samples[0].keys())
            placeholders = ",".join("?" for _ in keys)
            conn.executemany(
                f"INSERT OR REPLACE INTO samples ({','.join(keys)}) VALUES ({placeholders})",
                [[row.get(k) for k in keys] for row in samples],
            )
        conn.execute("CREATE INDEX idx_samples_trade_date ON samples(trade_date)")
        conn.execute("CREATE INDEX idx_samples_theme ON samples(theme_name)")
        conn.execute("CREATE INDEX idx_samples_d5 ON samples(d5_return_pct)")
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        for key, value in meta.items():
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, json.dumps(value, ensure_ascii=False)))
        conn.execute("CREATE TABLE summary_json (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        conn.execute("INSERT INTO summary_json(id, payload) VALUES(1, ?)", (json.dumps(report["summary"], ensure_ascii=False),))
        conn.commit()

    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"db": output_db, "json": json_path, "csv": csv_path, "md": md_path}


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    summary = report["summary"]
    lines = [
        f"# 热点低位 L2 补涨历史命中样本分析 {meta['start_date']} ~ {meta['end_date']}",
        "",
        "## 结论",
        "",
        f"- 严格主口径历史命中 {meta['sample_count']} 只次，频率不高，符合“稀缺机会池”的定位。",
    ]
    for h, stat in summary["horizon_stats"].items():
        lines.append(f"- D+{h}: 样本 {stat['n']}，均值 {stat['avg']:.2f}%，Alpha {stat['alpha']:.2f}%，胜率 {stat['win_rate']:.1%}。")
    lines += [
        "- 这个策略目前最像“热点扩散低位埋伏池”，不是每天必须出手的策略。",
        "",
        "## 赢家/输家画像（按 D+5）",
        "",
    ]
    for key, label in [
        ("d5_winner_ge3", "赢家 >= +3%"),
        ("d5_loser_le_minus3", "输家 <= -3%"),
        ("d5_middle", "中间样本"),
    ]:
        g = summary["groups"][key]
        lines.append(
            f"- {label}: n={g['n']}，D+5均值 {g['avg_d5']}%，开盘缺口 {g['avg_open_gap']}%，"
            f"量能比 {g['avg_amount_ratio']}，20日位置 {g['avg_pos20']}，60日乖离 {g['avg_ma60_abs']}%，"
            f"超大单3日 {g['avg_super_3d_yi']}亿，冲高回落率 {g['fade_ratio']:.1%}。"
        )
    lines += [
        "",
        "## 分组",
        "",
        "### D+1 开盘缺口",
    ]
    for label, g in summary["entry_gap_bins"].items():
        lines.append(f"- {label}: n={g['n']}，D+5均值 {g['avg_d5']}%，胜负观察优先看这个分组是否持续稳定。")
    lines += ["", "### 量能比"]
    for label, g in summary["amount_ratio_bins"].items():
        lines.append(f"- {label}: n={g['n']}，D+5均值 {g['avg_d5']}%。")
    lines += ["", "### 60日乖离"]
    for label, g in summary["ma60_abs_bins"].items():
        lines.append(f"- {label}: n={g['n']}，D+5均值 {g['avg_d5']}%。")
    lines += ["", "### D+1 冲高回落"]
    for label, g in summary.get("d1_fade_bins", {}).items():
        lines.append(f"- {label}: n={g['n']}，D+5均值 {g['avg_d5']}%，D+5胜率 {g.get('d5_win_rate', 0):.1%}。")
    lines += [
        "",
        "## D+5 最大赢家",
        "",
        "| 日期 | 股票 | 板块 | D+5 | D+3 | 开盘缺口 | 量能比 | 超大单3日 |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in summary["top_winners_d5"][:15]:
        lines.append(
            f"| {r['trade_date']} | {r['symbol']} {r['name']} | {r['theme_name']} | {safe_float(r.get('d5_return_pct')):.2f}% | "
            f"{safe_float(r.get('d3_return_pct')):.2f}% | {safe_float(r.get('open_gap_pct')):.2f}% | {safe_float(r.get('amount_ratio_10d')):.2f} | {safe_float(r.get('l2_super_net_3d_yi')):.2f} |"
        )
    lines += [
        "",
        "## D+5 最大输家",
        "",
        "| 日期 | 股票 | 板块 | D+5 | D+3 | 开盘缺口 | 量能比 | 超大单3日 |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in summary["top_losers_d5"][:15]:
        lines.append(
            f"| {r['trade_date']} | {r['symbol']} {r['name']} | {r['theme_name']} | {safe_float(r.get('d5_return_pct')):.2f}% | "
            f"{safe_float(r.get('d3_return_pct')):.2f}% | {safe_float(r.get('open_gap_pct')):.2f}% | {safe_float(r.get('amount_ratio_10d')):.2f} | {safe_float(r.get('l2_super_net_3d_yi')):.2f} |"
        )
    lines += [
        "",
        "## 高频主题",
        "",
    ]
    for name, count in summary["top_themes"][:20]:
        lines.append(f"- {name}: {count}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export all historical hits for hot-theme low-position L2 strategy.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--horizons", default="1,3,5")
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
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--no-heat-cache", action="store_true")
    parser.add_argument("--output-db", default=str(DEFAULT_OUTPUT_DB))
    args = parser.parse_args()
    args.horizons = sorted({int(x.strip()) for x in str(args.horizons).split(",") if x.strip()})
    return args


def main() -> None:
    args = parse_args()
    report = generate_samples(args)
    paths = save_report(report, Path(args.output_db))
    print(f"wrote {paths['db']}")
    print(f"wrote {paths['json']}")
    print(f"wrote {paths['csv']}")
    print(f"wrote {paths['md']}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
