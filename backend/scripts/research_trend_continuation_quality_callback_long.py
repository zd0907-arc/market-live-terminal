from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window
from backend.scripts.quick_trend_strategy_experiment import summarize
from backend.scripts.research_trend_continuation_strategy import build_candidates
from backend.scripts.research_trend_continuation_buy_points import add_confirmations, simulate_confirmed_trades
from backend.scripts.run_strategy_v1_trend_reversal import add_ma

OUT=Path('docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-quality-callback-long')


def apply_quality(confirms: pd.DataFrame)->pd.DataFrame:
    if confirms.empty: return confirms
    # 先沿用当前小样本候选规则：严格回踩确认 + 观察池质量/修复质量/不过度透支
    return confirms[
        (confirms.confirm_cancel_buy_ratio < 0.30)
        & (confirms.confirm_amount_anomaly_20d <= 1.30)
        & (confirms.confirm_return_1d_pct <= 4.0)
        & (confirms['rank'] <= 15)
        & (confirms.repair_score >= 45)
        & (confirms.pre20_return_pct <= 30)
    ].copy()


def summarize_period(trades: pd.DataFrame, label: str, start: str, end: str)->Dict[str,Any]:
    sub=trades[(trades.entry_date>=start)&(trades.entry_date<=end)].copy() if not trades.empty else pd.DataFrame()
    return {'period':label,'start':start,'end':end,**summarize(sub.to_dict('records') if not sub.empty else [])}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--load-start", default="2026-01-01")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--out", default=str(OUT))
    args=parser.parse_args()
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    raw=load_atomic_daily_window(args.load_start,args.end)
    metrics=add_ma(compute_v2_metrics(raw))
    candidates, by_symbol=build_candidates(metrics,args.start,args.end,top_n=20,min_score=58.0)
    confirms_all=add_confirmations(candidates,by_symbol,window=8,mode='callback_only',cooldown=5)
    confirms=apply_quality(confirms_all)
    trades=simulate_confirmed_trades(confirms,by_symbol,min_future_days=10)
    mature=trades[trades.is_mature_trade.astype(bool)].copy() if not trades.empty else pd.DataFrame()
    candidates.to_csv(out/'observation_pool.csv',index=False)
    confirms_all.to_csv(out/'all_callback_confirmations.csv',index=False)
    confirms.to_csv(out/'strict_refined_confirmations.csv',index=False)
    trades.to_csv(out/'trades.csv',index=False)
    mature.to_csv(out/'mature_trades.csv',index=False)
    periods=[
        ('全周期',args.start,args.end),
        ('2026年1-2月成交L2-only','2026-01-01','2026-02-28'),
        ('2026年3-4月完整L2挂单','2026-03-01','2026-04-24'),
    ]
    rows=[summarize_period(mature,*p) for p in periods]
    summary=pd.DataFrame(rows)
    summary.to_csv(out/'period_summary.csv',index=False)
    # 按是否有挂单数据分组
    if not mature.empty:
        mature['has_orderbook_l2']=mature.entry_date>='2026-03-01'
        orderbook_summary=mature.groupby('has_orderbook_l2').apply(lambda x: pd.Series(summarize(x.to_dict('records'))), include_groups=False).reset_index()
        orderbook_summary.to_csv(out/'orderbook_coverage_summary.csv',index=False)
    else:
        orderbook_summary=pd.DataFrame()
    (out/'summary.json').write_text(json.dumps({'period_summary':rows,'total_confirm_count':int(len(confirms)),'total_mature_count':int(len(mature))},ensure_ascii=False,indent=2),encoding='utf-8')
    readme='# 趋势中继严格高质量回踩：长周期验证\n\n'+summary.to_markdown(index=False)+'\n'
    (out/'README.md').write_text(readme,encoding='utf-8')
    print(summary.to_string(index=False))
    print('\norderbook split')
    print(orderbook_summary.to_string(index=False) if not orderbook_summary.empty else 'empty')

if __name__=='__main__': main()
