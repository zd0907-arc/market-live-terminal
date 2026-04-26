from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import compute_v2_metrics, load_atomic_daily_window
from backend.scripts.research_trend_sample_factors import slice_stats, safe_div

BASE = Path('docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-initial')
OUT = Path('docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-initial-review')
OUT.mkdir(parents=True, exist_ok=True)

trades = pd.read_csv(BASE / 'v1_trades.csv')
raw = load_atomic_daily_window('2026-01-01', '2026-04-24')
metrics = compute_v2_metrics(raw)
metrics = metrics.sort_values(['symbol', 'trade_date']).reset_index(drop=True)
by_symbol = {s: g.sort_values('trade_date').reset_index(drop=True) for s, g in metrics.groupby('symbol', sort=False)}

rows: List[Dict[str, Any]] = []
for _, t in trades.iterrows():
    sym = str(t.symbol)
    g = by_symbol.get(sym)
    if g is None:
        continue
    idx = {d: i for i, d in enumerate(g.trade_date.tolist())}
    entry_i = idx.get(str(t.entry_date))
    exit_i = idx.get(str(t.exit_signal_date))
    disc_i = idx.get(str(t.discovery_date))
    launch_i = idx.get(str(t.launch_start_date)) if pd.notna(t.launch_start_date) else None
    pull_i = idx.get(str(t.pullback_confirm_date)) if pd.notna(t.pullback_confirm_date) else None
    if entry_i is None:
        continue
    exit_i = exit_i if exit_i is not None else min(len(g) - 1, entry_i + int(t.holding_days))
    entry_to_exit = slice_stats(g, entry_i, exit_i, 'hold')
    disc_to_entry = slice_stats(g, disc_i, max(disc_i, entry_i - 1), 'discover_to_entry') if disc_i is not None else {}
    launch_to_entry = slice_stats(g, launch_i, max(launch_i, entry_i - 1), 'launch_to_entry') if launch_i is not None else {}
    pull_to_entry = slice_stats(g, pull_i, max(pull_i, entry_i - 1), 'pull_to_entry') if pull_i is not None else {}

    hold = g.iloc[entry_i: exit_i + 1].copy()
    cum_amount = hold.total_amount.cumsum().replace(0, pd.NA)
    cum_super_ratio_series = hold.l2_super_net_amount.cumsum() / cum_amount
    cum_main_ratio_series = hold.l2_main_net_amount.cumsum() / cum_amount
    super_peak = cum_super_ratio_series.cummax()
    super_dd = (cum_super_ratio_series - super_peak).fillna(0)
    main_peak = cum_main_ratio_series.cummax()
    main_dd = (cum_main_ratio_series - main_peak).fillna(0)

    row = {
        **t.to_dict(),
        **entry_to_exit,
        **disc_to_entry,
        **launch_to_entry,
        **pull_to_entry,
        'hold_cum_super_ratio_last': round(float(cum_super_ratio_series.iloc[-1] or 0), 5),
        'hold_cum_main_ratio_last': round(float(cum_main_ratio_series.iloc[-1] or 0), 5),
        'hold_cum_super_ratio_min': round(float(cum_super_ratio_series.min() or 0), 5),
        'hold_cum_main_ratio_min': round(float(cum_main_ratio_series.min() or 0), 5),
        'hold_cum_super_ratio_max_drawdown': round(float(super_dd.min() or 0), 5),
        'hold_cum_main_ratio_max_drawdown': round(float(main_dd.min() or 0), 5),
        'hold_negative_super_day_ratio': round(float((hold.l2_super_net_amount < 0).mean()), 4),
        'hold_negative_main_day_ratio': round(float((hold.l2_main_net_amount < 0).mean()), 4),
        'hold_big_super_outflow_days': int(((hold.l2_super_net_amount / hold.total_amount.replace(0, pd.NA)) < -0.05).sum()),
        'duplicate_symbol_count_in_v1': int((trades.symbol == sym).sum()),
    }
    rows.append(row)

enriched = pd.DataFrame(rows)
enriched.to_csv(OUT / 'v1_trades_enriched.csv', index=False)

