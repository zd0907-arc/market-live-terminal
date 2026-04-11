#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.l2_package_layout import is_symbol_dir, normalize_month_day_root

ORDER_EVENT_TYPE_MAP = {
    "0": "add",
    "1": "cancel",
    "U": "cancel",
    "A": "add",
    "D": "cancel",
}

ORDER_SIDE_MAP = {
    "B": "buy",
    "S": "sell",
}


def normalize_symbol_dir_name(name: str) -> str:
    raw = (name or "").strip().lower()
    if len(raw) == 9 and raw[6] == ".":
        market = raw[7:]
        code = raw[:6]
        if market in {"sz", "sh", "bj"}:
            return f"{market}{code}"
    return raw


def list_symbol_dirs(day_root: Path, symbols: Optional[Sequence[str]] = None) -> List[Path]:
    targets = {s.lower() for s in symbols} if symbols else None
    result: List[Path] = []
    for child in sorted(day_root.iterdir()):
        if not child.is_dir():
            continue
        if not re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", child.name, re.I):
            continue
        normalized = normalize_symbol_dir_name(child.name)
        if targets and normalized not in targets:
            continue
        result.append(child)
    return result

REPO_ROOT = Path(ROOT_DIR)
DEFAULT_ATOMIC_DB = REPO_ROOT / 'data' / 'atomic_facts' / 'market_atomic.db'
DEFAULT_SCHEMA = REPO_ROOT / 'backend' / 'scripts' / 'sql' / 'open_auction_summary_schema_draft.sql'


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding='gb18030', low_memory=False)
    bad_cols = [c for c in df.columns if str(c).strip() == '' or str(c).startswith('Unnamed')]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _format_time(raw_series: pd.Series) -> pd.Series:
    text = raw_series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(9)
    hhmmss = text.str[:-3].str.zfill(6)
    return hhmmss.str[0:2] + ':' + hhmmss.str[2:4] + ':' + hhmmss.str[4:6]


def _resolve_day_root(input_path: Path) -> Tuple[Path, str, List[Path]]:
    if is_symbol_dir(input_path):
        return input_path.parent, input_path.parent.name, [input_path]
    if input_path.is_dir() and (input_path / '逐笔成交.csv').is_file():
        return input_path.parent, input_path.parent.name, [input_path]
    day_root, trade_date = normalize_month_day_root(input_path)
    return day_root, trade_date, []


def _between(times: pd.Series, start: str, end: str) -> pd.Series:
    return (times >= start) & (times < end)


def _exact_0925(times: pd.Series) -> pd.Series:
    return (times >= '09:25:00') & (times <= '09:25:01')


def _safe_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors='coerce')


