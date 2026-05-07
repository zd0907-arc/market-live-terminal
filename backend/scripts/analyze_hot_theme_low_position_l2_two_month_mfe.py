#!/usr/bin/env python3
from __future__ import annotations

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

SAMPLE_DB = MARKET_HEAT_DIR / "hot_theme_low_position_l2_samples.db"
OUT_JSON = MARKET_HEAT_DIR / "hot_theme_low_position_l2_two_month_mfe.json"
OUT_MD = MARKET_HEAT_DIR / "hot_theme_low_position_l2_two_month_mfe.md"


def sf(x: Any, default: float = 0.0) -> float:
    try:
        return float(x) if x is not None else default
    except Exception:
        return default


def stat(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0, "avg": 0.0, "median": 0.0, "p75": 0.0, "p90": 0.0, "best": 0.0, "worst": 0.0, "ge10": 0.0, "ge20": 0.0, "ge50": 0.0}
    def q(p: float) -> float:
        return vals[int((len(vals) - 1) * p)]
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 4),
        "median": round(statistics.median(vals), 4),
        "p75": round(q(0.75), 4),
        "p90": round(q(0.90), 4),
        "best": round(vals[-1], 4),
        "worst": round(vals[0], 4),
        "ge10": round(sum(v >= 10 for v in vals) / len(vals), 4),
        "ge20": round(sum(v >= 20 for v in vals) / len(vals), 4),
        "ge50": round(sum(v >= 50 for v in vals) / len(vals), 4),
    }


def ret(high: float, entry: float) -> Optional[float]:
    if entry <= 0:
        return None
    return (high / entry - 1) * 100


