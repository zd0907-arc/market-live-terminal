"""
按 symbol 分片并发执行单日 L2 正式回补。

设计目的：
- 单个交易日日包解压后体积很大，不适合多天并行解压；
- 但可以在“单日已解压”的前提下，按 symbol 分片并发跑多个 worker，
  提升 CSV 解析和聚合速度。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Sequence

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.scripts.l2_daily_backfill import list_symbol_dirs, normalize_symbol_dir_name


def _chunk_symbols(symbols: Sequence[str], worker_count: int) -> List[List[str]]:
    if worker_count <= 1 or len(symbols) <= 1:
        return [list(symbols)]

    worker_count = max(1, min(worker_count, len(symbols)))
    chunk_size = math.ceil(len(symbols) / worker_count)
    return [list(symbols[i:i + chunk_size]) for i in range(0, len(symbols), chunk_size)]


def run_sharded_backfill(
    day_dir: Path,
    db_path: str,
    worker_count: int = 4,
    mode_prefix: str = "shard",
    large_threshold: float = 200000.0,
    super_threshold: float = 1000000.0,
) -> Dict[str, object]:
    symbol_dirs = list_symbol_dirs(day_dir)
    symbols = [normalize_symbol_dir_name(path.name) for path in symbol_dirs]
    if not symbols:
        raise ValueError(f"未发现 symbol 目录: {day_dir}")

    shards = _chunk_symbols(symbols, worker_count)
    processes = []
    logs_dir = Path(os.getenv("L2_SHARD_LOG_DIR", os.path.join(ROOT_DIR, ".run", "l2_shards")))
    logs_dir.mkdir(parents=True, exist_ok=True)

    for idx, shard_symbols in enumerate(shards, start=1):
        log_path = logs_dir / f"{Path(day_dir).name}_worker_{idx}.log"
        symbols_path = logs_dir / f"{Path(day_dir).name}_worker_{idx}.symbols.txt"
        symbols_path.write_text("\n".join(shard_symbols) + "\n", encoding="utf-8")
        log_fh = open(log_path, "w", encoding="utf-8")
        cmd = [
            sys.executable,
            os.path.join(ROOT_DIR, "backend", "scripts", "l2_daily_backfill.py"),
            str(day_dir),
            "--symbols-file",
            str(symbols_path),
            "--db-path",
            db_path,
            "--mode",
            f"{mode_prefix}_w{idx}",
            "--large-threshold",
            str(large_threshold),
            "--super-threshold",
            str(super_threshold),
            "--json",
        ]
        proc = subprocess.Popen(cmd, stdout=log_fh, stderr=log_fh)
        processes.append({
            "worker": idx,
            "symbols": len(shard_symbols),
            "log_path": str(log_path),
            "symbols_path": str(symbols_path),
            "process": proc,
            "log_fh": log_fh,
        })

    results = []
    for item in processes:
        proc = item["process"]
        return_code = proc.wait()
        item["log_fh"].close()
        results.append({
            "worker": item["worker"],
            "symbols": item["symbols"],
            "return_code": return_code,
            "log_path": item["log_path"],
            "symbols_path": item["symbols_path"],
        })

    return {
        "day_dir": str(day_dir),
        "worker_count": len(shards),
        "total_symbols": len(symbols),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="按 symbol 分片并发执行单日 L2 正式回补")
    parser.add_argument("day_dir", help=r"解压后的日目录，如 D:\MarketData\202603\20260312")
    parser.add_argument("--db-path", required=True, help="正式库路径")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--mode-prefix", default="shard")
    parser.add_argument("--large-threshold", type=float, default=200000.0)
    parser.add_argument("--super-threshold", type=float, default=1000000.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_sharded_backfill(
        day_dir=Path(args.day_dir),
        db_path=args.db_path,
        worker_count=int(args.workers),
        mode_prefix=args.mode_prefix,
        large_threshold=float(args.large_threshold),
        super_threshold=float(args.super_threshold),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[l2-day-sharded] day_dir={report['day_dir']} "
            f"workers={report['worker_count']} total_symbols={report['total_symbols']}"
        )
        for result in report["results"]:
            print(
                f"  - worker={result['worker']} symbols={result['symbols']} "
                f"rc={result['return_code']} log={result['log_path']}"
            )


if __name__ == "__main__":
    main()
