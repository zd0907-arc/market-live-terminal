#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.market_heat import refresh_fine_heat_snapshot_cache


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh fine market heat dashboard cache for daily pipeline.")
    parser.add_argument("--end-date", default=None, help="Trade date YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=63)
    parser.add_argument("--force", action="store_true", default=True)
    parser.add_argument("--no-force", dest="force", action="store_false")
    args = parser.parse_args()

    result = refresh_fine_heat_snapshot_cache(
        end_date=args.end_date,
        days=max(int(args.days or 63), 20),
        force=bool(args.force),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
