#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.core.config import candidate_atomic_db_paths

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STUDY_CSV = REPO_ROOT / 'logs' / 'ytd_doublers_20260430.study.csv'
DEFAULT_OUTPUT_DIR = REPO_ROOT / 'data' / 'selection' / 'doubler_analysis'
DEFAULT_DOCS_DIR = REPO_ROOT / 'docs' / 'selection' / 'doublers' / '2026-ytd' / 'top20'
DEFAULT_MARKET_DB = Path(os.getenv('DB_PATH', '/Users/dong/Desktop/AIGC/market-data/market_data.db'))
DEFAULT_SELECTION_DB = Path(os.getenv('SELECTION_DB_PATH', '/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db'))


def resolve_default_atomic_db() -> Path:
    explicit = str(os.getenv('ATOMIC_MAINBOARD_DB_PATH') or os.getenv('ATOMIC_DB_PATH') or '').strip()
    if explicit:
        return Path(explicit)
    for raw in candidate_atomic_db_paths():
        path = Path(str(raw))
        if path.exists():
            return path
    return Path('/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_compact_current.db')


DEFAULT_ATOMIC_DB = resolve_default_atomic_db()

SPECIAL_FLAG_KEYWORDS = ('ST', '退')
STORY_KEYWORDS: "OrderedDict[str, Tuple[str, ...]]" = OrderedDict(
    [
        ('算力/AI', ('算力', 'AI', '英伟达', '超聚变', '液冷', '服务器', '数据中心')),
        ('业绩', ('年报', '一季报', '业绩', '预增', '净利润', '扭亏')),
        ('有色/小金属', ('黄金', '白银', '钨', '稀土', '小金属', '锑', '铜')),
        ('机器人/军工', ('机器人', '商业航天', '军工', '船舶')),
        ('新能源', ('储能', '锂电', '光伏', '风电', '电池')),
        ('消费/传媒', ('消费', '包装', '饮料', '传媒', '游戏', '抖音')),
    ]
)
EVENT_CATEGORY_KEYWORDS: "OrderedDict[str, Tuple[str, ...]]" = OrderedDict(
    [
        ('业绩财报', ('业绩', '年报', '季报', '一季报', '半年报', '三季报', '预增', '预亏', '扭亏', '净利润')),
        ('异动监管', ('异常波动', '停牌核查', '问询函', '监管', '回复函', '风险提示')),
        ('题材问答', ('问答', '董秘', '合作', '算力', 'AI', '机器人', '商业航天', '液冷', '储能', '黄金', '白银', '钨', '稀土', '订单', '传闻', '澄清')),
        ('股东资本动作', ('减持', '增持', '质押', '解除质押', '回购', '激励', '解除限售', '股份上市流通')),
        ('融资担保治理', ('担保', '融资', '董事会', '股东会', '关联交易', '法律意见书', '工作细则', '制度')),
        ('行业新闻催化', ('板块', '概念', '涨停分析', '异动', '续创历史新高', '涨价', '龙头')),
        ('资产重组预期', ('资产注入', '重组', '收购', '并购', '置出资产', '借壳')),
    ]
)


def slugify(value: str) -> str:
    value = (value or '').strip().replace(' ', '-')
    value = re.sub(r'[\\/:*?"<>|]+', '-', value)
    value = re.sub(r'-+', '-', value)
    return value.strip('-') or 'unknown'


def pct(value: Optional[float]) -> str:
    if value is None:
        return '--'
    return f'{value * 100:.2f}%'


def pct_plain(value: Optional[float]) -> str:
    if value is None:
        return '--'
    return f'{value:.2f}%'


def amt_yi(value: Optional[float]) -> str:
    if value is None:
        return '--'
    return f'{value / 1e8:.2f}亿'


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def query_rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(sql, params).fetchall()


def query_one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(sql, params).fetchone()


def load_close_series(conn: sqlite3.Connection, symbol: str, start_date: str, end_date: str) -> List[Tuple[str, float]]:
    rows = query_rows(
        conn,
        '''
        SELECT trade_date, close
        FROM atomic_trade_daily
        WHERE lower(symbol)=lower(?) AND trade_date>=? AND trade_date<=?
        ORDER BY trade_date
        ''',
        (symbol, start_date, end_date),
    )
    return [(str(r['trade_date']), float(r['close'])) for r in rows if r['close'] is not None]


