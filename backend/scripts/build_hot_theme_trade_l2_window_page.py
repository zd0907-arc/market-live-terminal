#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
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
TRADES_CSVS = [
    ROOT / "data/selection/market_heat/backtests/hot_theme_strategy_variants_2025-01_2026-03_trades.csv",
    ROOT / "data/selection/market_heat/backtests/hot_theme_l2_5d_confirm_2025-01_2026-03_trades.csv",
]
OUT = ROOT / "docs/selection/market_heat/backtests/hot_theme_strategy_variants_l2_windows_2025_2026.html"
PRE_DAYS = 10
POST_DAYS = 10
DEFAULT_FLOW_WINDOW = 5
DEFAULT_FLOW_METRIC = "ratio"
FLOW_TEST_SUMMARY = {
    "bestFactor": "近5日超大单净流入 / 近5日成交额",
    "target": "后3个交易日最高价",
    "rankIc": 0.184,
    "pearson": 0.225,
    "sampleRows": 5017,
}


def safe_float(v, default=0.0):
    try:
        if v in ("", None):
            return default
        return float(v)
    except Exception:
        return default


def qmarks(n: int) -> str:
    return ",".join(["?"] * n)


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b <= 0:
        return None
    return (a / b - 1) * 100


def main() -> None:
    trades_raw = []
    for path in TRADES_CSVS:
        if path.exists():
            trades_raw.extend(list(csv.DictReader(path.open(encoding="utf-8"))))
    symbols = sorted({r["symbol"] for r in trades_raw})
    ac = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro", uri=True)
    ac.row_factory = sqlite3.Row
    rows_by_symbol: dict[str, list[dict]] = {s: [] for s in symbols}
    for i in range(0, len(symbols), 800):
        chunk = symbols[i : i + 800]
        for r in ac.execute(
            f"""
            select symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            from atomic_trade_daily
            where symbol in ({qmarks(len(chunk))})
              and trade_date between '2024-12-01' and '2026-05-15'
            order by symbol, trade_date
            """,
            chunk,
        ):
            rows_by_symbol[r["symbol"]].append(
                {
                    "date": r["trade_date"],
                    "open": round(float(r["open"]), 3),
                    "high": round(float(r["high"]), 3),
                    "low": round(float(r["low"]), 3),
                    "close": round(float(r["close"]), 3),
                    "amountYi": round(float(r["total_amount"]) / 1e8, 3),
                    "mainYi": round(float(r["l2_main_net_amount"]) / 1e8, 3),
                    "superYi": round(float(r["l2_super_net_amount"]) / 1e8, 3),
                }
            )
    for rows in rows_by_symbol.values():
        for i, r in enumerate(rows):
            for w in (1, 3, 5, 10):
                part = rows[max(0, i - w + 1) : i + 1]
                main = sum(x["mainYi"] for x in part)
                sup = sum(x["superYi"] for x in part)
                amt = sum(x["amountYi"] for x in part)
                r[f"main{w}Yi"] = round(main, 3)
                r[f"super{w}Yi"] = round(sup, 3)
                r[f"total{w}Yi"] = round(main + sup, 3)
                r[f"main{w}Ratio"] = round(main / amt * 100, 3) if amt > 0 else 0
                r[f"super{w}Ratio"] = round(sup / amt * 100, 3) if amt > 0 else 0
                r[f"total{w}Ratio"] = round((main + sup) / amt * 100, 3) if amt > 0 else 0
    idx = {(sym, r["date"]): i for sym, rows in rows_by_symbol.items() for i, r in enumerate(rows)}

    trades = []
    for n, r in enumerate(trades_raw, 1):
        sym = r["symbol"]
        rows = rows_by_symbol.get(sym) or []
        buy_i = idx.get((sym, r["buy_date"]))
        sell_i = idx.get((sym, r["sell_date"]))
        if buy_i is None or sell_i is None:
            continue
        lo = max(0, buy_i - PRE_DAYS)
        hi = min(len(rows), max(sell_i, buy_i) + POST_DAYS + 1)
        window = rows[lo:hi]
        buy_price = safe_float(r["buy_price"])
        post_rows = rows[buy_i + 1 : min(len(rows), buy_i + 11)]

        def max_high(days: int):
            part = rows[buy_i + 1 : min(len(rows), buy_i + 1 + days)]
            return max((x["high"] for x in part), default=None)

        pre3 = rows[max(0, buy_i - 3) : buy_i]
        pre5 = rows[max(0, buy_i - 5) : buy_i]
        buy_to_3 = rows[buy_i : min(len(rows), buy_i + 3)]
        trades.append(
            {
                "id": n,
                "strategy": r["strategy"],
                "decisionDate": r["decision_date"],
                "sector": r["sector_name"],
                "themeRank": int(safe_float(r["theme_rank"])),
                "themeState": r["theme_state"],
                "symbol": sym,
                "name": r["name"],
                "role": r["role"],
                "buyDate": r["buy_date"],
                "buyPrice": round(buy_price, 3),
                "sellDate": r["sell_date"],
                "sellPrice": round(safe_float(r["sell_price"]), 3),
                "returnPct": round(safe_float(r["return_pct"]), 2),
                "holdDays": int(safe_float(r["hold_days"])),
                "maxDrawdownPct": round(safe_float(r["max_drawdown_pct"]), 2),
                "peakDate": r["peak_date"],
                "peakPrice": round(safe_float(r["peak_price"]), 3),
                "buyReason": r["buy_reason"],
                "sellReason": r["sell_reason"],
                "d1HighPct": round(pct(max_high(1), buy_price) or 0, 2),
                "d3HighPct": round(pct(max_high(3), buy_price) or 0, 2),
                "d5HighPct": round(pct(max_high(5), buy_price) or 0, 2),
                "d10HighPct": round(pct(max_high(10), buy_price) or 0, 2),
                "pre3MainYi": round(sum(x["mainYi"] for x in pre3), 3),
                "pre3SuperYi": round(sum(x["superYi"] for x in pre3), 3),
                "pre5MainYi": round(sum(x["mainYi"] for x in pre5), 3),
                "pre5SuperYi": round(sum(x["superYi"] for x in pre5), 3),
                "buyTo3MainYi": round(sum(x["mainYi"] for x in buy_to_3), 3),
                "buyTo3SuperYi": round(sum(x["superYi"] for x in buy_to_3), 3),
                "post10MainYi": round(sum(x["mainYi"] for x in post_rows), 3),
                "post10SuperYi": round(sum(x["superYi"] for x in post_rows), 3),
                "windowStart": window[0]["date"],
                "windowEnd": window[-1]["date"],
                "rows": window,
            }
        )

    trades.sort(key=lambda x: (x["buyDate"], x["strategy"], x["symbol"]))
    data = {
        "preDays": PRE_DAYS,
        "postDays": POST_DAYS,
        "defaultFlowWindow": DEFAULT_FLOW_WINDOW,
        "defaultFlowMetric": DEFAULT_FLOW_METRIC,
        "flowTestSummary": FLOW_TEST_SUMMARY,
        "count": len(trades),
        "trades": trades,
    }
    json_data = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>热点策略交易局部图：股价 + L2资金</title>