def load() -> tuple[List[Dict[str, Any]], List[str], Dict[str, Dict[str, Dict[str, Any]]]]:
    with sqlite3.connect(SAMPLE_DB, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        samples = [dict(r) for r in conn.execute("SELECT * FROM samples ORDER BY trade_date, symbol")]
    symbols = sorted({str(r["symbol"]) for r in samples})
    ph = ",".join("?" for _ in symbols)
    with sqlite3.connect(ATOMIC_DB, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        dates = [str(r[0]) for r in conn.execute("SELECT DISTINCT trade_date FROM atomic_trade_daily ORDER BY trade_date")]
        by_symbol: Dict[str, Dict[str, Dict[str, Any]]] = {s: {} for s in symbols}
        for r in conn.execute(
            f"""
            SELECT symbol, trade_date, open, high, low, close
            FROM atomic_trade_daily
            WHERE symbol IN ({ph})
            """,
            symbols,
        ):
            by_symbol[str(r["symbol"])][str(r["trade_date"])] = dict(r)
    return samples, dates, by_symbol


def enrich(samples: List[Dict[str, Any]], dates: List[str], by_symbol: Dict[str, Dict[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    idx = {d: i for i, d in enumerate(dates)}
    rows = []
    for s in samples:
        i = idx.get(str(s["trade_date"]))
        symbol = str(s["symbol"])
        rb = by_symbol.get(symbol, {})
        if i is None or i + 1 >= len(dates):
            continue
        d1 = rb.get(dates[i + 1])
        if not d1:
            continue
        rec = dict(s)
        rec["d1_date"] = dates[i + 1]
        for h in [10, 20, 40]:
            # D+1 tail entry: no lookahead inside D+1, so use next h sessions D+2..D+(h+1).
            after = [rb.get(dates[j]) for j in range(i + 2, min(i + h + 2, len(dates))) if rb.get(dates[j])]
            # Intraday optimistic entries can include D+1 high after a hypothetical D+1 low/open entry.
            incl = [rb.get(dates[j]) for j in range(i + 1, min(i + h + 1, len(dates))) if rb.get(dates[j])]
            rec[f"avail_after_{h}"] = len(after)
            rec[f"avail_incl_{h}"] = len(incl)
            rec[f"mfe{h}_from_d1_close_after"] = ret(max(sf(r["high"]) for r in after), sf(d1.get("close"))) if after else None
            rec[f"mfe{h}_from_d1_open_incl"] = ret(max(sf(r["high"]) for r in incl), sf(d1.get("open"))) if incl else None
            rec[f"mfe{h}_from_d1_low_incl"] = ret(max(sf(r["high"]) for r in incl), sf(d1.get("low"))) if incl else None
            rec[f"close{h}_from_d1_close"] = ((sf(after[-1]["close"]) / sf(d1.get("close")) - 1) * 100) if after and sf(d1.get("close")) > 0 else None
        rows.append(rec)
    return rows


def groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "all87": rows,
        "d1_no_fade": [r for r in rows if int(r.get("intraday_fade") or 0) == 0],
        "d1_no_fade_gain_0_2": [r for r in rows if int(r.get("intraday_fade") or 0) == 0 and 0 <= sf(r.get("d1_return_pct")) <= 2],
        "d1_no_fade_gain_gt2": [r for r in rows if int(r.get("intraday_fade") or 0) == 0 and sf(r.get("d1_return_pct")) > 2],
        "d1_fade": [r for r in rows if int(r.get("intraday_fade") or 0) == 1],
        "amount_0_8_1_0": [r for r in rows if 0.8 <= sf(r.get("amount_ratio_10d")) <= 1.0],
        "ma60_abs_le5": [r for r in rows if sf(r.get("ma60_distance_abs_pct")) <= 5],
    }


def fmt(s: Dict[str, Any]) -> str:
    return f"n={s['n']} avg={s['avg']:.2f}% med={s['median']:.2f}% p75={s['p75']:.2f}% p90={s['p90']:.2f}% >=10={s['ge10']:.1%} >=20={s['ge20']:.1%} >=50={s['ge50']:.1%} best={s['best']:.2f}%"


def render(report: Dict[str, Any]) -> str:
    labels = {
        "all87": "全部87个D日信号",
        "d1_no_fade": "D+1不回落",
        "d1_no_fade_gain_0_2": "D+1不回落且涨幅0~2%",
        "d1_no_fade_gain_gt2": "D+1不回落但涨幅>2%",
        "d1_fade": "D+1冲高回落",
        "amount_0_8_1_0": "D日量能比0.8~1.0",
        "ma60_abs_le5": "60日乖离<=5%",
    }
    lines = [
        "# 热点低位 L2：两个月最大涨幅上限验证",
        "",
        "## 口径",
        "",
        "```text",
        "样本：全部87个热点低位L2严格信号。",
        "两个月：40个交易日。",
        "现实尾盘口径：D+1收盘买入，未来D+2到D+41最高价计算MFE。",
        "理想日内口径：假设D+1能买到最低价，D+1到D+40最高价计算MFE。",
        "```",
        "",
        "## 两个月MFE：D+1收盘买入现实口径",
        "",
        "| 分组 | 结果 |",
        "|---|---|",
    ]
    for k, g in report["groups"].items():
        lines.append(f"| {labels.get(k, k)} | {fmt(g['mfe40_from_d1_close_after'])} |")
    lines += ["", "## 两个月MFE：D+1最低价买入理想上限", "", "| 分组 | 结果 |", "|---|---|"]
    for k, g in report["groups"].items():
        lines.append(f"| {labels.get(k, k)} | {fmt(g['mfe40_from_d1_low_incl'])} |")
    lines += ["", "## 主买点最大样本", ""]
    for r in report["top_main"]:
        lines.append(f"- {r['trade_date']} {r['name']}（{r['symbol']}，{r['theme_name']}）：MFE40 {r['mfe40_from_d1_close_after']:.2f}%，40日收盘 {r['close40_from_d1_close']:.2f}%")
    return "\n".join(lines)


def main() -> None:
    samples, dates, by_symbol = load()
    rows = enrich(samples, dates, by_symbol)
    gs = groups(rows)
    metrics = ["mfe40_from_d1_close_after", "mfe40_from_d1_open_incl", "mfe40_from_d1_low_incl", "mfe20_from_d1_close_after", "mfe10_from_d1_close_after", "close40_from_d1_close"]
    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sample_count": len(rows),
            "start_date": rows[0]["trade_date"] if rows else None,
            "end_date": rows[-1]["trade_date"] if rows else None,
        },
        "groups": {k: {m: stat([r.get(m) for r in v]) for m in metrics} for k, v in gs.items()},
        "top_main": [
            {
                "trade_date": r["trade_date"], "symbol": r["symbol"], "name": r.get("name"), "theme_name": r.get("theme_name"),
                "mfe40_from_d1_close_after": round(sf(r.get("mfe40_from_d1_close_after")), 4),
                "close40_from_d1_close": round(sf(r.get("close40_from_d1_close")), 4),
            }
            for r in sorted(gs["d1_no_fade_gain_0_2"], key=lambda x: sf(x.get("mfe40_from_d1_close_after")), reverse=True)[:12]
        ],
        "rows": rows,
    }
    ensure_market_heat_dir()
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render(report), encoding="utf-8")
    print(render(report))
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
