#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path('/Users/dong/Desktop/AIGC/market-live-terminal')
HEAT_DB = Path('/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db')
THEME_DB = Path('/Users/dong/Desktop/AIGC/market-data/market_heat/tradable_theme_map.db')
ATOMIC_DB = Path('/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_compact_current.db')
OUT_DIR = ROOT / 'docs/selection/market_heat/backtests'
DATA_OUT = ROOT / 'data/selection/market_heat/backtests'
START='2025-01-02'
END_SIGNAL='2026-03-31'
END='2026-04-30'


def qmarks(n): return ','.join(['?']*n)
def f(x,n=2): return '-' if x is None else f'{float(x):.{n}f}'
def clamp(x,lo=0,hi=1):
    try: x=float(x)
    except: return lo
    if math.isnan(x) or math.isinf(x): return lo
    return max(lo,min(hi,x))

def norm_symbol(s):
    if s.startswith(('sh','sz','bj')): return s
    if s.startswith(('6','9')): return 'sh'+s
    if s.startswith(('0','2','3')): return 'sz'+s
    if s.startswith(('4','8')): return 'bj'+s
    return s

hc=sqlite3.connect(f'file:{HEAT_DB}?mode=ro',uri=True); hc.row_factory=sqlite3.Row
tc=sqlite3.connect(f'file:{THEME_DB}?mode=ro',uri=True); tc.row_factory=sqlite3.Row
ac=sqlite3.connect(f'file:{ATOMIC_DB}?mode=ro',uri=True); ac.row_factory=sqlite3.Row
trade_dates=[r['trade_date'] for r in ac.execute('select distinct trade_date from atomic_trade_daily where trade_date between ? and ? order by trade_date',(START,END))]
date_idx={d:i for i,d in enumerate(trade_dates)}

# theme memberships cache
members_cache={}
def members_for_theme(theme_id):
    if theme_id in members_cache: return members_cache[theme_id]
    parts=theme_id.split(':')
    if len(parts)<3: return []
    typ,code=parts[1],parts[2]
    rows=tc.execute('select symbol,name from clean_stock_sector_memberships where sector_code=? and sector_type=?',(code,typ)).fetchall()
    out=[(norm_symbol(r['symbol']),r['name']) for r in rows]
    members_cache[theme_id]=out
    return out

# theme rank history
rank_hist=defaultdict(dict)
for r in hc.execute('select trade_date,theme_id,sector_name,hot_rank,hot_score,persistence_score,avg_return_1d,avg_return_5d,up_ratio,amount_ratio,l2_main_net_yi,l2_positive_ratio from fine_theme_heat_daily where trade_date between ? and ?',(START,END_SIGNAL)):
    rank_hist[r['theme_id']][r['trade_date']]=dict(r)

# candidate theme lead events: theme just entered top30/top15 after not being hot recently.
events=[]
for theme_id,hist in rank_hist.items():
    ds=sorted(hist)
    for d in ds:
        r=hist[d]
        if r['hot_rank']>30: continue
        i=date_idx.get(d)
        if i is None or i<10: continue
        prev_dates=trade_dates[max(0,i-10):i]
        prev_ranks=[hist[p]['hot_rank'] for p in prev_dates if p in hist]
        prev_top30=sum(1 for x in prev_ranks if x<=30)
        prev_top15=sum(1 for x in prev_ranks if x<=15)
        # 主题先动：最近不热，今天突然进入前30/15，并且不是纯单票弱扩散。
        is_new_top30=(r['hot_rank']<=30 and prev_top30==0)
        is_new_top15=(r['hot_rank']<=15 and prev_top15==0)
        if not (is_new_top30 or is_new_top15): continue
        if float(r['hot_score'] or 0)<80: continue
        if float(r['up_ratio'] or 0)<50: continue
        if float(r['amount_ratio'] or 0)<1.05: continue
        if float(r['l2_main_net_yi'] or 0)<=0: continue
        events.append({**r,'event_type':'new_top15' if is_new_top15 else 'new_top30'})

# load atomic rows for all symbols that appear in candidate events.
syms=sorted({s for e in events for s,_ in members_for_theme(e['theme_id'])})
rows_by_sym=defaultdict(list)
for i in range(0,len(syms),800):
    chunk=syms[i:i+800]
    for r in ac.execute(f'''select symbol,trade_date,open,high,low,close,total_amount,l2_main_net_amount,l2_super_net_amount
        from atomic_trade_daily where symbol in ({qmarks(len(chunk))}) and trade_date between '2024-11-01' and ? order by symbol,trade_date''',(*chunk,END)):
        rows_by_sym[r['symbol']].append(dict(r))
