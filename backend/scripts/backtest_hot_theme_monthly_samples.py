#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

ROOT = Path('/Users/dong/Desktop/AIGC/market-live-terminal')
HEAT_DB = Path('/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db')
ATOMIC_DB = Path('/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_compact_current.db')
OUT_DIR = ROOT / 'docs/selection/market_heat/backtests'
DATA_OUT = ROOT / 'data/selection/market_heat/backtests'


def f(x, n=2):
    if x is None:
        return '-'
    return f'{float(x):.{n}f}'


def clamp(x, lo=0.0, hi=1.0):
    if x is None or math.isnan(float(x)) or math.isinf(float(x)):
        return lo
    return max(lo, min(hi, float(x)))


def qmarks(n):
    return ','.join(['?'] * n)


def month_iter(start_ym: str, end_ym: str):
    y, m = map(int, start_ym.split('-'))
    ey, em = map(int, end_ym.split('-'))
    while (y, m) <= (ey, em):
        yield f'{y:04d}-{m:02d}'
        m += 1
        if m == 13:
            y += 1
            m = 1


def choose_sample_dates(trade_dates: list[str], start_ym: str, end_ym: str) -> list[str]:
    out = []
    dset = set(trade_dates)
    for ym in month_iter(start_ym, end_ym):
        ds = [d for d in trade_dates if d.startswith(ym)]
        if not ds:
            continue
        out.append(ds[0])
        # 月中：选 >=15日的第一个交易日；如没有就取最接近15日。
        mid_candidates = [d for d in ds if int(d[-2:]) >= 15]
        mid = mid_candidates[0] if mid_candidates else min(ds, key=lambda d: abs(int(d[-2:]) - 15))
        if mid not in out:
            out.append(mid)
    return out


def theme_score(row) -> float:
    # 只用当日可见字段。偏向：热度强、持续强、L2正、上涨扩散、不过分单日脉冲。
    score = 0.0
    score += float(row['hot_score'] or 0) * 0.42
    score += float(row['persistence_score'] or 0) * 0.22
    score += clamp((float(row['l2_main_net_yi'] or 0) + 1) / 12) * 18
    score += clamp((float(row['up_ratio'] or 0) - 45) / 55) * 10
    score += clamp((float(row['amount_ratio'] or 1) - 0.8) / 1.2) * 8
    # 5日涨幅太负不要；太极端也略降权，防止高潮。
    r5 = float(row['avg_return_5d'] or 0)
    if r5 < -2:
        score -= 12
    if r5 > 18:
        score -= 6
    if row['lifecycle_state'] == 'new_hot':
        score += 4
    elif row['lifecycle_state'] == 'continuing_hot':
        score += 2
    return score


def choose_theme(hc: sqlite3.Connection, d: str):
    rows = hc.execute(
        '''
        select h.*, l.lifecycle_state, l.days_in_top15_5d, l.days_in_top30_10d
        from fine_theme_heat_daily h
        left join fine_theme_lifecycle_daily l on h.trade_date=l.trade_date and h.theme_id=l.theme_id
        where h.trade_date=? and h.hot_rank<=30
        order by h.hot_rank
        ''',
        (d,),
    ).fetchall()
    candidates = []
    for r in rows:
        # 基础过滤：当天必须是有扩散、有成交、有资金的主题。
        if float(r['hot_score'] or 0) < 78:
            continue
        if float(r['up_ratio'] or 0) < 50:
            continue
        if float(r['amount_ratio'] or 0) < 1.0:
            continue
        if float(r['l2_main_net_yi'] or 0) <= 0:
            continue
        if float(r['avg_return_1d'] or 0) < 0.5:
            continue
        candidates.append((theme_score(r), r))
    if not candidates:
        return None, rows
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1], rows


def stock_score(row) -> float:
    r1 = float(row['return_1d'] or 0)
    r5 = float(row['return_5d'] or 0)
    r20 = float(row['return_20d'] or 0)
    amount = float(row['amount_yi'] or 0)
    amount_ratio = float(row['amount_ratio_20d'] or 0)
    l2 = float(row['l2_main_net_yi'] or 0)
    super_l2 = float(row['l2_super_net_yi'] or 0)
    pos = float(row['price_position_20d'] or 0)
    role = row['role'] or ''
    score = 0.0
    score += clamp((r1 + 2) / 12) * 12
    score += clamp((r5 + 5) / 25) * 16
    score += clamp(amount_ratio / 2.5) * 14
    score += clamp((l2 + 0.2) / 3.5) * 20
    score += clamp((super_l2 + 0.1) / 2.5) * 10
    score += clamp(amount / 20) * 8
    if 'leader' in role:
        score += 8
    if 'volume_core' in role:
        score += 8
    if 'low_position_candidate' in role:
        score += 6
    # 高位不一刀切，但过热要扣分。
    if pos > 0.95 and r20 > 45:
        score -= 8
    if r1 > 9.8 and r20 > 50:
        score -= 5
    if r5 < -8 or l2 <= -0.2:
        score -= 15
    return score


