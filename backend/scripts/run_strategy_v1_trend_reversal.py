from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, compute_v2_metrics, load_atomic_daily_window, _compute_intent_profile
from backend.scripts.quick_trend_strategy_experiment import score_linear, simulate_trade, summarize
from backend.scripts.research_trend_sample_factors import slice_stats, safe_div, pct


def add_ma(metrics: pd.DataFrame) -> pd.DataFrame:
    frames=[]
    for _,g in metrics.groupby('symbol', sort=False):
        x=g.sort_values('trade_date').copy()
        x['close_ma5']=x.close.rolling(5,min_periods=3).mean()
        x['close_ma10']=x.close.rolling(10,min_periods=5).mean()
        frames.append(x)
    return pd.concat(frames, ignore_index=True)


def setup_score(pre20: Dict[str, Any], pre5: Dict[str, Any], current: pd.Series) -> float:
    pre20_ret=float(pre20.get('pre20_return_pct',0) or 0)
    pre5_ret=float(pre5.get('pre5_return_pct',0) or 0)
    pre20_super_div=float(pre20.get('pre20_super_price_divergence',0) or 0)
    pre20_main_div=float(pre20.get('pre20_main_price_divergence',0) or 0)
    pre5_super_div=float(pre5.get('pre5_super_price_divergence',0) or 0)
    pre5_main_div=float(pre5.get('pre5_main_price_divergence',0) or 0)
    amount=float(current.get('total_amount') or 0)
    current_dist=float(_compute_intent_profile(current, SelectionV2Params()).get('distribution_score') or 0)
    # 价格偏弱/未涨太多，资金价格背离为正。
    price_setup = 0.55 * score_linear(8 - pre20_ret, 0, 25) + 0.45 * score_linear(5 - pre5_ret, 0, 15)
    divergence = (
        0.35 * score_linear(pre20_super_div, 0.00, 0.10)
        + 0.30 * score_linear(pre20_main_div, 0.00, 0.10)
        + 0.20 * score_linear(pre5_super_div, 0.00, 0.07)
        + 0.15 * score_linear(pre5_main_div, 0.00, 0.07)
    )
    liquidity = score_linear(amount, 250_000_000, 1_200_000_000)
    risk_penalty = score_linear(current_dist, 45, 85)
    return round(max(0, min(100, 0.42*price_setup + 0.43*divergence + 0.15*liquidity - 0.18*risk_penalty)),2)


def candidate_ok(pre20: Dict[str, Any], pre5: Dict[str, Any], current: pd.Series, score: float) -> bool:
    if float(current.get('total_amount') or 0) < 250_000_000:
        return False
    if score < 50:
        return False
    if float(pre20.get('pre20_return_pct',0) or 0) > 12:
        return False
    if float(pre5.get('pre5_return_pct',0) or 0) > 8:
        return False
    if max(float(pre20.get('pre20_super_price_divergence',0) or 0), float(pre20.get('pre20_main_price_divergence',0) or 0), float(pre5.get('pre5_super_price_divergence',0) or 0)) <= 0.015:
        return False
    return True


def find_launch(g: pd.DataFrame, discovery_date: str, max_wait: int=5) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    idxs=g.index[g.trade_date==discovery_date].tolist()
    if not idxs: return None, None, {}
    start_idx=idxs[0]
    for i in range(start_idx, min(len(g), start_idx+max_wait+1)):
        j=min(len(g)-1,i+2)
        stats=slice_stats(g,i,j,'launch3')
        ret=float(stats.get('launch3_return_pct',0) or 0)
        super_ratio=float(stats.get('launch3_super_net_ratio',0) or 0)
        main_ratio=float(stats.get('launch3_main_net_ratio',0) or 0)
        mdd=float(stats.get('launch3_max_drawdown_pct',0) or 0)
        active=float(stats.get('launch3_active_buy_strength_avg',0) or 0)
        add_buy=float(stats.get('launch3_add_buy_ratio',0) or 0)
        # 启动质量：不追单日妖，要求3日稳、资金参与、回撤小。
        if 4 <= ret <= 24 and mdd >= -6 and (super_ratio >= 0.008 or main_ratio >= 0.008) and active > -1 and add_buy >= 0.8:
            return str(g.loc[i,'trade_date']), str(g.loc[j,'trade_date']), stats
    return None, None, {}


def find_pullback_confirm(g: pd.DataFrame, launch_start: str, launch_end: str, max_wait: int=14) -> Tuple[Optional[str], str, Dict[str, Any]]:
    end_idxs=g.index[g.trade_date==launch_end].tolist()
    start_idxs=g.index[g.trade_date==launch_start].tolist()
    if not end_idxs or not start_idxs: return None,'no_launch_index',{}
    launch_i=start_idxs[0]; scan_start=end_idxs[0]+1
    launch_close=float(g.loc[launch_i,'close'])
    launch_peak=float(g.iloc[launch_i:scan_start].high.max())
    low_i=None
    for i in range(scan_start, min(len(g), scan_start+max_wait)):
        low=float(g.loc[i,'low'])
        dd=pct(launch_peak, low)
        if dd <= -3:
            if low_i is None or low < float(g.loc[low_i,'low']):
                low_i=i
        if low_i is None:
            continue
        pull=slice_stats(g, low_i, i, 'pullback')
        pull_dd=pct(launch_peak, float(g.loc[low_i,'low']))
        super_ratio=float(pull.get('pullback_super_net_ratio',0) or 0)
        main_ratio=float(pull.get('pullback_main_net_ratio',0) or 0)
        support=float(pull.get('pullback_support_spread_avg',0) or 0)
        pos_main=float(pull.get('pullback_main_positive_day_ratio',0) or 0)
        close=float(g.loc[i,'close'])
        ma5=float(g.loc[i].get('close_ma5') or 0)
        intent=_compute_intent_profile(g.loc[i], SelectionV2Params())
        dist=float(intent.get('distribution_score') or 0)
        # 回调确认：跌过但不深，回调中资金/承接不差，价格开始修复。
        if -18 <= pull_dd <= -3 and dist < 70 and close >= ma5*0.985 and (super_ratio >= 0.005 or main_ratio >= 0.01 or support >= 0.02 or pos_main >= 0.6):
            meta={**pull,'pullback_depth_from_launch_peak_pct':round(pull_dd,2),'confirm_distribution_score':round(dist,2)}
            return str(g.loc[i,'trade_date']), 'pullback_absorption_confirm', meta
    return None,'no_pullback_confirm',{}


