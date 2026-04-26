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



def is_entry_overheated(g: pd.DataFrame, discovery_date: str, entry_signal_date: str) -> tuple[bool, Dict[str, Any]]:
    idx = {d: i for i, d in enumerate(g.trade_date.tolist())}
    di = idx.get(discovery_date)
    ei = idx.get(entry_signal_date)
    if di is None or ei is None or ei < di:
        return False, {}
    stats = slice_stats(g, di, ei, 'discover_to_entry')
    ret = float(stats.get('discover_to_entry_return_pct', 0) or 0)
    active = float(stats.get('discover_to_entry_active_buy_strength_avg', 0) or 0)
    amount = float(stats.get('discover_to_entry_amount_anomaly_avg', 0) or 0)
    main_ratio = float(stats.get('discover_to_entry_main_net_ratio', 0) or 0)
    super_ratio = float(stats.get('discover_to_entry_super_net_ratio', 0) or 0)
    # 过热不是绝对禁止：只拦截“发现后已经涨很多 + 主动买/成交热度过强”的追高形态。
    overheated = (ret >= 12 and active >= 3.5 and amount >= 1.15) or (ret >= 16 and (main_ratio >= 0.04 or super_ratio >= 0.03))
    return overheated, {
        'overheat_return_pct': round(ret, 2),
        'overheat_active_buy_strength': round(active, 4),
        'overheat_amount_anomaly': round(amount, 4),
        'overheat_main_net_ratio': round(main_ratio, 5),
        'overheat_super_net_ratio': round(super_ratio, 5),
        'entry_overheated': overheated,
    }


