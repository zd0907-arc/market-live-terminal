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
import os
import sqlite3
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.core.l2_package_layout import normalize_month_day_root
from backend.scripts.l2_daily_backfill import list_symbol_dirs, normalize_symbol_dir_name


def _chunk_symbols(symbols: Sequence[str], worker_count: int) -> List[List[str]]:
    if not symbols:
        return []
    if worker_count <= 1 or len(symbols) <= 1:
        return [list(symbols)]
    worker_count = max(1, min(int(worker_count), len(symbols)))
    chunks = [[] for _ in range(worker_count)]
    for idx, symbol in enumerate(symbols):
        chunks[idx % worker_count].append(symbol)
    return [chunk for chunk in chunks if chunk]


def _symbol_dir_weight(symbol_dir: Path) -> int:
    total = 0
    stack = [Path(symbol_dir)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_file():
                            total += int(entry.stat().st_size)
                        elif entry.is_dir():
                            stack.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return max(1, total)


def _balanced_symbol_chunks(symbol_weights: Sequence[Tuple[str, int]], worker_count: int) -> List[List[str]]:
    if not symbol_weights:
        return []
    if worker_count <= 1 or len(symbol_weights) <= 1:
        return [[symbol for symbol, _ in symbol_weights]]
    worker_count = max(1, min(int(worker_count), len(symbol_weights)))
    buckets: List[Dict[str, object]] = [{"weight": 0, "symbols": []} for _ in range(worker_count)]
    for symbol, weight in sorted(symbol_weights, key=lambda item: (-int(item[1]), item[0])):
        bucket = min(buckets, key=lambda item: (int(item["weight"]), len(item["symbols"])))
        bucket["symbols"].append(symbol)
        bucket["weight"] = int(bucket["weight"]) + int(weight)
    return [sorted(list(bucket["symbols"])) for bucket in buckets if bucket["symbols"]]


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


def _archive_size_snapshot(archive_path: Path) -> Dict[str, int]:
    size = int(archive_path.stat().st_size)
    return {"size_before": size, "size_after": size}


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


def _resolve_reuse_day_root(candidate: Optional[Path]) -> Optional[Path]:
    if candidate is None:
        return None
    path = Path(candidate)
    if not path.exists():
        return None
    try:
        day_root, _ = normalize_month_day_root(path)
    except Exception:
        return None
    if not day_root.exists():
        return None
    if not list_symbol_dirs(day_root):
        return None
    return day_root


def _load_excluded_symbols_from_artifact(artifact_db: Optional[Path], trade_date: str) -> List[str]:
    if artifact_db is None:
        return []
    path = Path(artifact_db)
    if not path.exists():
        return []
    try:
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM history_daily_l2 WHERE date=?",
                (f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}",),
            ).fetchall()
    except sqlite3.Error:
        return []
    return sorted({str(row[0]).strip().lower() for row in rows if str(row[0]).strip()})


def prepare_day(
    trade_date: str,
    market_root: Path,
    stage_root: Path,
    output_root: Path,
    workers: int,
    stable_seconds: int = 30,
    force_reextract: bool = True,
    reuse_day_root: Optional[Path] = None,
    exclude_artifact_db: Optional[Path] = None,
) -> Dict[str, object]:
    trade_date = str(trade_date).replace("-", "").strip()
    if len(trade_date) != 8 or not trade_date.isdigit():
        raise ValueError(f"非法 trade_date: {trade_date}")

    reused_day_root = _resolve_reuse_day_root(reuse_day_root)
    archive_path = _resolve_archive_path(Path(market_root), trade_date)
    size_info = (
        _archive_size_snapshot(archive_path)
        if reused_day_root is not None
        else _wait_archive_stable(archive_path, stable_seconds=stable_seconds)
    )

    extract_root = Path(stage_root) / trade_date
    if reused_day_root is not None:
        day_root = reused_day_root
        reused_extract = True
    else:
        day_root = _extract_archive(archive_path, extract_root, force_reextract=force_reextract)
        reused_extract = False

    symbol_dirs = list_symbol_dirs(day_root)
    excluded_symbols = set(_load_excluded_symbols_from_artifact(exclude_artifact_db, trade_date))
    symbol_weights: List[Tuple[str, int]] = []
    for symbol_dir in symbol_dirs:
        symbol = normalize_symbol_dir_name(symbol_dir.name)
        if symbol in excluded_symbols:
            continue
        symbol_weights.append((symbol, _symbol_dir_weight(symbol_dir)))
    symbols = [symbol for symbol, _ in symbol_weights]
    day_output_root = Path(output_root) / trade_date
    shards_root = day_output_root / "shards"
    artifacts_root = day_output_root / "artifacts"
    shards_root.mkdir(parents=True, exist_ok=True)
    artifacts_root.mkdir(parents=True, exist_ok=True)

    shard_paths: List[Dict[str, object]] = []
    chunks = _balanced_symbol_chunks(symbol_weights, workers)
    weight_by_symbol = {symbol: weight for symbol, weight in symbol_weights}
    for idx, chunk in enumerate(chunks, start=1):
        shard_file = shards_root / f"worker_{idx}.symbols.txt"
        shard_file.write_text("\n".join(chunk) + "\n", encoding="utf-8")
        artifact_db = artifacts_root / f"worker_{idx}.db"
        if artifact_db.exists():
            artifact_db.unlink()
        shard_paths.append(
            {
                "worker": idx,
                "symbol_count": len(chunk),
                "estimated_input_bytes": int(sum(weight_by_symbol.get(symbol, 0) for symbol in chunk)),
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
        "reused_extract": reused_extract,
        "reuse_day_root": str(reuse_day_root) if reuse_day_root else "",
        "exclude_artifact_db": str(exclude_artifact_db) if exclude_artifact_db else "",
        "excluded_symbol_count": len(excluded_symbols),
        "worker_count": len(shard_paths),
        "symbol_count": len(symbols),
        "shard_strategy": "input_size_balanced",
        "estimated_input_bytes": int(sum(weight for _, weight in symbol_weights)),
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
    parser.add_argument("--reuse-day-root", default="", help=r"可选复用已解压 day_root；命中时跳过再次解压")
    parser.add_argument("--exclude-artifact-db", default="", help=r"可选种子 artifact db；其中已有 symbol 会从本次 shard 中排除")
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
        reuse_day_root=Path(args.reuse_day_root) if args.reuse_day_root else None,
        exclude_artifact_db=Path(args.exclude_artifact_db) if args.exclude_artifact_db else None,
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
