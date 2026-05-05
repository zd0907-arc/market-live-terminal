#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/dong/Desktop/AIGC/market-live-terminal")
ATOMIC_DB = Path("/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db")
TRADES_CSV = ROOT / "data/selection/market_heat/backtests/hot_theme_strategy_variants_2025-01_2026-03_trades.csv"
OUT = ROOT / "docs/selection/market_heat/backtests/hot_theme_strategy_variants_trade_charts_2025_2026.html"
START = "2025-01-02"
END = "2026-04-30"


def qmarks(n: int) -> str:
    return ",".join(["?"] * n)


def safe_float(v, default=0.0):
    try:
        if v in ("", None):
            return default
        return float(v)
    except Exception:
        return default


def main() -> None:
    trades = list(csv.DictReader(TRADES_CSV.open(encoding="utf-8")))
    symbols = sorted({r["symbol"] for r in trades})
    by_symbol_trades = defaultdict(list)
    for r in trades:
        by_symbol_trades[r["symbol"]].append(
            {
                "strategy": r["strategy"],
                "decisionDate": r["decision_date"],
                "sector": r["sector_name"],
                "name": r["name"],
                "symbol": r["symbol"],
                "buyDate": r["buy_date"],
                "buyPrice": round(safe_float(r["buy_price"]), 3),
                "sellDate": r["sell_date"],
                "sellPrice": round(safe_float(r["sell_price"]), 3),
                "returnPct": round(safe_float(r["return_pct"]), 2),
                "holdDays": int(safe_float(r["hold_days"])),
                "maxDrawdownPct": round(safe_float(r["max_drawdown_pct"]), 2),
                "buyReason": r["buy_reason"],
                "sellReason": r["sell_reason"],
            }
        )

    ac = sqlite3.connect(f"file:{ATOMIC_DB}?mode=ro", uri=True)
    ac.row_factory = sqlite3.Row
    dates = [
        r["trade_date"]
        for r in ac.execute(
            "select distinct trade_date from atomic_trade_daily where trade_date between ? and ? order by trade_date",
            (START, END),
        )
    ]
    price_rows = []
    for i in range(0, len(symbols), 800):
        chunk = symbols[i : i + 800]
        price_rows += ac.execute(
            f"""
            select symbol, trade_date, close
            from atomic_trade_daily
            where symbol in ({qmarks(len(chunk))}) and trade_date between ? and ?
            order by symbol, trade_date
            """,
            (*chunk, START, END),
        ).fetchall()

    close = {(r["symbol"], r["trade_date"]): float(r["close"]) for r in price_rows}
    stocks = []
    for sym in symbols:
        trs = sorted(by_symbol_trades[sym], key=lambda x: (x["buyDate"], x["strategy"]))
        name = trs[0]["name"]
        prices = [round(close[(sym, d)], 3) if (sym, d) in close else None for d in dates]
        valid = [x for x in prices if x is not None]
        if not valid:
            continue
        stocks.append(
            {
                "symbol": sym,
                "name": name,
                "prices": prices,
                "trades": trs,
                "tradeCount": len(trs),
                "bestReturn": max(t["returnPct"] for t in trs),
                "avgReturn": round(sum(t["returnPct"] for t in trs) / len(trs), 2),
                "firstBuy": min(t["buyDate"] for t in trs),
            }
        )
    stocks.sort(key=lambda x: (x["firstBuy"], x["symbol"]))

    data = {"start": START, "end": END, "dates": dates, "stocks": stocks}
    json_data = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>热点策略回测交易图谱</title>
