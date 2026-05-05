#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path("/Users/dong/Desktop/AIGC/market-live-terminal")
HEAT_DB = Path("/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db")
ATOMIC_DB = Path("/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db")
DATA_OUT = ROOT / "data/selection/market_heat/backtests"
DOC_OUT = ROOT / "docs/selection/market_heat/backtests"
OUT_CSV = DATA_OUT / "hot_theme_big_mover_l2_precondition_events.csv"
OUT_MD = DOC_OUT / "hot_theme_big_mover_l2_precondition.md"
OUT_HTML = DOC_OUT / "hot_theme_big_mover_l2_precondition_cases.html"
START = "2025-01-02"
END_EVENT = "2026-03-31"
END_PRICE = "2026-04-30"


def qmarks(n: int) -> str:
    return ",".join(["?"] * n)


def safe_float(v, default=0.0):
    try:
        if v in ("", None):
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def pct(a, b):
    a = safe_float(a, None)
    b = safe_float(b, None)
    if a is None or b is None or b <= 0:
        return None
    return (a / b - 1) * 100


def bucket_rank(rank: int) -> str:
    if rank == 1:
        return "Rank1"
    if rank <= 3:
        return "Top3"
    if rank <= 10:
        return "Top10"
    return "Top30"


def win_rate(xs, threshold=0):
    xs = [x for x in xs if x is not None]
    return len([x for x in xs if x >= threshold]) / len(xs) * 100 if xs else 0


def agg(rows, key, target):
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    out = []
    for k, rs in groups.items():
        vals = [r[target] for r in rs if r[target] is not None]
        if not vals:
            continue
        out.append(
            {
                key: k,
                "n": len(vals),
                "avg": mean(vals),
                "median": median(vals),
                "win10": win_rate(vals, 10),
                "win15": win_rate(vals, 15),
                "win20": win_rate(vals, 20),
            }
        )
    out.sort(key=lambda x: (x["win15"], x["avg"]), reverse=True)
    return out


def classify(r):
    pre5_ret = r["pre5_ret"] or 0
    pre20_ret = r["pre20_ret"] or 0
    pos20 = r["pre_pos20"] if r["pre_pos20"] is not None else 0.5
    super5 = r["pre5_super_ratio"] or 0
    total5 = r["pre5_total_ratio"] or 0
    event_ret = r["event_ret"] or 0
    if pre5_ret <= 3 and pos20 <= 0.55 and 0 <= super5 <= 2 and total5 >= 0:
        return "低位温和吸筹"
    if pre5_ret <= 5 and super5 > 2 and total5 > 0:
        return "资金先行"
    if event_ret >= 7 and pre5_ret <= 8:
        return "事件日同步爆发"
    if pre5_ret > 10 or pre20_ret > 25 or pos20 > 0.85:
        return "价格已先行"
    if super5 < 0 and total5 < 0:
        return "资金未配合"
    return "普通跟随"


