#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

from backend.app.core.config import DATA_DIR
from backend.app.services.market_heat import MARKET_HEAT_DIR, _trade_dates, ensure_market_heat_dir
from backend.scripts.analyze_hot_sector_granularity import DEFAULT_FINE_RULES, load_fine_sector_themes, load_json
from backend.scripts.analyze_hot_theme_low_position_l2_strategy import (
    active_hot_themes,
    amount_bin,
    position_20d,
    prior_avg_amount,
)
from backend.scripts.analyze_hot_theme_winner_lead_lag import (
    ATOMIC_DB,
    DEFAULT_STOCK_SECTOR_DB,
    DEFAULT_TRADABLE_THEME_DB,
    forward_return,
    load_extra_names,
    load_price_and_limit_rows,
    safe_float,
    summarize,
)
from backend.scripts.analyze_new_theme_leader_strategy import new_hot_themes, open_gap_bin
from backend.scripts.analyze_strategy_theme_lifecycle import build_rank_history
from backend.scripts.analyze_strategy_theme_resonance import (
    DEFAULT_SELECTION_DB,
    compute_market_returns,
    first_indexes,
    is_valid_tradeable,
    load_or_build_heat_snapshots,
)


def pct_change(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def load_selection_feature_map(selection_db: Path, start_date: str, end_date: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if not selection_db.exists():
        return {}
    sql = """
        SELECT f.symbol, f.trade_date,
               f.net_inflow_10d, f.net_inflow_20d,
               f.positive_inflow_ratio_10d, f.positive_inflow_ratio_20d,
               f.main_activity_20d, f.activity_ratio_20d,
               f.l1_main_net_3d, f.l2_main_net_3d, f.l2_vs_l1_strength,
               f.l2_order_event_available,
               f.l2_add_buy_3d, f.l2_add_sell_3d,
               f.l2_cancel_buy_3d, f.l2_cancel_sell_3d,
               f.l2_cvd_3d, f.l2_oib_3d,
               max(s.stealth_signal) AS stealth_signal,
               max(s.confirm_signal) AS breakout_signal,
               max(s.stealth_score) AS stealth_score
        FROM selection_feature_daily f
        LEFT JOIN selection_signal_daily s
          ON s.symbol = f.symbol
         AND s.trade_date = f.trade_date
         AND s.feature_version = f.feature_version
        WHERE f.trade_date >= ? AND f.trade_date <= ?
        GROUP BY f.symbol, f.trade_date
    """
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    with sqlite3.connect(str(selection_db), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(sql, (start_date, end_date)):
            out[(str(row["symbol"]).lower(), str(row["trade_date"]))] = dict(row)
    return out


def load_atomic_extra(start_date: str, end_date: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    out: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    with sqlite3.connect(str(ATOMIC_DB), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            """
            SELECT symbol, trade_date,
                   l2_super_net_amount, l2_main_buy_amount, l2_main_sell_amount,
                   l2_super_buy_amount, l2_super_sell_amount,
                   l2_buy_ratio, l2_sell_ratio, l2_activity_ratio,
                   positive_l2_net_bar_count, negative_l2_net_bar_count,
                   open_30m_l2_main_net_amount, last_30m_l2_main_net_amount
            FROM atomic_trade_daily
            WHERE trade_date >= ? AND trade_date <= ?
            """,
            (start_date, end_date),
        ):
            out[str(row["symbol"]).lower()][str(row["trade_date"])] = dict(row)
    return dict(out)


def rolling_sum(extra_rows: Dict[str, Dict[str, Any]], trade_dates: Sequence[str], i: int, field: str, lookback: int) -> float:
    total = 0.0
    for d in trade_dates[max(0, i - lookback + 1):i + 1]:
        total += safe_float(extra_rows.get(d, {}).get(field))
    return total


def positive_day_ratio(extra_rows: Dict[str, Dict[str, Any]], trade_dates: Sequence[str], i: int, field: str, lookback: int) -> float:
    vals = []
    for d in trade_dates[max(0, i - lookback + 1):i + 1]:
        if d in extra_rows:
            vals.append(1 if safe_float(extra_rows[d].get(field)) > 0 else 0)
    return sum(vals) / len(vals) if vals else 0.0


def funding_tags(symbol: str, d: str, i: int, trade_dates: Sequence[str], features: Dict[Tuple[str, str], Dict[str, Any]], extras: Dict[str, Dict[str, Dict[str, Any]]]) -> List[str]:
    feat = features.get((symbol, d), {})
    erows = extras.get(symbol, {})
    today_extra = erows.get(d, {})
    yday_extra = erows.get(trade_dates[i - 1], {}) if i > 0 else {}

    tags = ["all"]
    if int(feat.get("stealth_signal") or 0) == 1:
        tags.append("old_stealth_signal")
    if safe_float(feat.get("stealth_score")) >= 60:
        tags.append("old_stealth_score60")

    # Legacy medium-term accumulation: persistent net inflow + enough activity.
    main_activity = safe_float(feat.get("main_activity_20d"))
    net20 = safe_float(feat.get("net_inflow_20d"))
    pos10 = safe_float(feat.get("positive_inflow_ratio_10d"))
    inflow_ratio20 = net20 / (abs(main_activity) + 1.0)
    if pos10 >= 0.60 and net20 > 0 and inflow_ratio20 >= 0.03:
        tags.append("legacy_inflow_accum")

    # Short-term L2 confirmation from existing selection feature layer.
    if safe_float(feat.get("l2_main_net_3d")) > 0 and safe_float(feat.get("l2_vs_l1_strength")) >= 0.20:
        tags.append("l2_3d_confirm")

    # Super-large order accumulation from atomic facts.
    super_3d = rolling_sum(erows, trade_dates, i, "l2_super_net_amount", 3)
    super_pos_ratio_3d = positive_day_ratio(erows, trade_dates, i, "l2_super_net_amount", 3)
    if super_3d > 0 and super_pos_ratio_3d >= 2 / 3:
        tags.append("super_3d_accum")
    if safe_float(today_extra.get("l2_super_net_amount")) > 0 and safe_float(yday_extra.get("l2_super_net_amount")) > 0:
        tags.append("super_2d_continuous")

    # Intraday bar consistency: more positive L2 bars than negative bars.
    pos_bars = safe_float(today_extra.get("positive_l2_net_bar_count"))
    neg_bars = safe_float(today_extra.get("negative_l2_net_bar_count"))
    if pos_bars + neg_bars > 0 and pos_bars / (pos_bars + neg_bars) >= 0.60:
        tags.append("intraday_l2_bar_consistency")

    # Order-book style support, only when selection layer says order event is available.
    if int(feat.get("l2_order_event_available") or 0) == 1:
        if safe_float(feat.get("l2_cvd_3d")) > 0 and safe_float(feat.get("l2_oib_3d")) > 0:
            tags.append("order_cvd_oib_positive")
        if safe_float(feat.get("l2_add_buy_3d")) > safe_float(feat.get("l2_add_sell_3d")):
            tags.append("order_add_buy_dominant")
        if (
            safe_float(feat.get("l2_cvd_3d")) > 0
            and safe_float(feat.get("l2_oib_3d")) > 0
            and safe_float(feat.get("l2_add_buy_3d")) > safe_float(feat.get("l2_add_sell_3d"))
        ):
            tags.append("orderbook_accum")

    # Strong combined version, intentionally strict.
    if "legacy_inflow_accum" in tags and "super_3d_accum" in tags:
        tags.append("legacy_plus_super")
    if "l2_3d_confirm" in tags and "intraday_l2_bar_consistency" in tags:
        tags.append("l2_confirm_plus_bar")
    if "legacy_inflow_accum" in tags and "l2_3d_confirm" in tags and ("super_3d_accum" in tags or "orderbook_accum" in tags):
        tags.append("strong_accum_combo")
    return tags


def add_intersection_tags(base_tags: List[str], context_tags: List[str]) -> List[str]:
    tags = list(base_tags) + list(context_tags)
    tagset = set(tags)
    if "amount_shrink_or_normal" in tagset:
        for t in [
            "legacy_inflow_accum",
            "l2_3d_confirm",
            "super_3d_accum",
            "super_2d_continuous",
            "legacy_plus_super",
            "strong_accum_combo",
        ]:
            if t in tagset:
                tags.append(f"shrink_normal+{t}")
    if "gap_<=0" in tagset:
        for t in [
            "old_stealth_score60",
            "legacy_inflow_accum",
            "l2_3d_confirm",
            "super_3d_accum",
            "legacy_plus_super",
            "strong_accum_combo",
        ]:
            if t in tagset:
                tags.append(f"gap_le0+{t}")
    if ("gap_<=0" in tagset or "gap_0_2" in tagset) and "legacy_inflow_accum" in tagset:
        tags.append("gap_le2+legacy_inflow_accum")
    return tags


def add_return(bucket: Dict[str, Dict[str, List[Dict[str, Any]]]], strategy: str, group: str, ret: float) -> None:
    bucket[strategy][group].append({"ret": ret})


def summarize_groups(groups: Dict[str, List[Dict[str, Any]]], market_avg: float) -> Dict[str, Any]:
    order = [
        "all", "old_stealth_signal", "old_stealth_score60", "legacy_inflow_accum", "l2_3d_confirm",
        "super_3d_accum", "super_2d_continuous", "intraday_l2_bar_consistency",
        "order_cvd_oib_positive", "order_add_buy_dominant", "orderbook_accum",
        "legacy_plus_super", "l2_confirm_plus_bar", "strong_accum_combo",
        "amount_shrink_or_normal", "amount_expand", "gap_<=0", "gap_0_2", "gap_2_5", "gap_5_8", "gap_>8",
        "shrink_normal+legacy_inflow_accum", "shrink_normal+l2_3d_confirm", "shrink_normal+super_3d_accum",
        "shrink_normal+super_2d_continuous", "shrink_normal+legacy_plus_super", "shrink_normal+strong_accum_combo",
        "gap_le0+old_stealth_score60", "gap_le0+legacy_inflow_accum", "gap_le0+l2_3d_confirm",
        "gap_le0+super_3d_accum", "gap_le0+legacy_plus_super", "gap_le0+strong_accum_combo",
        "gap_le2+legacy_inflow_accum",
    ]
    out = {}
    for group in order:
        vals = [x["ret"] for x in groups.get(group, [])]
        stat = summarize(vals)
        stat["alpha"] = round(stat["avg"] - market_avg, 4)
        out[group] = stat
    return out


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 热点策略 x 资金埋伏交叉验证 {meta['start_date']} ~ {meta['end_date']}",
        "",
        "这份验证回答：已有 L2/主力埋伏资金标签，能不能把热点策略里的真假机会切开。",
        "",
    ]
    for strategy, by_h in report["summary"].items():
        lines += [f"## {strategy}", ""]
        for hkey, groups in by_h.items():
            market = report["market"].get(hkey, {})
            lines += [f"### D+{hkey}，市场均值 {market.get('avg', 0):.2f}%", "", "| 资金/约束标签 | 样本 | 均值 | Alpha | 胜率 |", "|---|---:|---:|---:|---:|"]
            for group, stat in groups.items():
                if stat["n"] == 0:
                    continue
                lines.append(f"| {group} | {stat['n']} | {stat['avg']:.2f}% | {stat['alpha']:.2f}% | {stat['win_rate']:.1%} |")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross validate hot theme strategies with existing L2 accumulation / stealth funding tags.")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--horizons", default="1,3,5")
    parser.add_argument("--min-amount", type=float, default=30_000_000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--min-member-count", type=int, default=5)
    parser.add_argument("--max-member-count", type=int, default=80)
    parser.add_argument("--include-unbuyable", action="store_true")
    parser.add_argument("--selection-db", default=str(DEFAULT_SELECTION_DB))
    parser.add_argument("--tradable-theme-db", default=str(DEFAULT_TRADABLE_THEME_DB))
    parser.add_argument("--stock-sector-db", default=str(DEFAULT_STOCK_SECTOR_DB))
    parser.add_argument("--fine-rules", default=str(DEFAULT_FINE_RULES))
    parser.add_argument("--no-heat-cache", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    horizons = sorted({int(x.strip()) for x in args.horizons.split(",") if x.strip()})
    end_date = args.end_date or _trade_dates("9999-12-31", 1)[-1]
    all_dates = _trade_dates(end_date, args.days + args.min_history_days + max(horizons) + 60)
    analysis_dates = [d for d in all_dates if d <= end_date][-args.days:]
    trade_dates, price_rows, limit_rows = load_price_and_limit_rows(all_dates[0], end_date)
    date_index = {d: idx for idx, d in enumerate(trade_dates)}
    first_idx = first_indexes(price_rows, date_index)

    rules = load_json(Path(args.fine_rules))
    themes, theme_members, _symbol_themes, name_map = load_fine_sector_themes(Path(args.tradable_theme_db), rules, args.min_member_count, args.max_member_count)
    name_map.update({k: v for k, v in load_extra_names(Path(args.stock_sector_db)).items() if k not in name_map})

    heat_dates = [d for d in all_dates if d <= analysis_dates[-1]]
    snapshots = load_or_build_heat_snapshots(heat_dates, themes, 20, args.min_member_count, args.max_member_count, MARKET_HEAT_DIR / "cache", use_cache=not args.no_heat_cache)
    rank_history = build_rank_history(snapshots, heat_dates, 20)
    heat_pos = {d: idx for idx, d in enumerate(heat_dates)}
    market = compute_market_returns(analysis_dates, trade_dates, price_rows, limit_rows, name_map, horizons, args.min_amount, args.min_history_days, exclude_unbuyable=not args.include_unbuyable)
    features = load_selection_feature_map(Path(args.selection_db), all_dates[0], analysis_dates[-1])
    extras = load_atomic_extra(all_dates[0], analysis_dates[-1])

    returns: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    seen_low: Dict[Tuple[str, str], set] = defaultdict(set)
    seen_new: Dict[Tuple[str, str], set] = defaultdict(set)

    for d in analysis_dates:
        i = date_index.get(d)
        if i is None or i + max(horizons) >= len(trade_dates) or i < 10 or d not in heat_pos:
            continue
        entry_date = trade_dates[i + 1]

        # Strategy A: continuing hot theme low-position L2 accumulation.
        active = active_hot_themes(d, heat_dates, heat_pos, rank_history, snapshots, active_top_k=10, lookback=5, min_hits=2, max_hits=3)
        low_candidates: Dict[str, Dict[str, Any]] = {}
        for theme in active:
            for symbol in theme_members.get(theme["id"], set()):
                rows = price_rows.get(symbol, {})
                if d not in rows or entry_date not in rows or trade_dates[i - 1] not in rows or trade_dates[i - 5] not in rows:
                    continue
                if not is_valid_tradeable(symbol, d, entry_date, i, rows, first_idx, limit_rows, name_map, args.min_amount, args.min_history_days, not args.include_unbuyable):
                    continue
                ret5 = pct_change(safe_float(rows[d]["close"]), safe_float(rows[trade_dates[i - 5]]["close"]))
                pos20 = position_20d(rows, trade_dates, i)
                avg10 = prior_avg_amount(rows, trade_dates, i, 10)
                if ret5 is None or pos20 is None or avg10 is None or avg10 <= 0:
                    continue
                if not (-8.0 <= ret5 < 5.0 and pos20 <= 0.65):
                    continue
                if safe_float(rows[d]["l2_main_net_amount"]) <= 0 or safe_float(rows[trade_dates[i - 1]]["l2_main_net_amount"]) <= 0:
                    continue
                amount_ratio = safe_float(rows[d]["total_amount"]) / avg10
                rec = {"symbol": symbol, "amount_bin": amount_bin(amount_ratio), "theme_rank": theme["rank"]}
                old = low_candidates.get(symbol)
                if old is None or rec["theme_rank"] < old["theme_rank"]:
                    low_candidates[symbol] = rec
        for symbol, rec in low_candidates.items():
            rows = price_rows[symbol]
            tags = funding_tags(symbol, d, i, trade_dates, features, extras)
            context_tags = ["amount_shrink_or_normal" if rec["amount_bin"] != "expand_>1.2" else "amount_expand"]
            tags = add_intersection_tags(tags, context_tags)
            for h in horizons:
                exit_date = trade_dates[i + h]
                if exit_date not in rows:
                    continue
                ret = forward_return(rows[entry_date], rows[exit_date])
                if ret is None or symbol in seen_low[(str(h), d)]:
                    continue
                seen_low[(str(h), d)].add(symbol)
                for tag in set(tags):
                    returns["low_position_l2"][str(h)][tag].append({"ret": ret})

        # Strategy B: new theme leader, use L2 amount top3 as main variant.
        new_themes = new_hot_themes(d, heat_dates, heat_pos, rank_history, snapshots, new_rank_k=5, new_lookback=10, new_prev_top_k=20)
        for theme in new_themes:
            pool = []
            for symbol in theme_members.get(theme["id"], set()):
                rows = price_rows.get(symbol, {})
                if d not in rows or entry_date not in rows or trade_dates[i - 1] not in rows:
                    continue
                if not is_valid_tradeable(symbol, d, entry_date, i, rows, first_idx, limit_rows, name_map, args.min_amount, args.min_history_days, not args.include_unbuyable):
                    continue
                day_ret = pct_change(safe_float(rows[d]["close"]), safe_float(rows[trade_dates[i - 1]]["close"]))
                if day_ret is None or day_ret <= 0 or safe_float(rows[d]["close"]) < safe_float(rows[d]["open"]):
                    continue
                pool.append({"symbol": symbol, "l2_amount": safe_float(rows[d]["l2_main_net_amount"]), "theme_rank": theme["rank"]})
            for cand in sorted(pool, key=lambda x: x["l2_amount"], reverse=True)[:3]:
                symbol = cand["symbol"]
                rows = price_rows[symbol]
                gap = pct_change(safe_float(rows[entry_date]["open"]), safe_float(rows[d]["close"])) or 0.0
                tags = funding_tags(symbol, d, i, trade_dates, features, extras)
                tags = add_intersection_tags(tags, [open_gap_bin(gap)])
                for h in [x for x in horizons if x <= 3]:
                    exit_date = trade_dates[i + h]
                    if exit_date not in rows:
                        continue
                    ret = forward_return(rows[entry_date], rows[exit_date])
                    if ret is None or symbol in seen_new[(str(h), d)]:
                        continue
                    seen_new[(str(h), d)].add(symbol)
                    for tag in set(tags):
                        returns["new_theme_l2_amount_top3"][str(h)][tag].append({"ret": ret})

    summary: Dict[str, Dict[str, Any]] = {}
    for strategy, by_h in returns.items():
        summary[strategy] = {}
        for hkey, groups in by_h.items():
            summary[strategy][hkey] = summarize_groups(groups, market[hkey]["avg"])

    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_date": analysis_dates[0],
            "end_date": analysis_dates[-1],
            "analysis_days": len(analysis_dates),
        },
        "market": market,
        "summary": summary,
    }
    ensure_market_heat_dir()
    out_path = Path(args.output) if args.output else MARKET_HEAT_DIR / f"hot_theme_funding_cross_validation_{analysis_dates[0]}_{analysis_dates[-1]}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
