from pathlib import Path

import pandas as pd
import sqlite3

from backend.scripts.build_book_state_from_raw import build_book_rows, ensure_schema, replace_book_rows


def _make_quote_row(time_val: int, bid1: int, ask1: int, bidv1: int, askv1: int, total_bid: int, total_ask: int):
    row = {
        '时间': time_val,
        '叫买总量': total_bid,
        '叫卖总量': total_ask,
    }
    for i in range(1, 11):
        row[f'申买价{i}'] = bid1 - (i - 1) * 100
        row[f'申卖价{i}'] = ask1 + (i - 1) * 100
        row[f'申买量{i}'] = bidv1 if i == 1 else max(10, bidv1 - i * 10)
        row[f'申卖量{i}'] = askv1 if i == 1 else max(10, askv1 - i * 10)
    return row


def test_build_book_rows_and_replace(tmp_path: Path):
    symbol_dir = tmp_path / '603629.SH'
    symbol_dir.mkdir()
    quote = pd.DataFrame(
        [
            _make_quote_row(93001000, 100000, 100100, 1000, 800, 5000, 4000),
            _make_quote_row(93459000, 100200, 100300, 1500, 700, 6000, 3000),
            _make_quote_row(150000000, 101000, 101100, 900, 600, 4500, 2500),
        ]
    )
    quote.to_csv(symbol_dir / '行情.csv', index=False, encoding='gb18030')

    rows_5m, daily_row = build_book_rows(symbol_dir, '2026-03-11')

    assert len(rows_5m) == 2
    assert rows_5m[0][0] == 'sh603629'
    assert rows_5m[0][2] == '2026-03-11 09:30:00'
    assert rows_5m[1][2] == '2026-03-11 14:55:00'
    assert rows_5m[0][3] == '09:34:59'
    assert rows_5m[0][5] == 6000.0
    assert rows_5m[0][6] == 3000.0
    assert rows_5m[0][19] in {'bid_dominant', 'balanced', 'thin'}
    assert daily_row is not None
    assert daily_row[0] == 'sh603629'
    assert daily_row[1] == '2026-03-11'
    assert daily_row[16] == 2

    db_path = tmp_path / 'atomic.db'
    with sqlite3.connect(db_path) as conn:
        ensure_schema(conn)
        replace_book_rows(conn, rows_5m, daily_row)
        conn.commit()
        cnt_5m = conn.execute('select count(*) from atomic_book_state_5m').fetchone()[0]
        cnt_daily = conn.execute('select count(*) from atomic_book_state_daily').fetchone()[0]
        close_bucket = conn.execute(
            "select bucket_start, snapshot_time from atomic_book_state_5m order by bucket_start desc limit 1"
        ).fetchone()

    assert cnt_5m == 2
    assert cnt_daily == 1
    assert close_bucket == ('2026-03-11 14:55:00', '15:00:00')