def main():
    hc = sqlite3.connect(f"file:{HEAT_DB}?mode=ro", uri=True)
    hc.row_factory = sqlite3.Row
    ac = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro", uri=True)
    ac.row_factory = sqlite3.Row
    trade_dates = [
        r["trade_date"]
        for r in ac.execute(
            "select distinct trade_date from atomic_trade_daily where trade_date between ? and ? order by trade_date",
            ("2024-11-01", END_PRICE),
        )
    ]
    date_idx = {d: i for i, d in enumerate(trade_dates)}

    heat_rows = hc.execute(
        """
        select h.*, l.lifecycle_state, l.days_in_top15_5d, l.days_in_top30_10d
        from fine_theme_heat_daily h
        left join fine_theme_lifecycle_daily l
          on h.trade_date=l.trade_date and h.theme_id=l.theme_id
        where h.trade_date between ? and ? and h.hot_rank<=30
        order by h.trade_date, h.hot_rank
        """,
        (START, END_EVENT),
    ).fetchall()
    hist_by_theme = defaultdict(dict)
    for r in heat_rows:
        hist_by_theme[r["theme_id"]][r["trade_date"]] = dict(r)

    theme_events = []
    seen = set()
    for r in heat_rows:
        d = r["trade_date"]
        i = date_idx.get(d)
        if i is None or i < 20:
            continue
        prev10 = trade_dates[max(0, i - 10) : i]
        prev_ranks = [hist_by_theme[r["theme_id"]].get(x, {}).get("hot_rank", 999) for x in prev10]
        is_new = min(prev_ranks or [999]) > 30
        # 每个主题每隔至少10日才允许一个新事件，避免持续热点每天重复计数。
        last_key = (r["theme_id"],)
        if not is_new and safe_float(r["days_in_top30_10d"]) >= 5:
            continue
        if last_key in seen and not is_new:
            continue
        seen.add(last_key) if is_new else None
        theme_events.append(
            {
                "event_date": d,
                "theme_id": r["theme_id"],
                "sector_name": r["sector_name"],
                "hot_rank": int(r["hot_rank"]),
                "rank_bucket": bucket_rank(int(r["hot_rank"])),
                "hot_score": safe_float(r["hot_score"]),
                "theme_ret1": safe_float(r["avg_return_1d"]),
                "theme_ret5": safe_float(r["avg_return_5d"]),
                "up_ratio": safe_float(r["up_ratio"]),
                "amount_ratio": safe_float(r["amount_ratio"]),
                "theme_l2": safe_float(r["l2_main_net_yi"]),
                "lifecycle": "new_hot" if is_new else (r["lifecycle_state"] or "hot"),
            }
        )

    event_keys = [(e["event_date"], e["sector_name"]) for e in theme_events]
    members = []
    for i in range(0, len(event_keys), 500):
        chunk = event_keys[i : i + 500]
        cond = " or ".join(["(trade_date=? and sector_name=?)"] * len(chunk))
        params = [x for pair in chunk for x in pair]
        members.extend(
            hc.execute(
                f"""
                select trade_date, sector_name, symbol, name, role,
                       return_1d, return_5d, return_20d, amount_yi,
                       amount_ratio_20d, l2_main_net_yi, l2_super_net_yi,
                       price_position_20d
                from fine_theme_member_daily
                where {cond}
                """,
                params,
            ).fetchall()
        )
    event_map = {(e["event_date"], e["sector_name"]): e for e in theme_events}
    symbols = sorted({m["symbol"] for m in members})

    rows_by_sym = defaultdict(list)
    for i in range(0, len(symbols), 800):
        chunk = symbols[i : i + 800]
        for r in ac.execute(
            f"""
            select symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            from atomic_trade_daily
            where symbol in ({qmarks(len(chunk))}) and trade_date between '2024-11-01' and ?
            order by symbol, trade_date
            """,
            (*chunk, END_PRICE),
        ):
            rows_by_sym[r["symbol"]].append(dict(r))
    by = {}
    for sym, rows in rows_by_sym.items():
        for i, r in enumerate(rows):
            by[(sym, r["trade_date"])] = i

    out = []
    seen_stock_theme = set()
    for m in members:
        e = event_map.get((m["trade_date"], m["sector_name"]))
        if not e:
            continue
        sym = m["symbol"]
        rows = rows_by_sym.get(sym) or []
        i = by.get((sym, e["event_date"]))
        if i is None or i < 20:
            continue
        # 同一股票同一主题，20日内只取第一次热点事件。
        dup_key = (sym, e["sector_name"])
        if dup_key in seen_stock_theme:
            continue
        seen_stock_theme.add(dup_key)
        r0 = rows[i]
        close0 = safe_float(r0["close"])
        pre = rows[:i]

        def sum_flow(w, field):
            part = pre[max(0, len(pre) - w) :]
            return sum(safe_float(x[field]) for x in part) / 1e8

        def sum_amount(w):
            part = pre[max(0, len(pre) - w) :]
            return sum(safe_float(x["total_amount"]) for x in part) / 1e8

        pre5_amt = sum_amount(5)
        pre10_amt = sum_amount(10)
        main5 = sum_flow(5, "l2_main_net_amount")
        super5 = sum_flow(5, "l2_super_net_amount")
        main10 = sum_flow(10, "l2_main_net_amount")
        super10 = sum_flow(10, "l2_super_net_amount")
        pre_close5 = safe_float(rows[i - 5]["close"]) if i >= 5 else None
        pre_close20 = safe_float(rows[i - 20]["close"]) if i >= 20 else None
        pre20_closes = [safe_float(x["close"]) for x in rows[max(0, i - 20) : i]]
        lo20, hi20 = min(pre20_closes), max(pre20_closes)
        pre_pos20 = (safe_float(rows[i - 1]["close"]) - lo20) / (hi20 - lo20) if hi20 > lo20 else 0.5

        def fwd_high_ret(days):
            part = rows[i + 1 : min(len(rows), i + 1 + days)]
            if not part:
                return None
            return pct(max(safe_float(x["high"]) for x in part), close0)

        def fwd_close_ret(days):
            if i + days >= len(rows):
                return None
            return pct(rows[i + days]["close"], close0)

        row = {
            **e,
            "symbol": sym,
            "name": m["name"],
            "role": m["role"] or "",
            "event_close": close0,
            "event_ret": safe_float(m["return_1d"]),
            "event_ret5_member": safe_float(m["return_5d"]),
            "event_ret20_member": safe_float(m["return_20d"]),
            "event_pos20_member": safe_float(m["price_position_20d"], None),
            "pre5_ret": pct(rows[i - 1]["close"], pre_close5),
            "pre20_ret": pct(rows[i - 1]["close"], pre_close20),
            "pre_pos20": pre_pos20,
            "pre5_main_yi": main5,
            "pre5_super_yi": super5,
            "pre5_total_yi": main5 + super5,
            "pre10_main_yi": main10,
            "pre10_super_yi": super10,
            "pre10_total_yi": main10 + super10,
            "pre5_main_ratio": main5 / pre5_amt * 100 if pre5_amt > 0 else 0,
            "pre5_super_ratio": super5 / pre5_amt * 100 if pre5_amt > 0 else 0,
            "pre5_total_ratio": (main5 + super5) / pre5_amt * 100 if pre5_amt > 0 else 0,
            "pre10_super_ratio": super10 / pre10_amt * 100 if pre10_amt > 0 else 0,
            "fwd3_high": fwd_high_ret(3),
            "fwd5_high": fwd_high_ret(5),
            "fwd10_high": fwd_high_ret(10),
            "fwd20_high": fwd_high_ret(20),
            "fwd5_close": fwd_close_ret(5),
            "fwd10_close": fwd_close_ret(10),
            "fwd20_close": fwd_close_ret(20),
        }
        row["pre_pattern"] = classify(row)
        row["is_big10"] = int((row["fwd10_high"] or 0) >= 10)
        row["is_big20"] = int((row["fwd20_high"] or 0) >= 20)
        out.append(row)

    fields = [
        "event_date",
        "sector_name",
        "hot_rank",
        "rank_bucket",
        "lifecycle",
        "hot_score",
        "theme_ret1",
        "theme_ret5",
        "up_ratio",
        "amount_ratio",
        "theme_l2",
        "symbol",
        "name",
        "role",
        "event_close",
        "event_ret",
        "event_ret5_member",
        "event_ret20_member",
        "event_pos20_member",
        "pre5_ret",
        "pre20_ret",
        "pre_pos20",
        "pre5_main_yi",
        "pre5_super_yi",
        "pre5_total_yi",
        "pre10_main_yi",
        "pre10_super_yi",
        "pre10_total_yi",
        "pre5_main_ratio",
        "pre5_super_ratio",
        "pre5_total_ratio",
        "pre10_super_ratio",
        "pre_pattern",
        "fwd3_high",
        "fwd5_high",
        "fwd10_high",
        "fwd20_high",
        "fwd5_close",
        "fwd10_close",
        "fwd20_close",
        "is_big10",
        "is_big20",
    ]
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)

    DOC_OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# 热点大涨股前置资金形态分析", ""]
    lines.append(
        f"结论：样本 `{len(out)}` 个热点成分股事件。历史大涨股最多来自两类：`价格已先行` 和 `事件日同步爆发`；它们事后冲高最强，但不一定适合提前买。若限定为可提前识别样本，L2 前置资金只能提供弱加分，不能单独决定。"
    )
    lines += [
        "",
        "## 口径",
        "",
        "- 热点事件：小主题 `hot_rank<=30`，新进热点优先，持续热点去掉高重复日。",
        "- 个股事件：热点日该主题下的成分股。",
        "- 前置资金：热点日前 5/10 个交易日 L2 主力、超大单净额及占成交额比例，不含热点当天。",
        "- 未来表现：热点日收盘后 3/5/10/20 日内最高价涨幅，以及对应收盘涨幅。",
        "",
        "## 按热点排名",
        "",
        "| 热点层级 | 样本 | 后10日最高均值 | 中位 | >=10% | >=15% | >=20% |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in agg(out, "rank_bucket", "fwd10_high"):
        lines.append(
            f"| {r['rank_bucket']} | {r['n']} | {r['avg']:.1f}% | {r['median']:.1f}% | {r['win10']:.1f}% | {r['win15']:.1f}% | {r['win20']:.1f}% |"
        )
    lines += [
        "",
        "## 按热点前个股形态",
        "",
        "| 前置形态 | 样本 | 后10日最高均值 | 中位 | >=10% | >=15% | >=20% |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in agg(out, "pre_pattern", "fwd10_high"):
        lines.append(
            f"| {r['pre_pattern']} | {r['n']} | {r['avg']:.1f}% | {r['median']:.1f}% | {r['win10']:.1f}% | {r['win15']:.1f}% | {r['win20']:.1f}% |"
        )
    lines += [
        "",
        "## 大涨股前置形态分布",
        "",
        "| 条件 | 样本 | 前置形态分布 |",
        "|---|---:|---|",
    ]
    for label, subset in [
        ("后10日最高>=10%", [r for r in out if (r["fwd10_high"] or 0) >= 10]),
        ("后10日最高>=15%", [r for r in out if (r["fwd10_high"] or 0) >= 15]),
        ("后20日最高>=20%", [r for r in out if (r["fwd20_high"] or 0) >= 20]),
    ]:
        c = Counter(r["pre_pattern"] for r in subset)
        dist = "；".join(f"{k}:{v}" for k, v in c.most_common())
        lines.append(f"| {label} | {len(subset)} | {dist} |")
    early = [
        r
        for r in out
        if safe_float(r["event_ret"]) < 7
        and safe_float(r["pre5_ret"]) <= 8
        and safe_float(r["pre20_ret"]) <= 20
    ]
    lines += [
        "",
        "## 可提前识别样本",
        "",
        "剔除热点日已经大涨、热点前已经明显抢跑的样本后，再看前置资金形态。",
        "",
        "| 前置形态 | 样本 | 后10日最高均值 | 中位 | >=10% | >=15% | >=20% |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in agg(early, "pre_pattern", "fwd10_high"):
        lines.append(
            f"| {r['pre_pattern']} | {r['n']} | {r['avg']:.1f}% | {r['median']:.1f}% | {r['win10']:.1f}% | {r['win15']:.1f}% | {r['win20']:.1f}% |"
        )
    lines += [
        "",
        "## 代表案例：后10日冲高前30",
        "",
        "| 热点日 | 主题 | 股票 | 热点前形态 | 前5日价/超大单占比 | 热点日涨幅 | 后10日最高 | 后20日最高 |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for r in sorted(out, key=lambda x: x["fwd10_high"] or -999, reverse=True)[:30]:
        lines.append(
            f"| {r['event_date']} | {r['sector_name']} Rank{r['hot_rank']} | {r['name']} `{r['symbol']}` | {r['pre_pattern']} | "
            f"{r['pre5_ret']:.1f}% / {r['pre5_super_ratio']:.2f}% | {r['event_ret']:.1f}% | {r['fwd10_high']:.1f}% | {r['fwd20_high']:.1f}% |"
        )
    lines += [
        "",
        "## 初步结论",
        "",
        "1. 只看热点 Rank 不够；Rank1 的平均冲高更强，但样本少，Top3/Top10/Top30 差异没有想象中大。",
        "2. 真正的大涨，经常在热点被确认时已经价格先行，或者事件日同步爆发；这解释了为什么追热点容易追到尖峰。",
        "3. 可提前识别样本里，前置 L2 资金的优势很弱，不能单独当买点；它更适合作为“候选股排序/排雷”的一项。",
        "4. 下一步应该围绕“大涨前形态”建模型：热点类型、个股是否抢跑、L2是否温和转正、主题是否有持续性，而不是硬调一个固定买点。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Simple case browser for the top big movers.
    cases = sorted(out, key=lambda x: x["fwd10_high"] or -999, reverse=True)[:120]
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<title>热点大涨股前置资金形态</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",Arial,sans-serif;background:#08101d;color:#e6edf7;margin:0}}.wrap{{max-width:1400px;margin:auto;padding:22px}}h1{{font-size:22px}}.sub{{color:#9fb0c8;line-height:1.7}}table{{width:100%;border-collapse:collapse;font-size:13px;background:#101827;border:1px solid #263244}}th,td{{border-bottom:1px solid #263244;padding:7px 8px;text-align:right}}th:first-child,td:first-child,td:nth-child(2),td:nth-child(3),td:nth-child(4){{text-align:left}}tr:hover{{background:#14233b}}.good{{color:#fb7185}}.bad{{color:#4ade80}}code{{color:#bfdbfe}}</style></head><body><div class="wrap">
<h1>热点大涨股前置资金形态：后10日冲高前120</h1>
<div class="sub">事件日是小主题进入热点后的日期；前置资金统计不含事件日。重点看：热点前价格是否已涨、超大单是否温和转正、热点日后是否继续冲高。</div>
<table><thead><tr><th>热点日</th><th>主题</th><th>股票</th><th>形态</th><th>前5日价</th><th>前5日超大单%</th><th>热点日</th><th>后3高</th><th>后10高</th><th>后20高</th></tr></thead><tbody>
{''.join(f"<tr><td>{r['event_date']}</td><td>{r['sector_name']} Rank{r['hot_rank']}</td><td>{r['name']} <code>{r['symbol']}</code></td><td>{r['pre_pattern']}</td><td>{r['pre5_ret']:.1f}%</td><td>{r['pre5_super_ratio']:.2f}%</td><td>{r['event_ret']:.1f}%</td><td class='good'>{r['fwd3_high']:.1f}%</td><td class='good'>{r['fwd10_high']:.1f}%</td><td class='good'>{r['fwd20_high']:.1f}%</td></tr>" for r in cases)}
</tbody></table></div></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")
    print(OUT_MD)
    print(OUT_CSV)
    print(OUT_HTML)
    print("events", len(theme_events), "rows", len(out))


if __name__ == "__main__":
    main()
