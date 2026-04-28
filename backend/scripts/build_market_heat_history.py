#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import MARKET_HEAT_DIR, _trade_dates, build_market_heat_snapshot, ensure_market_heat_dir


def main() -> None:
    parser = argparse.ArgumentParser(description='Build historical market heat snapshots and compact score history.')
    parser.add_argument('--end-date', default=None, help='结束交易日，默认最新')
    parser.add_argument('--days', type=int, default=250, help='向前回溯交易日数量')
    parser.add_argument('--write-daily', action='store_true', help='同时写入每个交易日快照')
    args = parser.parse_args()

    latest_snapshot = build_market_heat_snapshot(args.end_date)
    end_date = latest_snapshot['meta']['trade_date']
    dates = _trade_dates(end_date, args.days)
    ensure_market_heat_dir()
    history = []
    for idx, trade_date in enumerate(dates, start=1):
        snapshot = build_market_heat_snapshot(trade_date)
        if args.write_daily:
            (MARKET_HEAT_DIR / f'{trade_date}.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
        for sector in snapshot.get('sectors', []):
            history.append({
                'date': trade_date,
                'sector_id': sector.get('id'),
                'sector_name': sector.get('name'),
                'hot_score': sector.get('hot_score'),
                'persistence_score': sector.get('persistence_score'),
                'pct_change': sector.get('pct_change'),
                'return_5d': sector.get('return_5d'),
                'return_20d': sector.get('return_20d'),
                'l2_net_inflow_yi': sector.get('l2_net_inflow_yi'),
                'up_ratio': sector.get('up_ratio'),
                'risk_tags': sector.get('risk_tags'),
            })
        print(f'[{idx}/{len(dates)}] {trade_date}')
    out = {
        'meta': {
            'start_date': dates[0] if dates else None,
            'end_date': end_date,
            'days': len(dates),
            'version': 'market_heat_history_v1',
        },
        'items': history,
    }
    out_path = MARKET_HEAT_DIR / f'history_{dates[0]}_{end_date}.json' if dates else MARKET_HEAT_DIR / 'history_empty.json'
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'wrote {out_path}')


if __name__ == '__main__':
    main()