by={}
for sym,rows in rows_by_sym.items():
    for i,r in enumerate(rows):
        close=float(r['close']); prev=rows[i-1] if i>0 else None
        prev5=rows[i-5] if i>=5 else None
        prev20=rows[i-20] if i>=20 else None
        win20=rows[max(0,i-19):i+1]
        highs=[float(x['close']) for x in win20]
        lo,hi=min(highs),max(highs)
        pos=(close-lo)/(hi-lo) if hi>lo else None
        amt_prev=[float(x['total_amount'] or 0) for x in rows[max(0,i-20):i] if x.get('total_amount')]
        amt_base=sum(amt_prev)/len(amt_prev) if amt_prev else None
        ma10=sum(float(x['close']) for x in rows[max(0,i-9):i+1])/len(rows[max(0,i-9):i+1])
        ma20=sum(float(x['close']) for x in rows[max(0,i-19):i+1])/len(rows[max(0,i-19):i+1])
        by[(sym,r['trade_date'])]={
            **r,
            'ret1': (close/float(prev['close'])-1)*100 if prev else None,
            'ret5': (close/float(prev5['close'])-1)*100 if prev5 else None,
            'ret20': (close/float(prev20['close'])-1)*100 if prev20 else None,
            'pos20': pos,
            'amount_ratio': float(r['total_amount'] or 0)/amt_base if amt_base else None,
            'ma10': ma10,
            'ma20': ma20,
        }

def next_trade(d,n=1):
    i=date_idx.get(d)
    if i is None or i+n>=len(trade_dates): return None
    return trade_dates[i+n]

def score_lag_stock(st):
    # 个股滞后：主题热了，但它自己不能已经飞；要求有量/L2初步跟随。
    r1=st['ret1'] or 0; r5=st['ret5'] or 0; r20=st['ret20'] or 0; pos=st['pos20'] if st['pos20'] is not None else 0.5
    ar=st['amount_ratio'] or 1; l2=float(st['l2_main_net_amount'] or 0)/1e8; amt=float(st['total_amount'] or 0)/1e8
    score=0
    score += clamp((0.85-pos)/0.85)*20
    score += clamp((20-r20)/45)*16
    score += clamp((8-r5)/18)*12
    score += clamp((r1+2)/7)*8
    score += clamp((ar-0.8)/1.4)*16
    score += clamp((l2+0.05)/1.5)*20
    score += clamp(amt/15)*8
    return score

def simulate(sym,buy_date,end_date=END):
    if (sym,buy_date) not in by: return None
    buy=float(by[(sym,buy_date)]['open'])
    peak=buy; maxdd=0; neg_l2=0; sell_date=None; sell_price=None; reason=''
    for d in [x for x in trade_dates if buy_date<=x<=end_date]:
        st=by.get((sym,d))
        if not st: continue
        c=float(st['close']); peak=max(peak,c); dd=(c/peak-1)*100; maxdd=min(maxdd,dd)
        ret=(c/buy-1)*100; l2=float(st['l2_main_net_amount'] or 0)
        neg_l2=neg_l2+1 if l2<0 else 0
        # lead-lag策略更短：最多持20日；先看能不能捕捉补涨一段。
        held=len([x for x in trade_dates if buy_date<=x<=d])
        sig=None
        if ret<=-12: sig='硬止损：亏损超过12%'
        elif peak/buy-1>=0.12 and dd<=-8: sig='补涨止盈：收益曾超过12%，回撤超过8%'
        elif neg_l2>=3 and c<float(st['ma10']): sig='资金转弱：L2连续3日净流出且跌破MA10'
        elif held>=20: sig='时间止盈/止损：持有满20个交易日'
        if sig:
            nd=next_trade(d,1)
            if nd and (sym,nd) in by:
                sell_date=nd; sell_price=float(by[(sym,nd)]['open']); reason=f'{sig}；{d}收盘触发，次日开盘卖出'
            else:
                sell_date=d; sell_price=c; reason=f'{sig}；最后收盘卖出'
            break
    if sell_date is None:
        sell_date=END; sell_price=float(by[(sym,END)]['close']); reason='期末估值'
    hold=len([x for x in trade_dates if buy_date<=x<=sell_date])
    return sell_date,sell_price,(sell_price/buy-1)*100,maxdd,hold,reason,buy

candidates=[]
for e in events:
    d=e['trade_date']
    buy_date=next_trade(d,1)
    if not buy_date: continue
    ms=[]
    for sym,name in members_for_theme(e['theme_id']):
        st=by.get((sym,d))
        if not st: continue
        r5=st['ret5']; r20=st['ret20']; pos=st['pos20']; ar=st['amount_ratio']; l2=float(st['l2_main_net_amount'] or 0)/1e8
        if r5 is None or r20 is None or pos is None: continue
        # 核心：主题热，股票还没热。
        if r5>5: continue
        if r20>20: continue
        if pos>0.78: continue
        if (ar or 0)<0.9: continue
        if l2<0: continue
        ms.append((score_lag_stock(st),sym,name,st))
    ms.sort(key=lambda x:x[0],reverse=True)
    for rank,(sc,sym,name,st) in enumerate(ms[:3],1):
        sim=simulate(sym,buy_date)
        if not sim: continue
        sell_date,sell_price,ret,maxdd,hold,reason,buy=sim
        candidates.append({
            'event_date':d,'event_type':e['event_type'],'theme':e['sector_name'],'theme_rank':e['hot_rank'],'theme_hot':e['hot_score'],
            'symbol':sym,'name':name,'pick_rank':rank,'score':sc,'buy_date':buy_date,'buy_price':buy,'sell_date':sell_date,'sell_price':sell_price,
            'return_pct':ret,'maxdd':maxdd,'hold_days':hold,'sell_reason':reason,
            'stock_ret1':st['ret1'],'stock_ret5':st['ret5'],'stock_ret20':st['ret20'],'pos20':st['pos20'],'amount_ratio':st['amount_ratio'],'l2_yi':float(st['l2_main_net_amount'] or 0)/1e8,
        })