def _trade_windows(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    times = df['time']
    return {
        '0915_0920': df[_between(times, '09:15:00', '09:20:00')],
        '0920_0925': df[_between(times, '09:20:00', '09:25:00')],
        '0925_match': df[_exact_0925(times)],
        'pre0930': df[_between(times, '09:15:00', '09:30:00')],
    }


def _quote_last_price(quote: pd.DataFrame) -> Optional[float]:
    candidates = ['成交价', '最新价', '现价', '收盘价']
    for col in candidates:
        if col in quote.columns:
            s = _safe_num(quote[col]).dropna()
            if not s.empty:
                return float(s.iloc[-1])
    return None


def _quote_prev_close(quote: pd.DataFrame) -> Optional[float]:
    candidates = ['昨收', '昨收价', '前收盘', '前收盘价']
    for col in candidates:
        if col in quote.columns:
            s = _safe_num(quote[col]).dropna()
            if not s.empty:
                return float(s.iloc[-1])
    return None


def _build_l1_summary(symbol_dir: Path, trade_date: str) -> Dict[str, object]:
    trade = _read_csv(symbol_dir / '逐笔成交.csv')
    quote = _read_csv(symbol_dir / '行情.csv')

    trade_df = pd.DataFrame({
        'time': _format_time(trade['时间']),
        'price': _safe_num(trade['成交价格']) / 10000,
        'volume': _safe_num(trade['成交数量']),
    })
    trade_df['amount'] = trade_df['price'] * trade_df['volume']
    trade_df = trade_df.dropna(subset=['time', 'price', 'volume', 'amount'])
    trade_df = trade_df[(trade_df['price'] > 0) & (trade_df['volume'] > 0) & (trade_df['amount'] > 0)]

    quote_df = pd.DataFrame({'time': _format_time(quote['时间'])})
    quote_df = quote_df.dropna(subset=['time'])
    quote_pre = quote_df[_between(quote_df['time'], '09:15:00', '09:30:00')]
    trade_windows = _trade_windows(trade_df)

    auction_price = None
    quote_pre_full = quote.copy()
    quote_pre_full['time'] = _format_time(quote_pre_full['时间'])
    quote_pre_full = quote_pre_full[_between(quote_pre_full['time'], '09:15:00', '09:30:00')]
    if not quote_pre_full.empty:
        auction_price = _quote_last_price(quote_pre_full)
    prev_close = _quote_prev_close(quote_pre_full if not quote_pre_full.empty else quote)
    price_chg_pct = None
    if auction_price is not None and prev_close not in (None, 0):
        price_chg_pct = (auction_price / prev_close - 1.0) * 100.0

    match_df = trade_windows['0925_match']
    pre_df = trade_windows['pre0930']
    return {
        'symbol': normalize_symbol_dir_name(symbol_dir.name),
        'trade_date': f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}' if len(trade_date) == 8 else trade_date,
        'auction_price': auction_price,
        'auction_match_volume': float(match_df['volume'].sum()) if not match_df.empty else None,
        'auction_match_amount': float(match_df['amount'].sum()) if not match_df.empty else None,
        'auction_price_change_pct_vs_prev_close': price_chg_pct,
        'auction_trade_count_total': int(len(pre_df)),
        'auction_trade_volume_total': float(pre_df['volume'].sum()) if not pre_df.empty else None,
        'auction_trade_amount_total': float(pre_df['amount'].sum()) if not pre_df.empty else None,
        'auction_trade_count_0915_0920': int(len(trade_windows['0915_0920'])),
        'auction_trade_count_0920_0925': int(len(trade_windows['0920_0925'])),
        'auction_trade_count_0925_match': int(len(match_df)),
        'auction_trade_amount_0915_0920': float(trade_windows['0915_0920']['amount'].sum()) if not trade_windows['0915_0920'].empty else None,
        'auction_trade_amount_0920_0925': float(trade_windows['0920_0925']['amount'].sum()) if not trade_windows['0920_0925'].empty else None,
        'auction_trade_amount_0925_match': float(match_df['amount'].sum()) if not match_df.empty else None,
        'auction_first_trade_time': str(pre_df['time'].min()) if not pre_df.empty else None,
        'auction_last_trade_time': str(pre_df['time'].max()) if not pre_df.empty else None,
        'auction_exact_0925_trade_count': int(len(match_df)),
        'quote_preopen_row_count': int(len(quote_pre)),
        'quote_has_0925_snapshot': int(((quote_pre['time'] >= '09:25:00') & (quote_pre['time'] <= '09:25:02')).any()) if not quote_pre.empty else 0,
        'quality_info': None,
        'source_type': 'l1_visible',
    }