def choose_stocks(hc: sqlite3.Connection, d: str, sector_name: str) -> list[sqlite3.Row]:
    rows = hc.execute(
        '''
        select * from fine_theme_member_daily
        where trade_date=? and sector_name=?
        ''',
        (d, sector_name),
    ).fetchall()
    filtered = []
    for r in rows:
        if float(r['amount_yi'] or 0) < 0.5:
            continue
        if float(r['return_1d'] or 0) < -4:
            continue
        if float(r['l2_main_net_yi'] or 0) < -0.2:
            continue
        filtered.append((stock_score(r), r))
    filtered.sort(key=lambda x: x[0], reverse=True)
    # 尽量包含不同角色；不足则按分数补满。
    selected = []
    def add_first(pred):
        for _, r in filtered:
            if r['symbol'] in {x['symbol'] for x in selected}:
                continue
            if pred(r):
                selected.append(r)
                return
    add_first(lambda r: 'leader' in (r['role'] or '') or 'volume_core' in (r['role'] or ''))
    add_first(lambda r: float(r['amount_yi'] or 0) >= 5 and float(r['l2_main_net_yi'] or 0) > 0)
    add_first(lambda r: float(r['price_position_20d'] or 0) < 0.9 or 'low_position_candidate' in (r['role'] or ''))
    for _, r in filtered:
        if len(selected) >= 3:
            break
        if r['symbol'] not in {x['symbol'] for x in selected}:
            selected.append(r)
    return selected[:3]


def load_stock_rows(ac: sqlite3.Connection, symbols: list[str], start: str, end: str):
    rows = {s: [] for s in symbols}
    if not symbols:
        return rows, {}
    for r in ac.execute(
        f'''
        select symbol,trade_date,open,high,low,close,total_amount,l2_main_net_amount,l2_super_net_amount
        from atomic_trade_daily
        where symbol in ({qmarks(len(symbols))}) and trade_date between ? and ?
        order by symbol,trade_date
        ''',
        (*symbols, start, end),
    ):
        rows[r['symbol']].append(dict(r))
    by = {}
    for s, rs in rows.items():
        for i, r in enumerate(rs):
            closes20 = [float(x['close']) for x in rs[max(0, i - 19): i + 1]]
            closes10 = [float(x['close']) for x in rs[max(0, i - 9): i + 1]]
            by[(s, r['trade_date'])] = {
                **r,
                'ma10': sum(closes10) / len(closes10),
                'ma20': sum(closes20) / len(closes20),
            }
    return rows, by


