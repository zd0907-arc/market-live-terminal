import os
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime
import hashlib
import json
from typing import Deque, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.app.db.sandbox_review_db import get_review_5m_bars
from backend.app.db.sandbox_review_v2_db import (
    get_stock_pool,
    query_review_bars,
)
from backend.app.models.schemas import APIResponse


router = APIRouter()
SANDBOX_MIN_DATE = "2025-01-01"
SANDBOX_MAX_DATE = "2026-02-28"


class SandboxEtlRequest(BaseModel):
    mode: str = "pilot"  # pilot/full
    symbol: str = "sh603629"
    start_date: str = "2026-01-01"
    end_date: str = "2026-02-28"
    src_root: Optional[str] = None
    output_db: Optional[str] = None


_ETL_LOCK = threading.Lock()
_ETL_LOG_TAIL: Deque[str] = deque(maxlen=200)
_ETL_STATUS = {
    "running": False,
    "mode": "",
    "symbol": "",
    "start_date": "",
    "end_date": "",
    "src_root": "",
    "output_db": "",
    "started_at": "",
    "finished_at": "",
    "exit_code": None,
    "message": "",
}


def normalize_review_symbol(symbol: str) -> str:
    raw = (symbol or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8:
        return raw
    if raw.isdigit() and len(raw) == 6:
        prefix = "sh" if raw.startswith("6") else "sz"
        return f"{prefix}{raw}"
    return raw


def _validate_date(date_text: str) -> None:
    datetime.strptime(date_text, "%Y-%m-%d")


def _validate_query_window(start_date: str, end_date: str) -> Optional[APIResponse]:
    if end_date < start_date:
        return APIResponse(code=400, message="结束日期必须大于等于开始日期", data=[])
    if start_date < SANDBOX_MIN_DATE or end_date > SANDBOX_MAX_DATE:
        return APIResponse(
            code=400,
            message=(
                f"查询日期超出沙盒范围：仅支持 {SANDBOX_MIN_DATE} 至 {SANDBOX_MAX_DATE}"
            ),
            data=[],
        )
    return None


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _default_src_root() -> str:
    return os.getenv("SANDBOX_REVIEW_SRC_ROOT", r"D:\MarketData")


def _default_output_db() -> str:
    return os.getenv("SANDBOX_REVIEW_DB_PATH", os.path.join(_repo_root(), "data", "sandbox_review.db"))


def _snapshot_status():
    with _ETL_LOCK:
        return {
            **_ETL_STATUS,
            "log_tail": list(_ETL_LOG_TAIL),
        }


def _dedupe_repeated_source_days(rows: list[dict]) -> tuple[list[dict], list[tuple[str, str]]]:
    """移除“整日逐5m完全重复”的后续日期，避免页面出现循环数据。"""
    if not rows:
        return rows, []

    day_buckets: dict[str, list[dict]] = {}
    for row in rows:
        day_buckets.setdefault(row.get("source_date", ""), []).append(row)

    signature_to_day: dict[str, str] = {}
    drop_days: set[str] = set()
    duplicate_pairs: list[tuple[str, str]] = []

    for day in sorted(day_buckets.keys()):
        day_rows = sorted(day_buckets[day], key=lambda r: r.get("datetime", ""))
        normalized = []
        for row in day_rows:
            normalized.append(
                (
                    str(row.get("datetime", ""))[11:19],  # 仅保留时分秒，忽略日期
                    round(float(row.get("open", 0.0)), 6),
                    round(float(row.get("high", 0.0)), 6),
                    round(float(row.get("low", 0.0)), 6),
                    round(float(row.get("close", 0.0)), 6),
                    round(float(row.get("l1_main_buy", 0.0)), 2),
                    round(float(row.get("l1_main_sell", 0.0)), 2),
                    round(float(row.get("l1_super_buy", 0.0)), 2),
                    round(float(row.get("l1_super_sell", 0.0)), 2),
                    round(float(row.get("l2_main_buy", 0.0)), 2),
                    round(float(row.get("l2_main_sell", 0.0)), 2),
                    round(float(row.get("l2_super_buy", 0.0)), 2),
                    round(float(row.get("l2_super_sell", 0.0)), 2),
                )
            )
        signature = hashlib.md5(
            json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        existed_day = signature_to_day.get(signature)
        if existed_day:
            drop_days.add(day)
            duplicate_pairs.append((day, existed_day))
            continue
        signature_to_day[signature] = day

    if not drop_days:
        return rows, []
    filtered = [row for row in rows if row.get("source_date") not in drop_days]
    return filtered, duplicate_pairs


def _run_etl_worker(payload: SandboxEtlRequest) -> None:
    root_dir = _repo_root()
    src_root = payload.src_root or _default_src_root()
    output_db = payload.output_db or _default_output_db()

    cmd = [
        sys.executable,
        "-m",
        "backend.scripts.sandbox_review_etl",
        src_root,
        "--output-db",
        output_db,
        "--symbol",
        normalize_review_symbol(payload.symbol),
        "--start-date",
        payload.start_date,
        "--end-date",
        payload.end_date,
        "--mode",
        payload.mode,
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = root_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    with _ETL_LOCK:
        _ETL_LOG_TAIL.clear()
        _ETL_STATUS.update(
            {
                "running": True,
                "mode": payload.mode,
                "symbol": normalize_review_symbol(payload.symbol),
                "start_date": payload.start_date,
                "end_date": payload.end_date,
                "src_root": src_root,
                "output_db": output_db,
                "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": "",
                "exit_code": None,
                "message": "ETL 任务运行中",
            }
        )

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=root_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            with _ETL_LOCK:
                _ETL_LOG_TAIL.append(line.rstrip("\n"))

        code = proc.wait()
        with _ETL_LOCK:
            _ETL_STATUS["running"] = False
            _ETL_STATUS["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _ETL_STATUS["exit_code"] = code
            _ETL_STATUS["message"] = "ETL 执行完成" if code == 0 else f"ETL 执行失败（exit_code={code}）"
    except Exception as exc:
        with _ETL_LOCK:
            _ETL_STATUS["running"] = False
            _ETL_STATUS["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _ETL_STATUS["exit_code"] = -1
            _ETL_STATUS["message"] = f"ETL 执行异常: {exc}"
            _ETL_LOG_TAIL.append(_ETL_STATUS["message"])


@router.get("/review_data", response_model=APIResponse)
def get_sandbox_review_data(
    symbol: str = Query(..., description="股票代码，例如 sh603629 或 603629"),
    start_date: str = Query(..., description="开始日期，格式 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期，格式 YYYY-MM-DD"),
    granularity: str = "5m",
):
    try:
        if not isinstance(granularity, str):
            granularity = "5m"
        normalized_symbol = normalize_review_symbol(symbol)
        if not normalized_symbol.startswith(("sh", "sz", "bj")):
            return APIResponse(code=400, message="股票代码格式错误", data=[])

        _validate_date(start_date)
        _validate_date(end_date)
        win_err = _validate_query_window(start_date, end_date)
        if win_err:
            return win_err

        rows = query_review_bars(
            normalized_symbol,
            start_date,
            end_date,
            granularity=granularity,
        )
        # 过渡兼容：若 V2 未准备完成，5m 查询可回退到既有 5m 沙盒库。
        if not rows and granularity == "5m":
            rows = get_review_5m_bars(normalized_symbol, start_date, end_date)
        if not rows:
            return APIResponse(code=200, message="无数据", data=[])

        deduped_rows, duplicate_pairs = _dedupe_repeated_source_days(rows)
        if duplicate_pairs:
            desc = "；".join([f"{drop}≈{keep}" for drop, keep in duplicate_pairs])
            return APIResponse(
                code=200,
                message=f"检测到重复交易日数据并已剔除：{desc}",
                data=deduped_rows,
            )
        return APIResponse(code=200, data=deduped_rows)
    except ValueError as exc:
        return APIResponse(code=400, message=str(exc), data=[])
    except Exception as exc:
        return APIResponse(code=500, message=f"沙盒查询失败: {exc}", data=[])


@router.get("/pool", response_model=APIResponse)
def get_sandbox_stock_pool(
    keyword: str = Query("", description="关键词过滤（symbol/name）"),
    limit: int = Query(0, ge=0, le=5000, description="返回数量上限，0表示不限制"),
):
    try:
        result = get_stock_pool(keyword=keyword, limit=limit if limit > 0 else None)
        if result["total"] == 0:
            return APIResponse(code=200, message="股票池为空，请先执行 pool build", data=result)
        return APIResponse(code=200, data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"股票池查询失败: {exc}", data=None)


@router.post("/run_etl", response_model=APIResponse)
def run_sandbox_review_etl(payload: SandboxEtlRequest):
    try:
        if payload.mode not in {"pilot", "full"}:
            return APIResponse(code=400, message="mode 仅支持 pilot/full", data=None)

        symbol = normalize_review_symbol(payload.symbol)
        if not symbol.startswith(("sh", "sz", "bj")):
            return APIResponse(code=400, message="股票代码格式错误", data=None)
        payload.symbol = symbol

        _validate_date(payload.start_date)
        _validate_date(payload.end_date)
        win_err = _validate_query_window(payload.start_date, payload.end_date)
        if win_err:
            return APIResponse(code=win_err.code, message=win_err.message, data=None)

        is_running = False
        with _ETL_LOCK:
            is_running = bool(_ETL_STATUS["running"])
        if is_running:
            return APIResponse(code=409, message="已有 ETL 任务在运行，请稍后", data=_snapshot_status())

        worker = threading.Thread(target=_run_etl_worker, args=(payload,), daemon=True)
        worker.start()
        return APIResponse(code=200, message="ETL 任务已启动", data=_snapshot_status())
    except ValueError as exc:
        return APIResponse(code=400, message=str(exc), data=None)
    except Exception as exc:
        return APIResponse(code=500, message=f"启动 ETL 失败: {exc}", data=None)


@router.get("/etl_status", response_model=APIResponse)
def get_sandbox_review_etl_status():
    return APIResponse(code=200, data=_snapshot_status())
