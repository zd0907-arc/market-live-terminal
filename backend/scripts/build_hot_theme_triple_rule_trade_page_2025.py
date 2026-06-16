#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path("/Users/dong/ZhangData/market-live-terminal")
BASE_SCRIPT = ROOT / "backend/scripts/backtest_hot_theme_rule_pack_portfolio_2025.py"
OUT_MD = ROOT / "docs/selection/market_heat/backtests/hot_theme_triple_rule_operations_2025.md"
OUT_HTML = ROOT / "docs/selection/market_heat/backtests/hot_theme_triple_rule_trades_2025.html"
OUT_CSV = ROOT / "data/selection/market_heat/backtests/hot_theme_triple_rule_operations_2025.csv"


def load_base_module():
    spec = importlib.util.spec_from_file_location("rule_pack", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trade_final_date(trade: dict) -> str:
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", trade["final_sell"])
    return dates[-1] if dates else trade["buy_date"]


def trade_final_reason(trade: dict) -> str:
    return trade["final_sell"]


def main() -> None:
    base = load_base_module()
    cases = base.attach_windows(base.load_cases())
    triple_cases = [c for c in cases if len(c["rules"]) >= 3]
    trades, skipped, capital = base.run_portfolio(triple_cases)

    by_key = {(t["symbol"], t["event_date"]): t for t in trades}
    chart_cases = []
    for c in triple_cases:
        t = by_key.get((c["symbol"], c["eventDate"]))
        if not t:
            continue
        chart_cases.append(
            {
                "eventDate": c["eventDate"],
                "theme": c["theme"],
                "rules": c["ruleLabel"],
                "symbol": c["symbol"],
                "name": c["name"],
                "buyDate": t["buy_date"],
                "buyPrice": round(t["buy_price"], 3),
                "firstSellDate": t["first_sell_date"],
                "firstSellPrice": round(t["first_sell_price"], 3),
                "sellDate": trade_final_date(t),
                "returnPct": round(t["return_pct"], 2),
                "finalSell": t["final_sell"],
                "maxDrawdownPct": round(t["max_drawdown_pct"], 2),
                "fwd20HighPct": round(t["fwd20_high_pct"], 2),
                "window": c["window"],
            }
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_date",
        "rules",
        "theme",
        "symbol",
        "name",
        "buy_date",
        "buy_price",
        "start_capital",
        "end_capital",
        "return_pct",
        "first_sell_date",
        "first_sell_price",
        "final_sell",
        "max_drawdown_pct",
        "fwd20_high_pct",
        "score",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(trades)

    lines = ["# 三规则都命中：2025 操作清单", ""]
    lines.append(
        f"结论：三条规则都命中时，2025 年 100万单账户最终 `{capital/10000:.2f}万`，收益 `{(capital/base.INITIAL_CAPITAL-1)*100:.1f}%`。"
    )
    lines += [
        "",
        "## 操作规则",
        "",
        "- 入场：热点确认日次一交易日开盘买入；若开盘接近涨停，按买不到跳过。",
        "- 仓位：单账户全仓一笔；资金未出来时，后续机会全部错过。",
        "- 第一卖点：买入后最高价触达 +10%，按 +10% 价格卖一半。",
        "- 剩余卖点：移动止盈、L2转弱、10日时间退出；跌停开盘卖不出则顺延。",
        "- 成本：佣金万2.5、最低5元、卖出印花税万5、过户费万0.1。",
        "",
        "## 操作清单",
        "",
        "| 序号 | 热点日 | 股票 | 主题 | 买入 | 第一止盈 | 最终卖出 | 收益 | 资金变化 | 备注 |",
        "|---:|---|---|---|---:|---:|---|---:|---:|---|",
    ]
    for i, t in enumerate(trades, start=1):
        first_sell = (
            f"{t['first_sell_date']} {t['first_sell_price']:.2f}"
            if t["first_sell_date"]
            else "未触发"
        )
        lines.append(
            f"| {i} | {t['event_date']} | {t['name']} `{t['symbol']}` | {t['theme']} | "
            f"{t['buy_date']} {t['buy_price']:.2f} | {first_sell} | "
            f"{trade_final_date(t)} | {t['return_pct']:.1f}% | {t['start_capital']:,.0f} -> {t['end_capital']:,.0f} | "
            f"{html.escape(trade_final_reason(t))} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    data = {
        "capital": round(capital, 2),
        "returnPct": round((capital / base.INITIAL_CAPITAL - 1) * 100, 2),
        "trades": chart_cases,
    }
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>三规则都命中：2025 交易图</title>
<style>
body{{margin:0;background:#08101d;color:#e6edf7;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",Arial,sans-serif}}
.wrap{{max-width:1440px;margin:auto;padding:22px}}h1{{font-size:22px;margin:0 0 8px}}.sub{{color:#9fb0c8;font-size:13px;line-height:1.7}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:12px}}@media(max-width:1050px){{.grid{{grid-template-columns:1fr}}}}
.card{{background:#101827;border:1px solid #263244;border-radius:10px;padding:13px 14px}}h3{{margin:0 0 6px;font-size:15px;display:flex;justify-content:space-between;gap:8px}}
code{{color:#bfdbfe}}.meta,.reason{{font-size:12px;color:#a9b6c9;line-height:1.55}}.good{{color:#fb7185}}.bad{{color:#4ade80}}
svg{{width:100%;height:auto;background:#0b1220;border-radius:8px;margin-top:8px;display:block}}.gridline{{stroke:#233047;stroke-width:1}}.axis{{fill:#8391a7;font-size:10px}}
.wick{{stroke-width:1.2}}.close-line{{fill:none;stroke:#e5e7eb;stroke-width:1.8;opacity:.9}}
.eventline{{stroke:#facc15;stroke-width:1.5;stroke-dasharray:4 3}}.buyline{{stroke:#a78bfa;stroke-width:1.7}}.firstsellline{{stroke:#f97316;stroke-width:1.7;stroke-dasharray:4 2}}.sellline{{stroke:#38bdf8;stroke-width:1.7}}
.zero{{stroke:#94a3b8;stroke-width:1;stroke-dasharray:3 3;opacity:.75}}.legend{{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;font-size:12px;color:#b9c5d6}}.pill{{background:#0b1322;border:1px solid #24344e;border-radius:7px;padding:5px 7px}}
</style></head><body><div class="wrap">
<h1>三规则都命中：2025 交易图</h1>
<div class="sub">只保留同时命中：强者恒强、事件日强+价格先行、事件日强+前5超强资金。黄色=热点日，紫色=买入，橙色=+10%半仓，蓝色=最终清仓；下方柱子为近5日超大单累计占成交额。</div>
<div class="sub">100万最终：<b>${{DATA.capital.toLocaleString()}}</b>，收益：<b>${{DATA.returnPct}}%</b></div>
<div id="cards" class="grid"></div></div><script>const DATA={js};</script>
<script>
function idx(rows,d){{return rows.findIndex(x=>x.date===d)}}
function path(vals,x,y){{let d='';vals.forEach((v,i)=>d+=(i?'L':'M')+x(i)+','+y(v));return d}}
function esc(s){{return String(s||'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function chart(c){{
 const rows=c.window,W=690,H=310,L=44,R=14,T=14,B=28,priceH=184,barTop=222,barH=58,n=rows.length;
 const pmin=Math.min(...rows.map(r=>r.low))*0.985,pmax=Math.max(...rows.map(r=>r.high))*1.015;
 const fmax=Math.max(0.01,...rows.map(r=>Math.abs(r.super5Ratio||0)))*1.15;
 const x=i=>L+(n===1?0:i/(n-1))*(W-L-R), step=n>1?(W-L-R)/(n-1):12, cw=Math.max(3,Math.min(9,step*.55));
 const py=v=>T+(pmax-v)/(pmax-pmin)*priceH, fy=v=>barTop+barH/2-(v/fmax)*(barH/2);
 let s='';
 for(let k=0;k<=4;k++){{const yy=T+priceH*k/4;s+=`<line x1="${{L}}" y1="${{yy}}" x2="${{W-R}}" y2="${{yy}}" class="gridline"/><text x="4" y="${{yy+3}}" class="axis">${{(pmax-(pmax-pmin)*k/4).toFixed(1)}}</text>`}}
 s+=`<line x1="${{L}}" y1="${{fy(0)}}" x2="${{W-R}}" y2="${{fy(0)}}" class="zero"/>`;
 rows.forEach((r,i)=>{{const up=r.close>=r.open,col=up?'#ef4444':'#22c55e',xx=x(i);s+=`<line x1="${{xx}}" y1="${{py(r.high)}}" x2="${{xx}}" y2="${{py(r.low)}}" stroke="${{col}}" class="wick"/><rect x="${{xx-cw/2}}" y="${{py(Math.max(r.open,r.close))}}" width="${{cw}}" height="${{Math.max(2,Math.abs(py(r.open)-py(r.close)))}}" fill="${{col}}" opacity=".72"/>`;const v=r.super5Ratio||0,y0=fy(0),yv=fy(v);s+=`<rect x="${{xx-cw*.55}}" y="${{Math.min(y0,yv)}}" width="${{cw*1.1}}" height="${{Math.max(1,Math.abs(yv-y0))}}" fill="${{v>=0?'#f43f5e':'#16a34a'}}" opacity=".82"/>`;}})
 s+=`<path d="${{path(rows.map(r=>r.close),x,py)}}" class="close-line"/>`;
 [['eventDate','eventline'],['buyDate','buyline'],['firstSellDate','firstsellline'],['sellDate','sellline']].forEach(a=>{{const i=idx(rows,c[a[0]]);if(i>=0)s+=`<line x1="${{x(i)}}" y1="${{T}}" x2="${{x(i)}}" y2="${{H-B}}" class="${{a[1]}}"/>`;}})
 rows.forEach((r,i)=>{{if(i%Math.ceil(n/6)===0||r.date===c.eventDate||r.date===c.buyDate||r.date===c.sellDate)s+=`<text x="${{x(i)-24}}" y="${{H-8}}" class="axis">${{r.date.slice(5)}}</text>`}})
 return `<svg viewBox="0 0 ${{W}} ${{H}}">${{s}}</svg>`;
}}
function card(c,i){{return `<section class="card"><h3><span>${{i+1}}. ${{esc(c.name)}} <code>${{c.symbol}}</code></span><span class="${{c.returnPct>=0?'good':'bad'}}">${{c.returnPct}}%</span></h3><div class="meta">${{esc(c.theme)}}<br>热点 ${{c.eventDate}}｜买入 ${{c.buyDate}} ${{c.buyPrice}}｜半仓 ${{c.firstSellDate}} ${{c.firstSellPrice}}｜清仓 ${{c.sellDate}}｜后20高 ${{c.fwd20HighPct}}%</div>${{chart(c)}}<div class="legend"><span class="pill">黄=热点</span><span class="pill">紫=买入</span><span class="pill">橙=半仓</span><span class="pill">蓝=清仓</span></div><div class="reason">${{esc(c.finalSell)}}</div></section>`}}
document.getElementById('cards').innerHTML=DATA.trades.map(card).join('');
</script></body></html>"""
    OUT_HTML.write_text(page, encoding="utf-8")
    print(OUT_MD)
    print(OUT_HTML)
    print(OUT_CSV)
    print("final", capital, "trades", len(trades), "skipped", len(skipped))


if __name__ == "__main__":
    main()
