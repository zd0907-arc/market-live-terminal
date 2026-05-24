#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path("/Users/dong/Desktop/AIGC/market-live-terminal")
ATOMIC_DB = Path("/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_compact_current.db")
IN_CSV = ROOT / "data/selection/market_heat/backtests/hot_theme_big_mover_l2_precondition_events.csv"
OUT = ROOT / "docs/selection/market_heat/backtests/hot_theme_strong_momentum_l2_cases.html"
PRE_DAYS = 10
POST_DAYS = 25


def fnum(v, default=0.0):
    try:
        if v in ("", None):
            return default
        return float(v)
    except Exception:
        return default


def qmarks(n: int) -> str:
    return ",".join(["?"] * n)


def next_trade_date(dates: list[str], d: str):
    later = [x for x in dates if x > d]
    return later[0] if later else None


def ma(rows: list[dict], i: int, n: int) -> float:
    part = rows[max(0, i - n + 1) : i + 1]
    return sum(fnum(x["close"]) for x in part) / len(part)


def next_open(rows: list[dict], i: int):
    j = min(i + 1, len(rows) - 1)
    return j, fnum(rows[j]["open"])


def simulate_exit(rows: list[dict], buy_i: int, buy_price: float):
    """Strong-momentum sell framework:
    sell half at +10%, then let the rest run until drawdown/L2 weakness/timeout.
    """
    peak = buy_price
    peak_i = buy_i
    cash = 0.0
    position = 1.0
    first_sell_i = None
    first_sell_price = None
    max_dd = 0.0
    for held, i in enumerate(range(buy_i, min(len(rows), buy_i + 21)), start=1):
        r = rows[i]
        high = fnum(r["high"])
        close = fnum(r["close"])
        if high > peak:
            peak = high
            peak_i = i
        max_dd = min(max_dd, (close / peak - 1) * 100 if peak else 0)
        ret_close = (close / buy_price - 1) * 100
        drawdown = (close / peak - 1) * 100 if peak > 0 else 0

        if first_sell_i is None and high >= buy_price * 1.10:
            first_sell_i = i
            first_sell_price = buy_price * 1.10
            cash += 0.5 * first_sell_price
            position = 0.5

        final_signal = None
        final_i = None
        final_price = None
        if first_sell_i is None and ret_close <= -10:
            final_i, final_price = next_open(rows, i)
            final_signal = "硬止损：未触发第一止盈且收盘亏损超过10%，次日开盘清仓"
        elif first_sell_i is not None:
            l2_weak = fnum(r["super5Ratio"]) < 0 and fnum(r["total5Ratio"]) < 0 and close < ma(rows, i, 5)
            if peak / buy_price - 1 >= 0.15 and drawdown <= -8:
                final_i, final_price = next_open(rows, i)
                final_signal = "剩余仓位移动止盈：最高收益超过15%，从高点回撤超过8%，次日开盘卖出"
            elif l2_weak:
                final_i, final_price = next_open(rows, i)
                final_signal = "剩余仓位L2转弱：近5日超大单和合计L2为负且跌破MA5，次日开盘卖出"
            elif held >= 10:
                final_i = i
                final_price = close
                final_signal = "剩余仓位时间退出：买入后10个交易日内未继续有效冲高，收盘卖出"
        elif held >= 10:
            final_i = i
            final_price = close
            final_signal = "时间退出：10个交易日未触发第一止盈，收盘清仓"

        if final_signal:
            cash += position * final_price
            total_return = (cash / buy_price - 1) * 100 if buy_price else 0
            if first_sell_i is None:
                first_sell_i = final_i
                first_sell_price = final_price
            return {
                "first_i": first_sell_i,
                "first_price": first_sell_price,
                "final_i": final_i,
                "final_price": final_price,
                "reason": final_signal,
                "return_pct": total_return,
                "peak_i": peak_i,
                "peak_price": peak,
                "max_dd": max_dd,
                "held_days": held,
            }

    j = min(buy_i + 20, len(rows) - 1)
    final_price = fnum(rows[j]["close"])
    cash += position * final_price
    if first_sell_i is None:
        first_sell_i = j
        first_sell_price = final_price
    return {
        "first_i": first_sell_i,
        "first_price": first_sell_price,
        "final_i": j,
        "final_price": final_price,
        "reason": "期末退出：持满20个交易日收盘卖出",
        "return_pct": (cash / buy_price - 1) * 100 if buy_price else 0,
        "peak_i": peak_i,
        "peak_price": peak,
        "max_dd": max_dd,
        "held_days": j - buy_i + 1,
    }