<style>
:root{{--bg:#080d19;--card:#101827;--line:#263244;--text:#e6edf7;--muted:#9aa8bd;--red:#ef4444;--green:#22c55e;--blue:#60a5fa;--purple:#c084fc;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,"PingFang SC",sans-serif}}
.wrap{{max-width:1500px;margin:0 auto;padding:20px}} h1{{font-size:22px;margin:0 0 8px}} .sub{{color:var(--muted);font-size:13px;line-height:1.7}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 14px;margin:12px 0}}
.toolbar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}} button{{background:#111d31;color:#dbeafe;border:1px solid #31425f;border-radius:8px;padding:7px 10px;cursor:pointer}} button.active{{background:#1e3a5f;box-shadow:inset 0 0 0 1px #93c5fd}}
input{{background:#0c1424;color:#e6edf7;border:1px solid #31425f;border-radius:8px;padding:7px 10px;min-width:220px}}
.legend{{display:flex;gap:14px;flex-wrap:wrap}} .sw{{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}} @media(max-width:1050px){{.grid{{grid-template-columns:1fr}}}}
.trade h3{{margin:0 0 4px;font-size:15px;display:flex;justify-content:space-between;gap:8px}} code{{color:#bfdbfe}}
.meta{{font-size:12px;color:#a9b6c9;line-height:1.55;margin-bottom:7px}} .bad{{color:#22c55e}} .good{{color:#ef4444}}
svg{{width:100%;height:auto;display:block;background:#0b1220;border-radius:8px}} .axis{{fill:#8391a7;font-size:10px}} .gridline{{stroke:#233047;stroke-width:1}} .zero{{stroke:#94a3b8;stroke-width:1;stroke-dasharray:3 3;opacity:.75}}
.wick{{stroke-width:1.2}} .candle{{stroke-width:1}} .close-line{{fill:none;stroke:#f8fafc;stroke-width:1.6;opacity:.85}}
.buyline{{stroke:#facc15;stroke-width:1.5;stroke-dasharray:4 3}} .sellline{{stroke:#38bdf8;stroke-width:1.5;stroke-dasharray:4 3}}
.note{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:7px;font-size:12px}} .pill{{background:#0b1322;border:1px solid #24344e;border-radius:8px;padding:6px 7px;line-height:1.45}}
.reason{{font-size:12px;color:#b9c5d6;line-height:1.55;margin-top:7px;max-height:60px;overflow:auto}}
.tip{{position:fixed;display:none;pointer-events:none;background:#06111f;border:1px solid #37506f;color:#e6edf7;border-radius:8px;padding:8px 10px;font-size:12px;line-height:1.55;max-width:360px;z-index:20}}
</style></head><body><div class="wrap">
<h1>热点策略交易局部图：股价 + L2 主力/超大单</h1>
<div class="sub">每笔交易截取买点前 {PRE_DAYS} 个交易日、卖点后 {POST_DAYS} 个交易日。上半区是K线/收盘线，下半区是滚动 L2 资金柱。默认显示近5日资金占成交额，因为它在这批样本里和“后3日最高价”的相关性最高。</div>
<div class="card toolbar">
  <button class="filter active" data-strategy="all">全部</button>
  <button class="filter" data-strategy="attack">进攻版</button>
  <button class="filter" data-strategy="low_position">低位补涨版</button>
  <button class="filter" data-strategy="pullback_confirm">回踩确认版</button>
  <button class="filter" data-strategy="l2_5d_confirm">L2-5日确认</button>
  <button class="ret active" data-ret="all">全部收益</button>
  <button class="ret" data-ret="win">只看盈利</button>
  <button class="ret" data-ret="loss">只看亏损</button>
  <button class="win" data-window="1">当日</button>
  <button class="win" data-window="3">近3日</button>
  <button class="win active" data-window="5">近5日</button>
  <button class="win" data-window="10">近10日</button>
  <button class="metric" data-metric="yi">净额</button>
  <button class="metric active" data-metric="ratio">占成交额</button>
  <input id="q" placeholder="搜索股票/主题/代码"/>
</div>
<div class="card legend sub">
  <span><i class="sw" style="background:#facc15"></i>黄色竖线：买入</span>
  <span><i class="sw" style="background:#38bdf8"></i>蓝色竖线：卖出</span>
  <span><i class="sw" style="background:#fb7185"></i>主力滚动净流入</span>
  <span><i class="sw" style="background:#f43f5e"></i>超大单滚动净流入</span>
  <span><i class="sw" style="background:#4ade80"></i>净流出</span>
  <span><i class="sw" style="background:#a78bfa"></i>L2-5日确认策略买卖点</span>
</div>
<div class="card"><div id="summary" class="sub"></div></div>
<div id="cards" class="grid"></div>
</div><div id="tip" class="tip"></div>
<script>const DATA={json_data};</script>
<script>
const labels={{attack:'进攻版',low_position:'低位补涨版',pullback_confirm:'回踩确认版',l2_5d_confirm:'L2-5日确认'}};
const strategyColors={{attack:'#ef4444',low_position:'#22c55e',pullback_confirm:'#facc15',l2_5d_confirm:'#a78bfa'}};
let strategy='l2_5d_confirm', ret='all', query='', flowWindow=DATA.defaultFlowWindow, flowMetric=DATA.defaultFlowMetric;
const el=id=>document.getElementById(id);
function esc(s){{return String(s||'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function idx(rows,d){{return rows.findIndex(x=>x.date===d)}}
function path(vals,x,y){{let d=''; vals.forEach((v,i)=>{{d+=(i?'L':'M')+x(i)+','+y(v)}}); return d}}
function chart(t){{
  const W=690,H=300,L=44,R=14,T=14,B=25,priceH=178,barTop=210,barH=62;
  const rows=t.rows,n=rows.length;
  const pmin=Math.min(...rows.map(r=>r.low))*0.985,pmax=Math.max(...rows.map(r=>r.high))*1.015;
  const suf=flowMetric==='ratio'?'Ratio':'Yi';
  const mainKey=`main${{flowWindow}}${{suf}}`, superKey=`super${{flowWindow}}${{suf}}`;
  const fmax=Math.max(0.01,...rows.flatMap(r=>[Math.abs(r[mainKey]||0),Math.abs(r[superKey]||0)]))*1.15;
  const x=i=>L+(n===1?0:i/(n-1))*(W-L-R);
  const step=n>1?(W-L-R)/(n-1):12, cw=Math.max(3,Math.min(9,step*.55));
  const py=v=>T+(pmax-v)/(pmax-pmin)*priceH;
  const fy=v=>barTop+barH/2-(v/fmax)*(barH/2);
  let s='';
  for(let k=0;k<=4;k++){{const yy=T+priceH*k/4; s+=`<line x1="${{L}}" y1="${{yy}}" x2="${{W-R}}" y2="${{yy}}" class="gridline"/><text x="4" y="${{yy+3}}" class="axis">${{(pmax-(pmax-pmin)*k/4).toFixed(1)}}</text>`}}
  s+=`<line x1="${{L}}" y1="${{fy(0)}}" x2="${{W-R}}" y2="${{fy(0)}}" class="zero"/><text x="4" y="${{fy(0)+3}}" class="axis">0</text>`;
  rows.forEach((r,i)=>{{
    const up=r.close>=r.open, c=up?'#ef4444':'#22c55e', xx=x(i);
    s+=`<line x1="${{xx}}" y1="${{py(r.high)}}" x2="${{xx}}" y2="${{py(r.low)}}" stroke="${{c}}" class="wick"/>`;
    const y1=py(Math.max(r.open,r.close)), y2=py(Math.min(r.open,r.close));
    s+=`<rect x="${{xx-cw/2}}" y="${{Math.min(y1,y2)}}" width="${{cw}}" height="${{Math.max(2,Math.abs(y2-y1))}}" fill="${{c}}" stroke="${{c}}" class="candle" opacity=".72"/>`;
    const mainVal=r[mainKey]||0, superVal=r[superKey]||0;
    const mainColor=mainVal>=0?'#fb7185':'#4ade80', supColor=superVal>=0?'#f43f5e':'#16a34a';
    const m0=fy(0), my=fy(mainVal), sy=fy(superVal);
    s+=`<rect class="bar" x="${{xx-cw*.75}}" y="${{Math.min(m0,my)}}" width="${{cw*1.5}}" height="${{Math.max(1,Math.abs(my-m0))}}" fill="${{mainColor}}" opacity=".55" data-i="${{i}}"/>`;
    s+=`<rect class="bar" x="${{xx-cw*.32}}" y="${{Math.min(m0,sy)}}" width="${{cw*.64}}" height="${{Math.max(1,Math.abs(sy-m0))}}" fill="${{supColor}}" opacity=".9" data-i="${{i}}"/>`;
  }});
  s+=`<path d="${{path(rows.map(r=>r.close),x,py)}}" class="close-line"/>`;
  const bi=idx(rows,t.buyDate), si=idx(rows,t.sellDate);
  const markColor=strategyColors[t.strategy]||'#facc15';
  if(bi>=0) s+=`<line x1="${{x(bi)}}" y1="${{T}}" x2="${{x(bi)}}" y2="${{H-B}}" class="buyline"/><circle cx="${{x(bi)}}" cy="${{py(t.buyPrice)}}" r="5" fill="${{markColor}}" stroke="#0b1220"/>`;
  if(si>=0) s+=`<line x1="${{x(si)}}" y1="${{T}}" x2="${{x(si)}}" y2="${{H-B}}" class="sellline"/><path d="M ${{x(si)-6}} ${{py(t.sellPrice)-5}} L ${{x(si)+6}} ${{py(t.sellPrice)-5}} L ${{x(si)}} ${{py(t.sellPrice)+6}} Z" fill="${{markColor}}" stroke="#0b1220"/>`;
  rows.forEach((r,i)=>{{ if(i%Math.ceil(n/6)===0||r.date===t.buyDate||r.date===t.sellDate) s+=`<text x="${{x(i)-24}}" y="${{H-7}}" class="axis">${{r.date.slice(5)}}</text>`; }});
  return `<svg viewBox="0 0 ${{W}} ${{H}}" data-trade="${{t.id}}">${{s}}</svg>`;
}}
function card(t){{
  const retClass=t.returnPct>=0?'good':'bad';
  return `<section class="card trade"><h3><span>${{t.name}} <code>${{t.symbol}}</code>｜<span style="color:${{strategyColors[t.strategy]||'#dbeafe'}}">${{labels[t.strategy]}}</span></span><span class="${{retClass}}">${{t.returnPct}}%</span></h3>
  <div class="meta">${{t.sector}} Rank${{t.themeRank}}｜${{t.themeState}}｜买入 ${{t.buyDate}} ${{t.buyPrice}}｜卖出 ${{t.sellDate}} ${{t.sellPrice}}｜持股 ${{t.holdDays}} 日</div>
  ${{chart(t)}}
  <div class="note">
    <div class="pill">D+1最高<br><b class="${{t.d1HighPct>=0?'good':'bad'}}">${{t.d1HighPct}}%</b></div>
    <div class="pill">D+3最高<br><b class="${{t.d3HighPct>=0?'good':'bad'}}">${{t.d3HighPct}}%</b></div>
    <div class="pill">买前3日主/超<br><b>${{t.pre3MainYi}} / ${{t.pre3SuperYi}} 亿</b></div>
    <div class="pill">买后3日主/超<br><b>${{t.buyTo3MainYi}} / ${{t.buyTo3SuperYi}} 亿</b></div>
  </div>
  <div class="reason">买入：${{esc(t.buyReason)}}<br>卖出：${{esc(t.sellReason)}}</div></section>`;
}}
function pass(t){{
  if(strategy!=='all'&&t.strategy!==strategy) return false;
  if(ret==='win'&&t.returnPct<0) return false;
  if(ret==='loss'&&t.returnPct>=0) return false;
  if(query) {{
    const q=query.toLowerCase();
    if(!(`${{t.name}} ${{t.symbol}} ${{t.sector}} ${{t.buyReason}}`.toLowerCase().includes(q))) return false;
  }}
  return true;
}}
function render(){{
  const arr=DATA.trades.filter(pass);
  el('cards').innerHTML=arr.map(card).join('');
  const avg=arr.length?arr.reduce((a,b)=>a+b.returnPct,0)/arr.length:0;
  const d1=arr.length?arr.reduce((a,b)=>a+b.d1HighPct,0)/arr.length:0;
  const unit=flowMetric==='ratio'?'%':'亿';
  el('summary').innerHTML=`当前显示：${{arr.length}} / ${{DATA.count}} 笔；平均最终收益 ${{avg.toFixed(2)}}%；平均 D+1 最高冲高 ${{d1.toFixed(2)}}%。<br>当前资金柱：近${{flowWindow}}日滚动主力/超大单${{flowMetric==='ratio'?'净流入占成交额':'净流入净额'}}（单位：${{unit}}）。测算最强口径：${{DATA.flowTestSummary.bestFactor}} -> ${{DATA.flowTestSummary.target}}，Rank IC ${{DATA.flowTestSummary.rankIc}}，样本日 ${{DATA.flowTestSummary.sampleRows}}。`;
  document.querySelectorAll('.filter').forEach(b=>b.classList.toggle('active',b.dataset.strategy===strategy));
  document.querySelectorAll('.ret').forEach(b=>b.classList.toggle('active',b.dataset.ret===ret));
  document.querySelectorAll('.win').forEach(b=>b.classList.toggle('active',+b.dataset.window===flowWindow));
  document.querySelectorAll('.metric').forEach(b=>b.classList.toggle('active',b.dataset.metric===flowMetric));
  bindTips();
}}
function bindTips(){{
  document.querySelectorAll('.bar').forEach(b=>{{
    b.onmousemove=e=>{{
      const svg=b.closest('svg'), t=DATA.trades.find(x=>String(x.id)===svg.dataset.trade), r=t.rows[+b.dataset.i];
      const tip=el('tip'); tip.style.display='block'; tip.style.left=e.clientX+14+'px'; tip.style.top=e.clientY+14+'px';
      const suf=flowMetric==='ratio'?'Ratio':'Yi';
      const unit=flowMetric==='ratio'?'%':'亿';
      tip.innerHTML=`<b>${{t.name}} ${{t.symbol}}</b><br>${{r.date}}<br>开高低收：${{r.open}} / ${{r.high}} / ${{r.low}} / ${{r.close}}<br>成交额：${{r.amountYi}} 亿<br>当日主/超：${{r.mainYi}} / ${{r.superYi}} 亿<br>近${{flowWindow}}日主/超：${{r[`main${{flowWindow}}${{suf}}`]}} / ${{r[`super${{flowWindow}}${{suf}}`]}} ${{unit}}`;
    }};
    b.onmouseleave=()=>el('tip').style.display='none';
  }});
}}
document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{{strategy=b.dataset.strategy;render()}});
document.querySelectorAll('.ret').forEach(b=>b.onclick=()=>{{ret=b.dataset.ret;render()}});
document.querySelectorAll('.win').forEach(b=>b.onclick=()=>{{flowWindow=+b.dataset.window;render()}});
document.querySelectorAll('.metric').forEach(b=>b.onclick=()=>{{flowMetric=b.dataset.metric;render()}});
el('q').oninput=e=>{{query=e.target.value.trim();render()}};
render();
</script></body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(OUT)
    print(f"trades={len(trades)}")


if __name__ == "__main__":
    main()
