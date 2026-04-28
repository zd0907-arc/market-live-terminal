#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import build_market_heat_snapshot, render_markdown, write_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump market hot sectors from local atomic data and curated themes.")
    parser.add_argument("--date", dest="trade_date", default=None, help="交易日 YYYY-MM-DD，默认最新 atomic_trade_daily 日期")
    parser.add_argument("--json", action="store_true", help="打印 JSON")
    parser.add_argument("--no-write", action="store_true", help="只打印，不写入 data/market_heat")
    args = parser.parse_args()

    snapshot = build_market_heat_snapshot(args.trade_date)
    if not args.no_write:
        json_path, md_path = write_snapshot(snapshot)
        print(f"wrote {json_path}")
        print(f"wrote {md_path}")
    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(snapshot))


if __name__ == "__main__":
    main()
