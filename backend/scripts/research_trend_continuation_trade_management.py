from __future__ import annotations

import json, sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Optional, List
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window, _apply_buy_costs, _apply_sell_costs, _is_limit_up_day
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.run_strategy_v1_trend_reversal import add_ma
from backend.scripts.run_strategy_v1_2_exit_grid import V12ExitParams
from backend.scripts.research_strong_runup_opportunity_audit import build_all_runups
from backend.scripts.research_trend_continuation_strategy import STABLE_TRADES, future_days_after_entry

OUT=Path('docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-trade-management')
PROTO=Path('docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-prototype/trend_continuation_candidates.csv')
BUYPOINT=Path('docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-buy-point-v1/callback_only/confirmed_buy_points.csv')

@dataclass(frozen=True)
class EarlyRule:
    name: str
    first_days: int
    cum_super_ratio: float
    cum_main_ratio: float
    close_return: float
    drawdown: float

RULES=[
    EarlyRule('no_early',0,-9,-9,-99,-99),
    EarlyRule('early_capital_escape_soft',3,-0.006,-0.008,-1.0,-5.0),
    EarlyRule('early_capital_escape_mid',3,-0.010,-0.012,-2.0,-6.0),
    EarlyRule('early_capital_escape_hard',5,-0.015,-0.018,-3.0,-7.0),
]


def simulate(g:pd.DataFrame, signal_date:str, rule:EarlyRule, cost:SelectionV2Params)->Optional[Dict[str,Any]]:
    future=g[g.trade_date>signal_date]
    if future.empty: return None
    entry_i=int(future.index[0]); entry=g.loc[entry_i]
    if _is_limit_up_day(entry,cost): return {'skipped':True,'skip_reason':'entry_blocked_limit_up'}
    gross_entry=float(entry.open)
    if gross_entry<=0: return None
    entry_price=_apply_buy_costs(gross_entry,cost)
    rows=g.loc[entry_i:].copy()
    cum_super=cum_main=cum_amount=0.0
    cum_super_peak=0.0; prev_cum_super=None; decline=0
    holding=0; max_runup=-999.0; max_drawdown=999.0
    exit_signal=None; exit_reason='window_end'
    p=V12ExitParams(stop_loss_pct=-8.0, super_peak_drawdown_pct=0.20, super_decline_days=3)
    final={}
    for _,row in rows.iterrows():
        holding+=1
        high=float(row.high); low=float(row.low); close=float(row.close); amount=float(row.total_amount or 0)
        daily_super=float(row.l2_super_net_amount or 0); daily_main=float(row.l2_main_net_amount or 0)
        cum_amount+=amount; cum_super+=daily_super; cum_main+=daily_main
        decline = decline+1 if prev_cum_super is not None and cum_super<prev_cum_super else 0
        prev_cum_super=cum_super
        cum_super_peak=max(cum_super_peak,cum_super)
        peak_dd=(max(0,cum_super_peak-cum_super)/cum_super_peak) if cum_super_peak>0 else 0
        daily_out=max(0,-daily_super)/max(cum_amount,1)
        max_runup=max(max_runup,(high/gross_entry-1)*100)
        max_drawdown=min(max_drawdown,(low/gross_entry-1)*100)
        close_ret=(close/gross_entry-1)*100
        final={'final_cum_super_amount':round(cum_super,2),'final_cum_main_amount':round(cum_main,2),'final_cum_super_ratio':round(cum_super/max(cum_amount,1),5),'final_cum_main_ratio':round(cum_main/max(cum_amount,1),5),'final_super_peak_drawdown_pct':round(peak_dd*100,2),'final_super_decline_streak':int(decline)}
        if rule.first_days>0 and holding<=rule.first_days:
            super_ratio=cum_super/max(cum_amount,1); main_ratio=cum_main/max(cum_amount,1)
            if super_ratio<=rule.cum_super_ratio and main_ratio<=rule.cum_main_ratio and close_ret<=rule.close_return and max_drawdown<=rule.drawdown:
                exit_signal=str(row.trade_date); exit_reason=rule.name; break
        if close_ret<=p.stop_loss_pct:
            exit_signal=str(row.trade_date); exit_reason='hard_stop_8pct'; break
        if cum_super_peak>0 and decline>=p.super_decline_days and peak_dd>=p.super_peak_drawdown_pct:
            exit_signal=str(row.trade_date); exit_reason='cum_super_peak_dd_20pct_3d'; break
        if cum_super_peak>0 and daily_super<0 and daily_out>=p.daily_super_outflow_cum_amount_ratio and peak_dd>=min(0.15,p.super_peak_drawdown_pct):
            exit_signal=str(row.trade_date); exit_reason='violent_super_outflow'; break
        if holding>=p.max_holding_days:
            exit_signal=str(row.trade_date); exit_reason='max_holding_days'; break
    if exit_signal:
        exit_next=g[g.trade_date>exit_signal]
        gross_exit=float(exit_next.iloc[0].open) if not exit_next.empty else float(g[g.trade_date==exit_signal].iloc[0].close)
        exit_date=str(exit_next.iloc[0].trade_date) if not exit_next.empty else exit_signal
    else:
        last=rows.iloc[-1]; gross_exit=float(last.close); exit_signal=str(last.trade_date); exit_date=exit_signal
    exit_price=_apply_sell_costs(gross_exit,cost)
    return {'entry_signal_date':signal_date,'entry_date':str(entry.trade_date),'gross_entry_price':round(gross_entry,4),'exit_signal_date':exit_signal,'exit_date':exit_date,'gross_exit_price':round(gross_exit,4),'return_pct':round((gross_exit/gross_entry-1)*100,2),'net_return_pct':round((exit_price/entry_price-1)*100,2),'max_runup_pct':round(max_runup,2),'max_drawdown_pct':round(max_drawdown,2),'holding_days':holding,'exit_reason':exit_reason,**final}


