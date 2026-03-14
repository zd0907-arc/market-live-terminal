"""
Sandbox Review V2 - 全月份总控脚本

用途：
1. 一次启动后，按月份逆序自动串行跑完整个沙盒区间（默认 2026-02 -> 2025-01）
2. 每个月单独调用 backfill 脚本，便于断点续跑、月级重试与日志追踪
3. 全部完成后只停在 done 态，不自动做云端同步或版本发布
"""

import argparse
import calendar
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from backend.app.db.sandbox_review_v2_db import (  # noqa: E402
    ensure_sandbox_review_v2_schema,
    get_latest_month_run,
    get_sandbox_review_v2_root,
)
from backend.scripts.sandbox_review_v2_backfill import (  # noqa: E402
    SANDBOX_MAX_DATE,
    SANDBOX_MIN_DATE,
)


def _month_floor(date_text: str) -> str:
    return date_text[:7]


def _month_range_desc(start_date: str, end_date: str) -> List[str]:
    months: List[str] = []
    year = int(end_date[:4])
    month = int(end_date[5:7])
    start_month = _month_floor(start_date)
    while True:
        current = f"{year:04d}-{month:02d}"
        if current < start_month:
            break
        months.append(current)
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return months


def _clip_month_window(month_text: str, start_date: str, end_date: str) -> Tuple[str, str]:
    year = int(month_text[:4])
    month = int(month_text[5:7])
    first_day = f"{year:04d}-{month:02d}-01"
    last_day = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    return max(first_day, start_date), min(last_day, end_date)


