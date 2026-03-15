"""
按月份顺序把 sandbox_review_v2 固定池历史提升到生产 history L2。

设计目标：
- 从 `2026-02` 开始，逐月向前；
- 每个月完成后立即写生产库（云端即刻可用）；
- 支持 stop-file，便于后续人工中止；
- 记录 state.json / report.json，供后续继续跑或复盘。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.scripts.promote_sandbox_review_v2_month import (
    _source_root,
    export_pool_snapshot,
    promote_month,
)


def _month_list(start_month: str, end_month: str) -> List[str]:
    start = datetime.strptime(start_month + "-01", "%Y-%m-%d")
    end = datetime.strptime(end_month + "-01", "%Y-%m-%d")
    if start < end:
        raise ValueError("start_month 必须不早于 end_month")

    result: List[str] = []
    cursor = start
    while cursor >= end:
        result.append(cursor.strftime("%Y-%m"))
        if cursor.month == 1:
            cursor = datetime(cursor.year - 1, 12, 1)
        else:
            cursor = datetime(cursor.year, cursor.month - 1, 1)
    return result


def _load_state(path: Path) -> Dict[str, object]:
    if not path.is_file():
        return {
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "running",
            "completed_months": [],
            "failed_months": [],
            "current_month": None,
            "last_report": None,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "running",
            "completed_months": [],
            "failed_months": [],
            "current_month": None,
            "last_report": None,
        }


def _save_state(path: Path, state: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_rollout(
    start_month: str,
    end_month: str,
    source_root: Path,
    state_path: Path,
    report_dir: Path,
    stop_file: Path,
    snapshot_dir: Path,
) -> Dict[str, object]:
    months = _month_list(start_month, end_month)
    state = _load_state(state_path)
    completed = set(state.get("completed_months") or [])

    snapshot_path = export_pool_snapshot(source_root, snapshot_dir)
    state["snapshot_path"] = str(snapshot_path)
    _save_state(state_path, state)

    for month in months:
        if stop_file.exists():
            state["status"] = "stopped"
            state["stopped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state["current_month"] = None
            _save_state(state_path, state)
            return state

        if month in completed:
            continue

        state["current_month"] = month
        state["status"] = "running"
        _save_state(state_path, state)

        report_path = report_dir / f"{month}.json"
        try:
            report = promote_month(
                month=month,
                source_root=source_root,
                symbols=[],
                report_path=report_path,
            )
        except Exception as exc:
            failed_months = list(state.get("failed_months") or [])
            failed_months.append({"month": month, "error": str(exc)})
            state["failed_months"] = failed_months
            state["status"] = "failed"
            state["current_month"] = month
            state["last_report"] = str(report_path)
            state["failed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save_state(state_path, state)
            raise

        completed_months = list(state.get("completed_months") or [])
        completed_months.append(month)
        state["completed_months"] = completed_months
        state["last_report"] = str(report_path)
        state["current_month"] = None
        state["last_completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save_state(state_path, state)
        print(
            f"[rollout] month={month} done rows_5m={report['rows_5m_inserted']} "
            f"rows_daily={report['rows_daily_inserted']}"
        )

    state["status"] = "done"
    state["current_month"] = None
    state["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_state(state_path, state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="按月把 sandbox_review_v2 固定池历史提升到生产 history L2")
    parser.add_argument("--start-month", default="2026-02")
    parser.add_argument("--end-month", default="2025-01")
    parser.add_argument("--source-root", default="", help="sandbox_review_v2 根目录")
    parser.add_argument("--state-path", default="", help="状态文件路径")
    parser.add_argument("--report-dir", default="", help="每月 JSON 报告目录")
    parser.add_argument("--stop-file", default="", help="停止文件路径；存在则中止")
    parser.add_argument("--snapshot-dir", default="", help="固定池快照输出目录")
    args = parser.parse_args()

    source_root = _source_root(args.source_root)
    state_path = Path(args.state_path) if args.state_path else (Path(ROOT_DIR) / "data" / "l2_month_rollout" / "state.json")
    report_dir = Path(args.report_dir) if args.report_dir else (Path(ROOT_DIR) / "data" / "l2_month_rollout" / "reports")
    stop_file = Path(args.stop_file) if args.stop_file else (Path(ROOT_DIR) / "data" / "l2_month_rollout" / "STOP")
    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else (Path(ROOT_DIR) / "data" / "l2_month_rollout")

    state = run_rollout(
        start_month=args.start_month,
        end_month=args.end_month,
        source_root=source_root,
        state_path=state_path,
        report_dir=report_dir,
        stop_file=stop_file,
        snapshot_dir=snapshot_dir,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