def load_close_series_market(conn: sqlite3.Connection, symbol: str, start_date: str, end_date: str) -> List[Tuple[str, float]]:
    rows = query_rows(
        conn,
        '''
        SELECT date, close
        FROM local_history
        WHERE lower(symbol)=lower(?) AND date>=? AND date<=?
        ORDER BY date
        ''',
        (symbol, start_date, end_date),
    )
    return [(str(r['date']), float(r['close'])) for r in rows if r['close'] is not None]


def derive_stage_markers(series: Sequence[Tuple[str, float]], launch_date: str, peak_date: str) -> Dict[str, Optional[str]]:
    if not series:
        return {
            'wave1_top_date': None,
            'wave1_top_close': None,
            'pullback_low_date': None,
            'pullback_low_close': None,
            'second_breakout_date': None,
            'second_breakout_close': None,
        }
    launch_idx = next((i for i, (d, _c) in enumerate(series) if d >= launch_date), 0)
    peak_idx = next((i for i, (d, _c) in enumerate(series) if d >= peak_date), len(series) - 1)
    if peak_idx < launch_idx:
        peak_idx = len(series) - 1

    low_close = series[0][1]
    rolling_high = low_close
    wave1_top_idx = launch_idx
    drawdown_break_idx: Optional[int] = None

    for i in range(launch_idx, peak_idx + 1):
        _d, close = series[i]
        if close >= rolling_high:
            rolling_high = close
            wave1_top_idx = i
        if rolling_high >= low_close * 1.30 and close <= rolling_high * 0.85:
            drawdown_break_idx = i
            break

    pullback_low_idx: Optional[int] = None
    second_breakout_idx: Optional[int] = None
    if drawdown_break_idx is not None:
        wave1_top_close = series[wave1_top_idx][1]
        min_close = float('inf')
        for i in range(drawdown_break_idx, peak_idx + 1):
            if series[i][1] <= min_close:
                min_close = series[i][1]
                pullback_low_idx = i
            if pullback_low_idx is not None and series[i][1] >= wave1_top_close * 1.03:
                second_breakout_idx = i
                break

    return {
        'wave1_top_date': series[wave1_top_idx][0],
        'wave1_top_close': f'{series[wave1_top_idx][1]:.4f}',
        'pullback_low_date': series[pullback_low_idx][0] if pullback_low_idx is not None else None,
        'pullback_low_close': f'{series[pullback_low_idx][1]:.4f}' if pullback_low_idx is not None else None,
        'second_breakout_date': series[second_breakout_idx][0] if second_breakout_idx is not None else None,
        'second_breakout_close': f'{series[second_breakout_idx][1]:.4f}' if second_breakout_idx is not None else None,
    }


def stage_snapshot(
    market_conn: sqlite3.Connection,
    selection_conn: sqlite3.Connection,
    atomic_conn: sqlite3.Connection,
    symbol: str,
    trade_date: str,
) -> Dict[str, Any]:
    trade = query_one(
        atomic_conn,
        '''
        SELECT trade_date, open, high, low, close,
               l2_main_net_amount, l2_super_net_amount, l2_buy_ratio, l2_sell_ratio,
               positive_l2_net_bar_count, negative_l2_net_bar_count
        FROM atomic_trade_daily
        WHERE lower(symbol)=lower(?) AND trade_date=?
        ''',
        (symbol, trade_date),
    )
    fallback_local = query_one(
        market_conn,
        '''
        SELECT date, close, net_inflow
        FROM local_history
        WHERE lower(symbol)=lower(?) AND date=?
        ''',
        (symbol, trade_date),
    )
    signal = query_one(
        selection_conn,
        '''
        SELECT f.return_20d_pct, f.price_position_20d, f.price_position_60d,
               f.net_inflow_20d, f.positive_inflow_ratio_20d, f.l2_main_net_3d,
               s.stealth_score, s.breakout_score, s.distribution_score,
               s.stealth_signal, s.confirm_signal, s.exit_signal
        FROM selection_feature_daily f
        JOIN selection_signal_daily s USING(symbol, trade_date, feature_version)
        WHERE lower(f.symbol)=lower(?) AND f.trade_date=?
        ''',
        (symbol, trade_date),
    )
    limit_state = query_one(
        atomic_conn,
        '''
        SELECT touch_limit_up, is_limit_up_close, broken_limit_up,
               touch_limit_up_count_5m, first_touch_limit_up_time, last_touch_limit_up_time,
               limit_state_label
        FROM atomic_limit_state_daily
        WHERE lower(symbol)=lower(?) AND trade_date=?
        ''',
        (symbol, trade_date),
    )
    order_state = query_one(
        atomic_conn,
        '''
        SELECT cvd_delta_amount, oib_delta_amount, buy_support_ratio, sell_pressure_ratio,
               positive_oib_streak_max
        FROM atomic_order_daily
        WHERE lower(symbol)=lower(?) AND trade_date=?
        ''',
        (symbol, trade_date),
    )
    titles = query_rows(
        market_conn,
        '''
        SELECT substr(published_at,1,10) AS event_date, source_type, event_subtype, title
        FROM stock_events
        WHERE lower(symbol)=lower(?) AND substr(published_at,1,10)=?
        ORDER BY importance DESC, published_at ASC
        LIMIT 6
        ''',
        (symbol, trade_date),
    )
    return {
        'trade': dict(trade) if trade else {},
        'fallback_local': dict(fallback_local) if fallback_local else {},
        'signal': dict(signal) if signal else {},
        'limit': dict(limit_state) if limit_state else {},
        'order': dict(order_state) if order_state else {},
        'titles': [dict(r) for r in titles],
    }