def simulate_trade(ac, hc, pick, trade_dates, buy_date, end_date):
    sym = pick['symbol']
    _, by = load_stock_rows(ac, [sym], '2024-11-01', end_date)
    if (sym, buy_date) not in by:
        return None
    theme_rank = {
        r['trade_date']: dict(r)
        for r in hc.execute(
            'select trade_date,hot_rank,hot_score from fine_theme_heat_daily where sector_name=? and trade_date between ? and ?',
            (pick['sector_name'], buy_date, end_date),
        )
    }
    buy_price = float(by[(sym, buy_date)]['open'])
    peak = buy_price
    peak_date = buy_date
    neg_l2_streak = 0
    theme_out_streak = 0
    sell_date = None
    sell_price = None
    sell_reason = None
    trigger_date = None
    max_dd = 0.0
    holding_dates = [d for d in trade_dates if buy_date <= d <= end_date]
    for d in holding_dates:
        r = by.get((sym, d))
        if not r:
            continue
        close = float(r['close'])
        if close > peak:
            peak = close
            peak_date = d
        dd = (close / peak - 1) * 100
        max_dd = min(max_dd, dd)
        ret = (close / buy_price - 1) * 100
        l2 = float(r['l2_main_net_amount'] or 0)
        neg_l2_streak = neg_l2_streak + 1 if l2 < 0 else 0
        tr = theme_rank.get(d)
        theme_in = bool(tr and tr['hot_rank'] <= 30)
        theme_out_streak = 0 if theme_in else theme_out_streak + 1
        signal = None
        if ret <= -20:
            signal = '硬止损：收盘亏损超过20%'
        elif peak / buy_price - 1 >= 0.20 and dd <= -15:
            signal = '移动止盈：收益曾超过20%，从高点回撤超过15%'
        elif theme_out_streak >= 5 and close < float(r['ma20']):
            signal = '主题退潮：主题连续5日未进Top30且跌破MA20'
        elif neg_l2_streak >= 3 and close < float(r['ma10']):
            signal = '资金转弱：L2连续3日净流出且跌破MA10'
        if signal:
            trigger_date = d
            later = [x for x in trade_dates if x > d]
            if later and by.get((sym, later[0])):
                sell_date = later[0]
                sell_price = float(by[(sym, sell_date)]['open'])
                sell_reason = f'{signal}；{d}收盘触发，次日开盘卖出'
            else:
                sell_date = d
                sell_price = close
                sell_reason = f'{signal}；最后交易日收盘卖出'
            break
    if sell_date is None:
        sell_date = holding_dates[-1]
        sell_price = float(by[(sym, sell_date)]['close'])
        sell_reason = '未触发卖出，期末收盘估值'
    hold_days = len([d for d in trade_dates if buy_date <= d <= sell_date])
    return {
        **pick,
        'buy_date': buy_date,
        'buy_price': buy_price,
        'sell_date': sell_date,
        'sell_price': sell_price,
        'trigger_date': trigger_date or '',
        'sell_reason': sell_reason,
        'hold_days': hold_days,
        'return_pct': (sell_price / buy_price - 1) * 100,
        'max_drawdown_pct': max_dd,
        'peak_price': peak,
        'peak_date': peak_date,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start-ym', default='2025-01')
    ap.add_argument('--end-ym', default='2026-03')
    ap.add_argument('--end-date', default='2026-04-30')
    args = ap.parse_args()

    hc = sqlite3.connect(f'file:{HEAT_DB}?mode=ro', uri=True)
    hc.row_factory = sqlite3.Row
    ac = sqlite3.connect(f'file:{ATOMIC_DB}?mode=ro', uri=True)
    ac.row_factory = sqlite3.Row
    trade_dates = [r['trade_date'] for r in ac.execute('select distinct trade_date from atomic_trade_daily where trade_date between ? and ? order by trade_date', ('2025-01-01', args.end_date))]
    sample_dates = choose_sample_dates(trade_dates, args.start_ym, args.end_ym)

    decisions = []
    trades = []
    for d in sample_dates:
        buy_candidates = [x for x in trade_dates if x > d]
        if not buy_candidates:
            continue
        buy_date = buy_candidates[0]
        theme, hot_rows = choose_theme(hc, d)
        if not theme:
            decisions.append({'decision_date': d, 'buy_date': buy_date, 'sector_name': '', 'skip_reason': '无合格热点主题'})
            continue
        stocks = choose_stocks(hc, d, theme['sector_name'])
        decisions.append({
            'decision_date': d,
            'buy_date': buy_date,
            'sector_name': theme['sector_name'],
            'theme_rank': theme['hot_rank'],
            'theme_hot_score': theme['hot_score'],
            'theme_state': theme['lifecycle_state'],
            'theme_l2': theme['l2_main_net_yi'],
            'theme_reason': f"Rank{theme['hot_rank']} 热度{f(theme['hot_score'],1)} 持续{f(theme['persistence_score'],1)} 5日{f(theme['avg_return_5d'],1)}% 上涨占比{f(theme['up_ratio'],1)}% L2 {f(theme['l2_main_net_yi'],1)}亿",
            'skip_reason': '' if stocks else '主题无合格个股',
        })
        for s in stocks:
            pick = {
                'decision_date': d,
                'sector_name': theme['sector_name'],
                'theme_rank': theme['hot_rank'],
                'theme_state': theme['lifecycle_state'],
                'symbol': s['symbol'],
                'name': s['name'],
                'role': s['role'] or '',
                'buy_reason': f"{theme['sector_name']} Rank{theme['hot_rank']}；个股角色 {s['role']}；1日{f(s['return_1d'],1)}%，5日{f(s['return_5d'],1)}%，20日{f(s['return_20d'],1)}%；成交{f(s['amount_yi'],1)}亿，量比{f(s['amount_ratio_20d'],2)}，L2 {f(s['l2_main_net_yi'],2)}亿，20日位置{f(s['price_position_20d'],2)}",
            }
            tr = simulate_trade(ac, hc, pick, trade_dates, buy_date, args.end_date)
            if tr:
                trades.append(tr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_OUT / 'hot_theme_monthly_samples_2025-01_2026-03_trades.csv'
    md_path = OUT_DIR / 'hot_theme_monthly_samples_2025-01_2026-03.md'
    fields = ['decision_date','sector_name','theme_rank','theme_state','symbol','name','role','buy_date','buy_price','sell_date','sell_price','hold_days','return_pct','max_drawdown_pct','peak_date','peak_price','buy_reason','sell_reason']
    with csv_path.open('w', newline='', encoding='utf-8') as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for t in trades:
            w.writerow(t)

    rets = [t['return_pct'] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    by_day = {}
    for t in trades:
        by_day.setdefault(t['decision_date'], []).append(t)
    day_returns = [mean([x['return_pct'] for x in xs]) for xs in by_day.values()]
    lines = []
    lines.append('# 热点策略批量样例回测：2025-01 至 2026-03 每月两日')
    lines.append('')
    lines.append(f"结论：共 `{len(by_day)}` 个决策日、`{len(trades)}` 笔交易；单笔平均收益 `{mean(rets):.1f}%`，胜率 `{len(wins)/len(rets)*100:.1f}%`；按决策日等权平均收益 `{mean(day_returns):.1f}%`。")
    lines.append('')
    lines.append('## 回测口径')
    lines.append('')
    lines.append('- 每月两个截面：当月第一个交易日 + 15 日后第一个交易日。')
    lines.append('- 决策日收盘后选 1 个热点主题，并在主题内最多选 3 只股票。')
    lines.append('- 次一交易日开盘买入，后续逐日按规则卖出。')
    lines.append('- 选股只使用决策日及以前的热点、成交、L2、价格衍生字段；卖出只使用当日及以前数据。')
    lines.append('- 当前仍使用现在的主题成分映射，正式严谨回测需做历史成分版本化。')
    lines.append('')
    lines.append('## 汇总')
    lines.append('')
    lines.append(f'- 决策日数量：`{len(by_day)}`')
    lines.append(f'- 交易数量：`{len(trades)}`')
    lines.append(f'- 单笔平均收益：`{mean(rets):.1f}%`')
    lines.append(f'- 单笔中位收益：`{sorted(rets)[len(rets)//2]:.1f}%`')
    lines.append(f'- 胜率：`{len(wins)/len(rets)*100:.1f}%`')
    lines.append(f'- 最大单笔收益：`{max(rets):.1f}%`')
    lines.append(f'- 最大单笔亏损：`{min(rets):.1f}%`')
    lines.append(f'- 平均持股交易日：`{mean([t["hold_days"] for t in trades]):.1f}`')
    lines.append(f'- 平均最大回撤：`{mean([t["max_drawdown_pct"] for t in trades]):.1f}%`')
    lines.append('')
    lines.append('## 按决策日结果')
    lines.append('')
    lines.append('| 决策日 | 买入日 | 主题 | 状态 | 交易数 | 平均收益 | 最好 | 最差 |')
    lines.append('|---|---|---|---|---:|---:|---:|---:|')
    for d in sorted(by_day):
        xs = by_day[d]
        dec = next((x for x in decisions if x['decision_date'] == d), {})
        rr = [x['return_pct'] for x in xs]
        lines.append(f"| {d} | {dec.get('buy_date','')} | {dec.get('sector_name','')} | {dec.get('theme_state','')} | {len(xs)} | {mean(rr):.1f}% | {max(rr):.1f}% | {min(rr):.1f}% |")
    lines.append('')
    lines.append('## 交易明细')
    lines.append('')
    lines.append('| 决策日 | 主题 | 股票 | 买入 | 卖出 | 持股日 | 收益 | 最大回撤 | 买入逻辑 | 卖出逻辑 |')
    lines.append('|---|---|---|---:|---:|---:|---:|---:|---|---|')
    for t in trades:
        lines.append(f"| {t['decision_date']} | {t['sector_name']} | {t['name']} `{t['symbol']}` | {t['buy_date']} {f(t['buy_price'],2)} | {t['sell_date']} {f(t['sell_price'],2)} | {t['hold_days']} | {f(t['return_pct'],1)}% | {f(t['max_drawdown_pct'],1)}% | {t['buy_reason']} | {t['sell_reason']} |")
    lines.append('')
    lines.append('## 初步问题与可调参数')
    lines.append('')
    lines.append('1. 如果结果过高，首先要排查主题成分是否有未来偏差；需要把 `clean_stock_sector_memberships` 做日期版本化。')
    lines.append('2. 当前策略偏进攻：允许买高位强势股，收益高但回撤也大。')
    lines.append('3. 可调参数：主题热度阈值、连续高热降权、个股20日位置惩罚、L2连续流出卖出天数、移动止盈回撤比例。')
    lines.append('4. 下一步应增加基准：同期全市场随机3股、同主题随机3股、只买主题龙头、只买低位补涨。')
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(md_path)
    print(csv_path)

if __name__ == '__main__':
    main()
