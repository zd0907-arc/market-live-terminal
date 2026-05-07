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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import ATOMIC_DB, MARKET_HEAT_DIR, ensure_market_heat_dir

DEFAULT_SAMPLE_DB = MARKET_HEAT_DIR / "hot_theme_low_position_l2_samples.db"


def sf(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def stat(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    vals = sorted(sf(v) for v in values if v is not None)
    if not vals:
        return {"n": 0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "p25": 0.0, "p75": 0.0, "worst": 0.0, "best": 0.0}
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 4),
        "median": round(statistics.median(vals), 4),
        "win_rate": round(sum(1 for v in vals if v > 0) / len(vals), 4),
        "p25": round(vals[int((len(vals) - 1) * 0.25)], 4),
        "p75": round(vals[int((len(vals) - 1) * 0.75)], 4),
        "worst": round(vals[0], 4),
        "best": round(vals[-1], 4),
    }


def pct(numer: float, denom: float) -> Optional[float]:
    if denom <= 0:
        return None
    return (numer / denom - 1) * 100


def load_rank_cache() -> Dict[str, Dict[str, int]]:
    cache_dir = MARKET_HEAT_DIR / "cache"
    candidates = sorted(cache_dir.glob("fine_heat_snapshots_*_m5_80.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshots = payload.get("snapshots") or {}
        if len(snapshots) >= 200:
            return {
                str(date): {str(item.get("id")): idx + 1 for idx, item in enumerate((snapshot.get("hot_top") or [])[:80])}
                for date, snapshot in snapshots.items()
            }
    return {}


def load_inputs(sample_db: Path) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Dict[str, Dict[str, Any]]]]:
    with sqlite3.connect(str(sample_db), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        samples = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM samples
                WHERE intraday_fade = 0
                  AND d1_return_pct <= 2
                ORDER BY trade_date, symbol
                """
            )
        ]
    symbols = sorted({str(row["symbol"]) for row in samples})
    if not symbols:
        return samples, [], {}
    placeholders = ",".join("?" for _ in symbols)
    with sqlite3.connect(str(ATOMIC_DB), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        dates = [str(row[0]) for row in conn.execute("SELECT DISTINCT trade_date FROM atomic_trade_daily ORDER BY trade_date")]
        by_symbol: Dict[str, Dict[str, Dict[str, Any]]] = {symbol: {} for symbol in symbols}
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


def rows_between(dates: Sequence[str], rows: Dict[str, Dict[str, Any]], start_idx: int, end_idx: int) -> List[Dict[str, Any]]:
    out = []
    for j in range(start_idx, min(end_idx + 1, len(dates))):
        row = rows.get(dates[j])
        if row:
            out.append(row)
    return out


def enrich_sample(
    sample: Dict[str, Any],
    dates: Sequence[str],
    date_index: Dict[str, int],
    by_symbol: Dict[str, Dict[str, Dict[str, Any]]],
    rank_by_date: Dict[str, Dict[str, int]],
) -> Optional[Dict[str, Any]]:
    d = str(sample["trade_date"])
    symbol = str(sample["symbol"])
    i = date_index.get(d)
    rows = by_symbol.get(symbol, {})
    if i is None or i + 1 >= len(dates):
        return None
    entry_date = dates[i + 1]
    entry = rows.get(entry_date)
    if not entry or sf(entry.get("close")) <= 0:
        return None
    entry_close = sf(entry["close"])
    out = dict(sample)
    out.update({"entry_date": entry_date, "entry_close": entry_close})

    for h in [2, 3, 5, 10, 20]:
        idx = i + h
        row = rows.get(dates[idx]) if idx < len(dates) else None
        out[f"d{h}_close_tail_ret"] = pct(sf(row["close"]), entry_close) if row else None

    for h in [5, 10, 20]:
        future = rows_between(dates, rows, i + 2, i + h)
        out[f"mfe{h}_tail"] = pct(max(sf(r["high"]) for r in future), entry_close) if future else None
        out[f"mae{h}_tail"] = pct(min(sf(r["low"]) for r in future), entry_close) if future else None

    for label, start_h, end_h in [("d1_d3", 1, 3), ("d1_d5", 1, 5), ("d2_d3", 2, 3), ("d2_d5", 2, 5)]:
        period = rows_between(dates, rows, i + start_h, i + end_h)
        out[f"l2_main_sum_{label}_yi"] = round(sum(sf(r.get("l2_main_net_amount")) for r in period) / 100_000_000, 4)
        out[f"l2_super_sum_{label}_yi"] = round(sum(sf(r.get("l2_super_net_amount")) for r in period) / 100_000_000, 4)
        out[f"l2_super_positive_days_{label}"] = sum(1 for r in period if sf(r.get("l2_super_net_amount")) > 0)

    theme_id = str(sample.get("theme_id") or "")
    for label, start_h, end_h in [("d1_d3", 1, 3), ("d1_d5", 1, 5)]:
        hits = 0
        best_rank = 999
        ranks: List[int] = []
        for j in range(i + start_h, min(i + end_h + 1, len(dates))):
            rank = rank_by_date.get(dates[j], {}).get(theme_id, 999)
            ranks.append(rank)
            best_rank = min(best_rank, rank)
            if rank <= 15:
                hits += 1
        out[f"theme_top15_hits_{label}"] = hits
        out[f"theme_best_rank_{label}"] = best_rank if best_rank < 999 else None
        out[f"theme_ranks_{label}"] = ranks

    mfe20 = out.get("mfe20_tail")
    if mfe20 is None:
        out["winner_bucket"] = "insufficient"
    elif mfe20 >= 10:
        out["winner_bucket"] = "big_mfe20_ge_10"
    elif mfe20 >= 5:
        out["winner_bucket"] = "mid_mfe20_5_10"
    else:
        out["winner_bucket"] = "small_mfe20_lt_5"
    return out


def summarize_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "n": len(rows),
        "mfe20": stat([r.get("mfe20_tail") for r in rows]),
        "d3_close": stat([r.get("d3_close_tail_ret") for r in rows]),
        "d5_close": stat([r.get("d5_close_tail_ret") for r in rows]),
        "d10_close": stat([r.get("d10_close_tail_ret") for r in rows]),
        "d20_close": stat([r.get("d20_close_tail_ret") for r in rows]),
        "d1_gain": stat([r.get("d1_return_pct") for r in rows]),
        "theme_hits_d1_d3_avg": round(sum(sf(r.get("theme_top15_hits_d1_d3")) for r in rows) / len(rows), 4) if rows else 0.0,
        "theme_hits_d1_d5_avg": round(sum(sf(r.get("theme_top15_hits_d1_d5")) for r in rows) / len(rows), 4) if rows else 0.0,
        "l2_main_d2_d3_yi": stat([r.get("l2_main_sum_d2_d3_yi") for r in rows]),
        "l2_super_d2_d3_yi": stat([r.get("l2_super_sum_d2_d3_yi") for r in rows]),
        "amount_ratio_10d": stat([r.get("amount_ratio_10d") for r in rows]),
        "ma60_distance_abs_pct": stat([r.get("ma60_distance_abs_pct") for r in rows]),
        "position_20d": stat([r.get("position_20d") for r in rows]),
    }


def condition_report(rows: Sequence[Dict[str, Any]], cond: Any) -> Dict[str, Any]:
    group = [r for r in rows if cond(r)]
    return {
        "n": len(group),
        "coverage": round(len(group) / len(rows), 4) if rows else 0.0,
        "big_rate": round(sum(1 for r in group if sf(r.get("mfe20_tail")) >= 10) / len(group), 4) if group else 0.0,
        "mfe20": stat([r.get("mfe20_tail") for r in group]),
        "d20_close": stat([r.get("d20_close_tail_ret") for r in group]),
        "examples": [
            {
                "trade_date": r["trade_date"],
                "symbol": r["symbol"],
                "name": r.get("name"),
                "theme_name": r.get("theme_name"),
                "d3_close_tail_ret": round(sf(r.get("d3_close_tail_ret")), 2),
                "theme_hits_d1_d3": r.get("theme_top15_hits_d1_d3"),
                "mfe20_tail": round(sf(r.get("mfe20_tail")), 2),
            }
            for r in sorted(group, key=lambda x: sf(x.get("mfe20_tail")), reverse=True)[:8]
        ],
    }


def build_report(sample_db: Path) -> Dict[str, Any]:
    samples, dates, by_symbol = load_inputs(sample_db)
    date_index = {d: i for i, d in enumerate(dates)}
    rank_by_date = load_rank_cache()
    enriched = [x for row in samples if (x := enrich_sample(row, dates, date_index, by_symbol, rank_by_date)) is not None]
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        buckets[str(row.get("winner_bucket"))].append(row)

    conditions = {
        "d3_close_ge_2": lambda r: sf(r.get("d3_close_tail_ret")) >= 2,
        "d3_close_ge_2_and_theme_hit_d1_d3_ge_1": lambda r: sf(r.get("d3_close_tail_ret")) >= 2 and sf(r.get("theme_top15_hits_d1_d3")) >= 1,
        "d3_close_ge_2_and_theme_hit_d1_d3_ge_2": lambda r: sf(r.get("d3_close_tail_ret")) >= 2 and sf(r.get("theme_top15_hits_d1_d3")) >= 2,
        "d3_close_ge_2_and_main_super_d2_d3_positive": lambda r: sf(r.get("d3_close_tail_ret")) >= 2 and sf(r.get("l2_main_sum_d2_d3_yi")) > 0 and sf(r.get("l2_super_sum_d2_d3_yi")) > 0,
        "d3_close_ge_2_and_theme_hit_ge_1_and_super_positive": lambda r: sf(r.get("d3_close_tail_ret")) >= 2 and sf(r.get("theme_top15_hits_d1_d3")) >= 1 and sf(r.get("l2_super_sum_d2_d3_yi")) > 0,
        "d5_close_ge_3": lambda r: sf(r.get("d5_close_tail_ret")) >= 3,
        "theme_hit_d1_d3_ge_1_only": lambda r: sf(r.get("theme_top15_hits_d1_d3")) >= 1,
        "l2_main_super_d2_d3_positive_only": lambda r: sf(r.get("l2_main_sum_d2_d3_yi")) > 0 and sf(r.get("l2_super_sum_d2_d3_yi")) > 0,
        "d3_close_lt_2": lambda r: sf(r.get("d3_close_tail_ret")) < 2,
        "d3_close_lt_2_and_no_theme_no_funding": lambda r: sf(r.get("d3_close_tail_ret")) < 2
        and sf(r.get("theme_top15_hits_d1_d3")) < 1
        and not (sf(r.get("l2_main_sum_d2_d3_yi")) > 0 and sf(r.get("l2_super_sum_d2_d3_yi")) > 0),
    }

    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sample_db": str(sample_db),
            "sample_scope": "D+1 no fade and D+1 open-to-close gain <= 2%; entry proxy = D+1 close/tail session",
            "sample_count": len(enriched),
            "start_date": enriched[0]["trade_date"] if enriched else None,
            "end_date": enriched[-1]["trade_date"] if enriched else None,
            "mfe_definition": "MFE after tail entry uses D+2..D+20 intraday highs against D+1 close; no D+1 intraday lookahead.",
        },
        "overall": summarize_rows(enriched),
        "buckets": {k: summarize_rows(v) for k, v in sorted(buckets.items())},
        "bucket_examples": {
            k: [
                {
                    "trade_date": r["trade_date"],
                    "symbol": r["symbol"],
                    "name": r.get("name"),
                    "theme_name": r.get("theme_name"),
                    "d3_close_tail_ret": round(sf(r.get("d3_close_tail_ret")), 2),
                    "d5_close_tail_ret": round(sf(r.get("d5_close_tail_ret")), 2),
                    "d20_close_tail_ret": round(sf(r.get("d20_close_tail_ret")), 2),
                    "mfe20_tail": round(sf(r.get("mfe20_tail")), 2),
                    "theme_hits_d1_d3": r.get("theme_top15_hits_d1_d3"),
                    "l2_super_d2_d3_yi": r.get("l2_super_sum_d2_d3_yi"),
                }
                for r in sorted(v, key=lambda x: sf(x.get("mfe20_tail")), reverse=True)
            ]
            for k, v in sorted(buckets.items())
        },
        "conditions": {name: condition_report(enriched, cond) for name, cond in conditions.items()},
        "theme_counts": Counter(str(r.get("theme_name")) for r in enriched).most_common(),
        "rows": enriched,
    }


def fmt_stat(s: Dict[str, Any]) -> str:
    return f"n={s['n']} avg={s['avg']:.2f}% med={s['median']:.2f}% win={s['win_rate']:.1%} worst={s['worst']:.2f}% best={s['best']:.2f}%"


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# 热点低位 L2：大肉路径深挖 {meta['start_date']} ~ {meta['end_date']}",
        "",
        "## 结论",
        "",
        "```text",
        "买入资格主要由 D+1 尾盘确认解决；但能不能拿成大肉，D+1 当天还看不清。",
        "当前样本里，大肉开始明显分化的时间点是 D+3：如果 D+3 已经有 >=2% 浮盈，后面跑出 10%+ MFE 的概率明显提高。",
        "板块热度延续是加分项，但不能单独用；更像 D+3 复核时的持仓信心来源。",
        "D+3 没有浮盈的票，不一定马上卖，但不能再当“大肉胚子”，后续应按弱票用资金/价格信号更敏感地处理。",
        "```",
        "",
        "## 样本口径",
        "",
        "```text",
        meta["sample_scope"],
        meta["mfe_definition"],
        f"样本数：{meta['sample_count']}",
        "```",
        "",
        "## 大肉 / 中肉 / 小肉",
        "",
        "| 分组 | 样本 | MFE20 | D+3收盘 | D+5收盘 | D+20收盘 | 板块D1~D3上榜均值 |",
        "|---|---:|---|---|---|---|---:|",
    ]
    labels = {
        "big_mfe20_ge_10": "大肉 MFE20>=10%",
        "mid_mfe20_5_10": "中肉 MFE20 5~10%",
        "small_mfe20_lt_5": "小肉 MFE20<5%",
        "insufficient": "数据不足",
    }
    for key in ["big_mfe20_ge_10", "mid_mfe20_5_10", "small_mfe20_lt_5", "insufficient"]:
        if key not in report["buckets"]:
            continue
        b = report["buckets"][key]
        lines.append(
            f"| {labels.get(key, key)} | {b['n']} | {fmt_stat(b['mfe20'])} | {fmt_stat(b['d3_close'])} | "
            f"{fmt_stat(b['d5_close'])} | {fmt_stat(b['d20_close'])} | {b['theme_hits_d1_d3_avg']:.2f} |"
        )
    lines += ["", "## D+3 复核条件测试", "", "| 条件 | 样本 | 覆盖 | 大肉率 | MFE20 | D+20收盘 |", "|---|---:|---:|---:|---|---|"]
    condition_labels = {
        "d3_close_ge_2": "D+3浮盈>=2%",
        "d3_close_ge_2_and_theme_hit_d1_d3_ge_1": "D+3浮盈>=2% 且 D1~D3板块至少1天Top15",
        "d3_close_ge_2_and_theme_hit_d1_d3_ge_2": "D+3浮盈>=2% 且 D1~D3板块至少2天Top15",
        "d3_close_ge_2_and_main_super_d2_d3_positive": "D+3浮盈>=2% 且 D2~D3主力/超大单都净流入",
        "d3_close_ge_2_and_theme_hit_ge_1_and_super_positive": "D+3浮盈>=2% 且板块延续且超大单为正",
        "d5_close_ge_3": "D+5浮盈>=3%（研究观察，不是买点）",
        "theme_hit_d1_d3_ge_1_only": "仅板块D1~D3仍进Top15",
        "l2_main_super_d2_d3_positive_only": "仅D2~D3资金继续流入",
        "d3_close_lt_2": "D+3浮盈<2%",
        "d3_close_lt_2_and_no_theme_no_funding": "D+3浮盈<2%，且板块没延续，且资金没继续",
    }
    for key, c in report["conditions"].items():
        lines.append(
            f"| {condition_labels.get(key, key)} | {c['n']} | {c['coverage']:.1%} | {c['big_rate']:.1%} | {fmt_stat(c['mfe20'])} | {fmt_stat(c['d20_close'])} |"
        )
    lines += ["", "## 代表大肉", ""]
    for r in report["bucket_examples"].get("big_mfe20_ge_10", [])[:10]:
        lines.append(
            f"- {r['trade_date']} {r['name']}（{r['symbol']}，{r['theme_name']}）："
            f"D+3 {r['d3_close_tail_ret']:.2f}%，D+5 {r['d5_close_tail_ret']:.2f}%，D+20 {r['d20_close_tail_ret']:.2f}%，MFE20 {r['mfe20_tail']:.2f}%"
        )
    lines += ["", "## 当前可执行解释", "", "```text",
              "D+1尾盘：只决定是否可以买，核心是不回落且涨幅<=2%。",
              "D+3复核：如果已有>=2%浮盈，且板块还没有完全熄火，可以把它从“小套利”升级为“可让利润奔跑”。",
              "D+3若仍无浮盈：不必机械卖，但它大概率不是主升扩散票，后续更看重资金转弱、跌破均线、板块退潮等退出信号。",
              "这个规则样本只有24只次，先作为影子观察规则，不直接写死进实盘。",
              "```"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze big-winner path for hot-theme low-position L2 tail-entry samples.")
    parser.add_argument("--sample-db", default=str(DEFAULT_SAMPLE_DB))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = build_report(Path(args.sample_db))
    ensure_market_heat_dir()
    out_json = Path(args.output) if args.output else MARKET_HEAT_DIR / "hot_theme_low_position_l2_big_winner_path.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    print(render_markdown(report))


if __name__ == "__main__":
    main()