def simulate_trade_v1_1(g: pd.DataFrame, signal_date: str, params: SelectionV2Params) -> Optional[Dict[str, Any]]:
    # v1.1：不再用单日出货分轻易卖，改为“累计资金转弱 + 主动卖/承接转弱”确认。
    idxs = g.index[g.trade_date > signal_date].tolist()
    if not idxs:
        return None
    entry_i = idxs[0]
    entry = g.loc[entry_i]
    gross_entry = float(entry.open)
    if gross_entry <= 0:
        return None
    entry_price = gross_entry * (1 + 0.0015 + 0.001)
    entry_date = str(entry.trade_date)
    cum_super = 0.0
    cum_main = 0.0
    cum_amount = 0.0
    super_pos_days = 0
    main_pos_days = 0
    l2bar_sum = 0.0
    active_sum = 0.0
    support_sum = 0.0
    days = 0
    max_runup = -999.0
    max_drawdown = 999.0
    exit_signal = None
    exit_reason = 'window_end'
    cum_super_peak = -999.0
    cum_main_peak = -999.0

    for i in range(entry_i, len(g)):
        r = g.loc[i]
        days += 1
        amount = float(r.total_amount or 0)
        cum_super += float(r.l2_super_net_amount or 0)
        cum_main += float(r.l2_main_net_amount or 0)
        cum_amount += amount
        super_ratio = cum_super / max(cum_amount, 1)
        main_ratio = cum_main / max(cum_amount, 1)
        cum_super_peak = max(cum_super_peak, super_ratio)
        cum_main_peak = max(cum_main_peak, main_ratio)
        super_peak_dd = super_ratio - cum_super_peak
        main_peak_dd = main_ratio - cum_main_peak
        if float(r.l2_super_net_amount or 0) > 0:
            super_pos_days += 1
        if float(r.l2_main_net_amount or 0) > 0:
            main_pos_days += 1
        pos_total = float(r.positive_l2_net_bar_count or 0) + float(r.negative_l2_net_bar_count or 0)
        l2bar = float(r.positive_l2_net_bar_count or 0) / pos_total if pos_total > 0 else 0.0
        l2bar_sum += l2bar
        active = float(r.active_buy_strength or 0)
        support = float(r.support_pressure_spread or 0)
        active_sum += active
        support_sum += support
        max_runup = max(max_runup, (float(r.high) / gross_entry - 1) * 100)
        max_drawdown = min(max_drawdown, (float(r.low) / gross_entry - 1) * 100)
        close_ret = (float(r.close) / gross_entry - 1) * 100
        super_pos_ratio = super_pos_days / days
        main_pos_ratio = main_pos_days / days
        l2bar_avg = l2bar_sum / days
        active_avg = active_sum / days
        support_avg = support_sum / days
        daily_super_ratio = float(r.l2_super_net_ratio or 0)
        daily_main_ratio = float(r.l2_main_net_ratio or 0)

        flow_weak = (
            super_ratio < -0.012
            or main_ratio < -0.028
            or (super_peak_dd < -0.035 and daily_super_ratio < -0.025)
            or (main_peak_dd < -0.045 and daily_main_ratio < -0.035)
        )
        persistence_weak = (
            days >= 3
            and (super_pos_ratio < 0.28 or main_pos_ratio < 0.25 or l2bar_avg < 0.36)
            and active_avg < -2.5
        )
        support_weak = days >= 3 and support_avg < -0.025 and active_avg < -2.0

        if close_ret <= -16:
            exit_signal = str(r.trade_date)
            exit_reason = 'hard_stop_16pct'
            break
        if close_ret <= -10 and (flow_weak or persistence_weak):
            exit_signal = str(r.trade_date)
            exit_reason = 'flow_confirmed_stop'
            break
        if days >= 4 and flow_weak and (persistence_weak or support_weak):
            exit_signal = str(r.trade_date)
            exit_reason = 'cum_flow_exit'
            break
        if days >= 40:
            exit_signal = str(r.trade_date)
            exit_reason = 'max_holding_days'
            break

    if exit_signal:
        next_rows = g[g.trade_date > exit_signal]
        if not next_rows.empty:
            ex = next_rows.iloc[0]
            gross_exit = float(ex.open)
            exit_date = str(ex.trade_date)
        else:
            ex = g[g.trade_date == exit_signal].iloc[0]
            gross_exit = float(ex.close)
            exit_date = str(ex.trade_date)
    else:
        ex = g.iloc[-1]
        gross_exit = float(ex.close)
        exit_date = str(ex.trade_date)
        exit_signal = exit_date
    exit_price = gross_exit * (1 - 0.0015 - 0.001)
    return {
        'entry_signal_date': signal_date,
        'entry_date': entry_date,
        'gross_entry_price': round(gross_entry, 4),
        'entry_price': round(entry_price, 4),
        'exit_signal_date': exit_signal,
        'exit_date': exit_date,
        'gross_exit_price': round(gross_exit, 4),
        'exit_price': round(exit_price, 4),
        'return_pct': round((gross_exit / gross_entry - 1) * 100, 2),
        'net_return_pct': round((exit_price / entry_price - 1) * 100, 2),
        'max_runup_pct': round(max_runup, 2),
        'max_drawdown_pct': round(max_drawdown, 2),
        'holding_days': int(days),
        'exit_reason': exit_reason,
        'final_cum_super_ratio': round(cum_super / max(cum_amount, 1), 5),
        'final_cum_main_ratio': round(cum_main / max(cum_amount, 1), 5),
        'final_super_pos_day_ratio': round(super_pos_days / max(days, 1), 4),
        'final_main_pos_day_ratio': round(main_pos_days / max(days, 1), 4),
    }

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
    parser.add_argument('--out', default='docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-1')
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
                overheated, overheat_meta = is_entry_overheated(g, day, pull_date)
                rec.update(overheat_meta)
                if not overheated:
                    t=simulate_trade_v1_1(g,pull_date,params)
                    if t and not t.get('skipped'):
                        trades.append({**rec, **t})
    out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(candidates).to_csv(out/'v1_candidates.csv',index=False)
    pd.DataFrame(trades).to_csv(out/'v1_trades.csv',index=False)
    summary={'range':{'start':args.start,'end':args.end,'replay_end':args.replay_end,'top_n':args.top_n},'summary':summarize_candidates(candidates,trades)}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    md=['# v1.1 实验结果','',f"区间：{args.start} ~ {args.end}，回放到 {args.replay_end}",'','## 汇总','']
    for k,v in summary['summary'].items(): md.append(f'- {k}: {v}')
    md += ['', '## 文件', '', '- v1_candidates.csv', '- v1_trades.csv', '- summary.json', '']
    (out/'README.md').write_text('\n'.join(md),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
