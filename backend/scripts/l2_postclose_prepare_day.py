"""
Windows 单日盘后 L2 预处理：
- 校验日包存在且大小稳定
- 解压到 staging
- 识别真实 day_root
- 按 symbol 切 shard，供 Mac 总控并发拉起 worker
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Sequence

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.l2_package_layout import normalize_month_day_root
from backend.scripts.l2_daily_backfill import list_symbol_dirs, normalize_symbol_dir_name


def _chunk_symbols(symbols: Sequence[str], worker_count: int) -> List[List[str]]:
    if worker_count <= 1 or len(symbols) <= 1:
        return [list(symbols)]
    worker_count = max(1, min(int(worker_count), len(symbols)))
    chunk_size = math.ceil(len(symbols) / worker_count)
    return [list(symbols[i:i + chunk_size]) for i in range(0, len(symbols), chunk_size)]


def _resolve_archive_path(market_root: Path, trade_date: str) -> Path:
    month = trade_date[:6]
    archive_path = market_root / month / f"{trade_date}.7z"
    if archive_path.is_file():
        return archive_path
    fallback = market_root / f"{trade_date}.7z"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"未找到日包: {archive_path}")


def _wait_archive_stable(archive_path: Path, stable_seconds: int) -> Dict[str, int]:
    size_before = archive_path.stat().st_size
    if stable_seconds > 0:
        time.sleep(max(1, stable_seconds))
    size_after = archive_path.stat().st_size
    if size_before != size_after:
        raise RuntimeError(
            f"日包大小仍在变化，拒绝开跑: {archive_path} before={size_before} after={size_after}"
        )
    return {"size_before": int(size_before), "size_after": int(size_after)}


def _extract_archive(archive_path: Path, extract_root: Path, force_reextract: bool) -> Path:
    if extract_root.exists() and force_reextract:
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    marker = extract_root / ".prepared_ok"
    if marker.is_file() and any(extract_root.iterdir()):
        day_root, _ = normalize_month_day_root(extract_root)
        return day_root

    result = subprocess.run(
        ["tar", "-xf", str(archive_path), "-C", str(extract_root)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"解压失败: {archive_path} :: {result.stderr.strip()}")

    day_root, _ = normalize_month_day_root(extract_root)
    marker.write_text("ok\n", encoding="utf-8")
    return day_root


def prepare_day(
    trade_date: str,
    market_root: Path,
    stage_root: Path,
    output_root: Path,
    workers: int,
    stable_seconds: int = 30,
    force_reextract: bool = True,
) -> Dict[str, object]:
    trade_date = str(trade_date).replace("-", "").strip()
    if len(trade_date) != 8 or not trade_date.isdigit():
        raise ValueError(f"非法 trade_date: {trade_date}")

    archive_path = _resolve_archive_path(Path(market_root), trade_date)
    size_info = _wait_archive_stable(archive_path, stable_seconds=stable_seconds)

    extract_root = Path(stage_root) / trade_date
    day_root = _extract_archive(archive_path, extract_root, force_reextract=force_reextract)

    symbol_dirs = list_symbol_dirs(day_root)
    symbols = [normalize_symbol_dir_name(path.name) for path in symbol_dirs]
    if not symbols:
        raise RuntimeError(f"解压后未发现 symbol 目录: {day_root}")

    day_output_root = Path(output_root) / trade_date
    shards_root = day_output_root / "shards"
    artifacts_root = day_output_root / "artifacts"
    shards_root.mkdir(parents=True, exist_ok=True)
    artifacts_root.mkdir(parents=True, exist_ok=True)

    shard_paths: List[Dict[str, object]] = []
    for idx, chunk in enumerate(_chunk_symbols(symbols, workers), start=1):
        shard_file = shards_root / f"worker_{idx}.symbols.txt"
        shard_file.write_text("\n".join(chunk) + "\n", encoding="utf-8")
        artifact_db = artifacts_root / f"worker_{idx}.db"
        if artifact_db.exists():
            artifact_db.unlink()
        shard_paths.append(
            {
                "worker": idx,
                "symbol_count": len(chunk),
                "symbols_file": str(shard_file),
                "artifact_db": str(artifact_db),
            }
        )

    manifest = {
        "trade_date": trade_date,
        "archive_path": str(archive_path),
        "archive_size": int(size_info["size_after"]),
        "extract_root": str(extract_root),
        "day_root": str(day_root),
        "worker_count": len(shard_paths),
        "symbol_count": len(symbols),
        "shards": shard_paths,
    }
    manifest_path = day_output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="准备单日盘后 L2 shard 运行环境")
    parser.add_argument("trade_date", help="交易日 YYYYMMDD")
    parser.add_argument("--market-root", required=True, help=r"Windows 日包根目录，如 D:\MarketData")
    parser.add_argument("--stage-root", required=True, help=r"Windows staging 根目录，如 Z:\l2_stage")
    parser.add_argument("--output-root", required=True, help=r"运行产物目录，如 D:\market-live-terminal\.run\l2_postclose")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--stable-seconds", type=int, default=30)
    parser.add_argument("--no-force-reextract", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = prepare_day(
        trade_date=args.trade_date,
        market_root=Path(args.market_root),
        stage_root=Path(args.stage_root),
        output_root=Path(args.output_root),
        workers=int(args.workers),
        stable_seconds=int(args.stable_seconds),
        force_reextract=not bool(args.no_force_reextract),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[l2-postclose-prepare] trade_date={report['trade_date']} "
            f"workers={report['worker_count']} symbol_count={report['symbol_count']}"
        )


if __name__ == "__main__":
    main()
