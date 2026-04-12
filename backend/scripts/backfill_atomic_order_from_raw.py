#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.l2_package_layout import is_symbol_dir, normalize_month_day_root

REPO_ROOT = Path(ROOT_DIR)
DEFAULT_ATOMIC_DB = REPO_ROOT / 'data' / 'atomic_facts' / 'market_atomic.db'
ORDER_EVENT_TYPE_MAP = {
    '0': 'add',
    '1': 'cancel',
    'U': 'cancel',
    'A': 'add',
    'D': 'cancel',
}
ORDER_SIDE_MAP = {
    'B': 'buy',
    'S': 'sell',
}
TRADE_USECOLS = ['时间', '成交价格', '成交数量', 'BS标志', '叫卖序号', '叫买序号']
ORDER_USECOLS = ['时间', '交易所委托号', '委托类型', '委托代码', '委托价格', '委托数量']
QUOTE_USECOLS = (
    ['时间', '叫买总量', '叫卖总量', '成交价', '最新价', '现价', '收盘价', '昨收', '昨收价', '前收盘', '前收盘价']
    + [f'申买价{i}' for i in range(1, 11)]
    + [f'申卖价{i}' for i in range(1, 11)]
    + [f'申买量{i}' for i in range(1, 11)]
    + [f'申卖量{i}' for i in range(1, 11)]
)


@dataclass
class L2SymbolBundle:
    symbol: str
    trade_date: str
    symbol_dir: Path
    trade_raw: pd.DataFrame
    order_raw: pd.DataFrame
    quote_raw: pd.DataFrame
    ticks: pd.DataFrame
    order_events: pd.DataFrame
    diagnostics: Dict[str, object]


def normalize_symbol_dir_name(name: str) -> str:
    raw = (name or '').strip().lower()
    if len(raw) == 9 and raw[6] == '.':
        market = raw[7:]
        code = raw[:6]
        if market in {'sz', 'sh', 'bj'}:
            return f'{market}{code}'
    return raw


def _format_trade_time(raw_series: pd.Series) -> pd.Series:
    text = raw_series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(9)
    hhmmss = text.str[:-3].str.zfill(6)
    return hhmmss.str[0:2] + ':' + hhmmss.str[2:4] + ':' + hhmmss.str[4:6]


def _trading_mask_from_time_text(time_text: pd.Series) -> pd.Series:
    return ((time_text >= '09:30:00') & (time_text <= '11:30:00')) | (
        (time_text >= '13:00:00') & (time_text <= '15:00:00')
    )


def _build_datetime(trade_date: str, time_text: pd.Series) -> pd.Series:
    return pd.to_datetime(f'{trade_date} ' + time_text, format='%Y-%m-%d %H:%M:%S', errors='coerce')


