from __future__ import annotations

import argparse
import base64
import calendar
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Sequence

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scripts.run_daily_new_framework import (  # noqa: E402
    WIN_MARKET_ROOT,
    WIN_PROJECT_ROOT,
    WIN_PYTHON_EXE,
    _decode_maybe_gbk,
    _powershell_encoded,
    _sync_required_windows_scripts,
    _win_scp_path,
    resolve_windows_host,
)

DEFAULT_WIN_ATOMIC_DB = r"D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_smoke_20260401_20260515.db"
DEFAULT_WIN_SELECTION_DB = r"D:\market-live-terminal\data\selection\selection_research_windows.db"
DEFAULT_WIN_MODEL_FEATURE_DB = r"D:\market-live-terminal\data\selection\model_feature_store_smoke_20260401_20260515.db"
DEFAULT_WIN_RUN_ROOT = r"D:\market-live-terminal\.run\new_framework_month_batch"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _progress(message: str) -> None:
    print(f"[month-batch] [{_now_text()}] {message}", flush=True)


def _ssh(host: str, command: str, *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["ssh", host, command], check=False, capture_output=True, text=False)
    decoded = subprocess.CompletedProcess(
        result.args,
        result.returncode,
        _decode_maybe_gbk(result.stdout),
        _decode_maybe_gbk(result.stderr),
    )
    if check and decoded.returncode != 0:
        raise subprocess.CalledProcessError(decoded.returncode, decoded.args, output=decoded.stdout, stderr=decoded.stderr)
    return decoded


def _run(cmd: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=check, capture_output=True, text=True)


