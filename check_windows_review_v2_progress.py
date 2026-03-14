#!/usr/bin/env python3
"""
Mac 本地检查脚本：查看 Windows 上 Sandbox Review V2 全月份总控进度

默认检查：
- 计划任务 SandboxBackfillAllMonths
- Windows 上相关 python 进程
- run_all_months_latest.json 状态文件
- run_all_months.out.log / err.log 尾部日志
- 2026-02 最近一次月份 run 记录（可通过参数改月份）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Optional

DEFAULT_HOST = "laqiyuan@100.115.228.56"
DEFAULT_TASK = "SandboxBackfillAllMonths"
DEFAULT_MONTH = "2026-02"
DEFAULT_STATE = r"D:\market-live-terminal\data\sandbox\review_v2\logs\run_all_months_latest.json"
DEFAULT_OUT_LOG = r"D:\market-live-terminal\data\sandbox\review_v2\logs\run_all_months.out.log"
DEFAULT_ERR_LOG = r"D:\market-live-terminal\data\sandbox\review_v2\logs\run_all_months.err.log"
DEFAULT_PYTHON = r"C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe"


def decode_output(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", errors="ignore")


def run_ssh(host: str, remote_cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "ConnectTimeout=8", host, remote_cmd],
        capture_output=True,
        timeout=timeout,
    )


def print_section(title: str, body: str) -> None:
    print(f"\n===== {title} =====")
    print(body.strip() if body.strip() else "(空)")


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Windows 上 Sandbox Review V2 总控进度")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Windows SSH 主机，默认 {DEFAULT_HOST}")
    parser.add_argument("--task", default=DEFAULT_TASK, help=f"计划任务名，默认 {DEFAULT_TASK}")
    parser.add_argument("--month", default=DEFAULT_MONTH, help=f"查询月份 run 状态，默认 {DEFAULT_MONTH}")
    parser.add_argument("--tail", type=int, default=20, help="日志尾部行数，默认 20")
    parser.add_argument("--timeout", type=int, default=40, help="单次 ssh 超时秒数，默认 40")
    args = parser.parse_args()

    tail = max(1, int(args.tail))

    # 1) 计划任务状态
    task_cmd = f'cmd /c schtasks /Query /TN {args.task} /V /FO LIST'
    task_res = run_ssh(args.host, task_cmd, timeout=args.timeout)
    print_section("计划任务状态", decode_output(task_res.stdout) or decode_output(task_res.stderr))

    # 2) 相关 python 进程（含命令行）
    proc_cmd = (
        "powershell -NoProfile -Command \""
        "$procs = Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -like '*sandbox_review_v2_run_all_months.py*' -or $_.CommandLine -like '*sandbox_review_v2_backfill.py*') } | "
        "Select-Object ProcessId,CommandLine; "
        "if ($procs) { $procs | Format-List } else { Write-Output 'NO_MATCHED_PYTHON_PROCESS' }"
        "\""
    )
    proc_res = run_ssh(args.host, proc_cmd, timeout=args.timeout)
    print_section("相关 Python 进程", decode_output(proc_res.stdout) or decode_output(proc_res.stderr))

    # 3) 状态文件 JSON
    state_cmd = (
        "powershell -NoProfile -Command \""
        f"if (Test-Path '{DEFAULT_STATE}') {{ Get-Content -Raw -Encoding UTF8 '{DEFAULT_STATE}' }} else {{ Write-Output 'STATE_NOT_FOUND' }}"
        "\""
    )
    state_res = run_ssh(args.host, state_cmd, timeout=args.timeout)
    state_text = decode_output(state_res.stdout) or decode_output(state_res.stderr)
    print_section("总控状态文件", state_text)
    try:
        state = json.loads(state_text)
        summary = {
            "status": state.get("status"),
            "current_month": state.get("current_month"),
            "completed_count": len(state.get("completed_months", [])),
            "failed_count": len(state.get("failed_months", [])),
            "updated_at": state.get("updated_at"),
        }
        print_section("状态摘要", json.dumps(summary, ensure_ascii=False, indent=2))
    except Exception:
        pass

    # 4) 月份完成信号（从总控 out.log 检查）
    month_cmd = (
        "powershell -NoProfile -Command \""
        f"if (Test-Path '{DEFAULT_OUT_LOG}') {{ "
        f"$m = Select-String -Path '{DEFAULT_OUT_LOG}' -Pattern '===== 月份完成 {args.month}'; "
        "if ($m) { $m | Select-Object -Last 3 | ForEach-Object { $_.Line } } else { Write-Output 'MONTH_NOT_DONE_YET' } "
        "} else { Write-Output 'OUT_LOG_NOT_FOUND' }"
        "\""
    )
    month_res = run_ssh(args.host, month_cmd, timeout=args.timeout)
    print_section(f"月份完成信号（{args.month}）", decode_output(month_res.stdout) or decode_output(month_res.stderr))

    # 5) out log
    out_cmd = (
        "powershell -NoProfile -Command \""
        f"if (Test-Path '{DEFAULT_OUT_LOG}') {{ Get-Item '{DEFAULT_OUT_LOG}' | Select-Object Length,LastWriteTime; Get-Content -Tail {tail} '{DEFAULT_OUT_LOG}' }} else {{ Write-Output 'OUT_LOG_NOT_FOUND' }}"
        "\""
    )
    out_res = run_ssh(args.host, out_cmd, timeout=args.timeout)
    print_section("总控 out.log 尾部", decode_output(out_res.stdout) or decode_output(out_res.stderr))

    # 6) err log
    err_cmd = (
        "powershell -NoProfile -Command \""
        f"if (Test-Path '{DEFAULT_ERR_LOG}') {{ Get-Item '{DEFAULT_ERR_LOG}' | Select-Object Length,LastWriteTime; Get-Content -Tail {tail} '{DEFAULT_ERR_LOG}' }} else {{ Write-Output 'ERR_LOG_NOT_FOUND' }}"
        "\""
    )
    err_res = run_ssh(args.host, err_cmd, timeout=args.timeout)
    print_section("总控 err.log 尾部", decode_output(err_res.stdout) or decode_output(err_res.stderr))

    has_error = any(res.returncode != 0 for res in [task_res, proc_res, state_res, month_res, out_res, err_res])
    if has_error:
        print("\n[check] 已完成，但部分子检查返回非 0，请结合上面输出判断。")
        return 1

    print("\n[check] 检查完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