def _logs_dir() -> str:
    path = os.path.join(get_sandbox_review_v2_root(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def _default_state_path() -> str:
    return os.path.join(_logs_dir(), "run_all_months_latest.json")


def _write_state(path: str, payload: Dict[str, object]) -> None:
    payload = dict(payload)
    payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def _build_backfill_cmd(args: argparse.Namespace, month: str, month_start: str, month_end: str) -> List[str]:
    cmd = [
        args.python_exe,
        "-u",
        os.path.join(ROOT_DIR, "backend", "scripts", "sandbox_review_v2_backfill.py"),
        args.src_root,
        "--start-date",
        month_start,
        "--end-date",
        month_end,
        "--months",
        month,
        "--workers",
        str(args.workers),
        "--min-workers",
        str(args.min_workers),
        "--mem-high-watermark",
        str(args.mem_high_watermark),
        "--day-symbol-batch-size",
        str(args.day_symbol_batch_size),
        "--large-threshold",
        str(args.large_threshold),
        "--super-threshold",
        str(args.super_threshold),
    ]
    if args.resume:
        cmd.append("--resume")
    if args.replace:
        cmd.append("--replace")
    if args.allow_missing_order_ids:
        cmd.append("--allow-missing-order-ids")
    if args.force_volume_multiplier is not None:
        cmd.extend(["--force-volume-multiplier", str(args.force_volume_multiplier)])
    if args.symbols:
        cmd.extend(["--symbols", args.symbols])
    elif args.max_symbols > 0:
        cmd.extend(["--max-symbols", str(args.max_symbols)])
    return cmd


def _run_single_month(args: argparse.Namespace, month: str) -> Dict[str, object]:
    month_start, month_end = _clip_month_window(month, args.start_date, args.end_date)
    cmd = _build_backfill_cmd(args, month, month_start, month_end)
    print(
        f"[run-all-months] >>> 开始月份 {month} window={month_start}~{month_end}"
    )
    print("[run-all-months] cmd=", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=ROOT_DIR)
    latest = get_latest_month_run(month) or {}
    return {
        "month": month,
        "window_start": month_start,
        "window_end": month_end,
        "returncode": int(completed.returncode),
        "latest_month_run": latest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sandbox Review V2 全月份总控（按月逆序自动串行）")
    parser.add_argument("src_root", help="Windows 历史逐笔根目录，如 D:\\MarketData")
    parser.add_argument("--start-date", default=SANDBOX_MIN_DATE)
    parser.add_argument("--end-date", default=SANDBOX_MAX_DATE)
    parser.add_argument("--symbols", default="", help="逗号分隔，留空则使用股票池")
    parser.add_argument("--max-symbols", type=int, default=0, help="仅前N只股票（0不限制）")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--min-workers", type=int, default=8)
    parser.add_argument("--mem-high-watermark", type=float, default=80.0)
    parser.add_argument("--day-symbol-batch-size", type=int, default=240)
    parser.add_argument("--resume", action="store_true", help="按 symbol+trade_date 断点续跑")
    parser.add_argument("--replace", action="store_true", help="重建目标 symbol 历史（慎用）")
    parser.add_argument("--large-threshold", type=float, default=200000.0)
    parser.add_argument("--super-threshold", type=float, default=1000000.0)
    parser.add_argument("--force-volume-multiplier", type=int, choices=[1, 100], default=None)
    parser.add_argument("--allow-missing-order-ids", action="store_true")
    parser.add_argument("--retry-months", type=int, default=1, help="单个月份失败后的额外重试次数")
    parser.add_argument("--continue-on-partial", action="store_true", help="月份状态为 partial_done 时继续跑后续月份")
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--state-file", default=_default_state_path())
    args = parser.parse_args()

    if args.start_date < SANDBOX_MIN_DATE or args.end_date > SANDBOX_MAX_DATE:
        raise ValueError(f"区间超限，仅支持 {SANDBOX_MIN_DATE} 至 {SANDBOX_MAX_DATE}")
    if args.end_date < args.start_date:
        raise ValueError("结束日期必须大于等于开始日期")
    if args.min_workers < 1 or args.min_workers > args.workers:
        raise ValueError("并发参数非法：需要满足 1 <= min-workers <= workers")

    ensure_sandbox_review_v2_schema()
    months = _month_range_desc(args.start_date, args.end_date)
    if not months:
        raise ValueError("未解析到任何目标月份")

    state = {
        "status": "running",
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "src_root": args.src_root,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "months": months,
        "current_month": None,
        "completed_months": [],
        "partial_months": [],
        "failed_months": [],
        "note": "全月份总控已启动；完成后仅停在 done，不自动同步云端或发布版本。",
    }
    _write_state(args.state_file, state)

    for month in months:
        state["current_month"] = month
        _write_state(args.state_file, state)
        month_success = False
        attempts = max(1, int(args.retry_months) + 1)
        last_result: Optional[Dict[str, object]] = None

        for attempt in range(1, attempts + 1):
            print(f"[run-all-months] ===== 月份 {month}，第 {attempt}/{attempts} 次尝试 =====")
            result = _run_single_month(args, month)
            last_result = result
            latest = result.get("latest_month_run") or {}
            latest_status = str(latest.get("status") or "")
            failed_count = int(latest.get("failed_count") or 0)
            return_code = int(result.get("returncode") or 0)

            if return_code != 0:
                print(f"[run-all-months] 月份 {month} 子进程失败，returncode={return_code}")
                continue

            if latest_status == "done":
                state["completed_months"].append(month)
                month_success = True
                print(f"[run-all-months] 月份 {month} 完成，rows={latest.get('total_rows', 0)}")
                break

            if latest_status == "partial_done":
                state["partial_months"].append(
                    {
                        "month": month,
                        "failed_count": failed_count,
                        "message": latest.get("message", ""),
                    }
                )
                if args.continue_on_partial:
                    month_success = True
                    print(
                        f"[run-all-months] 月份 {month} 部分完成，failed_count={failed_count}，按配置继续后续月份"
                    )
                    break
                print(
                    f"[run-all-months] 月份 {month} 为 partial_done，默认停机等待人工处理"
                )
                break

            print(
                f"[run-all-months] 月份 {month} 未获得成功状态，latest_status={latest_status or 'unknown'}"
            )

        _write_state(args.state_file, state)
        if month_success:
            continue

        state["status"] = "failed"
        state["failed_months"].append(
            {
                "month": month,
                "returncode": None if last_result is None else last_result.get("returncode"),
                "latest_month_run": None if last_result is None else last_result.get("latest_month_run"),
            }
        )
        state["stopped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_state(args.state_file, state)
        raise SystemExit(f"全月份总控在 {month} 停止，请查看 state_file 与月批日志")

    state["status"] = "done"
    state["current_month"] = None
    state["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_state(args.state_file, state)
    print("[run-all-months] 全月份总控完成；当前仅结束在 done 态，不自动同步云端或发布版本")


if __name__ == "__main__":
    main()