def _read_csv(path: Path, usecols: Optional[Sequence[str]] = None) -> pd.DataFrame:
    csv_usecols = None
    if usecols:
        wanted = {str(x).strip() for x in usecols}
        csv_usecols = lambda c: str(c).strip() in wanted
    df = pd.read_csv(path, encoding='gb18030', low_memory=False, usecols=csv_usecols, engine='c', memory_map=True)
    bad_cols = [c for c in df.columns if str(c).strip() == '' or str(c).startswith('Unnamed')]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _build_standardized_order_events(order: pd.DataFrame, trade_date: str) -> Tuple[pd.DataFrame, Dict[str, object]]:
    required_order = ['时间', '交易所委托号', '委托类型', '委托代码', '委托价格', '委托数量']
    missing_order = [c for c in required_order if c not in order.columns]
    if missing_order:
        raise ValueError(f'逐笔委托缺列: {", ".join(missing_order)}')

    time_text = _format_trade_time(order['时间'])
    trading_mask = _trading_mask_from_time_text(time_text)
    order = order.loc[trading_mask].reset_index(drop=True)
    time_text = time_text.loc[trading_mask].reset_index(drop=True)

    events = pd.DataFrame()
    events['time'] = time_text
    events['datetime'] = _build_datetime(trade_date, events['time'])
    events['order_id'] = pd.to_numeric(order['交易所委托号'], errors='coerce').fillna(0).astype('int64')
    events['event_code'] = order['委托类型'].astype(str).str.strip().str.upper()
    events['side'] = order['委托代码'].astype(str).str.strip().str.upper().map(ORDER_SIDE_MAP)
    events['price'] = pd.to_numeric(order['委托价格'], errors='coerce') / 10000
    events['volume'] = pd.to_numeric(order['委托数量'], errors='coerce')
    events['event_type'] = events['event_code'].map(ORDER_EVENT_TYPE_MAP)

    events = events.dropna(subset=['datetime', 'side', 'event_type', 'volume'])
    events = events[(events['volume'] > 0) & (events['order_id'] > 0)]
    if not events.empty:
        if events['datetime'].is_monotonic_increasing:
            events = events.reset_index(drop=True)
        else:
            events = events.sort_values('datetime').reset_index(drop=True)

    positive_price_rows = events[events['price'] > 0].copy()
    known_price_by_order_id = (
        positive_price_rows.groupby('order_id', sort=False)['price'].last().to_dict()
        if not positive_price_rows.empty
        else {}
    )
    events['fallback_price'] = events['order_id'].map(known_price_by_order_id)
    events['effective_price'] = events['price'].where(events['price'] > 0, events['fallback_price'])
    events['amount'] = events['effective_price'] * events['volume']
    events = events.dropna(subset=['amount'])
    events = events[events['amount'] > 0].reset_index(drop=True)

    diagnostics = {
        'order_event_rows': int(len(events)),
        'order_add_rows': int((events['event_type'] == 'add').sum()),
        'order_cancel_rows': int((events['event_type'] == 'cancel').sum()),
        'order_cancel_zero_price_rows': int(((events['event_type'] == 'cancel') & (events['price'] <= 0)).sum()),
        'order_cancel_repriced_rows': int(
            ((events['event_type'] == 'cancel') & (events['price'] <= 0) & events['fallback_price'].notna()).sum()
        ),
    }
    return events, diagnostics


