from __future__ import annotations

import json, sys
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window, _apply_buy_costs, _apply_sell_costs, _is_limit_up_day
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.run_strategy_v1_trend_reversal import add_ma
from backend.scripts.research_trend_continuation_strategy import build_candidates, future_days_after_entry
from backend.scripts.research_trend_continuation_buy_points import add_confirmations

OUT=Path('docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-current-candidate')


def apply_current_buy_filter(confirms: pd.DataFrame) -> pd.DataFrame:
    if confirms.empty:
        return confirms
    return confirms[
        (confirms.confirm_cancel_buy_ratio < 0.30)
        & (confirms.confirm_amount_anomaly_20d <= 1.30)
        & (confirms.confirm_return_1d_pct <= 4.0)
        & (confirms['rank'] <= 15)
        & (confirms.repair_score >= 45)
        & (confirms.pre20_return_pct <= 30)
        & (confirms.confirm_active_buy_strength > 0)
        & (confirms.confirm_main_net_ratio >= 0)
    ].copy()


def simulate_candidate_exit(g: pd.DataFrame, signal_date: str, cost: SelectionV2Params) -> Optional[Dict[str, Any]]:
    future=g[g.trade_date>signal_date]
    if future.empty: return None
    entry_i=int(future.index[0]); entry=g.loc[entry_i]
    if _is_limit_up_day(entry,cost): return {'skipped': True, 'skip_reason':'entry_blocked_limit_up'}
    gross_entry=float(entry.open)
    if gross_entry<=0: return None
    entry_price=_apply_buy_costs(gross_entry,cost)
    cum_super=0.0; cum_amount=0.0; peak=0.0; prev=None; decline=0
    holding=0; max_run=-999.0; max_dd=999.0; exit_signal=None; reason='window_end'; final={}
    for _,r in g.loc[entry_i:].iterrows():
        holding+=1
        daily_super=float(r.l2_super_net_amount or 0); amount=float(r.total_amount or 0)
        cum_super+=daily_super; cum_amount+=amount
        decline=decline+1 if prev is not None and cum_super<prev else 0
        prev=cum_super; peak=max(peak,cum_super)
        peak_dd=(peak-cum_super)/peak if peak>0 else 0.0
        daily_super_ratio=daily_super/max(amount,1.0)
        close_ret=(float(r.close)/gross_entry-1)*100
        max_run=max(max_run,(float(r.high)/gross_entry-1)*100)
        max_dd=min(max_dd,(float(r.low)/gross_entry-1)*100)
        final={
            'final_cum_super_amount': round(cum_super,2),
            'final_cum_super_peak_amount': round(peak,2),
            'final_super_peak_drawdown_pct': round(peak_dd*100,2),
            'final_super_decline_streak': int(decline),
        }
        # 新增：趋势中继单日大额派发退出。盈利状态下，看到高位大额超大单流出就先跑。
        if peak>0 and peak_dd>=0.25 and daily_super_ratio<=-0.05 and close_ret>=0:
            exit_signal=str(r.trade_date); reason='large_super_outflow_profit_guard'; break
        if close_ret<=-8:
            exit_signal=str(r.trade_date); reason='hard_stop_8pct'; break
        if peak>0 and decline>=3 and peak_dd>=0.20:
            exit_signal=str(r.trade_date); reason='cum_super_peak_dd_20pct_3d'; break
        daily_out=max(0,-daily_super)/max(cum_amount,1.0)
        if peak>0 and daily_super<0 and daily_out>=0.025 and peak_dd>=0.15:
            exit_signal=str(r.trade_date); reason='violent_super_outflow'; break
        if holding>=40:
            exit_signal=str(r.trade_date); reason='max_holding_days'; break
    if exit_signal:
        nxt=g[g.trade_date>exit_signal]
        if not nxt.empty:
            er=nxt.iloc[0]; gross_exit=float(er.open); exit_date=str(er.trade_date)
        else:
            er=g[g.trade_date==exit_signal].iloc[0]; gross_exit=float(er.close); exit_date=exit_signal
    else:
        er=g.iloc[-1]; gross_exit=float(er.close); exit_date=str(er.trade_date); exit_signal=exit_date
    exit_price=_apply_sell_costs(gross_exit,cost)
    return {
        'entry_signal_date': signal_date,
        'entry_date': str(entry.trade_date),
        'gross_entry_price': round(gross_entry,4),
        'entry_price': round(entry_price,4),
        'exit_signal_date': exit_signal,
        'exit_date': exit_date,
        'gross_exit_price': round(gross_exit,4),
        'exit_price': round(exit_price,4),
        'return_pct': round((gross_exit/gross_entry-1)*100,2),
        'net_return_pct': round((exit_price/entry_price-1)*100,2),
        'max_runup_pct': round(max_run,2),
        'max_drawdown_pct': round(max_dd,2),
        'holding_days': int(holding),
        'exit_reason': reason,
        **final,
    }


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    raw=load_atomic_daily_window('2026-01-01','2026-04-24')
    metrics=add_ma(compute_v2_metrics(raw))
    candidates, by_symbol=build_candidates(metrics,'2026-03-02','2026-04-24',top_n=20,min_score=58.0)
    confirms_all=add_confirmations(candidates,by_symbol,window=8,mode='callback_only',cooldown=5)
    confirms=apply_current_buy_filter(confirms_all)
    rows=[]; cost=SelectionV2Params()
    for _,rec in confirms.iterrows():
        g=by_symbol[str(rec.symbol)]
        tr=simulate_candidate_exit(g,str(rec.entry_signal_date),cost)
        if not tr or tr.get('skipped'): continue
        fdays=future_days_after_entry(g,str(tr['entry_date']))
        rows.append({**rec.to_dict(),**tr,'future_days_available':fdays,'is_mature_trade':fdays>=10})
    trades=pd.DataFrame(rows)
    mature=trades[trades.is_mature_trade.astype(bool)].copy() if not trades.empty else pd.DataFrame()
    candidates.to_csv(OUT/'observation_pool.csv',index=False)
    confirms_all.to_csv(OUT/'all_callback_confirmations.csv',index=False)
    confirms.to_csv(OUT/'current_buy_signals.csv',index=False)
    trades.to_csv(OUT/'trades.csv',index=False)
    mature.to_csv(OUT/'mature_trades.csv',index=False)
    summ=summarize(mature.to_dict('records') if not mature.empty else [])
    exit_counts=mature.exit_reason.value_counts().to_dict() if not mature.empty else {}
    summary={'summary':summ,'confirm_count':int(len(confirms)),'mature_count':int(len(mature)),'exit_reason_counts':exit_counts}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    readme='# 趋势中继当前候选版\n\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n'
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if not mature.empty:
        print(mature[['symbol','observe_date','entry_signal_date','entry_date','exit_signal_date','exit_date','rank','score','repair_score','net_return_pct','max_runup_pct','max_drawdown_pct','holding_days','exit_reason']].to_string(index=False))

if __name__=='__main__': main()
