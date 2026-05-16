from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.services.aggressive_10cm_strategy import Aggressive10cmParams, backtest_range  # noqa: E402


def _variant_grid() -> List[Dict[str, Any]]:
    values = {
        "min_score": [78.0, 82.0, 85.0],
        "max_open_gap_up_pct": [3.5, 4.8, 6.8],
        "first_15m_price_floor_pct": [0.0, 0.3],
        "first_15m_main_net_floor": [-0.005, 0.0],
        "max_total_exposure_pct": [0.60, 0.80],
        "max_positions": [3, 4],
    }
    keys = list(values)
    variants: List[Dict[str, Any]] = []
    for combo in itertools.product(*(values[key] for key in keys)):
        raw = dict(zip(keys, combo))
        raw["name"] = (
            f"s{raw['min_score']:g}_gap{raw['max_open_gap_up_pct']:g}"
            f"_p15{raw['first_15m_price_floor_pct']:g}"
            f"_m{raw['first_15m_main_net_floor']:g}"
            f"_exp{int(raw['max_total_exposure_pct'] * 100)}"
            f"_pos{raw['max_positions']}"
        )
        variants.append(raw)
    return variants


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="2026-04-01")
    parser.add_argument("--end-date", default="2026-04-30")
    parser.add_argument("--replay-end-date", default="2026-05-11")
    parser.add_argument("--budget", type=float, default=1_000_000.0)
    parser.add_argument("--top-n", type=int, default=12)
    parser.add_argument("--out", default="data/selection/aggressive_10cm/grid")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    variants = _variant_grid()
    if args.limit and args.limit > 0:
        variants = variants[: int(args.limit)]

    for idx, variant in enumerate(variants, start=1):
        params = Aggressive10cmParams(
            initial_budget=float(args.budget),
            min_score=float(variant["min_score"]),
            max_open_gap_up_pct=float(variant["max_open_gap_up_pct"]),
            first_15m_price_floor_pct=float(variant["first_15m_price_floor_pct"]),
            first_15m_main_net_floor=float(variant["first_15m_main_net_floor"]),
            first_15m_super_net_floor=float(variant["first_15m_main_net_floor"]),
            max_total_exposure_pct=float(variant["max_total_exposure_pct"]),
            max_positions=int(variant["max_positions"]),
            max_new_positions_per_day=min(3, int(variant["max_positions"])),
            per_position_pct=0.25,
        )
        payload = backtest_range(
            args.start_date,
            args.end_date,
            replay_end_date=args.replay_end_date,
            budget=float(args.budget),
            params=params,
            top_n=int(args.top_n),
        )
        row = {
            "variant": variant["name"],
            **{k: v for k, v in variant.items() if k != "name"},
            **payload["summary"],
        }
        rows.append(row)
        print(json.dumps({"idx": idx, "variant": variant["name"], "summary": payload["summary"]}, ensure_ascii=False))

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            ["total_return_pct", "max_drawdown_pct", "median_net_return_pct", "win_rate_pct"],
            ascending=[False, False, False, False],
        )
    csv_path = out / f"grid_{args.start_date}_{args.end_date}.csv"
    json_path = out / f"grid_{args.start_date}_{args.end_date}.json"
    md_path = out / f"grid_{args.start_date}_{args.end_date}.md"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps({"range": vars(args), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# aggressive_10cm 参数网格",
        "",
        f"区间：{args.start_date} ~ {args.end_date}，回放到 {args.replay_end_date}",
        "",
    ]
    if not df.empty:
        lines.append(df.head(20).to_markdown(index=False))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"written": {"csv": str(csv_path), "json": str(json_path), "markdown": str(md_path)}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