def build_standardized_ticks_from_frames(
    trade: pd.DataFrame,
    order: pd.DataFrame,
    trade_date: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, object]]:
    required_trade = ['时间', '成交价格', '成交数量', 'BS标志', '叫卖序号', '叫买序号']
    missing_trade = [c for c in required_trade if c not in trade.columns]
    if missing_trade:
        raise ValueError(f'逐笔成交缺列: {", ".join(missing_trade)}')

    order_events, order_diagnostics = _build_standardized_order_events(order, trade_date)

    time_text = _format_trade_time(trade['时间'])
    trading_mask = _trading_mask_from_time_text(time_text)
    trade = trade.loc[trading_mask].reset_index(drop=True)
    time_text = time_text.loc[trading_mask].reset_index(drop=True)

    ticks = pd.DataFrame()
    ticks['time'] = time_text
    ticks['datetime'] = _build_datetime(trade_date, ticks['time'])
    ticks['price'] = pd.to_numeric(trade['成交价格'], errors='coerce') / 10000
    ticks['volume'] = pd.to_numeric(trade['成交数量'], errors='coerce')
    ticks['side'] = trade['BS标志'].astype(str).str.strip().str.upper().map({'B': 'buy', 'S': 'sell'}).fillna('neutral')
    ticks['buy_order_id'] = pd.to_numeric(trade['叫买序号'], errors='coerce').fillna(0).astype('int64')
    ticks['sell_order_id'] = pd.to_numeric(trade['叫卖序号'], errors='coerce').fillna(0).astype('int64')
    ticks['amount'] = ticks['price'] * ticks['volume']

    ticks = ticks.dropna(subset=['datetime', 'price', 'volume', 'amount'])
    ticks = ticks[(ticks['price'] > 0) & (ticks['volume'] > 0) & (ticks['amount'] > 0)]
    if not ticks.empty:
        if ticks['datetime'].is_monotonic_increasing:
            ticks = ticks.reset_index(drop=True)
        else:
            ticks = ticks.sort_values('datetime').reset_index(drop=True)

    order_ids = pd.Index(pd.to_numeric(order['交易所委托号'], errors='coerce').dropna().astype('int64').unique())
    buy_refs = pd.Index(ticks.loc[ticks['buy_order_id'] > 0, 'buy_order_id'].astype('int64').unique())
    sell_refs = pd.Index(ticks.loc[ticks['sell_order_id'] > 0, 'sell_order_id'].astype('int64').unique())
    overlap_buy_count = int(buy_refs.intersection(order_ids).size)
    overlap_sell_count = int(sell_refs.intersection(order_ids).size)
    missing_buy_count = int(buy_refs.size - overlap_buy_count)
    missing_sell_count = int(sell_refs.size - overlap_sell_count)
    if (buy_refs.size > 0 and overlap_buy_count <= 0) and (sell_refs.size > 0 and overlap_sell_count <= 0):
        raise ValueError(
            f'OrderID 无法在逐笔委托中对齐: buy_missing={missing_buy_count}, sell_missing={missing_sell_count}'
        )

    diagnostics = {
        'trade_rows': int(len(trade)),
        'ticks_rows': int(len(ticks)),
        'order_rows': int(len(order)),
        'trade_date': trade_date,
        'sample_time_range': [
            ticks['time'].min() if not ticks.empty else None,
            ticks['time'].max() if not ticks.empty else None,
        ],
        'order_alignment_buy_overlap': overlap_buy_count,
        'order_alignment_sell_overlap': overlap_sell_count,
        'order_alignment_buy_missing': missing_buy_count,
        'order_alignment_sell_missing': missing_sell_count,
    }
    diagnostics.update(order_diagnostics)
    return ticks, order_events, diagnostics


def load_l2_symbol_bundle(symbol_dir: Path, trade_date: str) -> L2SymbolBundle:
    trade = _read_csv(symbol_dir / '逐笔成交.csv', usecols=TRADE_USECOLS)
    order = _read_csv(symbol_dir / '逐笔委托.csv', usecols=ORDER_USECOLS)
    quote = _read_csv(symbol_dir / '行情.csv', usecols=QUOTE_USECOLS)
    ticks, order_events, diagnostics = build_standardized_ticks_from_frames(trade, order, trade_date)
    return L2SymbolBundle(
        symbol=normalize_symbol_dir_name(symbol_dir.name),
        trade_date=trade_date,
        symbol_dir=symbol_dir,
        trade_raw=trade,
        order_raw=order,
        quote_raw=quote,
        ticks=ticks,
        order_events=order_events,
        diagnostics=diagnostics,
    )


def build_standardized_ticks(symbol_dir: Path, trade_date: str) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, object]]:
    bundle = load_l2_symbol_bundle(symbol_dir, trade_date)
    return bundle.ticks, bundle.order_events, bundle.diagnostics


def _build_quality_info(diagnostics: Dict[str, object]) -> Optional[str]:
    buy_overlap = int(diagnostics.get('order_alignment_buy_overlap', 0) or 0)
    sell_overlap = int(diagnostics.get('order_alignment_sell_overlap', 0) or 0)
    buy_missing = int(diagnostics.get('order_alignment_buy_missing', 0) or 0)
    sell_missing = int(diagnostics.get('order_alignment_sell_missing', 0) or 0)

    messages: List[str] = []
    if buy_missing > 0 and buy_overlap <= 0 and sell_overlap > 0:
        messages.append('L2 买边单边回退，数值可能偏小')
    if sell_missing > 0 and sell_overlap <= 0 and buy_overlap > 0:
        messages.append('L2 卖边单边回退，数值可能偏小')
    if not messages and (buy_missing > 0 or sell_missing > 0):
        messages.append('OrderID 部分缺失，L2 数值可能偏小')
    if not messages:
        return None
    return '；'.join(messages)