def event_highlights(conn: sqlite3.Connection, symbol: str, start_date: str, end_date: str, limit: int = 12) -> List[Dict[str, Any]]:
    rows = query_rows(
        conn,
        '''
        SELECT substr(published_at,1,10) AS event_date, source_type, event_subtype, title
        FROM stock_events
        WHERE lower(symbol)=lower(?) AND published_at>=? AND published_at<=?
        ORDER BY published_at ASC, importance DESC
        ''',
        (symbol, f'{start_date} 00:00:00', f'{end_date} 23:59:59'),
    )
    seen = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        title = str(r['title'] or '').strip()
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(dict(r))
        if len(out) >= limit:
            break
    return out


def company_context(conn: sqlite3.Connection, symbol: str) -> Dict[str, Any]:
    profile = query_one(
        conn,
        '''
        SELECT short_name, company_name, industry, main_business, listing_date, market, website
        FROM stock_company_profiles
        WHERE lower(symbol)=lower(?)
        ORDER BY fetched_at DESC
        LIMIT 1
        ''',
        (symbol,),
    )
    finance = query_one(
        conn,
        '''
        SELECT latest_period, eps, roe, revenue_growth, net_profit_growth,
               deducted_net_profit, debt_ratio, summary_text
        FROM stock_financial_snapshots
        WHERE lower(symbol)=lower(?)
        ORDER BY as_of_date DESC
        LIMIT 1
        ''',
        (symbol,),
    )
    return {
        'profile': dict(profile) if profile else {},
        'finance': dict(finance) if finance else {},
    }


def pick_stage(stage_rows: Sequence[Dict[str, Any]], stage_name: str) -> Optional[Dict[str, Any]]:
    return next((row for row in stage_rows if row['stage'] == stage_name), None)


def infer_story_tags(row: Dict[str, str], events: Sequence[Dict[str, Any]]) -> List[str]:
    texts = [row.get('theme_names') or '']
    texts.extend(str(item.get('title') or '') for item in events)
    joined = ' '.join(texts)
    tags: List[str] = []
    for label, keywords in STORY_KEYWORDS.items():
        if any(keyword in joined for keyword in keywords):
            tags.append(label)
    return tags