def run_set(name:str, signals:pd.DataFrame, date_col:str, by_symbol:dict[str,pd.DataFrame], runups:pd.DataFrame, stable_syms:set[str]):
    rows=[]; cost=SelectionV2Params()
    for rule in RULES:
        trades=[]
        for _,rec in signals.iterrows():
            sym=str(rec.symbol); g=by_symbol.get(sym)
            if g is None: continue
            tr=simulate(g,str(rec[date_col]),rule,cost)
            if not tr or tr.get('skipped'): continue
            fdays=future_days_after_entry(g,str(tr['entry_date']))
            trades.append({**rec.to_dict(),**tr,'rule':rule.name,'future_days_available':fdays,'is_mature_trade':fdays>=10})
        df=pd.DataFrame(trades)
        mature=df[df.is_mature_trade.astype(bool)].copy() if not df.empty else pd.DataFrame()
        subdir=OUT/name/rule.name; subdir.mkdir(parents=True,exist_ok=True)
        df.to_csv(subdir/'trades.csv',index=False); mature.to_csv(subdir/'mature_trades.csv',index=False)
        summ=summarize(mature.to_dict('records') if not mature.empty else [])
        t_syms=set(mature.symbol.astype(str)) if not mature.empty else set()
        cov={}
        for label,strong in [('ge30',runups[runups.runup_pct>=30]),('ge50',runups[runups.runup_pct>=50]),('top50',runups.head(50))]:
            syms=set(str(s) for s in strong.symbol)
            cov[label]=len(syms&t_syms); cov[label+'_combined']=len(syms&(t_syms|stable_syms))
        rows.append({'signal_set':name,'rule':rule.name,**summ,**cov,'early_exit_count':int((mature.exit_reason==rule.name).sum()) if not mature.empty else 0,'hard_stop_count':int((mature.exit_reason=='hard_stop_8pct').sum()) if not mature.empty else 0})
    return rows


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    raw=load_atomic_daily_window('2026-01-01','2026-04-24')
    metrics=add_ma(compute_v2_metrics(raw))
    by_symbol={s:g.sort_values('trade_date').reset_index(drop=True) for s,g in metrics.groupby('symbol',sort=False)}
    runups=build_all_runups(metrics,'2026-03-02','2026-04-24')
    stable=pd.read_csv(STABLE_TRADES) if STABLE_TRADES.exists() else pd.DataFrame()
    stable_syms=set(stable.symbol.astype(str)) if not stable.empty else set()
    all_rows=[]
    proto=pd.read_csv(PROTO)
    all_rows+=run_set('prototype_direct',proto,'signal_date',by_symbol,runups,stable_syms)
    if BUYPOINT.exists():
        bp=pd.read_csv(BUYPOINT)
        # 质量过滤：确认日不过度放量，且撤买单低，用于观察是否能明显改善交易质量。
        bpq=bp[(bp.confirm_cancel_buy_ratio<0.2)&(bp.confirm_amount_anomaly_20d<=1.5)].copy()
        all_rows+=run_set('buy_point_callback',bp,'entry_signal_date',by_symbol,runups,stable_syms)
        all_rows+=run_set('buy_point_quality',bpq,'entry_signal_date',by_symbol,runups,stable_syms)
    summary=pd.DataFrame(all_rows)
    summary.to_csv(OUT/'summary.csv',index=False)
    (OUT/'summary.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2),encoding='utf-8')
    readme='# 趋势中继交易管理实验\n\n验证：趋势中继的交易能力能否通过“二次买点”和“买入后早期资金逃逸退出”改善。\n\n'+summary.to_markdown(index=False)+'\n'
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    print(summary.to_string(index=False))

if __name__=='__main__': main()
