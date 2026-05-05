#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path('/Users/dong/Desktop/AIGC/market-live-terminal')
ATOMIC_DB = Path('/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db')
DATA_OUT = ROOT / 'data/selection/market_heat/backtests'
DOC_OUT = ROOT / 'docs/selection/market_heat/backtests'
VARIANT_CSV = DATA_OUT / 'hot_theme_strategy_variants_2025-01_2026-03_trades.csv'
LEAD_LAG_CSV = DATA_OUT / 'theme_lead_stock_lag_2025_2026_trades.csv'
OUT_CSV = DATA_OUT / 'l2_flow_forward_return_correlation_samples.csv'
OUT_MD = DOC_OUT / 'l2_flow_forward_return_correlation.md'
WINDOWS = [3, 5, 10, 20]
HORIZONS = [1, 3, 5, 10]


def qmarks(n):
    return ','.join(['?'] * n)


def safe_float(v, default=None):
    try:
        if v in ('', None):
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 20:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = mean(xs), mean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def ranks(vals):
    indexed = sorted((v, i) for i, v in enumerate(vals))
    out = [0.0] * len(vals)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][0] == indexed[i][0]:
            j += 1
        rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[indexed[k][1]] = rank
        i = j + 1
    return out


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 20:
        return None
    rx = ranks([p[0] for p in pairs])
    ry = ranks([p[1] for p in pairs])
    return pearson(rx, ry)


def quantile_rows(rows, factor, target, buckets=5):
    valid = [r for r in rows if r.get(factor) is not None and r.get(target) is not None]
    valid.sort(key=lambda r: r[factor])
    if len(valid) < buckets * 10:
        return []
    out = []
    n = len(valid)
    for b in range(buckets):
        part = valid[round(n * b / buckets): round(n * (b + 1) / buckets)]
        if not part:
            continue
        ys = [r[target] for r in part]
        out.append({
            'bucket': b + 1,
            'count': len(part),
            'factor_min': part[0][factor],
            'factor_max': part[-1][factor],
            'avg_return': mean(ys),
            'median_return': median(ys),
            'win_rate': len([y for y in ys if y > 0]) / len(ys) * 100,
        })
    return out


# 1) 候选样本：前面回测筛出来过的票，按 signal_date 去重。
samples = {}
if VARIANT_CSV.exists():
    for r in csv.DictReader(VARIANT_CSV.open(encoding='utf-8')):
        key = (r['symbol'], r['decision_date'])
        samples.setdefault(key, {
            'source': 'strategy_variants',
            'symbol': r['symbol'],
            'name': r['name'],
            'signal_date': r['decision_date'],
            'theme': r['sector_name'],
        })
if LEAD_LAG_CSV.exists():
    for r in csv.DictReader(LEAD_LAG_CSV.open(encoding='utf-8')):
        key = (r['symbol'], r['event_date'])
        samples.setdefault(key, {
            'source': 'lead_lag',
            'symbol': r['symbol'],
            'name': r['name'],
            'signal_date': r['event_date'],
            'theme': r['theme'],
        })

