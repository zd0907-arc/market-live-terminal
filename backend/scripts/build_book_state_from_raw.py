#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATOMIC_DB = REPO_ROOT / 'data' / 'atomic_facts' / 'market_atomic.db'
BOOK_STATE_SCHEMA = REPO_ROOT / 'backend' / 'scripts' / 'sql' / 'book_state_schema.sql'


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding='gb18030', low_memory=False, engine='c', memory_map=True)
    bad_cols = [c for c in df.columns if str(c).strip() == '' or str(c).startswith('Unnamed')]
    if bad_cols:
        df = df.drop(columns=bad_cols)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _format_time(raw_series: pd.Series) -> pd.Series:
    text = raw_series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(9)
    hhmmss = text.str[:-3].str.zfill(6)
    return hhmmss.str[0:2] + ':' + hhmmss.str[2:4] + ':' + hhmmss.str[4:6]


def _safe_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors='coerce')


def _normalize_symbol_dir_name(name: str) -> str:
    raw = (name or '').strip().lower()
    if len(raw) == 9 and raw[6] == '.':
        code = raw[:6]
        market = raw[7:]
        if market in {'sh', 'sz', 'bj'}:
            return f'{market}{code}'
    return raw


def _map_book_bucket(trade_date: str, time_text: str) -> Optional[pd.Timestamp]:
    if '09:30:00' <= time_text < '11:30:00':
        ts = pd.Timestamp(f'{trade_date} {time_text}')
        return ts.floor('5min')
    if '11:30:00' <= time_text < '11:31:00':
        return pd.Timestamp(f'{trade_date} 11:25:00')
    if '13:00:00' <= time_text < '15:00:00':
        ts = pd.Timestamp(f'{trade_date} {time_text}')
        return ts.floor('5min')
    if '15:00:00' <= time_text < '15:01:00':
        return pd.Timestamp(f'{trade_date} 14:55:00')
    return None


def _calc_amount(price: float, volume: float) -> float:
    if pd.isna(price) or pd.isna(volume) or price <= 0 or volume <= 0:
        return 0.0
    return float(price * volume)


def _resolve_total_volume(row: pd.Series, total_col: str, level_cols: Sequence[str]) -> float:
    total_val = row.get(total_col)
    if pd.notna(total_val) and float(total_val) > 0:
        return float(total_val)
    return float(sum(float(row.get(col) or 0.0) for col in level_cols))


def _label_book_state(imbalance_ratio: Optional[float], total_top5_amount: float) -> str:
    if imbalance_ratio is None:
        return 'unknown'
    if total_top5_amount < 500000:
        return 'thin'
    if imbalance_ratio >= 0.2:
        return 'bid_dominant'
    if imbalance_ratio <= -0.2:
        return 'ask_dominant'
    return 'balanced'


