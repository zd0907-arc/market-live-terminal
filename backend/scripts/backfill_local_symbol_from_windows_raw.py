"""
从 Windows 原始日包抽单票目录，回传到本地，再写入本地 market_data.db。

适用场景：
- 先补单票（如利通电子）做深复盘；
- 不想先同步整个 Windows 正式库；
- 需要快速验证某只股票某段时间的原始包与本地落库结果。

示例：
python3 backend/scripts/backfill_local_symbol_from_windows_raw.py \
  --symbol sh603629 \
  --dates 20260320,20260323,20260324
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.l2_daily_backfill import backfill_day_package


WIN_HOST = os.getenv("L2_WIN_HOST", "laqiyuan@100.115.228.56")
WIN_MARKET_ROOT = os.getenv("L2_WIN_MARKET_ROOT", r"D:\MarketData")
WIN_TMP_ROOT = os.getenv("L2_WIN_TMP_SYMBOL_ROOT", r"D:\tmp_l2_audit")
LOCAL_TMP_ROOT = Path(os.getenv("L2_LOCAL_TMP_SYMBOL_ROOT", "/tmp/l2_symbol_pull"))
LOCAL_DB_PATH = str(ROOT_DIR / "data" / "market_data.db")


def _decode_maybe(data: bytes) -> str:
    if not data:
        return ""
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, check=False, capture_output=True, text=False)
    stdout = _decode_maybe(result.stdout)
    stderr = _decode_maybe(result.stderr)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(cmd, result.returncode, stdout, stderr)


def _norm_symbol(symbol: str) -> str:
    s = (symbol or "").strip().lower()
    if len(s) == 8 and s[:2] in {"sh", "sz", "bj"}:
        return s
    raise ValueError(f"非法 symbol: {symbol}")


def _remote_symbol_dir_name(symbol: str) -> str:
    return f"{symbol[2:]}.{symbol[:2].upper()}"


def _expand_dates(raw: str) -> List[str]:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if not parts:
        raise ValueError("dates 不能为空")
    for p in parts:
        if len(p) != 8 or not p.isdigit():
            raise ValueError(f"非法日期: {p}，应为 YYYYMMDD")
    return parts


def _ssh_cmd(command: str) -> List[str]:
    return ["bash", "-lc", f"ssh -o ConnectTimeout=8 {shlex.quote(WIN_HOST)} {shlex.quote(command)}"]


def _ensure_local_symbol_dir(trade_date: str, symbol: str) -> Path:
    symbol_dir = LOCAL_TMP_ROOT / trade_date / _remote_symbol_dir_name(symbol)
    symbol_dir.mkdir(parents=True, exist_ok=True)
    return symbol_dir


def _extract_remote_day(symbol: str, trade_date: str) -> str:
    month = trade_date[:6]
    remote_dir = f"{WIN_TMP_ROOT}\\{trade_date}"
    remote_archive = f"{WIN_MARKET_ROOT}\\{month}\\{trade_date}.7z"
    remote_symbol_dir = _remote_symbol_dir_name(symbol)
    command = (
        f'cmd /c "if exist {remote_dir} rmdir /s /q {remote_dir} '
        f'& C:\\Wind\\Wind.NET.Client\\WindNET\\bin\\7za.exe x -y '
        f'{remote_archive} {trade_date}\\{remote_symbol_dir}\\* -o{WIN_TMP_ROOT}"'
    )
    _run(_ssh_cmd(command))
    return f"{WIN_TMP_ROOT.replace(chr(92), '/')}/{trade_date}/{remote_symbol_dir}"


def _pull_remote_symbol_dir(symbol: str, trade_date: str) -> Path:
    remote_dir = _extract_remote_day(symbol, trade_date)
    symbol_dir = _ensure_local_symbol_dir(trade_date, symbol)
    for filename in ["行情.csv", "逐笔成交.csv", "逐笔委托.csv"]:
        remote_file = f"{remote_dir}/{filename}"
        target_file = symbol_dir / filename
        _run(["scp", f"{WIN_HOST}:{remote_file}", str(target_file)])
    return symbol_dir


def _backfill_local(symbol: str, trade_date: str, dry_run: bool) -> dict:
    os.environ["DB_PATH"] = LOCAL_DB_PATH
    report = backfill_day_package(
        LOCAL_TMP_ROOT / trade_date,
        symbols=[symbol],
        mode=f"local_symbol_pull_{trade_date}",
        dry_run=dry_run,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="从 Windows 原始包补单票到本地")
    parser.add_argument("--symbol", required=True, help="如 sh603629")
    parser.add_argument("--dates", required=True, help="逗号分隔，如 20260320,20260323")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbol = _norm_symbol(args.symbol)
    dates = _expand_dates(args.dates)
    results = []

    for trade_date in dates:
        _pull_remote_symbol_dir(symbol, trade_date)
        report = _backfill_local(symbol, trade_date, bool(args.dry_run))
        results.append(report)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(
                f"[local-symbol-backfill] {item['trade_date']} "
                f"success={item['success_symbols']} failed={item['failed_symbols']} "
                f"rows_5m={item['rows_5m']} rows_daily={item['rows_daily']}"
            )


if __name__ == "__main__":
    main()