def actual_fwd20_peak(rows: list[dict], event_i: int):
    part = [(i, rows[i]) for i in range(event_i + 1, min(len(rows), event_i + 21))]
    if not part:
        return event_i, fnum(rows[event_i]["high"])
    peak_i, peak_row = max(part, key=lambda x: fnum(x[1]["high"]))
    return peak_i, fnum(peak_row["high"])


def main():
    all_rows = list(csv.DictReader(IN_CSV.open(encoding="utf-8")))
    raw_cases = [
        r
        for r in all_rows
        if fnum(r["event_ret"]) >= 7
        and fnum(r["pre20_ret"]) > 20
        and fnum(r["pre5_super_ratio"]) > 2
        and fnum(r["amount_ratio"]) >= 1.5
    ]
    grouped = {}
    for r in sorted(raw_cases, key=lambda x: (x["symbol"], x["event_date"], int(fnum(x["hot_rank"])), x["sector_name"])):
        key = (r["symbol"], r["event_date"])
        if key not in grouped:
            grouped[key] = {**r, "_themes": []}
        grouped[key]["_themes"].append(
            {
                "sector": r["sector_name"],
                "rank": int(fnum(r["hot_rank"])),
                "amount_ratio": fnum(r["amount_ratio"]),
            }
        )
        if int(fnum(r["hot_rank"])) < int(fnum(grouped[key]["hot_rank"])):
            keep_themes = grouped[key]["_themes"]
            grouped[key] = {**r, "_themes": keep_themes}
    cases = list(grouped.values())
    for r in cases:
        themes = sorted(r["_themes"], key=lambda x: (x["rank"], x["sector"]))
        r["_theme_label"] = " / ".join(f"{x['sector']} Rank{x['rank']}" for x in themes)
        r["_hot_rank_min"] = min(x["rank"] for x in themes)
        r["_theme_amount_ratio_max"] = max(x["amount_ratio"] for x in themes)
    cases.sort(key=lambda r: fnum(r["fwd20_high"]), reverse=True)
    symbols = sorted({r["symbol"] for r in cases})

    ac = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro", uri=True)
    ac.row_factory = sqlite3.Row
    trade_dates = [
        r["trade_date"]
        for r in ac.execute(
            "select distinct trade_date from atomic_trade_daily where trade_date between '2024-11-01' and '2026-04-30' order by trade_date"
        )
    ]
    rows_by_symbol = {s: [] for s in symbols}
    for i in range(0, len(symbols), 800):
        chunk = symbols[i : i + 800]
        for r in ac.execute(
            f"""
            select symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            from atomic_trade_daily
            where symbol in ({qmarks(len(chunk))})
              and trade_date between '2024-11-01' and '2026-04-30'
            order by symbol, trade_date
            """,
            chunk,
        ):
            rows_by_symbol[r["symbol"]].append(
                {
                    "date": r["trade_date"],
                    "open": round(fnum(r["open"]), 3),
                    "high": round(fnum(r["high"]), 3),
                    "low": round(fnum(r["low"]), 3),
                    "close": round(fnum(r["close"]), 3),
                    "amountYi": round(fnum(r["total_amount"]) / 1e8, 3),
                    "mainYi": round(fnum(r["l2_main_net_amount"]) / 1e8, 3),
                    "superYi": round(fnum(r["l2_super_net_amount"]) / 1e8, 3),
                }
            )

    for rows in rows_by_symbol.values():
        for i, r in enumerate(rows):
            part = rows[max(0, i - 4) : i + 1]
            amount = sum(x["amountYi"] for x in part)
            main = sum(x["mainYi"] for x in part)
            sup = sum(x["superYi"] for x in part)
            r["main5Yi"] = round(main, 3)
            r["super5Yi"] = round(sup, 3)
            r["total5Yi"] = round(main + sup, 3)
            r["main5Ratio"] = round(main / amount * 100, 3) if amount else 0
            r["super5Ratio"] = round(sup / amount * 100, 3) if amount else 0
            r["total5Ratio"] = round((main + sup) / amount * 100, 3) if amount else 0

    idx = {(sym, r["date"]): i for sym, rows in rows_by_symbol.items() for i, r in enumerate(rows)}
    out_cases = []
    for n, c in enumerate(cases, start=1):
        sym = c["symbol"]
        rows = rows_by_symbol.get(sym) or []
        event_i = idx.get((sym, c["event_date"]))
        buy_date = next_trade_date(trade_dates, c["event_date"])
        buy_i = idx.get((sym, buy_date)) if buy_date else None
        if event_i is None or buy_i is None:
            continue
        buy_price = fnum(rows[buy_i]["open"])
        exit_result = simulate_exit(rows, buy_i, buy_price)
        sell_i = exit_result["final_i"]
        sell_price = exit_result["final_price"]
        sell_reason = exit_result["reason"]
        trade_peak_i = exit_result["peak_i"]
        trade_peak_price = exit_result["peak_price"]
        fwd20_peak_i, fwd20_peak_price = actual_fwd20_peak(rows, event_i)
        event_close = fnum(rows[event_i]["close"])
        lo = max(0, event_i - PRE_DAYS)
        hi = min(len(rows), event_i + POST_DAYS + 1)
        out_cases.append(
            {
                "id": n,
                "eventDate": c["event_date"],
                "theme": c["_theme_label"],
                "hotRank": c["_hot_rank_min"],
                "symbol": sym,
                "name": c["name"],
                "pattern": c["pre_pattern"],
                "eventRet": round(fnum(c["event_ret"]), 2),
                "pre5Ret": round(fnum(c["pre5_ret"]), 2),
                "pre20Ret": round(fnum(c["pre20_ret"]), 2),
                "pre5SuperRatio": round(fnum(c["pre5_super_ratio"]), 2),
                "themeAmountRatio": round(c["_theme_amount_ratio_max"], 2),
                "fwd20High": round((fwd20_peak_price / event_close - 1) * 100, 2) if event_close else 0,
                "buyDate": buy_date,
                "buyPrice": round(buy_price, 3),
                "firstSellDate": rows[exit_result["first_i"]]["date"],
                "firstSellPrice": round(exit_result["first_price"], 3),
                "sellDate": rows[sell_i]["date"],
                "sellPrice": round(sell_price, 3),
                "sellReason": sell_reason,
                "returnPct": round(exit_result["return_pct"], 2),
                "maxDrawdownPct": round(exit_result["max_dd"], 2),
                "heldDays": exit_result["held_days"],
                "peakDate": rows[fwd20_peak_i]["date"],
                "peakPrice": round(fwd20_peak_price, 3),
                "peakRet": round((fwd20_peak_price / event_close - 1) * 100, 2) if event_close else 0,
                "tradePeakDate": rows[trade_peak_i]["date"],
                "tradePeakPrice": round(trade_peak_price, 3),
                "tradePeakRet": round((trade_peak_price / buy_price - 1) * 100, 2) if buy_price else 0,
                "window": rows[lo:hi],
            }
        )
    out_cases.sort(key=lambda x: x["fwd20High"], reverse=True)
    for i, c in enumerate(out_cases, start=1):
        c["id"] = i

    data = {"rawCount": len(raw_cases), "count": len(out_cases), "cases": out_cases}
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>强者恒强样本：K线 + 近5日L2累计</title>
<style>
body{{margin:0;background:#08101d;color:#e6edf7;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",Arial,sans-serif}}
.wrap{{max-width:1500px;margin:auto;padding:22px}}h1{{font-size:22px;margin:0 0 8px}}.sub{{color:#9fb0c8;line-height:1.7;font-size:13px}}
.card{{background:#101827;border:1px solid #263244;border-radius:12px;padding:13px 14px;margin:12px 0}}.toolbar{{display:flex;gap:8px;flex-wrap:wrap}}
button,input{{background:#0c1424;color:#e6edf7;border:1px solid #31425f;border-radius:8px;padding:7px 10px}}button{{cursor:pointer}}button.active{{background:#1e3a5f}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}@media(max-width:1050px){{.grid{{grid-template-columns:1fr}}}}
h3{{margin:0 0 5px;font-size:15px;display:flex;justify-content:space-between;gap:8px}}code{{color:#bfdbfe}}.meta{{font-size:12px;color:#a9b6c9;line-height:1.6;margin-bottom:7px}}
.good{{color:#fb7185}}.bad{{color:#4ade80}}svg{{width:100%;height:auto;background:#0b1220;border-radius:8px;display:block}}
.gridline{{stroke:#233047;stroke-width:1}}.axis{{fill:#8391a7;font-size:10px}}.zero{{stroke:#94a3b8;stroke-width:1;stroke-dasharray:3 3;opacity:.75}}
.wick{{stroke-width:1.2}}.close-line{{fill:none;stroke:#f8fafc;stroke-width:1.6;opacity:.85}}
.eventline{{stroke:#facc15;stroke-width:1.5;stroke-dasharray:4 3}}.buyline{{stroke:#a78bfa;stroke-width:1.6}}.firstsellline{{stroke:#f97316;stroke-width:1.6;stroke-dasharray:4 2}}.sellline{{stroke:#38bdf8;stroke-width:1.6}}.peakline{{stroke:#fb7185;stroke-width:1.4;stroke-dasharray:3 3}}
.note{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:7px;font-size:12px}}.pill{{background:#0b1322;border:1px solid #24344e;border-radius:8px;padding:6px 7px;line-height:1.45}}
.reason{{font-size:12px;color:#b9c5d6;line-height:1.55;margin-top:7px;max-height:54px;overflow:auto}}.tip{{position:fixed;display:none;pointer-events:none;background:#06111f;border:1px solid #37506f;color:#e6edf7;border-radius:8px;padding:8px 10px;font-size:12px;line-height:1.55;z-index:20}}
</style></head><body><div class="wrap">
<h1>强者恒强样本：买卖点 + 近5日L2累计资金</h1>
<div class="sub">规则：热点日涨>=7%，热点前20日已涨>20%，前5日超大单占成交额>2%，主题成交放大>=1.5。已按“股票+热点日”去重。黄色=热点确认日，紫色=次日开盘买入，橙色=+10%卖一半，蓝色=最终卖点，红虚线=热点确认后20个交易日内最高点。柱子默认显示近5日主力/超大单累计净流入金额。</div>
<div class="card toolbar"><button class="metric active" data-metric="yi">近5日净额</button><button class="metric" data-metric="ratio">近5日占成交额</button><button class="sort active" data-sort="fwd">按后20高排序</button><button class="sort" data-sort="ret">按规则收益排序</button><input id="q" placeholder="搜索股票/主题/代码"/></div>
<div class="card"><div id="summary" class="sub"></div></div><div id="cards" class="grid"></div>
</div><div id="tip" class="tip"></div><script>const DATA={js};</script>
<script>
let metric='yi', sort='fwd', query='';
const el=id=>document.getElementById(id);
function esc(s){{return String(s||'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function idx(rows,d){{return rows.findIndex(x=>x.date===d)}}
function path(vals,x,y){{let d='';vals.forEach((v,i)=>{{d+=(i?'L':'M')+x(i)+','+y(v)}});return d}}
function chart(c){{
 const rows=c.window,W=690,H=305,L=44,R=14,T=14,B=25,priceH=178,barTop=212,barH=64,n=rows.length;
 const pmin=Math.min(...rows.map(r=>r.low))*0.985,pmax=Math.max(...rows.map(r=>r.high))*1.015;
 const suf=metric==='ratio'?'Ratio':'Yi', mainKey='main5'+suf, superKey='super5'+suf;
 const fmax=Math.max(0.01,...rows.flatMap(r=>[Math.abs(r[mainKey]||0),Math.abs(r[superKey]||0)]))*1.15;
 const x=i=>L+(n===1?0:i/(n-1))*(W-L-R), step=n>1?(W-L-R)/(n-1):12, cw=Math.max(3,Math.min(9,step*.55));
 const py=v=>T+(pmax-v)/(pmax-pmin)*priceH, fy=v=>barTop+barH/2-(v/fmax)*(barH/2);
 let s='';
 for(let k=0;k<=4;k++){{const yy=T+priceH*k/4;s+=`<line x1="${{L}}" y1="${{yy}}" x2="${{W-R}}" y2="${{yy}}" class="gridline"/><text x="4" y="${{yy+3}}" class="axis">${{(pmax-(pmax-pmin)*k/4).toFixed(1)}}</text>`}}
 s+=`<line x1="${{L}}" y1="${{fy(0)}}" x2="${{W-R}}" y2="${{fy(0)}}" class="zero"/>`;
 rows.forEach((r,i)=>{{const up=r.close>=r.open,col=up?'#ef4444':'#22c55e',xx=x(i);s+=`<line x1="${{xx}}" y1="${{py(r.high)}}" x2="${{xx}}" y2="${{py(r.low)}}" stroke="${{col}}" class="wick"/><rect x="${{xx-cw/2}}" y="${{py(Math.max(r.open,r.close))}}" width="${{cw}}" height="${{Math.max(2,Math.abs(py(r.open)-py(r.close)))}}" fill="${{col}}" opacity=".72"/>`;
 const m=r[mainKey]||0,u=r[superKey]||0,m0=fy(0),my=fy(m),uy=fy(u);s+=`<rect class="bar" x="${{xx-cw*.75}}" y="${{Math.min(m0,my)}}" width="${{cw*1.5}}" height="${{Math.max(1,Math.abs(my-m0))}}" fill="${{m>=0?'#fb7185':'#4ade80'}}" opacity=".55" data-i="${{i}}"/><rect class="bar" x="${{xx-cw*.32}}" y="${{Math.min(m0,uy)}}" width="${{cw*.64}}" height="${{Math.max(1,Math.abs(uy-m0))}}" fill="${{u>=0?'#f43f5e':'#16a34a'}}" opacity=".9" data-i="${{i}}"/>`; }});
 s+=`<path d="${{path(rows.map(r=>r.close),x,py)}}" class="close-line"/>`;
 [['eventDate','eventline',c.eventDate,c.eventRet],['buyDate','buyline',c.buyDate,c.buyPrice],['firstSellDate','firstsellline',c.firstSellDate,c.firstSellPrice],['sellDate','sellline',c.sellDate,c.sellPrice],['peakDate','peakline',c.peakDate,c.peakPrice]].forEach(a=>{{const i=idx(rows,a[2]);if(i>=0)s+=`<line x1="${{x(i)}}" y1="${{T}}" x2="${{x(i)}}" y2="${{H-B}}" class="${{a[1]}}"/>`;}})
 rows.forEach((r,i)=>{{if(i%Math.ceil(n/6)===0||r.date===c.eventDate||r.date===c.buyDate||r.date===c.sellDate)s+=`<text x="${{x(i)-24}}" y="${{H-7}}" class="axis">${{r.date.slice(5)}}</text>`}})
 return `<svg viewBox="0 0 ${{W}} ${{H}}" data-id="${{c.id}}">${{s}}</svg>`;
}}
function card(c){{
 return `<section class="card"><h3><span>${{c.name}} <code>${{c.symbol}}</code>｜${{c.theme}}</span><span class="${{c.returnPct>=0?'good':'bad'}}">${{c.returnPct}}%</span></h3><div class="meta">热点日 ${{c.eventDate}}｜买入 ${{c.buyDate}} ${{c.buyPrice}}｜半仓 ${{c.firstSellDate}} ${{c.firstSellPrice}}｜清仓 ${{c.sellDate}} ${{c.sellPrice}}｜热点后20日最高 ${{c.fwd20High}}%</div>${{chart(c)}}<div class="note"><div class="pill">热点日前20日涨<br><b>${{c.pre20Ret}}%</b></div><div class="pill">前5超大单占比<br><b>${{c.pre5SuperRatio}}%</b></div><div class="pill">规则最大回撤<br><b>${{c.maxDrawdownPct}}%</b></div><div class="pill">持有交易日<br><b>${{c.heldDays}}</b></div></div><div class="reason">${{esc(c.sellReason)}}</div></section>`;
}}
function pass(c){{if(!query)return true;const q=query.toLowerCase();return `${{c.name}} ${{c.symbol}} ${{c.theme}}`.toLowerCase().includes(q)}}
function render(){{
 let arr=DATA.cases.filter(pass);
 arr.sort((a,b)=>sort==='ret'?b.returnPct-a.returnPct:b.fwd20High-a.fwd20High);
 el('cards').innerHTML=arr.map(card).join('');
 const avg=arr.reduce((s,x)=>s+x.returnPct,0)/(arr.length||1), med=[...arr].map(x=>x.returnPct).sort((a,b)=>a-b)[Math.floor((arr.length||1)/2)]||0, win=arr.filter(x=>x.returnPct>0).length/(arr.length||1)*100, hit20=arr.filter(x=>x.fwd20High>=20).length/(arr.length||1)*100;
 el('summary').innerHTML=`当前显示 ${{arr.length}} / ${{DATA.count}} 个去重后的强者恒强样本；原始命中 ${{DATA.rawCount}} 条主题-股票记录。分批卖出平均收益 ${{avg.toFixed(2)}}%，中位 ${{med.toFixed(2)}}%，胜率 ${{win.toFixed(1)}}%；热点后20日最高>=20% 占比 ${{hit20.toFixed(1)}}%。`;
 document.querySelectorAll('.metric').forEach(b=>b.classList.toggle('active',b.dataset.metric===metric));document.querySelectorAll('.sort').forEach(b=>b.classList.toggle('active',b.dataset.sort===sort));bindTips();
}}
function bindTips(){{document.querySelectorAll('.bar').forEach(b=>{{b.onmousemove=e=>{{const c=DATA.cases.find(x=>String(x.id)===b.closest('svg').dataset.id),r=c.window[+b.dataset.i],suf=metric==='ratio'?'Ratio':'Yi',unit=metric==='ratio'?'%':'亿';const tip=el('tip');tip.style.display='block';tip.style.left=e.clientX+14+'px';tip.style.top=e.clientY+14+'px';tip.innerHTML=`${{r.date}}<br>开高低收：${{r.open}}/${{r.high}}/${{r.low}}/${{r.close}}<br>当日主/超：${{r.mainYi}}/${{r.superYi}} 亿<br>近5日主/超/合计：${{r['main5'+suf]}}/${{r['super5'+suf]}}/${{r['total5'+suf]}} ${{unit}}`;}};b.onmouseleave=()=>el('tip').style.display='none';}})}}
document.querySelectorAll('.metric').forEach(b=>b.onclick=()=>{{metric=b.dataset.metric;render()}});document.querySelectorAll('.sort').forEach(b=>b.onclick=()=>{{sort=b.dataset.sort;render()}});el('q').oninput=e=>{{query=e.target.value.trim();render()}};render();
</script></body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(OUT)
    print("cases", len(out_cases))


if __name__ == "__main__":
    main()