def _prepare_quote_snapshot_df_from_quote(quote: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    time_col = '时间'
    if time_col not in quote.columns:
        raise ValueError('行情.csv 缺少 时间 列')

    bid_price_cols = [f'申买价{i}' for i in range(1, 11)]
    ask_price_cols = [f'申卖价{i}' for i in range(1, 11)]
    bid_vol_cols = [f'申买量{i}' for i in range(1, 11)]
    ask_vol_cols = [f'申卖量{i}' for i in range(1, 11)]
    required = bid_price_cols + ask_price_cols + bid_vol_cols + ask_vol_cols
    missing = [c for c in required if c not in quote.columns]
    if missing:
        raise ValueError(f'行情.csv 缺少盘口列: {missing[:6]}')

    df = pd.DataFrame({'time': _format_time(quote[time_col])})
    for col in required:
        df[col] = _safe_num(quote[col])
    df['叫买总量'] = _safe_num(quote['叫买总量']) if '叫买总量' in quote.columns else pd.NA
    df['叫卖总量'] = _safe_num(quote['叫卖总量']) if '叫卖总量' in quote.columns else pd.NA
    df['trade_date'] = trade_date
    df['bucket'] = df['time'].map(lambda x: _map_book_bucket(trade_date, x))
    df = df[df['bucket'].notna()].copy()
    if df.empty:
        return df

    for i in range(1, 11):
        df[f'bid_price_{i}'] = _safe_num(df[f'申买价{i}']) / 10000
        df[f'ask_price_{i}'] = _safe_num(df[f'申卖价{i}']) / 10000
        df[f'bid_vol_{i}'] = _safe_num(df[f'申买量{i}']).fillna(0.0)
        df[f'ask_vol_{i}'] = _safe_num(df[f'申卖量{i}']).fillna(0.0)
        df[f'bid_amt_{i}'] = (
            df[f'bid_price_{i}'].where(df[f'bid_price_{i}'] > 0, 0.0)
            * df[f'bid_vol_{i}'].where(df[f'bid_vol_{i}'] > 0, 0.0)
        ).astype(float)
        df[f'ask_amt_{i}'] = (
            df[f'ask_price_{i}'].where(df[f'ask_price_{i}'] > 0, 0.0)
            * df[f'ask_vol_{i}'].where(df[f'ask_vol_{i}'] > 0, 0.0)
        ).astype(float)

    df['top1_bid_volume'] = df['bid_vol_1']
    df['top1_ask_volume'] = df['ask_vol_1']
    df['top1_bid_amount'] = df['bid_amt_1']
    df['top1_ask_amount'] = df['ask_amt_1']
    df['top5_bid_volume'] = df[[f'bid_vol_{i}' for i in range(1, 6)]].sum(axis=1)
    df['top5_ask_volume'] = df[[f'ask_vol_{i}' for i in range(1, 6)]].sum(axis=1)
    df['top5_bid_amount'] = df[[f'bid_amt_{i}' for i in range(1, 6)]].sum(axis=1)
    df['top5_ask_amount'] = df[[f'ask_amt_{i}' for i in range(1, 6)]].sum(axis=1)
    df['top10_bid_volume'] = df[[f'bid_vol_{i}' for i in range(1, 11)]].sum(axis=1)
    df['top10_ask_volume'] = df[[f'ask_vol_{i}' for i in range(1, 11)]].sum(axis=1)
    df['top10_bid_amount'] = df[[f'bid_amt_{i}' for i in range(1, 11)]].sum(axis=1)
    df['top10_ask_amount'] = df[[f'ask_amt_{i}' for i in range(1, 11)]].sum(axis=1)
    df['end_bid_resting_volume'] = _safe_num(df['叫买总量']) if '叫买总量' in df.columns else pd.Series(pd.NA, index=df.index)
    df['end_ask_resting_volume'] = _safe_num(df['叫卖总量']) if '叫卖总量' in df.columns else pd.Series(pd.NA, index=df.index)
    df['end_bid_resting_volume'] = df['end_bid_resting_volume'].where(df['end_bid_resting_volume'] > 0, df['top10_bid_volume']).astype(float)
    df['end_ask_resting_volume'] = df['end_ask_resting_volume'].where(df['end_ask_resting_volume'] > 0, df['top10_ask_volume']).astype(float)
    df['end_bid_resting_amount'] = df['top10_bid_amount']
    df['end_ask_resting_amount'] = df['top10_ask_amount']
    denom = df['end_bid_resting_amount'] + df['end_ask_resting_amount']
    df['book_imbalance_ratio'] = ((df['end_bid_resting_amount'] - df['end_ask_resting_amount']) / denom.where(denom > 0)).astype(float)
    top1_sum = df['top1_bid_amount'] + df['top1_ask_amount']
    df['book_depth_ratio'] = ((df['top5_bid_amount'] + df['top5_ask_amount']) / top1_sum.where(top1_sum > 0)).astype(float)
    df['book_state_label'] = [
        _label_book_state(
            None if pd.isna(imb) else float(imb),
            float(tb + ta),
        )
        for imb, tb, ta in zip(df['book_imbalance_ratio'], df['top5_bid_amount'], df['top5_ask_amount'])
    ]
    return df


def _prepare_quote_snapshot_df(symbol_dir: Path, trade_date: str) -> pd.DataFrame:
    quote = _read_csv(symbol_dir / '行情.csv')
    return _prepare_quote_snapshot_df_from_quote(quote, trade_date)


def build_book_rows(symbol_dir: Path, trade_date: str, quote_df: Optional[pd.DataFrame] = None) -> Tuple[List[Tuple], Optional[Tuple]]:
    normalized_trade_date = f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}' if len(trade_date) == 8 else trade_date
    df = _prepare_quote_snapshot_df_from_quote(quote_df, normalized_trade_date) if quote_df is not None else _prepare_quote_snapshot_df(symbol_dir, normalized_trade_date)
    symbol = _normalize_symbol_dir_name(symbol_dir.name)
    if df.empty:
        return [], None

    grouped = df.groupby('bucket', sort=False)
    snapshot_df = grouped.agg(
        time=('time', 'last'),
        quote_row_count_5m=('time', 'size'),
        end_bid_resting_volume=('end_bid_resting_volume', 'last'),
        end_ask_resting_volume=('end_ask_resting_volume', 'last'),
        end_bid_resting_amount=('end_bid_resting_amount', 'last'),
        end_ask_resting_amount=('end_ask_resting_amount', 'last'),
        top1_bid_volume=('top1_bid_volume', 'last'),
        top1_ask_volume=('top1_ask_volume', 'last'),
        top5_bid_volume=('top5_bid_volume', 'last'),
        top5_ask_volume=('top5_ask_volume', 'last'),
        top1_bid_amount=('top1_bid_amount', 'last'),
        top1_ask_amount=('top1_ask_amount', 'last'),
        top5_bid_amount=('top5_bid_amount', 'last'),
        top5_ask_amount=('top5_ask_amount', 'last'),
        book_imbalance_ratio=('book_imbalance_ratio', 'last'),
        book_depth_ratio=('book_depth_ratio', 'last'),
        book_state_label=('book_state_label', 'last'),
        has_bid_total=('叫买总量', lambda s: bool(s.notna().any())),
        has_ask_total=('叫卖总量', lambda s: bool(s.notna().any())),
    ).reset_index()

    rows_5m: List[Tuple] = []
    source_type = 'l2_quote_book_state'
    for row in snapshot_df.itertuples(index=False):
        quality_parts = ['book_amount_uses_top10']
        if bool(row.has_bid_total) or bool(row.has_ask_total):
            quality_parts.append('resting_volume_uses_total_if_available')
        rows_5m.append(
            (
                symbol,
                normalized_trade_date,
                row.bucket.strftime('%Y-%m-%d %H:%M:%S'),
                str(row.time),
                int(row.quote_row_count_5m),
                float(row.end_bid_resting_volume) if pd.notna(row.end_bid_resting_volume) else None,
                float(row.end_ask_resting_volume) if pd.notna(row.end_ask_resting_volume) else None,
                float(row.end_bid_resting_amount) if pd.notna(row.end_bid_resting_amount) else None,
                float(row.end_ask_resting_amount) if pd.notna(row.end_ask_resting_amount) else None,
                float(row.top1_bid_volume) if pd.notna(row.top1_bid_volume) else None,
                float(row.top1_ask_volume) if pd.notna(row.top1_ask_volume) else None,
                float(row.top5_bid_volume) if pd.notna(row.top5_bid_volume) else None,
                float(row.top5_ask_volume) if pd.notna(row.top5_ask_volume) else None,
                float(row.top1_bid_amount) if pd.notna(row.top1_bid_amount) else None,
                float(row.top1_ask_amount) if pd.notna(row.top1_ask_amount) else None,
                float(row.top5_bid_amount) if pd.notna(row.top5_bid_amount) else None,
                float(row.top5_ask_amount) if pd.notna(row.top5_ask_amount) else None,
                float(row.book_imbalance_ratio) if pd.notna(row.book_imbalance_ratio) else None,
                float(row.book_depth_ratio) if pd.notna(row.book_depth_ratio) else None,
                str(row.book_state_label),
                source_type,
                '；'.join(quality_parts),
            )
        )

    rows_sorted = rows_5m
    bid_amounts = [r[7] for r in rows_sorted if r[7] is not None]
    ask_amounts = [r[8] for r in rows_sorted if r[8] is not None]
    imbalances = [r[17] for r in rows_sorted if r[17] is not None]
    depths = [r[18] for r in rows_sorted if r[18] is not None]
    labels = [r[19] for r in rows_sorted]
    daily_row = (
        symbol,
        normalized_trade_date,
        float(sum(bid_amounts) / len(bid_amounts)) if bid_amounts else None,
        float(sum(ask_amounts) / len(ask_amounts)) if ask_amounts else None,
        float(sum(imbalances) / len(imbalances)) if imbalances else None,
        float(sum(depths) / len(depths)) if depths else None,
        float(max(bid_amounts)) if bid_amounts else None,
        float(max(ask_amounts)) if ask_amounts else None,
        rows_sorted[-1][7],
        rows_sorted[-1][8],
        rows_sorted[-1][17],
        rows_sorted[-1][18],
        int(sum(1 for x in labels if x == 'bid_dominant')),
        int(sum(1 for x in labels if x == 'ask_dominant')),
        int(sum(1 for x in labels if x == 'thin')),
        int(sum(1 for x in labels if x == 'balanced')),
        int(len(rows_sorted)),
        'l2_quote_book_state',
        'book_daily_from_5m_snapshot',
    )
    return rows_sorted, daily_row