def _build_l2_summary(symbol_dir: Path, trade_date: str) -> Dict[str, object]:
    trade = _read_csv(symbol_dir / '逐笔成交.csv')
    order = _read_csv(symbol_dir / '逐笔委托.csv')

    trade_df = pd.DataFrame({
        'time': _format_time(trade['时间']),
        'price': _safe_num(trade['成交价格']) / 10000,
        'volume': _safe_num(trade['成交数量']),
    })
    trade_df['amount'] = trade_df['price'] * trade_df['volume']
    trade_df = trade_df.dropna(subset=['time', 'price', 'volume', 'amount'])
    trade_df = trade_df[(trade_df['price'] > 0) & (trade_df['volume'] > 0) & (trade_df['amount'] > 0)]
    trade_windows = _trade_windows(trade_df)

    order_df = pd.DataFrame({
        'time': _format_time(order['时间']),
        'event_code': order['委托类型'].astype(str).str.strip().str.upper(),
        'side': order['委托代码'].astype(str).str.strip().str.upper().map(ORDER_SIDE_MAP),
        'price': _safe_num(order['委托价格']) / 10000,
        'volume': _safe_num(order['委托数量']),
    })
    order_df['event_type'] = order_df['event_code'].map(ORDER_EVENT_TYPE_MAP)
    order_df['amount'] = order_df['price'] * order_df['volume']
    order_df = order_df.dropna(subset=['time', 'side', 'event_type', 'volume'])
    order_df = order_df[(order_df['volume'] > 0)]
    # 撤单价格有时为 0，这里允许金额为空后单独 fallback 为 0，不强行丢事件
    order_df['amount'] = order_df['amount'].fillna(0.0)
    order_pre = order_df[_between(order_df['time'], '09:15:00', '09:30:00')]
    add_buy = order_pre[(order_pre['event_type'] == 'add') & (order_pre['side'] == 'buy')]
    add_sell = order_pre[(order_pre['event_type'] == 'add') & (order_pre['side'] == 'sell')]
    cancel_buy = order_pre[(order_pre['event_type'] == 'cancel') & (order_pre['side'] == 'buy')]
    cancel_sell = order_pre[(order_pre['event_type'] == 'cancel') & (order_pre['side'] == 'sell')]
    add_buy_0915 = add_buy[_between(add_buy['time'], '09:15:00', '09:20:00')]
    add_buy_0920 = add_buy[_between(add_buy['time'], '09:20:00', '09:25:00')]
    add_sell_0915 = add_sell[_between(add_sell['time'], '09:15:00', '09:20:00')]
    add_sell_0920 = add_sell[_between(add_sell['time'], '09:20:00', '09:25:00')]
    cancel_buy_0915 = cancel_buy[_between(cancel_buy['time'], '09:15:00', '09:20:00')]
    cancel_sell_0915 = cancel_sell[_between(cancel_sell['time'], '09:15:00', '09:20:00')]
    match_df = trade_windows['0925_match']

    return {
        'symbol': normalize_symbol_dir_name(symbol_dir.name),
        'trade_date': f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}' if len(trade_date) == 8 else trade_date,
        'auction_trade_count_total': int(len(trade_windows['pre0930'])),
        'auction_trade_volume_total': float(trade_windows['pre0930']['volume'].sum()) if not trade_windows['pre0930'].empty else None,
        'auction_trade_amount_total': float(trade_windows['pre0930']['amount'].sum()) if not trade_windows['pre0930'].empty else None,
        'auction_trade_count_0915_0920': int(len(trade_windows['0915_0920'])),
        'auction_trade_count_0920_0925': int(len(trade_windows['0920_0925'])),
        'auction_trade_count_0925_match': int(len(match_df)),
        'auction_trade_amount_0915_0920': float(trade_windows['0915_0920']['amount'].sum()) if not trade_windows['0915_0920'].empty else None,
        'auction_trade_amount_0920_0925': float(trade_windows['0920_0925']['amount'].sum()) if not trade_windows['0920_0925'].empty else None,
        'auction_trade_amount_0925_match': float(match_df['amount'].sum()) if not match_df.empty else None,
        'auction_order_add_buy_amount': float(add_buy['amount'].sum()) if not add_buy.empty else None,
        'auction_order_add_sell_amount': float(add_sell['amount'].sum()) if not add_sell.empty else None,
        'auction_order_cancel_buy_amount': float(cancel_buy['amount'].sum()) if not cancel_buy.empty else None,
        'auction_order_cancel_sell_amount': float(cancel_sell['amount'].sum()) if not cancel_sell.empty else None,
        'auction_order_add_buy_count': int(len(add_buy)),
        'auction_order_add_sell_count': int(len(add_sell)),
        'auction_order_cancel_buy_count': int(len(cancel_buy)),
        'auction_order_cancel_sell_count': int(len(cancel_sell)),
        'auction_order_add_buy_amount_0915_0920': float(add_buy_0915['amount'].sum()) if not add_buy_0915.empty else None,
        'auction_order_add_buy_amount_0920_0925': float(add_buy_0920['amount'].sum()) if not add_buy_0920.empty else None,
        'auction_order_add_sell_amount_0915_0920': float(add_sell_0915['amount'].sum()) if not add_sell_0915.empty else None,
        'auction_order_add_sell_amount_0920_0925': float(add_sell_0920['amount'].sum()) if not add_sell_0920.empty else None,
        'auction_order_cancel_buy_amount_0915_0920': float(cancel_buy_0915['amount'].sum()) if not cancel_buy_0915.empty else None,
        'auction_order_cancel_sell_amount_0915_0920': float(cancel_sell_0915['amount'].sum()) if not cancel_sell_0915.empty else None,
        'auction_has_exact_0925_trade': int(len(match_df) > 0),
        'auction_has_exact_0925_order': int(_exact_0925(order_pre['time']).any()) if not order_pre.empty else 0,
        'quality_info': None,
        'source_type': 'l2_postclose',
    }


