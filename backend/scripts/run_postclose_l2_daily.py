"""
Mac 一条命令盘后 L2 日增量总控：
- 发现 Windows 已下载但云端未入正式库的交易日
- 远程 prepare 单日
- 并发 8 个 Windows worker 产出 artifact DB
- 中转 artifact 到云端并执行 merge
- 输出本地日报
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Dict, List, Optional, Sequence, Set


ROOT_DIR = Path(__file__).resolve().parents[2]

WIN_HOST = os.getenv("L2_WIN_HOST", "laqiyuan@100.115.228.56")
CLOUD_HOST = os.getenv("L2_CLOUD_HOST", "ubuntu@111.229.144.202")
WIN_MARKET_ROOT = os.getenv("L2_WIN_MARKET_ROOT", r"D:\MarketData")
WIN_STAGE_ROOT = os.getenv("L2_WIN_STAGE_ROOT", r"Z:\l2_stage")
WIN_OUTPUT_ROOT = os.getenv("L2_WIN_OUTPUT_ROOT", r"D:\market-live-terminal\.run\l2_postclose")
WIN_PREPARE_BAT = os.getenv("L2_WIN_PREPARE_BAT", r"D:\market-live-terminal\ops\win_prepare_l2_day.bat")
WIN_WORKER_BAT = os.getenv("L2_WIN_WORKER_BAT", r"D:\market-live-terminal\ops\win_run_l2_shard.bat")
CLOUD_PROJECT_ROOT = os.getenv("L2_CLOUD_PROJECT_ROOT", "~/market-live-terminal")
CLOUD_PROJECT_ROOT_ABS = os.getenv("L2_CLOUD_PROJECT_ROOT_ABS", "/home/ubuntu/market-live-terminal")
SOFT_WARNING_PATTERNS = (
    "无有效 bar：交易时段内无可用逐笔",
)
PROGRESS_ENABLED = True


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _progress(message: str) -> None:
    if PROGRESS_ENABLED:
        print(f"[postclose-l2] [{_now_text()}] {message}", flush=True)


def _run(cmd: Sequence[str], *, check: bool = True, capture_output: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=check, capture_output=capture_output, text=text)


def _decode_maybe_gbk(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _ssh(host: str, remote_command: str, *, check: bool = True) -> subprocess.CompletedProcess:
    escaped = remote_command.replace("\\", "\\\\").replace('"', '\\"')
    command = f'ssh {shlex.quote(host)} "{escaped}"'
    result = subprocess.run(["bash", "-lc", command], check=False, capture_output=True, text=False)
    decoded = subprocess.CompletedProcess(
        result.args,
        result.returncode,
        _decode_maybe_gbk(result.stdout),
        _decode_maybe_gbk(result.stderr),
    )
    if check and decoded.returncode != 0:
        raise subprocess.CalledProcessError(
            decoded.returncode,
            decoded.args,
            output=decoded.stdout,
            stderr=decoded.stderr,
        )
    return decoded


def _discover_windows_archives(market_root: str) -> List[str]:
    _progress(f"扫描 Windows 日包目录: {market_root}")
    cmd = f"cmd /c dir /b /s {market_root}\\*.7z"
    result = _ssh(WIN_HOST, cmd)
    days: Set[str] = set()
    for line in (result.stdout or "").splitlines():
        match = re.search(r"(20\d{6})\.7z$", line.strip(), re.IGNORECASE)
        if match:
            days.add(match.group(1))
    ready_days = sorted(days)
    _progress(f"发现可用日包 {len(ready_days)} 个: {','.join(ready_days[-5:]) if ready_days else '无'}")
    return ready_days


def _query_cloud_existing_dates() -> Set[str]:
    _progress("查询云端正式库已存在的 L2 交易日")
    python_code = (
        "import sqlite3; "
        "conn=sqlite3.connect('file:data/market_data.db?mode=ro&immutable=1', uri=True); "
        "cur=conn.cursor(); "
        "print('\\n'.join(r[0] for r in cur.execute(\"SELECT DISTINCT date FROM history_daily_l2 ORDER BY date\")))"
    )
    result = _ssh(CLOUD_HOST, f"cd {CLOUD_PROJECT_ROOT} && python3 -c {shlex.quote(python_code)}")
    existing: Set[str] = set()
    for line in (result.stdout or "").splitlines():
        text = line.strip()
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", text):
            existing.add(text.replace("-", ""))
    _progress(f"云端正式库已存在 {len(existing)} 个交易日")
    return existing


def _pending_days(all_days: Sequence[str], existing_cloud_days: Set[str]) -> List[str]:
    return [day for day in sorted(all_days) if day not in existing_cloud_days]


def _win_scp_path(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", text):
        return text
    return text


def _prepare_day(trade_date: str, workers: int, stable_seconds: int) -> Dict[str, object]:
    _progress(f"[{trade_date}] 开始 prepare：检查归档稳定性、解压、切 {workers} 个 shard")
    cmd = (
        f'cmd /c ""{WIN_PREPARE_BAT}" {trade_date} '
        f'--market-root "{WIN_MARKET_ROOT}" '
        f'--stage-root "{WIN_STAGE_ROOT}" '
        f'--output-root "{WIN_OUTPUT_ROOT}" '
        f'--workers {workers} --stable-seconds {stable_seconds} --json"'
    )
    result = _ssh(WIN_HOST, cmd)
    manifest = json.loads(result.stdout)
    _progress(
        f"[{trade_date}] prepare 完成：archive_size={manifest.get('archive_size')} "
        f"symbol_count={manifest.get('symbol_count')} worker_count={manifest.get('worker_count')}"
    )
    return manifest


def _worker_command(day_root: str, symbols_file: str, artifact_db: str, trade_date: str, worker: int) -> str:
    return (
        f'cmd /c ""{WIN_WORKER_BAT}" "{day_root}" '
        f'--symbols-file "{symbols_file}" '
        f'--db-path "{artifact_db}" '
        f'--mode "postclose_{trade_date}_w{worker}" --json"'
    )


def _run_workers(manifest: Dict[str, object], local_day_root: Path) -> List[Dict[str, object]]:
    shards = manifest.get("shards", [])
    day_root = str(manifest["day_root"])
    processes = []
    results: List[Dict[str, object]] = []
    worker_logs_root = local_day_root / "worker_logs"
    worker_logs_root.mkdir(parents=True, exist_ok=True)
    total_workers = len(shards)
    _progress(f"[{manifest['trade_date']}] 开始并发 worker：{total_workers} 个")

    for shard in shards:
        worker = int(shard["worker"])
        log_path = worker_logs_root / f"worker_{worker}.log"
        log_fh = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [
                "ssh",
                WIN_HOST,
                _worker_command(
                    day_root=day_root,
                    symbols_file=str(shard["symbols_file"]),
                    artifact_db=str(shard["artifact_db"]),
                    trade_date=str(manifest["trade_date"]),
                    worker=worker,
                ),
            ],
            stdout=log_fh,
            stderr=log_fh,
            text=True,
        )
        processes.append(
            {
                "worker": worker,
                "process": proc,
                "log_path": str(log_path),
                "log_fh": log_fh,
                "artifact_db": str(shard["artifact_db"]),
                "symbols_file": str(shard["symbols_file"]),
                "symbol_count": int(shard["symbol_count"]),
            }
        )

    finished = 0
    for item in processes:
        rc = item["process"].wait()
        item["log_fh"].close()
        finished += 1
        result = {
            "worker": item["worker"],
            "return_code": int(rc),
            "log_path": item["log_path"],
            "artifact_db": item["artifact_db"],
            "symbols_file": item["symbols_file"],
            "symbol_count": item["symbol_count"],
        }
        results.append(result)
        status = "成功" if int(rc) == 0 else "失败"
        _progress(
            f"[{manifest['trade_date']}] worker {item['worker']}/{total_workers} 完成："
            f"{status} rc={rc} symbol_count={item['symbol_count']} ({finished}/{total_workers})"
        )

    failed = [item for item in results if item["return_code"] != 0]
    if failed:
        raise RuntimeError(f"存在 worker 非零退出: {failed}")
    _progress(f"[{manifest['trade_date']}] 全部 worker 执行完成")
    return results


def _copy_artifacts_to_local(trade_date: str, remote_artifacts: Sequence[str], local_day_root: Path) -> List[str]:
    _progress(f"[{trade_date}] 开始从 Windows 回传 {len(remote_artifacts)} 份 artifact 到本地")
    artifacts_root = local_day_root / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    local_paths: List[str] = []
    for remote_path in remote_artifacts:
        local_name = PureWindowsPath(remote_path).name if "\\" in str(remote_path) else Path(remote_path).name
        local_path = artifacts_root / local_name
        normalized_remote = _win_scp_path(remote_path)
        _run(["scp", f"{WIN_HOST}:{normalized_remote}", str(local_path)], check=True)
        local_paths.append(str(local_path))
        _progress(f"[{trade_date}] 已回传 artifact: {local_name}")
    _progress(f"[{trade_date}] Windows artifact 已全部回传到本地")
    return local_paths


def _upload_artifacts_to_cloud(trade_date: str, local_artifacts: Sequence[str]) -> List[str]:
    _progress(f"[{trade_date}] 开始上传 {len(local_artifacts)} 份 artifact 到云端")
    cloud_tmp_dir = f"{CLOUD_PROJECT_ROOT_ABS}/.run/l2_postclose/{trade_date}"
    _ssh(CLOUD_HOST, f"mkdir -p {cloud_tmp_dir}")
    cloud_paths: List[str] = []
    for local_path in local_artifacts:
        remote_path = f"{cloud_tmp_dir}/{Path(local_path).name}"
        _run(["scp", str(local_path), f"{CLOUD_HOST}:{remote_path}"], check=True)
        cloud_paths.append(remote_path)
        _progress(f"[{trade_date}] 已上传云端 artifact: {Path(local_path).name}")
    _progress(f"[{trade_date}] artifact 已全部上传到云端")
    return cloud_paths


def _merge_on_cloud(trade_date: str, cloud_artifacts: Sequence[str]) -> Dict[str, object]:
    _progress(f"[{trade_date}] 开始云端 merge 入正式库")
    artifacts_arg = ",".join(cloud_artifacts)
    remote_cmd = (
        f"cd {CLOUD_PROJECT_ROOT} && "
        f"sudo python3 backend/scripts/merge_l2_day_delta.py {trade_date} "
        f"--artifacts {shlex.quote(artifacts_arg)} "
        f'--source-root {shlex.quote("postclose_l2_daily")} '
        f'--mode {shlex.quote("postclose_one_command")} --json'
    )
    result = _ssh(CLOUD_HOST, remote_cmd)
    merge_report = json.loads(result.stdout)
    _progress(
        f"[{trade_date}] 云端 merge 完成：status={merge_report.get('status')} "
        f"rows_daily={merge_report.get('rows_daily')} rows_5m={merge_report.get('rows_5m')} "
        f"failure_count={merge_report.get('failure_count')}"
    )
    return merge_report


def _verify_cloud_day(trade_date: str) -> Dict[str, int]:
    _progress(f"[{trade_date}] 校验云端正式库写入结果")
    trade_date_iso = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    python_code = (
        "import sqlite3, json; "
        "conn=sqlite3.connect('file:data/market_data.db?mode=ro&immutable=1', uri=True); "
        "cur=conn.cursor(); "
        f"rows_daily=cur.execute(\"SELECT COUNT(*) FROM history_daily_l2 WHERE date='{trade_date_iso}'\").fetchone()[0]; "
        f"rows_5m=cur.execute(\"SELECT COUNT(*) FROM history_5m_l2 WHERE source_date='{trade_date_iso}'\").fetchone()[0]; "
        "print(json.dumps({'rows_daily': rows_daily, 'rows_5m': rows_5m}))"
    )
    result = _ssh(CLOUD_HOST, f"cd {CLOUD_PROJECT_ROOT} && python3 -c {shlex.quote(python_code)}")
    verify_report = json.loads(result.stdout)
    _progress(
        f"[{trade_date}] verify 完成：rows_daily={verify_report.get('rows_daily')} "
        f"rows_5m={verify_report.get('rows_5m')}"
    )
    return verify_report


def _fetch_cloud_failure_summary(run_id: int) -> Dict[str, object]:
    python_code = (
        "import sqlite3, json; "
        "conn=sqlite3.connect('file:data/market_data.db?mode=ro&immutable=1', uri=True); "
        "conn.row_factory=sqlite3.Row; "
        "cur=conn.cursor(); "
        f"rows=[dict(r) for r in cur.execute(\"SELECT symbol, source_file, error_message FROM l2_daily_ingest_failures WHERE run_id={int(run_id)} ORDER BY symbol\")]; "
        "summary={}; "
        "[summary.__setitem__(r['error_message'], summary.get(r['error_message'], 0) + 1) for r in rows]; "
        "print(json.dumps({'count': len(rows), 'summary': summary, 'samples': rows[:20]}, ensure_ascii=False))"
    )
    result = _ssh(CLOUD_HOST, f"cd {CLOUD_PROJECT_ROOT} && python3 -c {shlex.quote(python_code)}")
    return json.loads(result.stdout or "{}")


def _is_soft_warning_message(message: str) -> bool:
    text = str(message or "").strip()
    return any(pattern in text for pattern in SOFT_WARNING_PATTERNS)


def _classify_day_report(report: Dict[str, object]) -> Dict[str, object]:
    worker_results = report.get("worker_results") or []
    merge_report = report.get("merge_report") or {}
    verify_report = report.get("verify_report") or {}
    skip_cloud_merge = bool(report.get("skip_cloud_merge"))

    if any(int(item.get("return_code", 1)) != 0 for item in worker_results if isinstance(item, dict)):
        return {
            "final_status": "FAIL",
            "reason": "存在 worker 非零退出",
            "warning_count": 0,
            "failure_summary": {},
            "is_production_ready": False,
        }

    if skip_cloud_merge:
        return {
            "final_status": "FAIL",
            "reason": "跳过 cloud merge，未形成生产可用结果",
            "warning_count": 0,
            "failure_summary": {},
            "is_production_ready": False,
        }

    if not merge_report:
        return {
            "final_status": "FAIL",
            "reason": "缺少 merge_report",
            "warning_count": 0,
            "failure_summary": {},
            "is_production_ready": False,
        }

    merge_status = str(merge_report.get("status") or "").strip().lower()
    rows_daily = int(merge_report.get("rows_daily") or 0)
    rows_5m = int(merge_report.get("rows_5m") or 0)
    verify_daily = int(verify_report.get("rows_daily") or 0)
    verify_5m = int(verify_report.get("rows_5m") or 0)
    failure_count = int(merge_report.get("failure_count") or 0)

    if merge_status == "failed":
        return {
            "final_status": "FAIL",
            "reason": "cloud merge 失败",
            "warning_count": failure_count,
            "failure_summary": {},
            "is_production_ready": False,
        }

    if rows_daily <= 0 or rows_5m <= 0:
        return {
            "final_status": "FAIL",
            "reason": "merge 后正式库写入结果为空",
            "warning_count": failure_count,
            "failure_summary": {},
            "is_production_ready": False,
        }

    if verify_daily != rows_daily or verify_5m != rows_5m:
        return {
            "final_status": "FAIL",
            "reason": "verify_report 与 merge_report 不一致",
            "warning_count": failure_count,
            "failure_summary": {},
            "is_production_ready": False,
        }

    if failure_count <= 0:
        return {
            "final_status": "PASS",
            "reason": "正式回补完成，且无失败样本",
            "warning_count": 0,
            "failure_summary": {},
            "is_production_ready": True,
        }

    run_id = int(merge_report.get("run_id") or 0)
    failure_report = _fetch_cloud_failure_summary(run_id) if run_id > 0 else {}
    failure_summary = failure_report.get("summary") or {}
    unique_messages = [str(key) for key in failure_summary.keys()]
    only_soft_warnings = bool(unique_messages) and all(_is_soft_warning_message(message) for message in unique_messages)

    if only_soft_warnings:
        return {
            "final_status": "PASS_WITH_WARNINGS",
            "reason": "正式回补完成，但存在仅空样本类软告警",
            "warning_count": int(failure_report.get("count") or failure_count),
            "failure_summary": failure_summary,
            "is_production_ready": True,
        }

    return {
        "final_status": "FAIL",
        "reason": "存在非空样本类硬失败",
        "warning_count": int(failure_report.get("count") or failure_count),
        "failure_summary": failure_summary,
        "is_production_ready": False,
    }


def _cleanup_remote_day(trade_date: str) -> None:
    _progress(f"[{trade_date}] 清理 Windows staging 与云端临时 artifact")
    _ssh(WIN_HOST, f'cmd /c if exist "{WIN_STAGE_ROOT}\\{trade_date}" rmdir /s /q "{WIN_STAGE_ROOT}\\{trade_date}"', check=False)
    _ssh(CLOUD_HOST, f"rm -rf {CLOUD_PROJECT_ROOT_ABS}/.run/l2_postclose/{trade_date}", check=False)


def _write_local_report(local_day_root: Path, report: Dict[str, object]) -> None:
    local_day_root.mkdir(parents=True, exist_ok=True)
    (local_day_root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = ROOT_DIR / ".run" / "postclose_l2" / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def run_day(trade_date: str, workers: int, stable_seconds: int, skip_cloud_merge: bool = False) -> Dict[str, object]:
    local_day_root = ROOT_DIR / ".run" / "postclose_l2" / trade_date
    _progress(f"[{trade_date}] ===== 开始处理 =====")
    prepared = _prepare_day(trade_date=trade_date, workers=workers, stable_seconds=stable_seconds)
    worker_results = _run_workers(prepared, local_day_root=local_day_root)
    local_artifacts = _copy_artifacts_to_local(
        trade_date=trade_date,
        remote_artifacts=[str(item["artifact_db"]) for item in worker_results],
        local_day_root=local_day_root,
    )

    merge_report: Optional[Dict[str, object]] = None
    verify_report: Optional[Dict[str, object]] = None
    cloud_artifacts: List[str] = []
    if not skip_cloud_merge:
        cloud_artifacts = _upload_artifacts_to_cloud(trade_date=trade_date, local_artifacts=local_artifacts)
        merge_report = _merge_on_cloud(trade_date=trade_date, cloud_artifacts=cloud_artifacts)
        verify_report = _verify_cloud_day(trade_date=trade_date)
        _cleanup_remote_day(trade_date)

    report = {
        "trade_date": trade_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prepared": prepared,
        "worker_results": worker_results,
        "local_artifacts": local_artifacts,
        "cloud_artifacts": cloud_artifacts,
        "merge_report": merge_report,
        "verify_report": verify_report,
        "skip_cloud_merge": skip_cloud_merge,
    }
    report["execution_summary"] = _classify_day_report(report)
    _write_local_report(local_day_root, report)
    summary = report["execution_summary"]
    _progress(
        f"[{trade_date}] ===== 结束：final_status={summary.get('final_status')} "
        f"reason={summary.get('reason')} warning_count={summary.get('warning_count')} ====="
    )
    return report


def main() -> None:
    global PROGRESS_ENABLED
    parser = argparse.ArgumentParser(description="Mac 一条命令盘后 L2 日增量总控")
    parser.add_argument("--date", default="", help="只跑指定日期 YYYYMMDD")
    parser.add_argument("--force-date", default="", help="强制重跑指定日期 YYYYMMDD")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--stable-seconds", type=int, default=30)
    parser.add_argument("--skip-cloud-merge", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    PROGRESS_ENABLED = not bool(args.json)

    if args.date and args.force_date:
        raise SystemExit("--date 与 --force-date 不能同时使用")

    ready_days = _discover_windows_archives(WIN_MARKET_ROOT)
    if not ready_days:
        raise SystemExit("Windows 未发现可处理的 .7z 日包")

    existing_cloud_days = set() if args.force_date else _query_cloud_existing_dates()

    if args.force_date:
        target_days = [str(args.force_date).replace("-", "")]
    elif args.date:
        target_days = [str(args.date).replace("-", "")]
    else:
        target_days = _pending_days(ready_days, existing_cloud_days)

    if not target_days:
        result = {
            "status": "noop",
            "ready_days": ready_days,
            "existing_cloud_days_count": len(existing_cloud_days),
            "message": "无待跑交易日",
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("[postclose-l2] 无待跑交易日")
        return

    _progress(f"本次目标交易日: {','.join(target_days)}")

    if args.dry_run:
        result = {
            "status": "dry_run",
            "ready_days": ready_days,
            "target_days": target_days,
            "existing_cloud_days_count": len(existing_cloud_days),
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"[postclose-l2] dry_run target_days={','.join(target_days)}")
        return

    day_reports = [
        run_day(
            trade_date=day,
            workers=int(args.workers),
            stable_seconds=int(args.stable_seconds),
            skip_cloud_merge=bool(args.skip_cloud_merge),
        )
        for day in target_days
    ]
    final_status = "PASS"
    if any((report.get("execution_summary") or {}).get("final_status") == "FAIL" for report in day_reports):
        final_status = "FAIL"
    elif any((report.get("execution_summary") or {}).get("final_status") == "PASS_WITH_WARNINGS" for report in day_reports):
        final_status = "PASS_WITH_WARNINGS"

    final_result = {
        "status": "done",
        "final_status": final_status,
        "target_days": target_days,
        "day_reports": day_reports,
    }
    if args.json:
        print(json.dumps(final_result, ensure_ascii=False, indent=2))
    else:
        _progress(f"全部完成：final_status={final_status} 完成交易日={','.join(target_days)}")


if __name__ == "__main__":
    main()