def replace_book_rows(conn: sqlite3.Connection, rows_5m: Sequence[Tuple], daily_row: Optional[Tuple]) -> None:
    if not rows_5m:
        return
    symbol = rows_5m[0][0]
    trade_date = rows_5m[0][1]
    conn.execute('DELETE FROM atomic_book_state_5m WHERE symbol = ? AND trade_date = ?', (symbol, trade_date))
    conn.execute('DELETE FROM atomic_book_state_daily WHERE symbol = ? AND trade_date = ?', (symbol, trade_date))
    conn.executemany(
        """
        INSERT INTO atomic_book_state_5m (
            symbol, trade_date, bucket_start, snapshot_time, quote_row_count_5m,
            end_bid_resting_volume, end_ask_resting_volume,
            end_bid_resting_amount, end_ask_resting_amount,
            top1_bid_volume, top1_ask_volume, top5_bid_volume, top5_ask_volume,
            top1_bid_amount, top1_ask_amount, top5_bid_amount, top5_ask_amount,
            book_imbalance_ratio, book_depth_ratio, book_state_label,
            source_type, quality_info
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows_5m,
    )
    if daily_row:
        conn.execute(
            """
            INSERT INTO atomic_book_state_daily (
                symbol, trade_date,
                avg_bid_resting_amount, avg_ask_resting_amount,
                avg_book_imbalance_ratio, avg_book_depth_ratio,
                max_bid_resting_amount, max_ask_resting_amount,
                close_bid_resting_amount, close_ask_resting_amount,
                close_book_imbalance_ratio, close_book_depth_ratio,
                bid_dominant_bar_count, ask_dominant_bar_count, thin_book_bar_count, balanced_bar_count,
                valid_bucket_count, source_type, quality_info
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            daily_row,
        )


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(BOOK_STATE_SCHEMA.read_text(encoding='utf-8'))
    conn.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build book state 5m/daily tables from 行情.csv snapshots.')
    parser.add_argument('input_path', help='Symbol dir such as 603629.SH or full path to that dir')
    parser.add_argument('--trade-date', required=True, help='YYYY-MM-DD or YYYYMMDD')
    parser.add_argument('--atomic-db', type=Path, default=DEFAULT_ATOMIC_DB)
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbol_dir = Path(args.input_path)
    if not symbol_dir.is_dir():
        raise SystemExit(f'symbol dir not found: {symbol_dir}')
    rows_5m, daily_row = build_book_rows(symbol_dir, args.trade_date)
    if not args.dry_run:
        args.atomic_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(args.atomic_db) as conn:
            ensure_schema(conn)
            replace_book_rows(conn, rows_5m, daily_row)
            conn.commit()
    print({
        'symbol_dir': str(symbol_dir),
        'trade_date': args.trade_date,
        'rows_5m': len(rows_5m),
        'has_daily': bool(daily_row),
        'atomic_db': str(args.atomic_db),
        'dry_run': bool(args.dry_run),
    })


if __name__ == '__main__':
    main()