def summarize_candidates(cands: List[Dict[str, Any]], trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    s=summarize(trades)
    s.update({
        'candidate_count': len(cands),
        'launch_confirmed_count': sum(1 for c in cands if c.get('launch_start_date')),
        'pullback_confirmed_count': sum(1 for c in cands if c.get('pullback_confirm_date')),
        'pullback_confirm_rate': round(100*sum(1 for c in cands if c.get('pullback_confirm_date'))/max(len(cands),1),2),
    })
    return s


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--start', default='2026-03-02')
    parser.add_argument('--end', default='2026-03-31')
    parser.add_argument('--replay-end', default='2026-04-24')
    parser.add_argument('--top-n', type=int, default=10)
    parser.add_argument('--out', default='docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-initial')
    args=parser.parse_args()

    raw=load_atomic_daily_window('2026-01-01', args.replay_end)
    metrics=add_ma(compute_v2_metrics(raw))
    by_symbol={s:g.sort_values('trade_date').reset_index(drop=True) for s,g in metrics.groupby('symbol', sort=False)}
    days=sorted(metrics[(metrics.trade_date>=args.start)&(metrics.trade_date<=args.end)].trade_date.unique().tolist())
    candidates=[]; trades=[]
    params=SelectionV2Params()
    for day in days:
        ranked=[]
        for sym,g in by_symbol.items():
            idxs=g.index[g.trade_date==day].tolist()
            if not idxs: continue
            i=idxs[0]
            if i < 8: continue
            pre20=slice_stats(g,i-20,i-1,'pre20')
            pre5=slice_stats(g,i-5,i-1,'pre5')
            current=g.loc[i]
            sc=setup_score(pre20,pre5,current)
            if not candidate_ok(pre20,pre5,current,sc):
                continue
            ranked.append({'symbol':sym,'score':sc,'row':current,'pre20':pre20,'pre5':pre5})
        ranked=sorted(ranked,key=lambda x:(-x['score'],x['symbol']))[:args.top_n]
        for rank,item in enumerate(ranked, start=1):
            sym=item['symbol']; g=by_symbol[sym]
            launch_start, launch_end, launch_meta=find_launch(g,day)
            pull_date=None; pull_reason='no_launch'; pull_meta={}
            if launch_end:
                pull_date,pull_reason,pull_meta=find_pullback_confirm(g,launch_start,launch_end)
            rec={
                'discovery_date':day,'symbol':sym,'rank':rank,'setup_score':item['score'],
                'pre20_return_pct':item['pre20'].get('pre20_return_pct'),
                'pre20_super_price_divergence':item['pre20'].get('pre20_super_price_divergence'),
                'pre20_main_price_divergence':item['pre20'].get('pre20_main_price_divergence'),
                'pre5_return_pct':item['pre5'].get('pre5_return_pct'),
                'pre5_super_price_divergence':item['pre5'].get('pre5_super_price_divergence'),
                'launch_start_date':launch_start,'launch_end_date':launch_end,
                'pullback_confirm_date':pull_date,'pullback_confirm_reason':pull_reason,
                **{k:v for k,v in launch_meta.items() if k in ['launch3_return_pct','launch3_super_net_ratio','launch3_main_net_ratio','launch3_max_drawdown_pct','launch3_add_buy_ratio']},
                **{k:v for k,v in pull_meta.items() if k in ['pullback_super_net_ratio','pullback_main_net_ratio','pullback_support_spread_avg','pullback_depth_from_launch_peak_pct','confirm_distribution_score']},
            }
            candidates.append(rec)
            if pull_date:
                t=simulate_trade(g,pull_date,params,stop_loss_pct=-10,max_holding_days=40)
                if t and not t.get('skipped'):
                    trades.append({**rec, **t})
    out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(candidates).to_csv(out/'v1_candidates.csv',index=False)
    pd.DataFrame(trades).to_csv(out/'v1_trades.csv',index=False)
    summary={'range':{'start':args.start,'end':args.end,'replay_end':args.replay_end,'top_n':args.top_n},'summary':summarize_candidates(candidates,trades)}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    md=['# v1 初始实验结果','',f"区间：{args.start} ~ {args.end}，回放到 {args.replay_end}",'','## 汇总','']
    for k,v in summary['summary'].items(): md.append(f'- {k}: {v}')
    md += ['', '## 文件', '', '- v1_candidates.csv', '- v1_trades.csv', '- summary.json', '']
    (out/'README.md').write_text('\n'.join(md),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