numeric = enriched.select_dtypes(include='number').columns.tolist()
ignore = {'gross_entry_price','entry_price','gross_exit_price','exit_price','return_pct','net_return_pct','max_runup_pct','max_drawdown_pct'}
feature_rows=[]
win = enriched[enriched.net_return_pct > 0]
loss = enriched[enriched.net_return_pct <= 0]
big = enriched[enriched.net_return_pct >= 10]
bad = enriched[enriched.net_return_pct <= -8]
for col in numeric:
    if col in ignore or enriched[col].notna().sum() < 20:
        continue
    corr = float(enriched[[col,'net_return_pct']].corr(numeric_only=True).iloc[0,1]) if enriched[col].std() else 0.0
    feature_rows.append({
        'feature': col,
        'corr_return': round(corr,4),
        'win_mean': round(float(win[col].mean()),6) if not win.empty else None,
        'loss_mean': round(float(loss[col].mean()),6) if not loss.empty else None,
        'win_loss_diff': round(float(win[col].mean() - loss[col].mean()),6) if not win.empty and not loss.empty else None,
        'big_mean': round(float(big[col].mean()),6) if not big.empty else None,
        'bad_mean': round(float(bad[col].mean()),6) if not bad.empty else None,
        'big_bad_diff': round(float(big[col].mean() - bad[col].mean()),6) if not big.empty and not bad.empty else None,
    })
features = pd.DataFrame(feature_rows)
features['abs_corr'] = features.corr_return.abs()
features = features.sort_values(['abs_corr'], ascending=False).drop(columns=['abs_corr'])
features.to_csv(OUT / 'v1_win_loss_feature_diff.csv', index=False)

# 简单规则扫描：看哪些单因子过滤能改善中位/胜率，同时保留>=40笔。
rules=[]
for col in numeric:
    if col in ignore or enriched[col].notna().sum() < 40 or enriched[col].nunique() < 5:
        continue
    qs = enriched[col].quantile([0.2,0.35,0.5,0.65,0.8]).dropna().unique().tolist()
    for q in qs:
        for op in ['>=','<=']:
            sub = enriched[enriched[col] >= q] if op == '>=' else enriched[enriched[col] <= q]
            if len(sub) < 40:
                continue
            rules.append({
                'rule': f'{col} {op} {q:.6g}',
                'count': int(len(sub)),
                'win_rate': round(float((sub.net_return_pct > 0).mean()*100),2),
                'avg_return': round(float(sub.net_return_pct.mean()),2),
                'median_return': round(float(sub.net_return_pct.median()),2),
                'max_return': round(float(sub.net_return_pct.max()),2),
                'min_return': round(float(sub.net_return_pct.min()),2),
            })
rules_df = pd.DataFrame(rules)
if not rules_df.empty:
    rules_df['score'] = rules_df['median_return'] + 0.08*rules_df['win_rate'] + 0.2*rules_df['avg_return']
    rules_df = rules_df.sort_values(['score','median_return','win_rate'], ascending=False)
    rules_df.to_csv(OUT / 'v1_single_factor_filter_scan.csv', index=False)

summary = {
    'base': {
        'count': int(len(enriched)),
        'win_rate': round(float((enriched.net_return_pct > 0).mean()*100),2),
        'avg_return': round(float(enriched.net_return_pct.mean()),2),
        'median_return': round(float(enriched.net_return_pct.median()),2),
    },
    'top_feature_corr': features.head(30).to_dict(orient='records'),
    'top_filter_rules': rules_df.head(30).to_dict(orient='records') if not rules_df.empty else [],
}
(OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

lines = ['# v1 初版交易复盘', '', '## 基础结果', '', f"- 交易数：{summary['base']['count']}", f"- 胜率：{summary['base']['win_rate']}%", f"- 平均收益：{summary['base']['avg_return']}%", f"- 中位收益：{summary['base']['median_return']}%", '', '## 相关性 Top 20', '', features.head(20).to_markdown(index=False), '', '## 单因子过滤扫描 Top 20', '', rules_df.head(20).to_markdown(index=False) if not rules_df.empty else '无', '']
(OUT / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2)[:10000])
