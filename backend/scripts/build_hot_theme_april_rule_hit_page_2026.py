#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import sqlite3
from pathlib import Path

from backend.app.core.config import RESEARCH_CURRENT_ROOT


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_ROOT = Path(os.getenv("RESEARCH_CURRENT_ROOT", RESEARCH_CURRENT_ROOT))
ATOMIC_DB = Path(
    os.getenv(
        "ATOMIC_COMPACT_DB_PATH",
        os.getenv(
            "ATOMIC_MAINBOARD_DB_PATH",
            str(DEFAULT_RESEARCH_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"),
        ),
    )
)
IN_CSV = ROOT / "data/selection/market_heat/backtests/hot_theme_rule_hits_2026_04.csv"
OUT_HTML = ROOT / "docs/selection/market_heat/backtests/hot_theme_rule_hits_2026_04_charts.html"

START = "2026-03-01"
END = "2026-04-30"


def fnum(v, default=0.0) -> float:
    try:
        if v in ("", None):
            return default
        x = float(v)
        return default if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return default


def qmarks(n: int) -> str:
    return ",".join(["?"] * n)


def main() -> None:
    cases = [
        r
        for r in csv.DictReader(IN_CSV.open(encoding="utf-8"))
        if int(fnum(r["hit_count"])) >= 2
    ]
    cases.sort(key=lambda r: (r["event_date"], r["symbol"]))
    symbols = sorted({r["symbol"] for r in cases})

    ac = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro", uri=True)
    ac.row_factory = sqlite3.Row
    rows_by_symbol: dict[str, list[dict]] = {s: [] for s in symbols}
    for i in range(0, len(symbols), 800):
        chunk = symbols[i : i + 800]
        if not chunk:
            continue
        for r in ac.execute(
            f"""
            select symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            from atomic_trade_daily
            where symbol in ({qmarks(len(chunk))})
              and trade_date between ? and ?
            order by symbol, trade_date
            """,
            (*chunk, START, END),
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
    ac.close()

    for rows in rows_by_symbol.values():
        for i, r in enumerate(rows):
            part = rows[max(0, i - 4) : i + 1]
            amount = sum(x["amountYi"] for x in part)
            main = sum(x["mainYi"] for x in part)
            sup = sum(x["superYi"] for x in part)
            r["main5Yi"] = round(main, 3)
            r["super5Yi"] = round(sup, 3)
            r["total5Yi"] = round(main + sup, 3)
            r["main5Ratio"] = round(main / amount * 100, 3) if amount else 0.0
            r["super5Ratio"] = round(sup / amount * 100, 3) if amount else 0.0
            r["total5Ratio"] = round((main + sup) / amount * 100, 3) if amount else 0.0

    chart_cases = []
    for i, c in enumerate(cases, start=1):
        rows = rows_by_symbol.get(c["symbol"]) or []
        event_i = next((j for j, r in enumerate(rows) if r["date"] == c["event_date"]), None)
        event_close = rows[event_i]["close"] if event_i is not None else 0
        after = rows[event_i + 1 :] if event_i is not None else []
        fwd_high = max((r["high"] for r in after), default=event_close)
        fwd_low = min((r["low"] for r in after), default=event_close)
        chart_cases.append(
            {
                "id": i,
                "eventDate": c["event_date"],
                "symbol": c["symbol"],
                "name": c["name"],
                "hitCount": int(fnum(c["hit_count"])),
                "rules": c["rules"],
                "themes": c["themes"],
                "eventRet": round(fnum(c["event_ret"]), 2),
                "pre5Ret": round(fnum(c["pre5_ret"]), 2),
                "pre20Ret": round(fnum(c["pre20_ret"]), 2),
                "pre5SuperRatio": round(fnum(c["pre5_super_ratio"]), 2),
                "amountRatio": round(fnum(c["amount_ratio"]), 2),
                "fwdHighTo0430": round((fwd_high / event_close - 1) * 100, 2) if event_close else 0,
                "fwdLowTo0430": round((fwd_low / event_close - 1) * 100, 2) if event_close else 0,
                "window": rows,
            }
        )

    data = {
        "start": START,
        "end": END,
        "count": len(chart_cases),
        "cases": chart_cases,
    }
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>2026年4月热点规则命中票：3-4月走势</title>
<style>
body{{margin:0;background:#08101d;color:#e6edf7;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",Arial,sans-serif}}
.wrap{{max-width:1480px;margin:auto;padding:22px}}h1{{font-size:22px;margin:0 0 8px}}.sub{{color:#9fb0c8;font-size:13px;line-height:1.7}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}}button,input{{background:#0c1424;color:#e6edf7;border:1px solid #31425f;border-radius:8px;padding:7px 10px}}button{{cursor:pointer}}button.active{{background:#1e3a5f}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}@media(max-width:1050px){{.grid{{grid-template-columns:1fr}}}}
.card{{background:#101827;border:1px solid #263244;border-radius:12px;padding:13px 14px}}h3{{margin:0 0 5px;font-size:15px;display:flex;justify-content:space-between;gap:8px}}
code{{color:#bfdbfe}}.meta{{font-size:12px;color:#a9b6c9;line-height:1.6;margin-bottom:7px}}.good{{color:#fb7185}}.bad{{color:#4ade80}}
svg{{width:100%;height:auto;background:#0b1220;border-radius:8px;display:block}}.gridline{{stroke:#233047;stroke-width:1}}.axis{{fill:#8391a7;font-size:10px}}.zero{{stroke:#94a3b8;stroke-width:1;stroke-dasharray:3 3;opacity:.75}}
.wick{{stroke-width:1.2}}.close-line{{fill:none;stroke:#f8fafc;stroke-width:1.9;opacity:.9}}.eventline{{stroke:#facc15;stroke-width:1.7;stroke-dasharray:4 3}}
.note{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:7px;font-size:12px}}.pill{{background:#0b1322;border:1px solid #24344e;border-radius:8px;padding:6px 7px;line-height:1.45}}
.tip{{position:fixed;display:none;pointer-events:none;background:#06111f;border:1px solid #37506f;color:#e6edf7;border-radius:8px;padding:8px 10px;font-size:12px;line-height:1.55;z-index:20}}
</style></head><body><div class="wrap">
<h1>2026年4月热点规则命中票：3-4月走势</h1>
<div class="sub">严格口径：与 2025 回测一致的主题事件去重/生命周期过滤。4 月三条全命中为 0，下面是命中 2 条的 5 只票。黄色虚线=热点确认日；上半区=K线+收盘线；下半区=近5日主力/超大单累计资金。</div>
<div class="toolbar"><button class="metric active" data-metric="yi">近5日净额</button><button class="metric" data-metric="ratio">近5日占成交额</button><input id="q" placeholder="搜索股票/主题/代码"/></div>
<div id="summary" class="sub"></div><div id="cards" class="grid"></div>
</div><div id="tip" class="tip"></div><script>const DATA={js};</script>
<script>
let metric='yi', query='';
const el=id=>document.getElementById(id);
function esc(s){{return String(s||'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function idx(rows,d){{return rows.findIndex(x=>x.date===d)}}
function path(vals,x,y){{let d='';vals.forEach((v,i)=>d+=(i?'L':'M')+x(i)+','+y(v));return d}}
function chart(c){{
 const rows=c.window,W=690,H=315,L=44,R=14,T=14,B=25,priceH=186,barTop=224,barH=62,n=rows.length;
 const pmin=Math.min(...rows.map(r=>r.low))*0.985,pmax=Math.max(...rows.map(r=>r.high))*1.015;
 const suf=metric==='ratio'?'Ratio':'Yi', mainKey='main5'+suf, superKey='super5'+suf, totalKey='total5'+suf;
 const fmax=Math.max(0.01,...rows.flatMap(r=>[Math.abs(r[mainKey]||0),Math.abs(r[superKey]||0),Math.abs(r[totalKey]||0)]))*1.15;
 const x=i=>L+(n===1?0:i/(n-1))*(W-L-R), step=n>1?(W-L-R)/(n-1):12, cw=Math.max(3,Math.min(9,step*.55));
 const py=v=>T+(pmax-v)/(pmax-pmin)*priceH, fy=v=>barTop+barH/2-(v/fmax)*(barH/2);
 let s='';
 for(let k=0;k<=4;k++){{const yy=T+priceH*k/4;s+=`<line x1="${{L}}" y1="${{yy}}" x2="${{W-R}}" y2="${{yy}}" class="gridline"/><text x="4" y="${{yy+3}}" class="axis">${{(pmax-(pmax-pmin)*k/4).toFixed(1)}}</text>`}}
 s+=`<line x1="${{L}}" y1="${{fy(0)}}" x2="${{W-R}}" y2="${{fy(0)}}" class="zero"/>`;
 rows.forEach((r,i)=>{{const up=r.close>=r.open,col=up?'#ef4444':'#22c55e',xx=x(i);s+=`<line x1="${{xx}}" y1="${{py(r.high)}}" x2="${{xx}}" y2="${{py(r.low)}}" stroke="${{col}}" class="wick"/><rect x="${{xx-cw/2}}" y="${{py(Math.max(r.open,r.close))}}" width="${{cw}}" height="${{Math.max(2,Math.abs(py(r.open)-py(r.close)))}}" fill="${{col}}" opacity=".72"/>`;
 const m=r[mainKey]||0,u=r[superKey]||0,m0=fy(0),my=fy(m),uy=fy(u);s+=`<rect class="bar" x="${{xx-cw*.75}}" y="${{Math.min(m0,my)}}" width="${{cw*1.5}}" height="${{Math.max(1,Math.abs(my-m0))}}" fill="${{m>=0?'#fb7185':'#4ade80'}}" opacity=".48" data-id="${{c.id}}" data-i="${{i}}"/><rect class="bar" x="${{xx-cw*.3}}" y="${{Math.min(m0,uy)}}" width="${{cw*.6}}" height="${{Math.max(1,Math.abs(uy-m0))}}" fill="${{u>=0?'#f43f5e':'#16a34a'}}" opacity=".92" data-id="${{c.id}}" data-i="${{i}}"/>`; }});
 s+=`<path d="${{path(rows.map(r=>r.close),x,py)}}" class="close-line"/>`;
 const ei=idx(rows,c.eventDate);if(ei>=0)s+=`<line x1="${{x(ei)}}" y1="${{T}}" x2="${{x(ei)}}" y2="${{H-B}}" class="eventline"/>`;
 rows.forEach((r,i)=>{{if(i%Math.ceil(n/6)===0||r.date===c.eventDate)s+=`<text x="${{x(i)-24}}" y="${{H-7}}" class="axis">${{r.date.slice(5)}}</text>`}})
 return `<svg viewBox="0 0 ${{W}} ${{H}}">${{s}}</svg>`;
}}
function card(c){{return `<section class="card"><h3><span>${{c.name}} <code>${{c.symbol}}</code></span><span class="${{c.fwdHighTo0430>=0?'good':'bad'}}">后续高点 ${{c.fwdHighTo0430}}%</span></h3><div class="meta">${{esc(c.themes)}}<br>${{esc(c.rules)}}｜热点日 ${{c.eventDate}}｜当日涨 ${{c.eventRet}}%</div>${{chart(c)}}<div class="note"><div class="pill">前5日涨<br><b>${{c.pre5Ret}}%</b></div><div class="pill">前20日涨<br><b>${{c.pre20Ret}}%</b></div><div class="pill">前5超大单占比<br><b>${{c.pre5SuperRatio}}%</b></div><div class="pill">热点后低点<br><b>${{c.fwdLowTo0430}}%</b></div></div></section>`}}
function pass(c){{if(!query)return true;const q=query.toLowerCase();return `${{c.name}} ${{c.symbol}} ${{c.themes}}`.toLowerCase().includes(q)}}
function render(){{const arr=DATA.cases.filter(pass);el('cards').innerHTML=arr.map(card).join('');el('summary').innerHTML=`显示 ${{arr.length}} / ${{DATA.count}} 个命中 2 项以上信号，窗口 ${{DATA.start}} 至 ${{DATA.end}}。红/绿柱：宽柱=近5日主力累计，窄柱=近5日超大单累计。`;document.querySelectorAll('.metric').forEach(b=>b.classList.toggle('active',b.dataset.metric===metric));bindTips();}}
function bindTips(){{document.querySelectorAll('.bar').forEach(b=>{{b.onmousemove=e=>{{const c=DATA.cases.find(x=>String(x.id)===b.dataset.id),r=c.window[+b.dataset.i],suf=metric==='ratio'?'Ratio':'Yi',unit=metric==='ratio'?'%':'亿';const tip=el('tip');tip.style.display='block';tip.style.left=e.clientX+14+'px';tip.style.top=e.clientY+14+'px';tip.innerHTML=`${{r.date}}<br>开高低收：${{r.open}}/${{r.high}}/${{r.low}}/${{r.close}}<br>当日主/超：${{r.mainYi}}/${{r.superYi}} 亿<br>近5日主/超/合计：${{r['main5'+suf]}}/${{r['super5'+suf]}}/${{r['total5'+suf]}} ${{unit}}`;}};b.onmouseleave=()=>el('tip').style.display='none';}})}}
document.querySelectorAll('.metric').forEach(b=>b.onclick=()=>{{metric=b.dataset.metric;render()}});el('q').oninput=e=>{{query=e.target.value.trim();render()}};render();
</script></body></html>"""
    OUT_HTML.write_text(page, encoding="utf-8")
    print(OUT_HTML)
    print("cases", len(chart_cases))


if __name__ == "__main__":
    main()