def list_symbol_dirs(day_root: Path, symbols: Optional[Sequence[str]] = None) -> List[Path]:
    targets = {s.lower() for s in symbols} if symbols else None
    result: List[Path] = []
    for child in sorted(day_root.iterdir()):
        if not child.is_dir():
            continue
        name = normalize_symbol_dir_name(child.name)
        if not name.startswith(('sz', 'sh', 'bj')):
            continue
        if targets and name not in targets:
            continue
        result.append(child)
    return result


def _resolve_day_root(input_path: Path) -> Tuple[Path, str, List[Path]]:
    if is_symbol_dir(input_path):
        return input_path.parent, input_path.parent.name, [input_path]
    if input_path.is_dir() and (input_path / '逐笔委托.csv').is_file():
        return input_path.parent, input_path.parent.name, [input_path]
    day_root, trade_date = normalize_month_day_root(input_path)
    return day_root, trade_date, []


def _canonical_trade_date(raw: str) -> str:
    text = (raw or '').strip()
    if len(text) == 8 and text.isdigit():
        return f'{text[:4]}-{text[4:6]}-{text[6:]}'
    return text


def _build_order_rows(
    symbol_dir: Path,
    trade_date: str,
    prepared: Optional[L2SymbolBundle] = None,
) -> Tuple[str, List[Tuple], Optional[Tuple], Dict[str, object]]:
    symbol = normalize_symbol_dir_name(symbol_dir.name)
    if prepared is None:
        ticks, order_events, diagnostics = build_standardized_ticks(symbol_dir, trade_date)
    else:
        ticks, order_events, diagnostics = prepared.ticks, prepared.order_events, prepared.diagnostics
    quality_info = _build_quality_info(diagnostics)
    if order_events.empty and quality_info:
        quality_info = f'{quality_info}；无有效逐笔委托事件'
    elif order_events.empty:
        quality_info = '无有效逐笔委托事件'

    tick_side = pd.DataFrame(columns=['bucket', 'cvd_buy_amount', 'cvd_sell_amount'])
    if not ticks.empty:
        tick_frame = ticks.copy()
        tick_frame['bucket'] = tick_frame['datetime'].dt.floor('5min')
        tick_frame['cvd_buy_amount'] = tick_frame['amount'].where(tick_frame['side'] == 'buy', 0.0)
        tick_frame['cvd_sell_amount'] = tick_frame['amount'].where(tick_frame['side'] == 'sell', 0.0)
        tick_side = (
            tick_frame.groupby('bucket', sort=False)
            [['cvd_buy_amount', 'cvd_sell_amount']]
            .sum()
            .reset_index()
        )

    event_side = pd.DataFrame(
        columns=[
            'bucket',
            'add_buy_amount', 'add_sell_amount', 'cancel_buy_amount', 'cancel_sell_amount',
            'add_buy_count', 'add_sell_count', 'cancel_buy_count', 'cancel_sell_count',
            'add_buy_volume', 'add_sell_volume', 'cancel_buy_volume', 'cancel_sell_volume',
        ]
    )
    if not order_events.empty:
        event_frame = order_events.copy()
        event_frame['bucket'] = event_frame['datetime'].dt.floor('5min')
        event_frame['is_add_buy'] = ((event_frame['event_type'] == 'add') & (event_frame['side'] == 'buy')).astype('int64')
        event_frame['is_add_sell'] = ((event_frame['event_type'] == 'add') & (event_frame['side'] == 'sell')).astype('int64')
        event_frame['is_cancel_buy'] = ((event_frame['event_type'] == 'cancel') & (event_frame['side'] == 'buy')).astype('int64')
        event_frame['is_cancel_sell'] = ((event_frame['event_type'] == 'cancel') & (event_frame['side'] == 'sell')).astype('int64')
        event_frame['add_buy_amount'] = event_frame['amount'] * event_frame['is_add_buy']
        event_frame['add_sell_amount'] = event_frame['amount'] * event_frame['is_add_sell']
        event_frame['cancel_buy_amount'] = event_frame['amount'] * event_frame['is_cancel_buy']
        event_frame['cancel_sell_amount'] = event_frame['amount'] * event_frame['is_cancel_sell']
        event_frame['add_buy_volume'] = event_frame['volume'] * event_frame['is_add_buy']
        event_frame['add_sell_volume'] = event_frame['volume'] * event_frame['is_add_sell']
        event_frame['cancel_buy_volume'] = event_frame['volume'] * event_frame['is_cancel_buy']
        event_frame['cancel_sell_volume'] = event_frame['volume'] * event_frame['is_cancel_sell']
        event_side = (
            event_frame.groupby('bucket', sort=False)
            [[
                'add_buy_amount', 'add_sell_amount', 'cancel_buy_amount', 'cancel_sell_amount',
                'is_add_buy', 'is_add_sell', 'is_cancel_buy', 'is_cancel_sell',
                'add_buy_volume', 'add_sell_volume', 'cancel_buy_volume', 'cancel_sell_volume',
            ]]
            .sum()
            .reset_index()
            .rename(columns={
                'is_add_buy': 'add_buy_count',
                'is_add_sell': 'add_sell_count',
                'is_cancel_buy': 'cancel_buy_count',
                'is_cancel_sell': 'cancel_sell_count',
            })
        )

    bucket_df = pd.concat(
        [
            tick_side[['bucket']] if not tick_side.empty else pd.DataFrame(columns=['bucket']),
            event_side[['bucket']] if not event_side.empty else pd.DataFrame(columns=['bucket']),
        ],
        ignore_index=True,
    ).drop_duplicates().sort_values('bucket')

    if bucket_df.empty:
        diagnostics['bars_5m'] = 0
        return symbol, [], None, diagnostics

    merged = bucket_df.merge(tick_side, how='left', on='bucket').merge(event_side, how='left', on='bucket')
    fill_zero_cols = [c for c in merged.columns if c != 'bucket']
    merged[fill_zero_cols] = merged[fill_zero_cols].fillna(0)
    merged['cvd_delta_amount'] = merged['cvd_buy_amount'] - merged['cvd_sell_amount']
    merged['oib_delta_amount'] = (
        merged['add_buy_amount']
        - merged['cancel_buy_amount']
        - merged['add_sell_amount']
        + merged['cancel_sell_amount']
    )
    merged['buy_add_cancel_net_amount'] = merged['add_buy_amount'] - merged['cancel_buy_amount']
    merged['sell_add_cancel_net_amount'] = merged['add_sell_amount'] - merged['cancel_sell_amount']

    rows_5m = [
        (
            symbol,
            _canonical_trade_date(trade_date),
            row['bucket'].strftime('%Y-%m-%d %H:%M:%S'),
            float(row['add_buy_amount']),
            float(row['add_sell_amount']),
            float(row['cancel_buy_amount']),
            float(row['cancel_sell_amount']),
            float(row['cvd_delta_amount']),
            float(row['oib_delta_amount']),
            int(row['add_buy_count']),
            int(row['add_sell_count']),
            int(row['cancel_buy_count']),
            int(row['cancel_sell_count']),
            float(row['add_buy_volume']),
            float(row['add_sell_volume']),
            float(row['cancel_buy_volume']),
            float(row['cancel_sell_volume']),
            int(row['add_buy_count'] + row['add_sell_count'] + row['cancel_buy_count'] + row['cancel_sell_count']),
            float(row['buy_add_cancel_net_amount']),
            float(row['sell_add_cancel_net_amount']),
            'trade_order',
            quality_info,
        )
        for _, row in merged.iterrows()
    ]

    daily_key = (symbol, _canonical_trade_date(trade_date))
    positive_oib_values = [float(r[8]) for r in rows_5m if float(r[8]) > 0]
    positive_total = float(sum(positive_oib_values))
    positive_sorted = sorted(positive_oib_values, reverse=True)
    moderate_threshold = positive_sorted[len(positive_sorted) // 2] if positive_sorted else None
    moderate_positive_count = (
        int(sum(1 for value in positive_oib_values if moderate_threshold is not None and value >= moderate_threshold))
        if positive_oib_values
        else 0
    )
    streak = 0
    streak_max = 0
    for row in rows_5m:
        if float(row[8]) > 0:
            streak += 1
            streak_max = max(streak_max, streak)
        else:
            streak = 0
    daily_row = (
        symbol,
        daily_key[1],
        float(sum(r[3] for r in rows_5m)),
        float(sum(r[4] for r in rows_5m)),
        float(sum(r[5] for r in rows_5m)),
        float(sum(r[6] for r in rows_5m)),
        float(sum(r[7] for r in rows_5m)),
        float(sum(r[8] for r in rows_5m)),
        int(sum(r[9] for r in rows_5m)),
        int(sum(r[10] for r in rows_5m)),
        int(sum(r[11] for r in rows_5m)),
        int(sum(r[12] for r in rows_5m)),
        float(sum(r[8] for r in rows_5m if r[2][11:19] < '13:00:00')),
        float(sum(r[8] for r in rows_5m if r[2][11:19] >= '13:00:00')),
        float(sum(r[8] for r in rows_5m if r[2][11:19] < '10:30:00')),
        float(sum(r[8] for r in rows_5m if r[2][11:19] >= '14:30:00')),
        float(sum(r[7] for r in rows_5m if r[2][11:19] < '10:30:00')),
        float(sum(r[7] for r in rows_5m if r[2][11:19] >= '14:30:00')),
        int(sum(1 for r in rows_5m if r[8] > 0)),
        int(sum(1 for r in rows_5m if r[8] < 0)),
        int(sum(1 for r in rows_5m if r[7] > 0)),
        int(sum(1 for r in rows_5m if r[7] < 0)),
        int(sum(r[17] for r in rows_5m)),
        float(sum(positive_sorted[:3]) / positive_total) if positive_total > 0 else None,
        moderate_positive_count,
        float(moderate_positive_count / len(positive_oib_values)) if positive_oib_values else None,
        int(streak_max),
        None,
        None,
        quality_info,
    )
    diagnostics['bars_5m'] = len(rows_5m)
    return symbol, rows_5m, daily_row, diagnostics


def _load_trade_total_amount(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Optional[float]:
    row = conn.execute(
        'SELECT total_amount FROM atomic_trade_daily WHERE symbol = ? AND trade_date = ?',
        (symbol, trade_date),
    ).fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _apply_support_ratios(daily_row: Tuple, total_amount: Optional[float]) -> Tuple:
    if not total_amount or total_amount <= 0:
        return daily_row
    values = list(daily_row)
    add_buy_amount, cancel_buy_amount = float(values[2]), float(values[4])
    add_sell_amount, cancel_sell_amount = float(values[3]), float(values[5])
    values[27] = float((add_buy_amount - cancel_buy_amount) / total_amount)
    values[28] = float((add_sell_amount - cancel_sell_amount) / total_amount)
    return tuple(values)


def _replace_rows(conn: sqlite3.Connection, rows_5m: Sequence[Tuple], daily_row: Tuple) -> Dict[str, int]:
    if rows_5m:
        symbol = rows_5m[0][0]
        trade_date = rows_5m[0][1]
        conn.execute('DELETE FROM atomic_order_5m WHERE symbol = ? AND trade_date = ?', (symbol, trade_date))
        conn.executemany(
            '''
            INSERT INTO atomic_order_5m (
                symbol, trade_date, bucket_start,
                add_buy_amount, add_sell_amount, cancel_buy_amount, cancel_sell_amount,
                cvd_delta_amount, oib_delta_amount,
                add_buy_count, add_sell_count, cancel_buy_count, cancel_sell_count,
                add_buy_volume, add_sell_volume, cancel_buy_volume, cancel_sell_volume,
                order_event_count,
                buy_add_cancel_net_amount, sell_add_cancel_net_amount,
                source_type, quality_info, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
            )
            ''',
            rows_5m,
        )
    conn.execute('DELETE FROM atomic_order_daily WHERE symbol = ? AND trade_date = ?', (daily_row[0], daily_row[1]))
    conn.execute(
        '''
        INSERT INTO atomic_order_daily (
            symbol, trade_date,
            add_buy_amount, add_sell_amount, cancel_buy_amount, cancel_sell_amount,
            cvd_delta_amount, oib_delta_amount,
            add_buy_count, add_sell_count, cancel_buy_count, cancel_sell_count,
            am_oib_delta_amount, pm_oib_delta_amount,
            open_60m_oib_delta_amount, last_30m_oib_delta_amount,
            open_60m_cvd_delta_amount, last_30m_cvd_delta_amount,
            positive_oib_bar_count, negative_oib_bar_count,
            positive_cvd_bar_count, negative_cvd_bar_count,
            order_event_count, oib_top3_concentration_ratio,
            moderate_positive_oib_bar_count, moderate_positive_oib_bar_ratio, positive_oib_streak_max,
            buy_support_ratio, sell_pressure_ratio,
            quality_info, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
        )
        ''',
        daily_row,
    )
    return {'rows_5m': len(rows_5m), 'rows_daily': 1}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Backfill atomic order tables from raw order/trade CSVs.')
    parser.add_argument('input_path', help='Day root or symbol dir')
    parser.add_argument('--atomic-db', type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument('--symbols', default='', help='Comma-separated symbols like sh603629,sz000833')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.atomic_db.exists():
        raise SystemExit(f'Atomic DB not found: {args.atomic_db}')

    day_root, trade_date_raw, preselected = _resolve_day_root(Path(args.input_path))
    trade_date = _canonical_trade_date(trade_date_raw)
    symbols = [s.strip().lower() for s in args.symbols.split(',') if s.strip()]
    symbol_dirs = preselected or list_symbol_dirs(day_root, symbols=symbols or None)
    if args.limit > 0:
        symbol_dirs = symbol_dirs[:args.limit]

    results = []
    failures = []
    with sqlite3.connect(args.atomic_db) as conn:
        for symbol_dir in symbol_dirs:
            try:
                symbol, rows_5m, daily_row, diagnostics = _build_order_rows(symbol_dir, trade_date)
                if not rows_5m or daily_row is None:
                    failures.append({'symbol': symbol, 'error': '无有效 atomic_order 结果', 'diagnostics': diagnostics})
                    continue
                total_amount = _load_trade_total_amount(conn, symbol, trade_date)
                daily_row = _apply_support_ratios(daily_row, total_amount)
                write_stats = {'rows_5m': len(rows_5m), 'rows_daily': 1}
                if not args.dry_run:
                    write_stats = _replace_rows(conn, rows_5m, daily_row)
                results.append(
                    {
                        'symbol': symbol,
                        'trade_date': trade_date,
                        'bars_5m': len(rows_5m),
                        'order_event_rows': int(diagnostics.get('order_event_rows', 0) or 0),
                        'trade_rows': int(diagnostics.get('ticks_rows', 0) or 0),
                        'has_trade_total_amount': total_amount is not None,
                        **write_stats,
                    }
                )
            except Exception as exc:
                failures.append({'symbol': normalize_symbol_dir_name(symbol_dir.name), 'error': str(exc)})
        if not args.dry_run:
            conn.commit()

    print(
        {
            'input_path': str(args.input_path),
            'resolved_day_root': str(day_root),
            'trade_date': trade_date,
            'processed_count': len(results),
            'failure_count': len(failures),
            'results': results[:20],
            'failures': failures[:20],
            'dry_run': bool(args.dry_run),
            'atomic_db': str(args.atomic_db),
        }
    )


if __name__ == '__main__':
    main()