def _build_manifest(l1_row: Dict[str, object], l2_row: Dict[str, object], auction_shape: str = 'trade+order+quote') -> Dict[str, object]:
    return {
        'symbol': l1_row['symbol'],
        'trade_date': l1_row['trade_date'],
        'has_l1_auction': 1,
        'has_l2_auction': 1,
        'l1_quality_info': l1_row.get('quality_info'),
        'l2_quality_info': l2_row.get('quality_info'),
        'auction_shape': auction_shape,
        'parser_version': 'auction_v1_draft',
        'generated_at': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
        'notes': 'draft summary build',
    }


def _upsert(conn: sqlite3.Connection, table: str, row: Dict[str, object]) -> None:
    cols = list(row.keys())
    placeholders = ','.join(['?'] * len(cols))
    sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, [row[c] for c in cols])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build open auction L1/L2 daily summaries from raw day packages.')
    parser.add_argument('input_path', help='Day root or symbol dir')
    parser.add_argument('--atomic-db', type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument('--schema', type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument('--symbols', default='', help='Comma-separated symbols like sh603629,sz000833')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    day_root, trade_date, preselected = _resolve_day_root(Path(args.input_path))
    symbols = [s.strip().lower() for s in args.symbols.split(',') if s.strip()]
    symbol_dirs = preselected or list_symbol_dirs(day_root, symbols=symbols or None)
    if args.limit > 0:
        symbol_dirs = symbol_dirs[:args.limit]

    args.atomic_db.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = args.schema.read_text(encoding='utf-8')

    processed = []
    failures = []
    with sqlite3.connect(args.atomic_db) as conn:
        conn.executescript(schema_sql)
        for symbol_dir in symbol_dirs:
            try:
                l1_row = _build_l1_summary(symbol_dir, trade_date)
                l2_row = _build_l2_summary(symbol_dir, trade_date)
                manifest = _build_manifest(l1_row, l2_row)
                if not args.dry_run:
                    _upsert(conn, 'atomic_open_auction_l1_daily', l1_row)
                    _upsert(conn, 'atomic_open_auction_l2_daily', l2_row)
                    _upsert(conn, 'atomic_open_auction_manifest', manifest)
                processed.append({'symbol': l1_row['symbol'], 'trade_date': l1_row['trade_date']})
            except Exception as exc:
                failures.append({'symbol': normalize_symbol_dir_name(symbol_dir.name), 'error': str(exc)})
        conn.commit()

    print({
        'input_path': str(args.input_path),
        'resolved_day_root': str(day_root),
        'trade_date': trade_date,
        'processed_count': len(processed),
        'failure_count': len(failures),
        'processed': processed[:10],
        'failures': failures[:10],
        'dry_run': bool(args.dry_run),
        'atomic_db': str(args.atomic_db),
    })


if __name__ == '__main__':
    main()
