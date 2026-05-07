#!/usr/bin/env python3
from __future__ import annotations

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

INPUT_JSON = MARKET_HEAT_DIR / "hot_theme_low_l2_two_month_opportunity.json"
OUT_JSON = MARKET_HEAT_DIR / "hot_theme_low_l2_two_month_winner_profile.json"
OUT_MD = MARKET_HEAT_DIR / "hot_theme_low_l2_two_month_winner_profile.md"


def sf(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def stat(values: Sequence[Any]) -> Dict[str, Any]:
    vals = sorted(sf(v) for v in values if v is not None)
    if not vals:
        return {"n": 0, "avg": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0, "p90": 0.0, "worst": 0.0, "best": 0.0}
    def q(p: float) -> float:
        return vals[int((len(vals) - 1) * p)]
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 4),
        "median": round(statistics.median(vals), 4),
        "p25": round(q(0.25), 4),
        "p75": round(q(0.75), 4),
        "p90": round(q(0.90), 4),
        "worst": round(vals[0], 4),
        "best": round(vals[-1], 4),
    }


def rate(rows: Sequence[Dict[str, Any]], pred) -> float:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 4) if rows else 0.0


def pct(a: float, b: float) -> Optional[float]:
    if b <= 0:
        return None
    return (a / b - 1) * 100


def d1_fade(row: Dict[str, Any]) -> tuple[bool, Optional[float]]:
    high, low, open_, close = sf(row.get("high")), sf(row.get("low")), sf(row.get("open")), sf(row.get("close"))
    if high <= low:
        return close < open_, None
    ratio = (high - close) / (high - low)
    return ratio > 0.5 or (high > open_ and close < open_), ratio


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