OUT_DIR.mkdir(parents=True,exist_ok=True); DATA_OUT.mkdir(parents=True,exist_ok=True)
csv_path=DATA_OUT/'theme_lead_stock_lag_2025_2026_trades.csv'
with csv_path.open('w',newline='',encoding='utf-8') as fcsv:
    w=csv.DictWriter(fcsv,fieldnames=list(candidates[0].keys()) if candidates else [])
    if candidates:
        w.writeheader(); w.writerows(candidates)
rets=[x['return_pct'] for x in candidates]
by_event=defaultdict(list)
for x in candidates:
    by_event[x['event_date']].append(x['return_pct'])
event_rets=[sum(v)/len(v) for v in by_event.values()]
md=OUT_DIR/'theme_lead_stock_lag_2025_2026.md'
lines=[]
lines.append('# 主题先动、个股滞后：lead-lag 探索回测')
lines.append('')
if candidates:
    lines.append(f"结论：扫描 `{len(events)}` 个新热点事件，选出 `{len(candidates)}` 笔滞后个股交易；单笔平均 `{mean(rets):.1f}%`，中位 `{median(rets):.1f}%`，胜率 `{len([r for r in rets if r>0])/len(rets)*100:.1f}%`。")
    lines.append('')
    lines.append('## 规则')
    lines.append('')
    lines.append('- 主题事件：小主题进入 Top30/Top15，且前10日没有同级别热度，热度>=80，上涨占比>=50%，量比>=1.05，L2为正。')
    lines.append('- 个股必须滞后：5日涨幅<=5%，20日涨幅<=20%，20日价格位置<=0.78，量比>=0.9，L2>=0。')
    lines.append('- 买入：主题事件次日开盘。')
    lines.append('- 卖出：亏损-12%、盈利后回撤8%、L2转弱跌破MA10、或持满20日。')
    lines.append('')
    lines.append('## 汇总')
    lines.append('')
    lines.append(f'- 主题事件数：`{len(events)}`')
    lines.append(f'- 交易数：`{len(candidates)}`')
    lines.append(f'- 单笔平均：`{mean(rets):.1f}%`')
    lines.append(f'- 单笔中位：`{median(rets):.1f}%`')
    lines.append(f'- 胜率：`{len([r for r in rets if r>0])/len(rets)*100:.1f}%`')
    lines.append(f'- 最大收益：`{max(rets):.1f}%`')
    lines.append(f'- 最大亏损：`{min(rets):.1f}%`')
    lines.append(f'- 按事件日均值：`{mean(event_rets):.1f}%`')
    lines.append('')
    lines.append('## 收益前20')
    lines.append('')
    lines.append('| 事件日 | 主题 | 股票 | 买入 | 卖出 | 收益 | 事件时个股状态 | 卖出逻辑 |')
    lines.append('|---|---|---|---:|---:|---:|---|---|')
    for x in sorted(candidates,key=lambda r:r['return_pct'],reverse=True)[:20]:
        lines.append(f"| {x['event_date']} | {x['theme']} Rank{x['theme_rank']} | {x['name']} `{x['symbol']}` | {x['buy_date']} {f(x['buy_price'],2)} | {x['sell_date']} {f(x['sell_price'],2)} | {f(x['return_pct'],1)}% | 5日{f(x['stock_ret5'],1)}%、20日{f(x['stock_ret20'],1)}%、位置{f(x['pos20'],2)}、L2 {f(x['l2_yi'],2)}亿 | {x['sell_reason']} |")
    lines.append('')
    lines.append('## 亏损前20')
    lines.append('')
    lines.append('| 事件日 | 主题 | 股票 | 买入 | 卖出 | 收益 | 事件时个股状态 | 卖出逻辑 |')
    lines.append('|---|---|---|---:|---:|---:|---|---|')
    for x in sorted(candidates,key=lambda r:r['return_pct'])[:20]:
        lines.append(f"| {x['event_date']} | {x['theme']} Rank{x['theme_rank']} | {x['name']} `{x['symbol']}` | {x['buy_date']} {f(x['buy_price'],2)} | {x['sell_date']} {f(x['sell_price'],2)} | {f(x['return_pct'],1)}% | 5日{f(x['stock_ret5'],1)}%、20日{f(x['stock_ret20'],1)}%、位置{f(x['pos20'],2)}、L2 {f(x['l2_yi'],2)}亿 | {x['sell_reason']} |")
else:
    lines.append('无候选。')
md.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(md)
print(csv_path)
print('events',len(events),'trades',len(candidates),'avg',mean(rets) if rets else None,'median',median(rets) if rets else None)