<style>
:root{{--bg:#0b1020;--card:#11182b;--line:#26334f;--text:#e6edf7;--muted:#9fb0c8;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,"PingFang SC",sans-serif}}
.wrap{{max-width:1440px;margin:0 auto;padding:22px}} h1{{font-size:24px;margin:0 0 8px}} .sub{{color:var(--muted);line-height:1.7;font-size:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:14px 0;box-shadow:0 10px 28px rgba(0,0,0,.2)}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}} button{{background:#101a2f;color:#d7e6fb;border:1px solid #2d3d5f;border-radius:9px;padding:7px 10px;cursor:pointer}} button.active{{box-shadow:inset 0 0 0 1px currentColor;background:#172554}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;color:#cbd5e1;font-size:13px}} .dot{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px;vertical-align:-1px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} @media(max-width:1000px){{.grid{{grid-template-columns:1fr}}}}
.stock h3{{margin:0 0 4px;font-size:16px;display:flex;justify-content:space-between;gap:8px}} .meta{{color:#9fb0c8;font-size:12px;margin-bottom:8px;line-height:1.5}}
svg{{width:100%;height:auto;display:block;background:#0d1324;border-radius:9px}} .gridline{{stroke:#25314c;stroke-width:1}} .month{{stroke:#33415f;stroke-width:1;stroke-dasharray:4 4}} .axis{{fill:#8192b0;font-size:10px}}
.price{{fill:none;stroke:#e5e7eb;stroke-width:2.1;opacity:.9}} .buy{{stroke:#0d1324;stroke-width:1.1}} .sell{{stroke:#0d1324;stroke-width:1.1}}
.trade-line{{stroke-width:1.5;stroke-dasharray:4 3;opacity:.72}} .table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}} .table td,.table th{{border-bottom:1px solid #22304b;padding:5px 4px;text-align:right}} .table td:first-child,.table th:first-child{{text-align:left}}
.tip{{position:fixed;display:none;pointer-events:none;background:#07111f;border:1px solid #37506f;color:#e6edf7;border-radius:8px;padding:8px 10px;font-size:12px;line-height:1.55;max-width:420px;z-index:20}}
</style></head><body><div class="wrap">
<h1>热点策略回测交易图谱：2025-01 至 2026-04</h1>
<div class="sub">每只被三版策略选中过的股票一张图；全时间线为 2025-01-02 至 2026-04-30。圆点=买入，倒三角=卖出，同色虚线连接一次交易。</div>
<div class="card">
  <div class="toolbar">
    <button class="filter active" data-strategy="all">全部策略</button>
    <button class="filter" data-strategy="attack">进攻版</button>
    <button class="filter" data-strategy="low_position">低位补涨版</button>
    <button class="filter" data-strategy="pullback_confirm">回踩确认版</button>
  </div>
</div>
<div class="card legend">
  <span><i class="dot" style="background:#ef4444"></i>进攻版</span>
  <span><i class="dot" style="background:#22c55e"></i>低位补涨版</span>
  <span><i class="dot" style="background:#facc15"></i>回踩确认版</span>
  <span>灰白线：股票收盘价</span>
</div>
<div class="card"><div id="summary" class="sub"></div></div>
<div id="cards" class="grid"></div>
</div><div id="tip" class="tip"></div>
<script>const DATA={json_data};</script>
<script>
const colors={{attack:'#ef4444',low_position:'#22c55e',pullback_confirm:'#facc15'}};
const labels={{attack:'进攻版',low_position:'低位补涨版',pullback_confirm:'回踩确认版'}};
let active='all';
const el=id=>document.getElementById(id);
function idxOfDate(d){{return DATA.dates.indexOf(d)}}
function esc(s){{return String(s||'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function path(vals,x,y){{let d='',open=false; vals.forEach((v,i)=>{{if(v==null){{open=false;return}}; if(!open){{d+='M'+x(i)+','+y(v);open=true}}else d+='L'+x(i)+','+y(v)}}); return d}}
function renderStock(s){{
  const trades=s.trades.filter(t=>active==='all'||t.strategy===active);
  if(!trades.length) return '';
  const W=660,H=260,L=48,R=16,T=18,B=28,iw=W-L-R,ih=H-T-B;
  const vals=s.prices.filter(v=>v!=null), min=Math.min(...vals)*0.94, max=Math.max(...vals)*1.06;
  const x=i=>L+i/(DATA.dates.length-1)*iw, y=v=>T+(max-v)/(max-min)*ih;
  let html='';
  for(let k=0;k<=4;k++){{const yy=T+ih*k/4; html+=`<line x1="${{L}}" y1="${{yy}}" x2="${{W-R}}" y2="${{yy}}" class="gridline"/><text x="4" y="${{yy+3}}" class="axis">${{(max-(max-min)*k/4).toFixed(1)}}</text>`}}
  let last=''; DATA.dates.forEach((d,i)=>{{const m=d.slice(0,7); if(m!==last && d.slice(5,7)==='01'){{last=m; html+=`<line x1="${{x(i)}}" y1="${{T}}" x2="${{x(i)}}" y2="${{H-B}}" class="month"/><text x="${{x(i)+3}}" y="${{H-8}}" class="axis">${{d.slice(0,4)}}</text>`}} }});
  html+=`<path d="${{path(s.prices,x,y)}}" class="price"/>`;
  trades.forEach((t,ti)=>{{
    const bi=idxOfDate(t.buyDate), si=idxOfDate(t.sellDate); if(bi<0||si<0) return;
    const c=colors[t.strategy], by=y(t.buyPrice), sy=y(t.sellPrice), bx=x(bi), sx=x(si);
    html+=`<line x1="${{bx}}" y1="${{by}}" x2="${{sx}}" y2="${{sy}}" stroke="${{c}}" class="trade-line"/>`;
    html+=`<circle class="buy mark" cx="${{bx}}" cy="${{by}}" r="5" fill="${{c}}" data-symbol="${{s.symbol}}" data-trade="${{ti}}" data-kind="buy"/>`;
    html+=`<path class="sell mark" d="M ${{sx-6}} ${{sy-5}} L ${{sx+6}} ${{sy-5}} L ${{sx}} ${{sy+6}} Z" fill="${{c}}" data-symbol="${{s.symbol}}" data-trade="${{ti}}" data-kind="sell"/>`;
  }});
  const rows=trades.map(t=>`<tr><td><span style="color:${{colors[t.strategy]}}">${{labels[t.strategy]}}</span></td><td>${{t.buyDate}} ${{t.buyPrice}}</td><td>${{t.sellDate}} ${{t.sellPrice}}</td><td>${{t.holdDays}}</td><td style="color:${{t.returnPct>=0?'#ef4444':'#22c55e'}}">${{t.returnPct}}%</td></tr>`).join('');
  return `<section class="card stock"><h3><span>${{s.name}} <code>${{s.symbol}}</code></span><span>${{trades.length}}笔</span></h3><div class="meta">首次买入：${{s.firstBuy}}｜该股策略平均：${{s.avgReturn}}%｜最好：${{s.bestReturn}}%</div><svg viewBox="0 0 ${{W}} ${{H}}">${{html}}</svg><table class="table"><tr><th>策略</th><th>买入</th><th>卖出</th><th>持股日</th><th>收益</th></tr>${{rows}}</table></section>`;
}}
function render(){{
  const cards=DATA.stocks.map(renderStock).filter(Boolean);
  el('cards').innerHTML=cards.join('');
  const tradeCount=DATA.stocks.flatMap(s=>s.trades).filter(t=>active==='all'||t.strategy===active).length;
  el('summary').innerHTML=`当前显示：${{cards.length}} 只股票，${{tradeCount}} 笔交易。`;
  document.querySelectorAll('.filter').forEach(b=>b.classList.toggle('active',b.dataset.strategy===active));
  bindTips();
}}
function bindTips(){{
  document.querySelectorAll('.mark').forEach(m=>{{
    m.onmousemove=e=>{{
      const s=DATA.stocks.find(x=>x.symbol===m.dataset.symbol);
      const visible=s.trades.filter(t=>active==='all'||t.strategy===active);
      const t=visible[+m.dataset.trade] || s.trades[+m.dataset.trade];
      const tip=el('tip'); tip.style.display='block'; tip.style.left=e.clientX+14+'px'; tip.style.top=e.clientY+14+'px';
      tip.innerHTML=`<b>${{s.name}} ${{s.symbol}}</b><br><span style="color:${{colors[t.strategy]}}">${{labels[t.strategy]}}</span>｜${{t.sector}}｜决策日 ${{t.decisionDate}}<br>买入：${{t.buyDate}} ${{t.buyPrice}}｜卖出：${{t.sellDate}} ${{t.sellPrice}}<br>持股：${{t.holdDays}}日｜收益：${{t.returnPct}}%｜最大回撤：${{t.maxDrawdownPct}}%<br><b>买入逻辑</b>：${{esc(t.buyReason)}}<br><b>卖出逻辑</b>：${{esc(t.sellReason)}}`;
    }};
    m.onmouseleave=()=>el('tip').style.display='none';
  }});
}}
document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{{active=b.dataset.strategy;render()}});
render();
</script></body></html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(OUT)
    print(f"stocks={len(stocks)} trades={len(trades)}")


if __name__ == "__main__":
    main()