def enrich(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    symbols = sorted({str(r["symbol"]) for r in rows})
    ph = ",".join("?" for _ in symbols)
    with sqlite3.connect(str(ATOMIC_DB), timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        dates = [str(r[0]) for r in conn.execute("SELECT DISTINCT trade_date FROM atomic_trade_daily ORDER BY trade_date")]
        by_symbol = {s: {} for s in symbols}
        for r in conn.execute(
            f"""
            SELECT symbol, trade_date, open, high, low, close,
                   l2_main_net_amount, l2_super_net_amount
            FROM atomic_trade_daily
            WHERE symbol IN ({ph})
            """,
            symbols,
        ):
            by_symbol[str(r["symbol"])][str(r["trade_date"])] = dict(r)
    idx = {d: i for i, d in enumerate(dates)}
    ranks = load_rank_cache()
    out = []
    for r in rows:
        rec = dict(r)
        symbol = str(r["symbol"])
        rb = by_symbol.get(symbol, {})
        i = idx.get(str(r["trade_date"]))
        if i is not None and i + 1 < len(dates):
            d0 = rb.get(dates[i])
            d1 = rb.get(dates[i + 1])
            if d0 and d1:
                fade, ratio = d1_fade(d1)
                rec["d1_fade"] = fade
                rec["d1_fade_ratio"] = ratio
                rec["d1_return_pct"] = pct(sf(d1["close"]), sf(d1["open"]))
                rec["d1_gap_pct"] = pct(sf(d1["open"]), sf(d0["close"]))
                rec["d1_main_yi"] = sf(d1.get("l2_main_net_amount")) / 100_000_000
                rec["d1_super_yi"] = sf(d1.get("l2_super_net_amount")) / 100_000_000
                rec["d1_funding_pos"] = sf(d1.get("l2_main_net_amount")) > 0 and sf(d1.get("l2_super_net_amount")) > 0
            theme_id = str(r.get("theme_id") or "")
            d1_d5_ranks = [ranks.get(dates[j], {}).get(theme_id, 999) for j in range(i + 1, min(i + 6, len(dates)))]
            rec["theme_top15_hits_d1_d5"] = sum(1 for x in d1_d5_ranks if x <= 15)
            rec["theme_best_rank_d1_d5"] = min(d1_d5_ranks) if d1_d5_ranks else None
        out.append(rec)
    return out


def classify(r: Dict[str, Any]) -> str:
    if bool(r.get("hit20")) and sf(r.get("mae_before_hit20"), -999) >= -8:
        return "comfortable_20"
    if bool(r.get("hit20")) and sf(r.get("mae_before_hit20"), 0) < -8:
        return "pain_20"
    if (not bool(r.get("hit10"))) or sf(r.get("close40")) < 0:
        return "failure"
    return "middle"


def summarize_group(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields = [
        "mfe40", "mae40", "close40", "return_5d_pct", "position_20d", "amount_ratio_10d", "ma60_abs_pct",
        "l2_main_2d_yi", "theme_rank", "theme_recent_hits", "d1_return_pct", "d1_gap_pct", "d1_main_yi", "d1_super_yi", "theme_top15_hits_d1_d5",
    ]
    return {
        "n": len(rows),
        "stats": {f: stat([r.get(f) for r in rows]) for f in fields},
        "rates": {
            "amount_0_5_1_2": rate(rows, lambda r: 0.5 <= sf(r.get("amount_ratio_10d")) <= 1.2),
            "amount_0_8_1_1": rate(rows, lambda r: 0.8 <= sf(r.get("amount_ratio_10d")) <= 1.1),
            "pos20_le_0_45": rate(rows, lambda r: sf(r.get("position_20d")) <= 0.45),
            "pos20_le_0_5": rate(rows, lambda r: sf(r.get("position_20d")) <= 0.5),
            "ma60_le_8": rate(rows, lambda r: sf(r.get("ma60_abs_pct")) <= 8),
            "ma60_le_10": rate(rows, lambda r: sf(r.get("ma60_abs_pct")) <= 10),
            "super_2of3": rate(rows, lambda r: bool(r.get("super_2of3"))),
            "super_3d_sum_positive": rate(rows, lambda r: bool(r.get("super_3d_sum_positive"))),
            "d1_no_fade": rate(rows, lambda r: r.get("d1_fade") is False),
            "d1_no_fade_gain_0_2": rate(rows, lambda r: r.get("d1_fade") is False and 0 <= sf(r.get("d1_return_pct")) <= 2),
            "d1_funding_pos": rate(rows, lambda r: bool(r.get("d1_funding_pos"))),
            "theme_d1_d5_hit_ge_1": rate(rows, lambda r: sf(r.get("theme_top15_hits_d1_d5")) >= 1),
            "theme_d1_d5_hit_ge_2": rate(rows, lambda r: sf(r.get("theme_top15_hits_d1_d5")) >= 2),
        },
        "themes": Counter(str(r.get("theme_name")) for r in rows).most_common(12),
    }


def screen_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    screens = {
        "base_all": lambda r: True,
        "pos_le_05_amount_05_12": lambda r: sf(r.get("position_20d")) <= 0.5 and 0.5 <= sf(r.get("amount_ratio_10d")) <= 1.2,
        "pos_le_05_amount_08_11": lambda r: sf(r.get("position_20d")) <= 0.5 and 0.8 <= sf(r.get("amount_ratio_10d")) <= 1.1,
        "pos_le_05_amount_05_12_ma60_le10": lambda r: sf(r.get("position_20d")) <= 0.5 and 0.5 <= sf(r.get("amount_ratio_10d")) <= 1.2 and sf(r.get("ma60_abs_pct")) <= 10,
        "pos_le_05_amount_05_12_theme_continue": lambda r: sf(r.get("position_20d")) <= 0.5 and 0.5 <= sf(r.get("amount_ratio_10d")) <= 1.2 and sf(r.get("theme_top15_hits_d1_d5")) >= 1,
        "pos_le_05_amount_05_12_d1_no_fade": lambda r: sf(r.get("position_20d")) <= 0.5 and 0.5 <= sf(r.get("amount_ratio_10d")) <= 1.2 and r.get("d1_fade") is False,
        "pos_le_05_amount_05_12_no_fade_theme": lambda r: sf(r.get("position_20d")) <= 0.5 and 0.5 <= sf(r.get("amount_ratio_10d")) <= 1.2 and r.get("d1_fade") is False and sf(r.get("theme_top15_hits_d1_d5")) >= 1,
    }
    out = {}
    for name, pred in screens.items():
        rs = [r for r in rows if pred(r)]
        out[name] = {
            "n": len(rs),
            "comfortable20": rate(rs, lambda r: classify(r) == "comfortable_20"),
            "pain20": rate(rs, lambda r: classify(r) == "pain_20"),
            "failure": rate(rs, lambda r: classify(r) == "failure"),
            "middle": rate(rs, lambda r: classify(r) == "middle"),
            "mfe40": stat([r.get("mfe40") for r in rs]),
            "mae40": stat([r.get("mae40") for r in rs]),
            "close40": stat([r.get("close40") for r in rs]),
        }
    return out


def build() -> Dict[str, Any]:
    payload = json.loads(INPUT_JSON.read_text(encoding="utf-8"))
    rows = enrich(payload.get("rows", []))
    for r in rows:
        r["bucket"] = classify(r)
    buckets = {name: [r for r in rows if r["bucket"] == name] for name in ["comfortable_20", "pain_20", "failure", "middle"]}
    report = {
        "meta": {"generated_at": datetime.now().isoformat(timespec="seconds"), "input": str(INPUT_JSON), "sample_count": len(rows)},
        "buckets": {k: summarize_group(v) for k, v in buckets.items()},
        "screens": screen_report(rows),
        "examples": {
            k: [
                {field: r.get(field) for field in ["trade_date", "symbol", "name", "theme_name", "mfe40", "mae40", "close40", "mae_before_hit20", "position_20d", "amount_ratio_10d", "ma60_abs_pct", "theme_top15_hits_d1_d5", "d1_return_pct", "d1_fade"]}
                for r in sorted(v, key=lambda x: sf(x.get("mfe40")), reverse=True)[:10]
            ]
            for k, v in buckets.items()
        },
        "rows": rows,
    }
    return report


def fmt(s: Dict[str, Any]) -> str:
    return f"avg={s['avg']:.2f} med={s['median']:.2f} p75={s['p75']:.2f}"


def render(report: Dict[str, Any]) -> str:
    labels = {"comfortable_20": "舒服赢家", "pain_20": "痛苦赢家", "failure": "失败", "middle": "中间"}
    lines = [
        "# 热门板块低位埋伏：赢家/失败画像拆解",
        "",
        "## 分桶定义",
        "",
        "```text",
        "舒服赢家：未来40日达到+20%，且达到前最大浮亏不超过8%。",
        "痛苦赢家：未来40日达到+20%，但达到前先亏超过8%。",
        "失败：未来40日没摸到+10%，或40日收盘仍亏损。",
        "中间：其余样本。",
        "```",
        "",
        "## 画像对比",
        "",
        "| 分桶 | 样本 | MFE40 | MAE40 | close40 | pos20中位 | 量能中位 | 60日乖离中位 | D+1不回落 | D+1~D+5板块延续>=1 |",
        "|---|---:|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for k, item in report["buckets"].items():
        st = item["stats"]
        rt = item["rates"]
        lines.append(
            f"| {labels.get(k,k)} | {item['n']} | {fmt(st['mfe40'])} | {fmt(st['mae40'])} | {fmt(st['close40'])} | "
            f"{st['position_20d']['median']:.2f} | {st['amount_ratio_10d']['median']:.2f} | {st['ma60_abs_pct']['median']:.2f}% | "
            f"{rt['d1_no_fade']:.1%} | {rt['theme_d1_d5_hit_ge_1']:.1%} |"
        )
    lines += ["", "## 筛选规则试算", "", "| 规则 | 样本 | 舒服赢家 | 痛苦赢家 | 失败 | MFE40 | MAE40 | close40 |", "|---|---:|---:|---:|---:|---|---|---|"]
    screen_labels = {
        "base_all": "全部核心样本",
        "pos_le_05_amount_05_12": "pos<=0.5 + 量能0.5~1.2",
        "pos_le_05_amount_08_11": "pos<=0.5 + 量能0.8~1.1",
        "pos_le_05_amount_05_12_ma60_le10": "+ 60日乖离<=10",
        "pos_le_05_amount_05_12_theme_continue": "+ D+1~D+5板块延续",
        "pos_le_05_amount_05_12_d1_no_fade": "+ D+1不回落",
        "pos_le_05_amount_05_12_no_fade_theme": "+ D+1不回落 + 板块延续",
    }
    for k, item in report["screens"].items():
        lines.append(
            f"| {screen_labels.get(k,k)} | {item['n']} | {item['comfortable20']:.1%} | {item['pain20']:.1%} | {item['failure']:.1%} | "
            f"{fmt(item['mfe40'])} | {fmt(item['mae40'])} | {fmt(item['close40'])} |"
        )
    lines += ["", "## 舒服赢家代表", ""]
    for r in report["examples"]["comfortable_20"][:8]:
        lines.append(
            f"- {r['trade_date']} {r['name']}（{r['symbol']}，{r['theme_name']}）：MFE40 {sf(r['mfe40']):.2f}%，MAE40 {sf(r['mae40']):.2f}%，40日收盘 {sf(r['close40']):.2f}%"
        )
    return "\n".join(lines)


def main() -> None:
    report = build()
    ensure_market_heat_dir()
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render(report), encoding="utf-8")
    print(render(report))
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
