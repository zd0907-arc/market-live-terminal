#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import sqlite3
from pathlib import Path
from statistics import mean

from backend.app.core.config import RESEARCH_CURRENT_ROOT


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_ROOT = Path(os.getenv("RESEARCH_CURRENT_ROOT", RESEARCH_CURRENT_ROOT))
HEAT_DB = Path(
    os.getenv(
        "FINE_THEME_HEAT_DB",
        str(DEFAULT_RESEARCH_ROOT / "market_heat" / "fine_theme_heat_daily.db"),
    )
)
THEME_DB = Path(
    os.getenv(
        "TRADABLE_THEME_MAP_DB",
        str(DEFAULT_RESEARCH_ROOT / "market_heat" / "tradable_theme_map.db"),
    )
)
ATOMIC_DB = Path(
    os.getenv(
        "ATOMIC_COMPACT_DB_PATH",
        os.getenv(
            "ATOMIC_MAINBOARD_DB_PATH",
            str(DEFAULT_RESEARCH_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"),
        ),
    )
)
OUT = ROOT / 'docs/selection/market_heat/fine_theme_heat_trend_2025_2026_top10.html'
START = '2025-01-02'
END = '2026-04-30'
WARMUP = '2024-08-01'


def qmarks(n: int) -> str:
    return ','.join(['?'] * n)


def norm_symbol(s: str) -> str:
    s = s or ''
    if s.startswith(('sh', 'sz', 'bj')):
        return s
    if s.startswith(('6', '9')):
        return 'sh' + s
    if s.startswith(('0', '2', '3')):
        return 'sz' + s
    if s.startswith(('4', '8')):
        return 'bj' + s
    return s


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if math.isnan(x) or math.isinf(x):
        return lo
    return max(lo, min(hi, x))


def avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def round_or_none(x, n=2):
    return None if x is None else round(float(x), n)


hc = sqlite3.connect(f'file:{HEAT_DB}?mode=ro', uri=True)
hc.row_factory = sqlite3.Row
# 先按整体热度排名取前10，再按相同口径取末尾10，用于对照。
all_ranked = hc.execute(
    '''
    with s as (
      select theme_id, sector_name,
             count(*) as top50_days,
             sum(case when hot_rank<=15 then 1 else 0 end) as top15_days,
             min(hot_rank) as best_rank,
             max(hot_score) as max_hot,
             min(case when hot_rank<=15 then trade_date end) as first_top15
      from fine_theme_heat_daily
      where trade_date between ? and ?
      group by theme_id, sector_name
    )
    select * from s
    order by top15_days desc, top50_days desc, best_rank asc, max_hot desc
    ''',
    (START, END),
).fetchall()
top = list(all_ranked[:10])
bottom = sorted(
    all_ranked,
    key=lambda r: (int(r['top15_days'] or 0), int(r['top50_days'] or 0), -int(r['best_rank'] or 999), float(r['max_hot'] or 0)),
)[:10]
# 防止极端情况下重复。
seen = {r['theme_id'] for r in top}
top = top + [r for r in bottom if r['theme_id'] not in seen]
theme_ids = [r['theme_id'] for r in top]

# 用交易库日期作为连续横轴。
ac = sqlite3.connect(f'file:{ATOMIC_DB}?mode=ro', uri=True)
ac.row_factory = sqlite3.Row
dates = [
    r['trade_date']
    for r in ac.execute(
        'select distinct trade_date from atomic_trade_daily where trade_date between ? and ? order by trade_date',
        (START, END),
    )
]

# 成员。fine_theme_heat_daily 的 theme_id 来自 clean_stock_sector_memberships，
# 形如 fine:industry:BK1592 / fine:concept:BKxxxx；不能用 tradable_theme_memberships。
tc = sqlite3.connect(f'file:{THEME_DB}?mode=ro', uri=True)
tc.row_factory = sqlite3.Row
members = {tid: [] for tid in theme_ids}
name_by_symbol = {}
for tid in theme_ids:
    parts = tid.split(':')
    if len(parts) >= 3:
        sector_type = parts[1]
        sector_code = parts[2]
        mem_rows = tc.execute(
            '''
            select symbol, name
            from clean_stock_sector_memberships
            where sector_code=? and sector_type=?
            order by symbol
            ''',
            (sector_code, sector_type),
        ).fetchall()
    else:
        mem_rows = []
    for r in mem_rows:
        sym = norm_symbol(r['symbol'])
        members[tid].append(sym)
        name_by_symbol[sym] = r['name']
all_symbols = sorted({s for arr in members.values() for s in arr})

# 原始交易数据，带 warmup 用于成交额倍率。
rows_by_symbol = {s: [] for s in all_symbols}
if all_symbols:
    for i in range(0, len(all_symbols), 800):
        chunk = all_symbols[i : i + 800]
        for r in ac.execute(
            f'''
            select symbol, trade_date, open, high, low, close, total_amount,
                   l2_main_net_amount, l2_super_net_amount
            from atomic_trade_daily
            where symbol in ({qmarks(len(chunk))}) and trade_date between ? and ?
            order by symbol, trade_date
            ''',
            (*chunk, WARMUP, END),
        ):
            rows_by_symbol[r['symbol']].append(dict(r))

by_sym_date = {}
for sym, rows in rows_by_symbol.items():
    for idx, r in enumerate(rows):
        prev = rows[idx - 1] if idx > 0 else None
        prev5 = rows[idx - 5] if idx >= 5 else None
        prev20_amounts = [float(x['total_amount'] or 0) for x in rows[max(0, idx - 20) : idx] if x.get('total_amount')]
        amt_base = sum(prev20_amounts) / len(prev20_amounts) if prev20_amounts else None
        close = float(r['close'])
        ret1 = (close / float(prev['close']) - 1) * 100 if prev and float(prev['close']) > 0 else None
        ret5 = (close / float(prev5['close']) - 1) * 100 if prev5 and float(prev5['close']) > 0 else None
        amt = float(r['total_amount'] or 0)
        by_sym_date[(sym, r['trade_date'])] = {
            'close': close,
            'ret1': ret1,
            'ret5': ret5,
            'amount': amt,
            'amount_ratio': amt / amt_base if amt_base and amt_base > 0 else None,
            'l2_main': float(r['l2_main_net_amount'] or 0),
            'l2_super': float(r['l2_super_net_amount'] or 0),
        }

# 原热度表只用于 tooltip 对照。
heat_rows = hc.execute(
    f'''
    select h.trade_date,h.theme_id,h.hot_rank,h.hot_score,h.leader_name,h.leader_return_1d,l.lifecycle_state
    from fine_theme_heat_daily h
    left join fine_theme_lifecycle_daily l on h.trade_date=l.trade_date and h.theme_id=l.theme_id
    where h.theme_id in ({qmarks(len(theme_ids))}) and h.trade_date between ? and ?
    ''',
    (*theme_ids, START, END),
).fetchall()
old_heat = {(r['theme_id'], r['trade_date']): r for r in heat_rows}

palette = ['#60a5fa','#f97316','#22c55e','#e879f9','#f43f5e','#14b8a6','#facc15','#a78bfa','#fb7185','#38bdf8','#84cc16','#f59e0b','#2dd4bf','#c084fc','#ef4444','#93c5fd','#d946ef','#10b981','#eab308','#06b6d4','#fb923c','#4ade80','#818cf8','#f472b6','#67e8f9','#bef264','#fdba74','#86efac','#c4b5fd','#f9a8d4']
series = []
for idx, r in enumerate(top):
    tid = r['theme_id']
    syms = members.get(tid, [])
    index = []
    price_ret = []
    cont_heat = []
    avg_ret1 = []
    avg_ret5 = []
    amount_ratio = []
    up_ratio = []
    l2_net_yi = []
    l2_pos_ratio = []
    strong_count = []
    limit_count = []
    old_rank = []
    old_score = []
    leader = []
    lifecycle = []
    val = 100.0
    for d in dates:
        rows = [by_sym_date.get((s, d)) for s in syms]
        rows = [x for x in rows if x]
        r1s = [x['ret1'] for x in rows if x['ret1'] is not None]
        r5s = [x['ret5'] for x in rows if x['ret5'] is not None]
        ar1 = avg(r1s) or 0.0
        ar5 = avg(r5s) or 0.0
        val *= 1 + ar1 / 100
        amounts = [x['amount'] for x in rows]
        amt_ratios = [x['amount_ratio'] for x in rows if x['amount_ratio'] is not None]
        l2s = [x['l2_main'] for x in rows]
        up = sum(1 for x in r1s if x > 0) / len(r1s) * 100 if r1s else 0.0
        l2pos = sum(1 for x in l2s if x > 0) / len(l2s) * 100 if l2s else 0.0
        strong = sum(1 for x in r1s if x >= 5)
        limit = sum(1 for x in r1s if x >= 9.8)
        l2_yi = sum(l2s) / 1e8
        n = max(len(rows), 1)
        # 连续热度：绝对分数，不再使用“全市场百分位 + Top50截断”。
        return_score = clamp((ar1 + 1.5) / 7.5) * 22
        trend_score = clamp((ar5 + 3.0) / 15.0) * 18
        volume_score = clamp(((avg(amt_ratios) or 1.0) - 0.75) / 1.25) * 18
        breadth_score = clamp(up / 100) * 14
        strong_score = clamp((strong + limit * 1.5) / max(3.0, n / 3.0)) * 14
        l2_score = clamp((l2pos - 35) / 65) * 8 + clamp((l2_yi / n + 0.03) / 0.18) * 6
        heat = return_score + trend_score + volume_score + breadth_score + strong_score + l2_score
        hr = old_heat.get((tid, d))
        index.append(round(val, 2))
        price_ret.append(round(ar1, 2))
        avg_ret1.append(round(ar1, 2))
        avg_ret5.append(round(ar5, 2))
        amount_ratio.append(round(avg(amt_ratios) or 1.0, 2))
        up_ratio.append(round(up, 1))
        l2_net_yi.append(round(l2_yi, 2))
        l2_pos_ratio.append(round(l2pos, 1))
        strong_count.append(strong)
        limit_count.append(limit)
        cont_heat.append(round(heat, 1))
        old_rank.append(int(hr['hot_rank']) if hr and hr['hot_rank'] is not None else None)
        old_score.append(round(float(hr['hot_score']), 1) if hr and hr['hot_score'] is not None else None)
        leader.append(hr['leader_name'] if hr else '')
        lifecycle.append(hr['lifecycle_state'] if hr else '')
    series.append({
        'themeId': tid,
        'name': r['sector_name'],
        'color': palette[idx % len(palette)],
        'memberCount': len(syms),
        'top15Days': int(r['top15_days'] or 0),
        'bestRank': int(r['best_rank'] or 999),
        'firstTop15': r['first_top15'] or '',
        'index': index,
        'priceRet': price_ret,
        'heat': cont_heat,
        'avgRet1': avg_ret1,
        'avgRet5': avg_ret5,
        'amountRatio': amount_ratio,
        'upRatio': up_ratio,
        'l2NetYi': l2_net_yi,
        'l2PosRatio': l2_pos_ratio,
        'strongCount': strong_count,
        'limitCount': limit_count,
        'oldRank': old_rank,
        'oldScore': old_score,
        'leader': leader,
        'lifecycle': lifecycle,
        'periodReturn': round(index[-1] - 100, 1),
        'maxIndex': round(max(index), 1),
        'maxHeat': round(max(cont_heat), 1),
    })

data = {'start': START, 'end': END, 'dates': dates, 'series': series}
json_data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>2026小颗粒热点连续热度与价格复盘</title>
<style>
:root{{--bg:#0b1020;--card:#11182b;--line:#26334f;--text:#e6edf7;--muted:#9fb0c8;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,"PingFang SC",sans-serif;}}
.wrap{{max-width:1420px;margin:0 auto;padding:22px}} h1{{font-size:24px;margin:0 0 8px}} .sub,.note{{color:var(--muted);line-height:1.7;font-size:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:14px 0;box-shadow:0 10px 28px rgba(0,0,0,.2)}}
.tags,.toolbar{{display:flex;flex-wrap:wrap;gap:8px}} button{{background:#101a2f;color:#d7e6fb;border:1px solid #2d3d5f;border-radius:9px;padding:7px 10px;cursor:pointer}} button.active{{background:#172554;box-shadow:inset 0 0 0 1px currentColor}} button small{{color:#9fb0c8}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} @media(max-width:1000px){{.grid{{grid-template-columns:1fr}}}}
.theme h3{{margin:0 0 4px;font-size:17px;display:flex;justify-content:space-between;gap:8px}} .meta{{color:#9fb0c8;font-size:12px;margin-bottom:8px}}
svg{{width:100%;height:auto;display:block;background:#0d1324;border-radius:9px}} .gridline{{stroke:#25314c;stroke-width:1}} .month{{stroke:#33415f;stroke-width:1;stroke-dasharray:4 4}} .axis{{fill:#8192b0;font-size:10px}} .price{{fill:none;stroke-width:3.4;opacity:.95}} .ma5{{fill:none;stroke:#ffffff;stroke-width:1.8;opacity:.58}} .ma10{{fill:none;stroke:#cbd5e1;stroke-width:1.4;opacity:.42;stroke-dasharray:5 4}} .heat{{fill:none;stroke:#facc15;stroke-width:1.8}} .heatfill{{fill:#facc15;opacity:.12}} .bar{{fill:#38bdf8;opacity:.38}} .dot{{stroke:#0d1324;stroke-width:1}}
.table{{width:100%;border-collapse:collapse;font-size:13px}} .table th,.table td{{border-bottom:1px solid #22304b;padding:7px 6px;text-align:right}} .table th:first-child,.table td:first-child{{text-align:left}}
.tip{{position:fixed;display:none;pointer-events:none;background:#07111f;border:1px solid #37506f;color:#e6edf7;border-radius:8px;padding:8px 10px;font-size:12px;line-height:1.6;max-width:360px;z-index:20}}
</style></head><body><div class="wrap"><h1>2025-2026 小颗粒热点：前10 vs 末尾10</h1>
<div class="sub">修正版：热度不再使用 Top50 截断值，而是对 Top10 主题逐日重算连续热度；价格指数为成员等权复合指数，起点=100，每个交易日都有。</div>
<div class="card note"><b>读法：</b>蓝柱+黄线=连续热度；彩色细线=原始板块价格指数；白线=价格MA5；灰色虚线=价格MA10。热度连续抬高且 MA5/MA10 上行，是趋势主线；热度尖峰后价格横/跌，是高潮兑现；价格横着但热度底部抬高，是低位补涨观察区。虚线点/tooltip 里保留原 Top50 排名作对照。</div>
<div class="card"><div class="toolbar"><button id="top10" class="active">Top10</button><button id="all30">全部20个</button><button id="clear">清空</button></div></div>
<div class="card"><div id="tags" class="tags"></div></div>
<div id="cards" class="grid"></div>
<div class="card"><table class="table" id="summary"></table></div></div><div id="tip" class="tip"></div>
<script>const DATA={json_data};</script>
<script>
const state={{active:new Set(DATA.series.slice(0,10).map(s=>s.name))}};
const el=id=>document.getElementById(id);
function fmt(x){{return x==null?'-':x}}
function path(vals,x,y){{let d=''; vals.forEach((v,i)=>{{if(v==null)return; d+=(d?'L':'M')+x(i)+','+y(v)}}); return d}}
function renderTags(){{const box=el('tags');box.innerHTML='';DATA.series.forEach((s,i)=>{{const b=document.createElement('button');b.className=state.active.has(s.name)?'active':'';b.style.color=s.color;b.innerHTML=`${{i+1}}. ${{s.name}} <small>Top15:${{s.top15Days}}｜涨:${{s.periodReturn}}%</small>`;b.onclick=()=>{{state.active.has(s.name)?state.active.delete(s.name):state.active.add(s.name);renderAll()}};box.appendChild(b)}})}}
function renderCard(s){{const W=660,H=260,L=46,R=14,T=18,B=28;const iw=W-L-R,ih=H-T-B;const pmin=Math.min(...s.index)*0.96,pmax=Math.max(...s.index)*1.04;const hmax=Math.max(80,...s.heat)*1.05;const x=i=>L+i/(DATA.dates.length-1)*iw;const yp=v=>T+(pmax-v)/(pmax-pmin)*ih;const yh=v=>T+(hmax-v)/(hmax)*ih;let html='';
[0,25,50,75,100].forEach(t=>{{const yy=yh(t);html+=`<line x1="${{L}}" y1="${{yy}}" x2="${{W-R}}" y2="${{yy}}" class="gridline"/><text x="4" y="${{yy+3}}" class="axis">热${{t}}</text>`}});
let last='';DATA.dates.forEach((d,i)=>{{const m=d.slice(5,7);if(m!==last){{last=m;html+=`<line x1="${{x(i)}}" y1="${{T}}" x2="${{x(i)}}" y2="${{H-B}}" class="month"/><text x="${{x(i)+3}}" y="${{H-8}}" class="axis">${{m}}月</text>`}}}});
s.heat.forEach((v,i)=>{{const bw=Math.max(2,iw/DATA.dates.length*.58), yy=yh(v); html+=`<rect class="bar" x="${{x(i)-bw/2}}" y="${{yy}}" width="${{bw}}" height="${{H-B-yy}}"/>`}});
const ma=(arr,n)=>arr.map((_,i)=>arr.slice(Math.max(0,i-n+1),i+1).reduce((a,b)=>a+b,0)/(i-Math.max(0,i-n+1)+1));
html+=`<path d="${{path(s.index,x,yp)}}" class="price" stroke="${{s.color}}"/><path d="${{path(ma(s.index,5),x,yp)}}" class="ma5"/><path d="${{path(ma(s.index,10),x,yp)}}" class="ma10"/><path d="${{path(s.heat,x,yh)}}" class="heat"/>`;
s.oldRank.forEach((r,i)=>{{if(r&&r<=15)html+=`<circle class="dot pt" cx="${{x(i)}}" cy="${{yp(s.index[i])}}" r="3.5" fill="${{s.color}}" data-name="${{s.name}}" data-i="${{i}}"/>`}});
html+=`<text x="${{W-92}}" y="16" class="axis">价指 ${{s.index[s.index.length-1]}}</text>`;return `<section class="card theme"><h3><span style="color:${{s.color}}">${{s.name}}</span><span>${{s.periodReturn}}%</span></h3><div class="meta">成员${{s.memberCount}}｜首次Top15：${{s.firstTop15||'-'}}｜最好Rank：${{s.bestRank}}｜最高连续热度：${{s.maxHeat}}</div><svg viewBox="0 0 ${{W}} ${{H}}">${{html}}</svg></section>`}}
function bindTips(){{document.querySelectorAll('.pt').forEach(pt=>{{pt.onmousemove=e=>{{const s=DATA.series.find(z=>z.name===pt.dataset.name),i=+pt.dataset.i,t=el('tip');t.style.display='block';t.style.left=e.clientX+14+'px';t.style.top=e.clientY+14+'px';t.innerHTML=`<b style="color:${{s.color}}">${{s.name}}</b><br>${{DATA.dates[i]}}｜原Rank:${{fmt(s.oldRank[i])}}｜原热度:${{fmt(s.oldScore[i])}}<br>连续热度:${{s.heat[i]}}｜价指:${{s.index[i]}}｜当日均涨:${{s.avgRet1[i]}}%｜5日均涨:${{s.avgRet5[i]}}%<br>量比:${{s.amountRatio[i]}}｜上涨占比:${{s.upRatio[i]}}%｜L2:${{s.l2NetYi[i]}}亿<br>龙头:${{s.leader[i]||'-'}}｜状态:${{s.lifecycle[i]||'-'}}`;}};pt.onmouseleave=()=>el('tip').style.display='none'}})}}
function renderCards(){{el('cards').innerHTML=DATA.series.filter(s=>state.active.has(s.name)).map(renderCard).join('');bindTips()}}
function renderSummary(){{el('summary').innerHTML='<tr><th>主题</th><th>成员</th><th>Top15天数</th><th>首次Top15</th><th>最好Rank</th><th>最高热度</th><th>价格指数涨幅</th></tr>'+DATA.series.map(s=>`<tr><td>${{s.name}}</td><td>${{s.memberCount}}</td><td>${{s.top15Days}}</td><td>${{s.firstTop15||'-'}}</td><td>${{s.bestRank}}</td><td>${{s.maxHeat}}</td><td>${{s.periodReturn}}%</td></tr>`).join('') }}
function renderAll(){{renderTags();renderCards();renderSummary();el('top10').classList.toggle('active',DATA.series.slice(0,10).every(s=>state.active.has(s.name))&&state.active.size===10)}}
el('top10').onclick=()=>{{state.active=new Set(DATA.series.slice(0,10).map(s=>s.name));renderAll()}};el('all30').onclick=()=>{{state.active=new Set(DATA.series.map(s=>s.name));renderAll()}};el('clear').onclick=()=>{{state.active.clear();renderAll()}};renderAll();
</script></body></html>'''
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding='utf-8')
print(OUT)