def interval_stats(
    market_conn: sqlite3.Connection,
    atomic_conn: sqlite3.Connection,
    symbol: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    trade_rows = query_rows(
        atomic_conn,
        '''
        SELECT trade_date, close, l2_main_net_amount, l2_super_net_amount
        FROM atomic_trade_daily
        WHERE lower(symbol)=lower(?) AND trade_date>=? AND trade_date<=?
        ORDER BY trade_date
        ''',
        (symbol, start_date, end_date),
    )
    limit_summary = query_one(
        atomic_conn,
        '''
        SELECT
            SUM(CASE WHEN touch_limit_up=1 THEN 1 ELSE 0 END) AS touch_limit_up_days,
            SUM(CASE WHEN is_limit_up_close=1 THEN 1 ELSE 0 END) AS sealed_up_days,
            SUM(CASE WHEN broken_limit_up=1 THEN 1 ELSE 0 END) AS broken_up_days
        FROM atomic_limit_state_daily
        WHERE lower(symbol)=lower(?) AND trade_date>=? AND trade_date<=?
        ''',
        (symbol, start_date, end_date),
    )
    event_counts = query_rows(
        market_conn,
        '''
        SELECT source_type, COUNT(*) AS cnt
        FROM stock_events
        WHERE lower(symbol)=lower(?) AND published_at>=? AND published_at<=?
        GROUP BY source_type
        ORDER BY cnt DESC, source_type ASC
        ''',
        (symbol, f'{start_date} 00:00:00', f'{end_date} 23:59:59'),
    )
    best_positive = None
    worst_negative = None
    if trade_rows:
        best_positive = max(trade_rows, key=lambda r: float(r['l2_main_net_amount'] or -10**18))
        worst_negative = min(trade_rows, key=lambda r: float(r['l2_main_net_amount'] or 10**18))
    return {
        'trade_days': len(trade_rows),
        'best_positive': dict(best_positive) if best_positive else None,
        'worst_negative': dict(worst_negative) if worst_negative else None,
        'touch_limit_up_days': int(limit_summary['touch_limit_up_days'] or 0) if limit_summary else 0,
        'sealed_up_days': int(limit_summary['sealed_up_days'] or 0) if limit_summary else 0,
        'broken_up_days': int(limit_summary['broken_up_days'] or 0) if limit_summary else 0,
        'event_counts': {str(r['source_type']): int(r['cnt']) for r in event_counts},
    }


def render_counterparty_story(event_counts: Dict[str, int]) -> str:
    if not event_counts:
        return '事件层覆盖仍偏弱，更多依赖价格与资金本身。'
    ordered = [f"{k}:{v}" for k, v in event_counts.items()]
    return ' / '.join(ordered)


def classify_event_category(event: Dict[str, Any]) -> str:
    text = ' '.join(
        str(event.get(key) or '')
        for key in ('title', 'event_subtype', 'source_type')
    )
    for label, keywords in EVENT_CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return label
    return '其他'


def summarize_event_phase(events: Sequence[Dict[str, Any]], *, empty_hint: str) -> List[str]:
    if not events:
        return [empty_hint]
    counts: "OrderedDict[str, int]" = OrderedDict()
    examples: Dict[str, List[str]] = {}
    for event in events:
        category = classify_event_category(event)
        counts[category] = counts.get(category, 0) + 1
        examples.setdefault(category, [])
        title = str(event.get('title') or '').strip()
        if title and title not in examples[category] and len(examples[category]) < 3:
            examples[category].append(title)
    top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    lines = []
    headline = '、'.join(f'{label}({count})' for label, count in top)
    lines.append(f'该阶段消息面主线集中在：{headline}。')
    if '业绩财报' in counts and '题材问答' in counts:
        lines.append('说明市场不是只看公告本身，而是把业绩线和题材想象一起抬价。')
    elif '异动监管' in counts and '题材问答' in counts:
        lines.append('说明股价已经进入高波动博弈区，监管/异动公告并没有压住题材情绪。')
    elif '股东资本动作' in counts and '行业新闻催化' in counts:
        lines.append('说明高位阶段一边有资本动作/兑现压力，一边仍有板块热度在续命。')
    elif '融资担保治理' in counts and len(counts) == 1:
        lines.append('说明公告多偏治理/流程型，本身不是决定性利好，更多是资金先行。')
    for label, _count in top:
        if examples.get(label):
            lines.append(f"{label}代表标题：{'；'.join(examples[label][:2])}。")
    return lines


def build_stage_rows(
    base_row: Dict[str, str],
    stage_marks: Dict[str, Optional[str]],
    market_conn: sqlite3.Connection,
    selection_conn: sqlite3.Connection,
    atomic_conn: sqlite3.Connection,
) -> List[Dict[str, Any]]:
    stages = OrderedDict([
        ('区间低点', base_row['low_time'][:10]),
        ('启动确认', base_row.get('launch_date') or None),
        ('一波顶部', stage_marks.get('wave1_top_date')),
        ('一波回撤低点', stage_marks.get('pullback_low_date')),
        ('二波再启动', stage_marks.get('second_breakout_date')),
        ('区间高点', base_row['high_time'][:10]),
        ('当前状态', base_row['last_time'][:10] if base_row.get('last_time') else None),
    ])
    out = []
    seen_dates = set()
    for name, trade_date in stages.items():
        if not trade_date or trade_date in seen_dates:
            continue
        seen_dates.add(trade_date)
        snap = stage_snapshot(market_conn, selection_conn, atomic_conn, base_row['symbol'], trade_date)
        trade = snap['trade']
        fallback_local = snap['fallback_local']
        signal = snap['signal']
        limit_state = snap['limit']
        order_state = snap['order']
        out.append(
            {
                'stage': name,
                'date': trade_date,
                'close': trade.get('close') if trade.get('close') is not None else fallback_local.get('close'),
                'l2_main_net_amount': trade.get('l2_main_net_amount'),
                'fallback_net_inflow': fallback_local.get('net_inflow'),
                'l2_super_net_amount': trade.get('l2_super_net_amount'),
                'l2_buy_ratio': trade.get('l2_buy_ratio'),
                'l2_sell_ratio': trade.get('l2_sell_ratio'),
                'return_20d_pct': signal.get('return_20d_pct'),
                'price_position_20d': signal.get('price_position_20d'),
                'price_position_60d': signal.get('price_position_60d'),
                'breakout_score': signal.get('breakout_score'),
                'stealth_score': signal.get('stealth_score'),
                'distribution_score': signal.get('distribution_score'),
                'net_inflow_20d': signal.get('net_inflow_20d'),
                'l2_main_net_3d': signal.get('l2_main_net_3d'),
                'limit_state_label': limit_state.get('limit_state_label'),
                'is_limit_up_close': limit_state.get('is_limit_up_close'),
                'broken_limit_up': limit_state.get('broken_limit_up'),
                'buy_support_ratio': order_state.get('buy_support_ratio'),
                'sell_pressure_ratio': order_state.get('sell_pressure_ratio'),
                'titles': snap['titles'],
            }
        )
    return out


def render_stage_table(stage_rows: Sequence[Dict[str, Any]]) -> str:
    lines = [
        '| 阶段 | 日期 | 收盘 | 20日收益 | breakout | stealth | 主力/资金净额 | 涨停形态 | 备注消息 |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |',
    ]
    for row in stage_rows:
        titles = '；'.join(item['title'] for item in row['titles'][:2]) if row['titles'] else '--'
        funding_amount = row['l2_main_net_amount'] if row['l2_main_net_amount'] is not None else row.get('fallback_net_inflow')
        lines.append(
            f"| {row['stage']} | {row['date']} | {row['close'] or '--'} | {pct_plain(row['return_20d_pct']) if row['return_20d_pct'] is not None else '--'} | "
            f"{row['breakout_score'] if row['breakout_score'] is not None else '--'} | {row['stealth_score'] if row['stealth_score'] is not None else '--'} | "
            f"{amt_yi(funding_amount) if funding_amount is not None else '--'} | {row['limit_state_label'] or '--'} | {titles} |"
        )
    return '\n'.join(lines)


def render_event_list(events: Sequence[Dict[str, Any]]) -> str:
    if not events:
        return '- 暂无事件样本\n'
    return '\n'.join(
        f"- `{item['event_date']}` [{item['source_type']}/{item['event_subtype']}] {item['title']}" for item in events
    ) + '\n'


def generate_report(
    row: Dict[str, str],
    stage_marks: Dict[str, Optional[str]],
    market_conn: sqlite3.Connection,
    selection_conn: sqlite3.Connection,
    atomic_conn: sqlite3.Connection,
    docs_dir: Path,
    *,
    overwrite: bool = False,
) -> Path:
    ctx = company_context(market_conn, row['symbol'])
    profile = ctx['profile']
    finance = ctx['finance']
    stage_rows = build_stage_rows(row, stage_marks, market_conn, selection_conn, atomic_conn)
    fallback_mode = any(item.get('l2_main_net_amount') is None and item.get('fallback_net_inflow') is not None for item in stage_rows)
    low_date = row['low_time'][:10]
    launch_date = row.get('launch_date') or low_date
    peak_date = row['high_time'][:10]
    current_date = row['last_time'][:10] if row.get('last_time') else peak_date
    report_slug = f"{int(row['rank']):02d}-{row['symbol']}-{slugify(row['display_name'])}.md"
    out_path = docs_dir / report_slug
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not overwrite:
        return out_path

    launch_events = event_highlights(market_conn, row['symbol'], launch_date, peak_date, limit=12)
    low_events = event_highlights(market_conn, row['symbol'], low_date, launch_date, limit=8)
    post_peak_events = event_highlights(market_conn, row['symbol'], peak_date, current_date, limit=8)
    all_events = event_highlights(market_conn, row['symbol'], low_date, current_date, limit=40)
    stats = interval_stats(market_conn, atomic_conn, row['symbol'], low_date, current_date)
    story_tags = infer_story_tags(row, all_events)
    low_stage = pick_stage(stage_rows, '区间低点') or {}
    launch_stage = pick_stage(stage_rows, '启动确认') or low_stage
    wave1_stage = pick_stage(stage_rows, '一波顶部') or {}
    pullback_stage = pick_stage(stage_rows, '一波回撤低点') or {}
    second_stage = pick_stage(stage_rows, '二波再启动') or {}
    peak_stage = pick_stage(stage_rows, '区间高点') or {}
    current_stage = pick_stage(stage_rows, '当前状态') or peak_stage or {}

    notes = []
    if row['phase_label'] == 'near_high':
        notes.append('当前仍贴近区间高点，说明主升未被有效破坏。')
    elif row['phase_label'] == 'second_wave':
        notes.append('样本存在明显二波结构，首波回撤后再次创出有效新高。')
    else:
        notes.append('样本更像一波快速冲顶，随后进入明显回撤或横盘消化。')
    if row.get('launch_type') == 'breakout70':
        notes.append('启动是典型新高突破型，不是低位 stealth 型。')
    else:
        notes.append('启动更依赖大阳线/情绪点火，而不是现有 breakout70。')

    rise_points: List[str] = []
    if launch_stage:
        rise_points.append(
            f"启动确认日 `{launch_date}` 的 breakout_score={launch_stage.get('breakout_score') or '--'}，"
            f"20/60日位置={launch_stage.get('price_position_20d') or '--'} / {launch_stage.get('price_position_60d') or '--'}，"
            "说明赚钱段是突破后确认，不是底部静默吸筹。"
        )
    if story_tags:
        rise_points.append(f"消息叙事主线集中在 **{' / '.join(story_tags[:3])}**。")
    if stats['sealed_up_days'] or stats['broken_up_days']:
        rise_points.append(
            f"区间内共有 `{stats['touch_limit_up_days']}` 次冲击涨停、其中 `{stats['sealed_up_days']}` 次封死、"
            f"`{stats['broken_up_days']}` 次炸板，说明它更像高波动强主线，而不是平滑慢牛。"
        )
    best_positive = stats.get('best_positive') or {}
    if best_positive and best_positive.get('trade_date'):
        rise_points.append(
            f"L2 主力最强日出现在 `{best_positive['trade_date']}`，主力净额约 **{amt_yi(best_positive.get('l2_main_net_amount'))}**，"
            "说明关键拐点确实有大资金显性参与。"
        )
    if finance.get('summary_text'):
        rise_points.append(f"基本面层面，库内最新财务快照显示：{finance.get('summary_text')}。")

    retrace_points: List[str] = []
    worst_negative = stats.get('worst_negative') or {}
    if worst_negative and worst_negative.get('trade_date'):
        retrace_points.append(
            f"区间内最强分歧日是 `{worst_negative['trade_date']}`，L2 主力净额约 **{amt_yi(worst_negative.get('l2_main_net_amount'))}**，"
            "高位兑现/洗盘特征明显。"
        )
    if pullback_stage:
        retrace_points.append(
            f"一波回撤低点大致落在 `{pullback_stage['date']}`，若之后还能出现资金回补或再突破，就更像洗盘而不是趋势终结。"
        )
    if post_peak_events:
        retrace_points.append(
            f"高位之后主要扰动来自：{'；'.join(item['title'] for item in post_peak_events[:3])}。"
        )
    if current_stage.get('buy_support_ratio') is not None or current_stage.get('sell_pressure_ratio') is not None:
        retrace_points.append(
            f"当前订单层可参考 buy_support_ratio={current_stage.get('buy_support_ratio') or '--'}，"
            f"sell_pressure_ratio={current_stage.get('sell_pressure_ratio') or '--'}。"
        )

    follow_points: List[str] = []
    follow_points.append('继续看题材主线是否扩散，尤其是否还有新的事件/公告把故事往下续。')
    follow_points.append('继续看 L2 主力净额是否连续转负、而价格又不再创新高。')
    if row['phase_label'] == 'near_high':
        follow_points.append('这类 near_high 样本，重点不是猜顶，而是盯“高位放量滞涨 + 消息边际转弱”是否同时出现。')
    elif row['phase_label'] == 'second_wave':
        follow_points.append('这类 second_wave 样本，重点看二波后还能否演化成三波，还是转成平台派发。')
    else:
        follow_points.append('这类 one_wave_retrace 样本，重点看它后面有没有重新拿回主线地位。')
    fallback_note = '- 说明：该票部分阶段不在当前 atomic 主库覆盖范围，表格中的“主力/资金净额”已回退到 local_history 净流口径。\n' if fallback_mode else ''
    rise_block = '\n'.join(f"- {point}" for point in rise_points)
    retrace_block = '\n'.join(f"- {point}" for point in retrace_points) if retrace_points else '- 当前库内尚未观察到特别清晰的回落归因，需后续补更多事件与订单层数据。'
    follow_block = '\n'.join(f"{idx}. {point}" for idx, point in enumerate(follow_points, 1))
    low_phase_summary = '\n'.join(f"- {point}" for point in summarize_event_phase(low_events, empty_hint='这一段几乎没有成体系的消息催化，更像价格和资金先把股票从底部拉起来。'))
    launch_phase_summary = '\n'.join(f"- {point}" for point in summarize_event_phase(launch_events, empty_hint='启动到主升浪阶段缺少足够事件样本，说明走势主要由价格与资金驱动。'))
    peak_phase_summary = '\n'.join(f"- {point}" for point in summarize_event_phase(post_peak_events, empty_hint='高位之后库里还没积累到足够消息样本，先以资金与价格行为为主。'))

    content = f"""# {row['display_name']} {row['symbol']} 翻倍股样本报告

## 1. 先给结论

- 区间口径：`{low_date}` 到 `{peak_date}`
- 区间最大涨幅：**{float(row['max_gain_pct']) * 100:.2f}%**
- 当前阶段：**{row['phase_label']}**
- 启动日期：`{launch_date}`（{row.get('launch_type') or '--'}）
- 截至 `{current_date}` 距区间高点：**{float(row['close_vs_peak_pct']) * 100:.2f}%**
- 主题近似：{row['theme_names'] or '--'}
- 事件结构：{render_counterparty_story(stats['event_counts'])}
- 结论提炼：{' '.join(notes)}

## 2. 公司/财报背景

- 公司：{profile.get('company_name') or row['display_name']}
- 行业：{profile.get('industry') or '--'}
- 主营：{profile.get('main_business') or '--'}
- 上市日期：{profile.get('listing_date') or '--'}
- 最新财务快照：{finance.get('summary_text') or '--'}
- 关键财务字段：EPS {finance.get('eps') or '--'}；ROE {finance.get('roe') or '--'}；营收增速 {finance.get('revenue_growth') or '--'}%；净利增速 {finance.get('net_profit_growth') or '--'}%；资产负债率 {finance.get('debt_ratio') or '--'}%
{fallback_note}

## 3. 阶段拆解

{render_stage_table(stage_rows)}

## 4. 阶段消息面

### 4.1 低点到启动
{render_event_list(low_events)}
{low_phase_summary}

### 4.2 启动到主升浪
{render_event_list(launch_events)}
{launch_phase_summary}

### 4.3 高位后续/回撤线索
{render_event_list(post_peak_events)}
{peak_phase_summary}

## 5. 为什么它能涨

{rise_block}

## 6. 为什么会分歧 / 回落

{retrace_block}

## 7. 对策略的启发

1. **母策略别再执着纯底部 stealth**：这类票的大肉阶段是“回撤后 3~5 天内最先新高”的那一批。
2. **启动后持有状态机要独立**：主升里允许高波动、允许炸板，只要承接修复和事件主线没断，就不能机械卖。
3. **回撤归因要结合消息面**：如果回撤对应减持、监管、传闻证伪，但随后资金与题材修复，则更像洗盘不是结束。
4. **高位风险看分歧而不是绝对涨幅**：真正危险的是连续负向 L2、卖压抬升、消息驱动失真，而不是单纯涨太多。

## 8. 后续跟踪点

{follow_block}
"""
    out_path.write_text(content, encoding='utf-8')
    return out_path


def maybe_hydrate_events(symbols: Sequence[str]) -> None:
    from backend.app.services.stock_events import hydrate_symbol_event_context

    for symbol in symbols:
        hydrate_symbol_event_context(
            symbol,
            announcement_days=180,
            qa_days=120,
            news_days=60,
            recent_limit=8,
            mode='ytd_doubler_batch',
        )


def build_manifest(rows: Sequence[Dict[str, str]], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    filtered = [r for r in rows if r.get('is_special_treatment') != '1']
    filtered = sorted(filtered, key=lambda r: float(r['max_gain_pct']), reverse=True)
    if limit is not None:
        filtered = filtered[:limit]
    out: List[Dict[str, Any]] = []
    for rank, row in enumerate(filtered, 1):
        item = dict(row)
        item['rank'] = rank
        item['analysis_status'] = 'queued'
        item['report_path'] = ''
        out.append(item)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description='Build persistent YTD doubler checklist and optional sample reports')
    parser.add_argument('--study-csv', type=Path, default=DEFAULT_STUDY_CSV)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--docs-dir', type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument('--market-db', type=Path, default=DEFAULT_MARKET_DB)
    parser.add_argument('--selection-db', type=Path, default=DEFAULT_SELECTION_DB)
    parser.add_argument('--atomic-db', type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--report-symbols', nargs='*', default=[])
    parser.add_argument('--hydrate-events', action='store_true')
    parser.add_argument('--overwrite-reports', action='store_true')
    args = parser.parse_args()

    rows = load_rows(args.study_csv)
    master_manifest = build_manifest(rows, None)
    manifest = build_manifest(rows, args.limit)
    symbol_set = {item['symbol'].lower() for item in master_manifest}
    report_symbols = {item.lower() for item in args.report_symbols}
    if args.hydrate_events and report_symbols:
        maybe_hydrate_events(sorted(report_symbols))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.docs_dir.mkdir(parents=True, exist_ok=True)

    market_conn = sqlite3.connect(args.market_db)
    selection_conn = sqlite3.connect(args.selection_db)
    atomic_conn = sqlite3.connect(args.atomic_db)

    master_by_symbol = {item['symbol'].lower(): item for item in master_manifest}

    for item in master_manifest:
        series = load_close_series(atomic_conn, item['symbol'], item['low_time'][:10], item['last_time'][:10])
        if not series:
            series = load_close_series_market(market_conn, item['symbol'], item['low_time'][:10], item['last_time'][:10])
        stage_marks = derive_stage_markers(
            series,
            item.get('launch_date') or item['low_time'][:10],
            item['high_time'][:10],
        )
        item.update(stage_marks)
        if item['symbol'].lower() in report_symbols:
            report_path = generate_report(
                item,
                stage_marks,
                market_conn,
                selection_conn,
                atomic_conn,
                args.docs_dir,
                overwrite=args.overwrite_reports,
            )
            item['analysis_status'] = 'sample_done'
            item['report_path'] = str(report_path)

    for item in manifest:
        symbol = item['symbol'].lower()
        item.clear()
        item.update(master_by_symbol[symbol])

    market_conn.close()
    selection_conn.close()
    atomic_conn.close()

    master_manifest_path = args.output_dir / '2026_ytd_doublers_master_manifest.csv'
    manifest_path = args.output_dir / '2026_ytd_doublers_top20_manifest.csv'
    fieldnames = list(master_manifest[0].keys()) if master_manifest else []
    write_csv(master_manifest_path, master_manifest, fieldnames)
    write_csv(manifest_path, manifest, fieldnames)

    readme_lines = [
        '# 2026 YTD 翻倍股 Top20 持久化分析清单',
        '',
        f'- 数据源：`{args.study_csv}`',
        f'- 全量清单：`{master_manifest_path}`',
        f'- Top20 清单：`{manifest_path}`',
        '',
        '| Rank | 股票 | 区间涨幅 | 当前阶段 | 启动日 | 状态 | 报告 |',
        '| --- | --- | ---: | --- | --- | --- | --- |',
    ]
    for item in manifest:
        report_label = f"[{Path(item['report_path']).name}]({Path(item['report_path']).name})" if item['report_path'] else '--'
        readme_lines.append(
            f"| {item['rank']} | {item['display_name']} `{item['symbol']}` | {float(item['max_gain_pct']) * 100:.2f}% | {item['phase_label']} | {item.get('launch_date') or '--'} | {item['analysis_status']} | {report_label} |"
        )
    (args.docs_dir / 'README.md').write_text('\n'.join(readme_lines) + '\n', encoding='utf-8')

    print(master_manifest_path)
    print(manifest_path)
    print(args.docs_dir / 'README.md')


if __name__ == '__main__':
    main()