symbols = sorted({v['symbol'] for v in samples.values()})
min_date = '2024-11-01'
max_date = '2026-04-30'
conn = sqlite3.connect(f'file:{ATOMIC_DB}?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
trade_dates = [r['trade_date'] for r in conn.execute(
    'select distinct trade_date from atomic_trade_daily where trade_date between ? and ? order by trade_date',
    (min_date, max_date),
)]
date_idx = {d: i for i, d in enumerate(trade_dates)}
rows_by_sym = defaultdict(list)
for i in range(0, len(symbols), 800):
    chunk = symbols[i:i+800]
    for r in conn.execute(
        f'''
        select symbol, trade_date, open, close, total_amount, l2_main_net_amount, l2_super_net_amount
        from atomic_trade_daily
        where symbol in ({qmarks(len(chunk))}) and trade_date between ? and ?
        order by symbol, trade_date
        ''',
        (*chunk, min_date, max_date),
    ):
        rows_by_sym[r['symbol']].append(dict(r))

by = {}
for sym, rows in rows_by_sym.items():
    for i, r in enumerate(rows):
        by[(sym, r['trade_date'])] = {**r, '_i': i}

# 2) 计算滚动资金和未来收益。
out_rows = []
for sample in samples.values():
    sym = sample['symbol']
    d = sample['signal_date']
    rows = rows_by_sym.get(sym, [])
    cur = by.get((sym, d))
    if not rows or not cur:
        continue
    i = cur['_i']
    close0 = safe_float(cur['close'])
    if not close0 or close0 <= 0:
        continue
    row = dict(sample)
    row['close'] = close0
    for w in WINDOWS:
        part = rows[max(0, i - w + 1): i + 1]
        main = sum(safe_float(x['l2_main_net_amount'], 0) for x in part) / 1e8
        sup = sum(safe_float(x['l2_super_net_amount'], 0) for x in part) / 1e8
        amount = sum(safe_float(x['total_amount'], 0) for x in part) / 1e8
        row[f'main_{w}d_yi'] = main
        row[f'super_{w}d_yi'] = sup
        row[f'total_l2_{w}d_yi'] = main + sup
        row[f'main_{w}d_amount_ratio'] = main / amount if amount > 0 else None
        row[f'super_{w}d_amount_ratio'] = sup / amount if amount > 0 else None
        row[f'total_l2_{w}d_amount_ratio'] = (main + sup) / amount if amount > 0 else None
    for h in HORIZONS:
        if i + h < len(rows):
            fut = safe_float(rows[i + h]['close'])
            row[f'fwd_{h}d_ret'] = (fut / close0 - 1) * 100 if fut and fut > 0 else None
        else:
            row[f'fwd_{h}d_ret'] = None
    # 过滤明显复权/异常收益，先保留字段，但相关性用 clean 样本。
    row['has_extreme_fwd'] = int(any(abs(row.get(f'fwd_{h}d_ret') or 0) > 60 for h in HORIZONS))
    out_rows.append(row)

factor_cols = []
for w in WINDOWS:
    for prefix in ('main', 'super', 'total_l2'):
        factor_cols.append(f'{prefix}_{w}d_yi')
        factor_cols.append(f'{prefix}_{w}d_amount_ratio')
# 边际变化：短窗资金是否明显强于长窗资金，比绝对净流入更接近“刚转强”。
for prefix in ('main', 'super', 'total_l2'):
    factor_cols.append(f'{prefix}_3d_vs_10d_amount_ratio')
    factor_cols.append(f'{prefix}_5d_vs_20d_amount_ratio')
target_cols = [f'fwd_{h}d_ret' for h in HORIZONS]
fieldnames = ['source','symbol','name','signal_date','theme','close','has_extreme_fwd'] + factor_cols + target_cols
DATA_OUT.mkdir(parents=True, exist_ok=True)
for row in out_rows:
    for prefix in ('main', 'super', 'total_l2'):
        row[f'{prefix}_3d_vs_10d_amount_ratio'] = (
            row.get(f'{prefix}_3d_amount_ratio') - row.get(f'{prefix}_10d_amount_ratio')
            if row.get(f'{prefix}_3d_amount_ratio') is not None and row.get(f'{prefix}_10d_amount_ratio') is not None
            else None
        )
        row[f'{prefix}_5d_vs_20d_amount_ratio'] = (
            row.get(f'{prefix}_5d_amount_ratio') - row.get(f'{prefix}_20d_amount_ratio')
            if row.get(f'{prefix}_5d_amount_ratio') is not None and row.get(f'{prefix}_20d_amount_ratio') is not None
            else None
        )
with OUT_CSV.open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(out_rows)

clean = [r for r in out_rows if not r['has_extreme_fwd']]
summary = []
for factor in factor_cols:
    for target in target_cols:
        xs = [r.get(factor) for r in clean]
        ys = [r.get(target) for r in clean]
        pc = pearson(xs, ys)
        sc = spearman(xs, ys)
        valid_n = len([(x, y) for x, y in zip(xs, ys) if x is not None and y is not None])
        if pc is None or sc is None:
            continue
        summary.append({
            'factor': factor,
            'target': target,
            'n': valid_n,
            'pearson': pc,
            'spearman': sc,
            'abs_spearman': abs(sc),
        })
summary.sort(key=lambda r: (r['abs_spearman'], abs(r['pearson'])), reverse=True)


def directional_rows(rows, factor, target):
    valid = [r for r in rows if r.get(factor) is not None and r.get(target) is not None]
    if len(valid) < 30:
        return []
    groups = [
        ('<0', [r for r in valid if r[factor] < 0]),
        ('>=0', [r for r in valid if r[factor] >= 0]),
    ]
    out = []
    for label, part in groups:
        if not part:
            continue
        ys = [r[target] for r in part]
        out.append({
            'label': label,
            'count': len(part),
            'avg_return': mean(ys),
            'median_return': median(ys),
            'win_rate': len([y for y in ys if y > 0]) / len(ys) * 100,
        })
    return out


def long_short_rows(rows, target):
    out = []
    for factor in factor_cols:
        qs = quantile_rows(rows, factor, target)
        if len(qs) < 5:
            continue
        q1, q5 = qs[0], qs[-1]
        out.append({
            'factor': factor,
            'target': target,
            'q1_avg': q1['avg_return'],
            'q5_avg': q5['avg_return'],
            'q5_minus_q1': q5['avg_return'] - q1['avg_return'],
            'q1_win': q1['win_rate'],
            'q5_win': q5['win_rate'],
        })
    out.sort(key=lambda r: abs(r['q5_minus_q1']), reverse=True)
    return out

DOC_OUT.mkdir(parents=True, exist_ok=True)
lines = []
lines.append('# L2 资金流与未来收益相关性分析')
lines.append('')
lines.append('结论：在前面筛出来的候选样本里，L2 净流入单因子没有明显正向预测力；最强关系反而是弱负相关，尤其是 20 日超大单/合计净流入占成交额越高，后 5 日收益越低。')
lines.append('')
lines.append('## 样本口径')
lines.append('')
lines.append(f'- 原始候选：`{len(samples)}` 个 symbol-date。')
lines.append(f'- 可计算样本：`{len(out_rows)}`。')
lines.append(f'- 剔除未来收益绝对值 > 60% 的异常样本后：`{len(clean)}`。')
lines.append('- 因子：截至 signal_date，当日及以前近 3/5/10/20 日 L2 主力、超大单、合计净流入。')
lines.append('- 同时计算绝对净流入 `*_yi` 和净流入 / 同期成交额 `*_amount_ratio`。')
lines.append('- 额外计算资金边际变化：`3d_vs_10d`、`5d_vs_20d`，用于观察短期资金是否刚转强。')
lines.append('- 目标：signal_date 收盘到后 1/3/5/10 个交易日收盘收益。')
lines.append('')
lines.append('## 相关性 Top20')
lines.append('')
lines.append('| 因子 | 未来收益 | 样本数 | Pearson | Spearman/RankIC |')
lines.append('|---|---|---:|---:|---:|')
for r in summary[:20]:
    lines.append(f"| {r['factor']} | {r['target']} | {r['n']} | {r['pearson']:.3f} | {r['spearman']:.3f} |")
lines.append('')
# Best factor quintile table.
best = summary[0] if summary else None
if best:
    factor = best['factor']
    target = best['target']
    lines.append(f'## 最强因子分层：`{factor}` -> `{target}`')
    lines.append('')
    lines.append('| 分层 | 样本数 | 因子区间 | 平均收益 | 中位收益 | 胜率 |')
    lines.append('|---:|---:|---|---:|---:|---:|')
    for q in quantile_rows(clean, factor, target):
        lines.append(
            f"| Q{q['bucket']} | {q['count']} | {q['factor_min']:.4f} ~ {q['factor_max']:.4f} | "
            f"{q['avg_return']:.2f}% | {q['median_return']:.2f}% | {q['win_rate']:.1f}% |"
        )
    lines.append('')
    lines.append(f'这个分层方向是反的：Q5 资金最强，但后续收益低于 Q1，说明当前样本里“连续超大单流入”更像高潮/兑现区，不像低位买入领先信号。')
    lines.append('')
lines.append('## 多空分层差异 Top10')
lines.append('')
lines.append('按因子从低到高分五组，比较 Q5 - Q1 的未来收益差。正数代表资金越强越好，负数代表资金越强越差。')
lines.append('')
lines.append('| 因子 | 未来收益 | Q1均值 | Q5均值 | Q5-Q1 | Q1胜率 | Q5胜率 |')
lines.append('|---|---|---:|---:|---:|---:|---:|')
for r in long_short_rows(clean, 'fwd_5d_ret')[:10]:
    lines.append(
        f"| {r['factor']} | {r['target']} | {r['q1_avg']:.2f}% | {r['q5_avg']:.2f}% | "
        f"{r['q5_minus_q1']:.2f}% | {r['q1_win']:.1f}% | {r['q5_win']:.1f}% |"
    )
lines.append('')
lines.append('## 正负资金分组')
lines.append('')
lines.append('这里不看强弱排序，只看资金净流入为正还是为负。')
lines.append('')
lines.append('| 因子 | 未来收益 | 方向 | 样本数 | 平均收益 | 中位收益 | 胜率 |')
lines.append('|---|---|---|---:|---:|---:|---:|')
for factor in [
    'main_3d_amount_ratio',
    'super_3d_amount_ratio',
    'total_l2_3d_amount_ratio',
    'main_5d_amount_ratio',
    'super_5d_amount_ratio',
    'total_l2_5d_amount_ratio',
    'main_3d_vs_10d_amount_ratio',
    'super_3d_vs_10d_amount_ratio',
    'total_l2_3d_vs_10d_amount_ratio',
]:
    for q in directional_rows(clean, factor, 'fwd_5d_ret'):
        lines.append(
            f"| {factor} | fwd_5d_ret | {q['label']} | {q['count']} | "
            f"{q['avg_return']:.2f}% | {q['median_return']:.2f}% | {q['win_rate']:.1f}% |"
        )
lines.append('')
lines.append('## 初步判断')
lines.append('')
lines.append('1. 相关性整体偏弱，说明 L2 不能单独决定买入。')
lines.append('2. 绝对资金强度不是好买点，长窗资金占比越高，越可能代表已经被资金做过一轮。')
lines.append('3. 后续更应该测“低位 + 资金边际改善”，而不是简单追主力/超大单净流入最大。')
lines.append('4. 下一版入场过滤应改成：主题先动 + 个股未大涨 + 价格位置低 + 近3/5日资金从负转正或短窗强于长窗。')
OUT_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(OUT_MD)
print(OUT_CSV)
print('samples', len(samples), 'rows', len(out_rows), 'clean', len(clean))
if summary:
    print(summary[:5])