def _run_local_windows_cmd(cmd: str, *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=WIN_PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
    return result


def _run_windows_step(host: str, cmd: str, *, local_windows: bool) -> subprocess.CompletedProcess:
    if local_windows:
        return _run_local_windows_cmd(cmd)
    return _ssh(host, f'cmd /c "cd /d {WIN_PROJECT_ROOT} && {cmd}"')


def _month_range_desc(start_month: str, end_month: str) -> List[str]:
    def parse_month(value: str) -> tuple[int, int]:
        text = str(value).strip()
        if len(text) != 7 or text[4] != "-":
            raise ValueError(f"非法月份: {value}")
        return int(text[:4]), int(text[5:7])

    start_y, start_m = parse_month(start_month)
    end_y, end_m = parse_month(end_month)
    start_value = start_y * 12 + start_m
    end_value = end_y * 12 + end_m
    if start_value < end_value:
        raise ValueError("start-month 必须不早于 end-month，脚本按倒序跑")

    months: List[str] = []
    y, m = start_y, start_m
    while y * 12 + m >= end_value:
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y -= 1
            m = 12
    return months


def _month_bounds(month: str) -> tuple[str, str]:
    year = int(month[:4])
    month_num = int(month[5:7])
    last_day = calendar.monthrange(year, month_num)[1]
    return f"{year:04d}-{month_num:02d}-01", f"{year:04d}-{month_num:02d}-{last_day:02d}"


def _win_slash(path: str) -> str:
    return str(path).replace("\\", "/")


def _build_atomic_config(
    *,
    month: str,
    date_from: str,
    date_to: str,
    atomic_db: str,
    selection_db: str,
    market_root: str,
    run_root: str,
    workers: int,
) -> Dict[str, Any]:
    tag = month.replace("-", "")
    run_root_slash = _win_slash(run_root)
    max_failed_items = int(os.getenv("MONTH_BATCH_MAX_FAILED_ITEMS_PER_DAY", "10") or 10)
    max_failed_ratio = float(os.getenv("MONTH_BATCH_MAX_FAILED_ITEM_RATIO_PER_DAY", "0.002") or 0.002)
    return {
        "atomic_db": _win_slash(atomic_db),
        "selection_db": _win_slash(selection_db),
        "market_root": _win_slash(market_root),
        "extract_root": "Z:/atomic_stage",
        "workers": int(workers),
        "large_threshold": 200000.0,
        "super_threshold": 1000000.0,
        "include_bj": False,
        "include_star": False,
        "include_gem": False,
        "main_board_only": True,
        "stop_on_failure": True,
        "max_failed_items_per_day": 3,
        "max_failed_item_ratio_per_day": 0.002,
        "cleanup_extracted": True,
        "prefetch_next_day_extract": True,
        "reuse_extracted_day_if_exists": False,
        "max_failed_items_per_day": max_failed_items,
        "max_failed_item_ratio_per_day": max_failed_ratio,
        "state_file": f"{run_root_slash}/{tag}/atomic_state.json",
        "report_file": f"{run_root_slash}/{tag}/atomic_report.json",
        "batches": [
            {
                "name": f"new_framework_{tag}",
                "kind": "l2",
                "date_from": date_from,
                "date_to": date_to,
            }
        ],
        "extractor": "7z",
    }


def _upload_json(host: str, payload: Dict[str, Any], local_path: Path, remote_path: str) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    remote_dir = str(PureWindowsPath(remote_path).parent).replace("/", "\\")
    _ssh(host, f'cmd /c if not exist "{remote_dir}" mkdir "{remote_dir}"', check=False)
    _run(["scp", str(local_path), f"{host}:{_win_scp_path(remote_path)}"])


def _upload_text(host: str, text: str, local_path: Path, remote_path: str) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(text, encoding="utf-8")
    remote_dir = str(PureWindowsPath(remote_path).parent).replace("/", "\\")
    _ssh(host, f'cmd /c if not exist "{remote_dir}" mkdir "{remote_dir}"', check=False)
    _run(["scp", str(local_path), f"{host}:{_win_scp_path(remote_path)}"])


def _bat_quote(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _start_background_on_windows(args: argparse.Namespace) -> Dict[str, Any]:
    host = resolve_windows_host()
    _sync_required_windows_scripts()
    tag = f"{args.start_month.replace('-', '')}_{args.end_month.replace('-', '')}"
    task_name = f"MLT_ModelFeatureStore_{tag}"
    remote_log_dir = f"{args.run_root}\\logs"
    remote_bat = f"{args.run_root}\\run_month_batch_{tag}.cmd"
    remote_status = f"{args.run_root}\\run_status_{tag}.txt"
    remote_stdout = f"{remote_log_dir}\\month_batch_{tag}.out.log"
    remote_stderr = f"{remote_log_dir}\\month_batch_{tag}.err.log"
    remote_done = f"{remote_log_dir}\\month_batch_{tag}.done.log"
    local_run_root = ROOT_DIR / ".run" / "windows_new_framework_months"
    local_bat = local_run_root / f"run_month_batch_{tag}.cmd"
    child_script = f"{WIN_PROJECT_ROOT}\\backend\\scripts\\run_windows_new_framework_months.py"
    child_cmd = " ".join(
        [
            _bat_quote(WIN_PYTHON_EXE),
            "-u",
            _bat_quote(child_script),
            "--local-windows",
            "--start-month",
            _bat_quote(args.start_month),
            "--end-month",
            _bat_quote(args.end_month),
            "--atomic-db",
            _bat_quote(args.atomic_db),
            "--selection-db",
            _bat_quote(args.selection_db),
            "--model-feature-db",
            _bat_quote(args.model_feature_db),
            "--market-root",
            _bat_quote(args.market_root),
            "--run-root",
            _bat_quote(args.run_root),
            "--workers",
            str(args.workers),
            "--validation-mode",
            args.validation_mode,
            "--json",
        ]
    )
    bat_text = "\r\n".join(
        [
            "@echo off",
            "setlocal EnableExtensions",
            "chcp 65001 >nul",
            f"cd /d {_bat_quote(WIN_PROJECT_ROOT)}",
            "set PYTHONUTF8=1",
            "set PYTHONUNBUFFERED=1",
            f"echo START %DATE% %TIME% > {_bat_quote(remote_status)}",
            f"echo phase=month_batch >> {_bat_quote(remote_status)}",
            f"{child_cmd} > {_bat_quote(remote_stdout)} 2> {_bat_quote(remote_stderr)}",
            "set RC=%ERRORLEVEL%",
            f"echo month_batch_exit=%RC% >> {_bat_quote(remote_status)}",
            f"echo %DATE% %TIME% exit_code=%RC%>> {_bat_quote(remote_done)}",
            f"echo FINISH %DATE% %TIME% >> {_bat_quote(remote_status)}",
            "exit /b %RC%",
            "",
        ]
    )
    _ssh(host, f'cmd /c if not exist "{remote_log_dir}" mkdir "{remote_log_dir}"', check=False)
    _upload_text(host, bat_text, local_bat, remote_bat)
    start_script = rf"""
$ErrorActionPreference = "Stop"
$taskName = "{task_name}"
$cmd = "{remote_bat}"
$work = "{WIN_PROJECT_ROOT}"
try {{ Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue }} catch {{}}
$action = New-ScheduledTaskAction -Execute $cmd -WorkingDirectory $work
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 24)
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "started $taskName"
"""
    _ssh(host, _powershell_encoded(start_script))
    state = {
        "status": "background_started",
        "started_at": _now_text(),
        "windows_host": host,
        "task_name": task_name,
        "months": _month_range_desc(args.start_month, args.end_month),
        "remote_bat": remote_bat,
        "remote_status": remote_status,
        "remote_stdout": remote_stdout,
        "remote_stderr": remote_stderr,
        "paths": {
            "atomic_db": args.atomic_db,
            "selection_db": args.selection_db,
            "model_feature_db": args.model_feature_db,
            "market_root": args.market_root,
            "run_root": args.run_root,
        },
    }
    _write_state(local_run_root / "latest_launch.json", state)
    return state


def _run_month(
    *,
    host: str,
    month: str,
    atomic_db: str,
    selection_db: str,
    model_feature_db: str,
    market_root: str,
    run_root: str,
    workers: int,
    mode: str,
    local_run_root: Path,
    local_windows: bool,
) -> Dict[str, Any]:
    date_from, date_to = _month_bounds(month)
    tag = month.replace("-", "")
    remote_month_dir = f"{run_root}\\{tag}"
    remote_config = f"{remote_month_dir}\\atomic_config.json"
    local_config = local_run_root / tag / "atomic_config.json"
    config = _build_atomic_config(
        month=month,
        date_from=date_from,
        date_to=date_to,
        atomic_db=atomic_db,
        selection_db=selection_db,
        market_root=market_root,
        run_root=run_root,
        workers=workers,
    )
    if local_windows:
        local_config.parent.mkdir(parents=True, exist_ok=True)
        Path(remote_month_dir).mkdir(parents=True, exist_ok=True)
        Path(remote_config).write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        _upload_json(host, config, local_config, remote_config)

    report: Dict[str, Any] = {
        "month": month,
        "date_from": date_from,
        "date_to": date_to,
        "started_at": _now_text(),
        "remote_config": remote_config,
        "atomic_db": atomic_db,
        "selection_db": selection_db,
        "model_feature_db": model_feature_db,
    }

    _progress(f"{month} atomic 开始")
    atomic_cmd = f'"{WIN_PYTHON_EXE}" backend\\scripts\\run_atomic_backfill_windows.py --config "{remote_config}"'
    atomic_result = _run_windows_step(host, atomic_cmd, local_windows=local_windows)
    report["atomic_stdout_tail"] = atomic_result.stdout[-4000:]

    _progress(f"{month} selection refresh 开始")
    selection_cmd = (
        f'set DB_PATH={WIN_PROJECT_ROOT}\\data\\market_data.db&& '
        f'set ATOMIC_MAINBOARD_DB_PATH={atomic_db}&& '
        f'set ATOMIC_DB_PATH={atomic_db}&& '
        f'set SELECTION_DB_PATH={selection_db}&& '
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\run_selection_research.py refresh '
        f"--start-date {date_from} --end-date {date_to} --skip-daily-candidates"
    )
    selection_result = _run_windows_step(host, selection_cmd, local_windows=local_windows)
    report["selection_stdout_tail"] = selection_result.stdout[-4000:]

    _progress(f"{month} model_feature_store build 开始")
    feature_cmd = (
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\build_model_feature_store.py '
        f"--start-date {date_from} --end-date {date_to} "
        f'--atomic-db "{atomic_db}" '
        f'--selection-db "{selection_db}" '
        f'--target-db "{model_feature_db}"'
    )
    feature_result = _run_windows_step(host, feature_cmd, local_windows=local_windows)
    report["feature_stdout_tail"] = feature_result.stdout[-4000:]

    validation_path = f"{remote_month_dir}\\model_feature_store_validation_{mode}.json"
    _progress(f"{month} validator {mode} 开始")
    validate_cmd = (
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\validate_model_feature_store.py '
        f'--db "{model_feature_db}" --mode {mode} --output "{validation_path}"'
    )
    validate_result = _run_windows_step(host, validate_cmd, local_windows=local_windows)
    report["validation_stdout_tail"] = validate_result.stdout[-4000:]
    report["validation_path"] = validation_path
    report["finished_at"] = _now_text()
    report["status"] = "done"
    return report


def _write_state(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_months(args: argparse.Namespace) -> Dict[str, Any]:
    months = _month_range_desc(args.start_month, args.end_month)
    local_run_root = ROOT_DIR / ".run" / "windows_new_framework_months"
    state_path = local_run_root / "latest.json"
    if args.background and not args.local_windows:
        return _start_background_on_windows(args)
    host = "local-windows" if args.local_windows else resolve_windows_host()
    state: Dict[str, Any] = {
        "status": "running",
        "started_at": _now_text(),
        "windows_host": host,
        "months": months,
        "current_month": None,
        "completed_months": [],
        "failed_months": [],
        "paths": {
            "atomic_db": args.atomic_db,
            "selection_db": args.selection_db,
            "model_feature_db": args.model_feature_db,
            "market_root": args.market_root,
            "run_root": args.run_root,
        },
    }
    _write_state(state_path, state)

    if args.dry_run:
        state["status"] = "dry_run"
        _write_state(state_path, state)
        return state

    if not args.local_windows:
        _sync_required_windows_scripts()

    for month in months:
        state["current_month"] = month
        _write_state(state_path, state)
        try:
            month_report = _run_month(
                host=host,
                month=month,
                atomic_db=args.atomic_db,
                selection_db=args.selection_db,
                model_feature_db=args.model_feature_db,
                market_root=args.market_root,
                run_root=args.run_root,
                workers=args.workers,
                mode=args.validation_mode,
                local_run_root=local_run_root,
                local_windows=args.local_windows,
            )
            report_path = local_run_root / month.replace("-", "") / "report.json"
            _write_state(report_path, month_report)
            state["completed_months"].append(month)
            state["current_month"] = None
            _write_state(state_path, state)
        except Exception as exc:
            state["status"] = "failed"
            state["failed_months"].append({"month": month, "error": str(exc)})
            _write_state(state_path, state)
            raise

    state["status"] = "done"
    state["finished_at"] = _now_text()
    state["current_month"] = None
    _write_state(state_path, state)
    return state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Windows 新框架按月倒序批跑：只落 Windows，不同步 Mac")
    parser.add_argument("--start-month", required=True, help="YYYY-MM，倒序起点，如 2026-03")
    parser.add_argument("--end-month", required=True, help="YYYY-MM，倒序终点，如 2026-01")
    parser.add_argument("--atomic-db", default=os.getenv("MONTH_BATCH_WIN_ATOMIC_DB", DEFAULT_WIN_ATOMIC_DB))
    parser.add_argument("--selection-db", default=os.getenv("MONTH_BATCH_WIN_SELECTION_DB", DEFAULT_WIN_SELECTION_DB))
    parser.add_argument("--model-feature-db", default=os.getenv("MONTH_BATCH_WIN_MODEL_FEATURE_DB", DEFAULT_WIN_MODEL_FEATURE_DB))
    parser.add_argument("--market-root", default=os.getenv("MONTH_BATCH_WIN_MARKET_ROOT", WIN_MARKET_ROOT))
    parser.add_argument("--run-root", default=os.getenv("MONTH_BATCH_WIN_RUN_ROOT", DEFAULT_WIN_RUN_ROOT))
    parser.add_argument("--workers", type=int, default=int(os.getenv("MONTH_BATCH_WORKERS", "12")))
    parser.add_argument("--validation-mode", choices=["prediction", "training"], default="training")
    parser.add_argument("--background", action="store_true", help="Mac 侧下发 Windows 后台任务后立即返回")
    parser.add_argument("--local-windows", action="store_true", help="仅供 Windows 后台任务本机执行")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_months(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _progress(
            f"完成 status={result.get('status')} completed={result.get('completed_months')} "
            f"failed={result.get('failed_months')}"
        )


if __name__ == "__main__":
    main()
