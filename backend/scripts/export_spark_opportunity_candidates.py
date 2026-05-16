#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.spark_opportunity_selector import (
    DEFAULT_MODEL_DIR,
    generate_candidates_from_latest_csv,
    generate_daily_candidates,
    source_registry_record,
    write_source_manifest,
)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Export Spark Opportunity 1.0 standard candidate records")
    parser.add_argument("--date", default="", help="Signal date YYYY-MM-DD. Required for model inference; optional for latest-csv bridge.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--atomic-db", default=None)
    parser.add_argument("--selection-db", default=None)
    parser.add_argument("--heat-db", default=None)
    parser.add_argument("--out", default=str(DEFAULT_MODEL_DIR / "sample_candidates_2026-05-14.json"))
    parser.add_argument(
        "--mode",
        choices=["latest-csv", "infer"],
        default="latest-csv",
        help="latest-csv is the P1 bridge. infer loads model.joblib and computes candidates for --date.",
    )
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args(argv)

    if args.write_manifest:
        write_source_manifest(args.model_dir)

    if args.mode == "infer":
        if not args.date:
            raise SystemExit("--date is required when --mode=infer")
        records = generate_daily_candidates(
            args.date,
            limit=args.limit,
            model_dir=args.model_dir,
            atomic_db=args.atomic_db,
            selection_db=args.selection_db,
            heat_db=args.heat_db,
        )
    else:
        records = generate_candidates_from_latest_csv(
            trade_date=args.date or None,
            limit=args.limit,
            csv_path=Path(args.model_dir) / "latest_candidates.csv",
        )

    payload = {
        "registry": source_registry_record(),
        "mode": args.mode,
        "trade_date": args.date or (records[0]["trade_date"] if records else None),
        "count": len(records),
        "items": records,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "count": len(records), "mode": args.mode}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
