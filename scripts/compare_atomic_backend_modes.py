#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKET_DATA_ROOT = Path("/Users/dong/Desktop/AIGC/market-data")
DEFAULT_FORMAL_DB = DEFAULT_MARKET_DATA_ROOT / "atomic_facts" / "market_atomic_mainboard_full_reverse.db"
DEFAULT_COMPACT_DB = (
    DEFAULT_MARKET_DATA_ROOT
    / "atomic_facts"
    / "shadow"
    / "market_atomic_mainboard_compact_20250102_20260514.db"
)
URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass(frozen=True)
class CompareCheck:
    name: str
    path: str
    compare_body: bool = True
    allow_mismatch: bool = False
    allow_failure: bool = False
    timeout_seconds: int = 90


COMPARE_CHECKS = [
    CompareCheck("health", "/api/health", compare_body=False),
    CompareCheck("review_pool", "/api/review/pool?limit=20"),
    CompareCheck(
        "review_5m_2026",
        "/api/review/data?symbol=sh601138&start_date=2026-05-12&end_date=2026-05-15&granularity=5m",
    ),
    CompareCheck(
        "review_1d_2025",
        "/api/review/data?symbol=sh601138&start_date=2025-01-02&end_date=2025-01-06&granularity=1d",
    ),
    CompareCheck(
        "history_multiframe_5m",
        "/api/history/multiframe?symbol=sh601138&start_date=2026-05-12&end_date=2026-05-15&granularity=5m&include_today_preview=false",
    ),
    CompareCheck("selection_health", "/api/selection/health"),
    CompareCheck(
        "selection_candidates_stable",
        "/api/selection/candidates?strategy=stable_capital_callback&date=2026-05-15&limit=10",
    ),
    CompareCheck(
        "selection_candidates_v2",
        "/api/selection/candidates?strategy=v2&date=2026-05-15&limit=10",
        timeout_seconds=180,
    ),
    CompareCheck(
        "selection_profile_v2",
        "/api/selection/profile/sh601138?date=2026-05-15&strategy=v2",
        timeout_seconds=180,
    ),
    CompareCheck(
        "selection_multiframe",
        "/api/selection/history/multiframe?symbol=sh601138&start_date=2026-05-12&end_date=2026-05-15&granularity=5m&include_today_preview=false",
    ),
    CompareCheck(
        "selection_v2_evaluate",
        "/api/selection/v2/evaluate?start_date=2026-05-12&end_date=2026-05-15&top_n=5",
        timeout_seconds=240,
    ),
    CompareCheck(
        "selection_stable_evaluate",
        "/api/selection/stable-callback/evaluate?start_date=2026-05-12&end_date=2026-05-15&top_n=5",
        timeout_seconds=180,
    ),
    CompareCheck("selection_backtests", "/api/selection/backtests"),
    CompareCheck("selection_ppo_report", "/api/selection/ppo-backtest-report", allow_failure=True),
    CompareCheck("stock_event_feed", "/api/stock_events/feed/sh601138?limit=5"),
    CompareCheck("stock_event_coverage", "/api/stock_events/coverage/sh601138?days=365"),
    CompareCheck("market_heat_latest", "/api/market_heat/latest?date=2026-05-14"),
    CompareCheck("market_heat_history", "/api/market_heat/history?end_date=2026-05-14&days=20"),
    CompareCheck("market_heat_fine_dates", "/api/market_heat/fine_dates?end_date=2026-05-14&days=60"),
    CompareCheck(
        "market_heat_fine_dashboard",
        "/api/market_heat/fine_dashboard?end_date=2026-05-15&days=20&pool_size=8",
        allow_failure=True,
    ),
    CompareCheck("low_position_summary", "/api/market_heat/low_position_l2_samples/summary"),
    CompareCheck("low_position_list", "/api/market_heat/low_position_l2_samples?limit=10"),
    CompareCheck("trend_ideas", "/api/trend-research/ideas"),
    CompareCheck("sentiment", "/api/sentiment?symbol=sh601138", allow_failure=True),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare API outputs between formal atomic DB and compact atomic DB.")
    parser.add_argument("--formal-db", type=Path, default=DEFAULT_FORMAL_DB)
    parser.add_argument("--compact-db", type=Path, default=DEFAULT_COMPACT_DB)
    parser.add_argument("--old-port", type=int, default=8014)
    parser.add_argument("--compact-port", type=int, default=8015)
    parser.add_argument("--out", type=Path, default=Path("/tmp/market-live-terminal-db-governance-compare/report.json"))
    parser.add_argument("--keep-running", action="store_true")
    return parser.parse_args()


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_url(url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Optional[str] = None
    while time.time() < deadline:
        try:
            with URL_OPENER.open(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def start_process(cmd: List[str], env: Dict[str, str], log_path: Path) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def terminate_process(process: Optional[subprocess.Popen[str]]) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except Exception:  # noqa: BLE001
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            pass


def request_json(base_url: str, path: str, timeout: int) -> tuple[int, Any, float]:
    started = time.time()
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with URL_OPENER.open(request, timeout=timeout) as response:
            raw = response.read()
            body = json.loads(raw.decode("utf-8") or "null")
            return int(response.status), body, round((time.time() - started) * 1000, 1)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body: Any = json.loads(raw.decode("utf-8") or "null")
        except json.JSONDecodeError:
            body = raw.decode("utf-8", errors="replace")
        return int(exc.code), body, round((time.time() - started) * 1000, 1)
    except Exception as exc:  # noqa: BLE001
        return 0, {"code": 0, "message": f"{type(exc).__name__}: {exc}", "data": None}, round((time.time() - started) * 1000, 1)


def canonical_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compact_payload_preview(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__, "repr": str(payload)[:500]}
    data = payload.get("data")
    preview: Dict[str, Any] = {
        "code": payload.get("code"),
        "message": payload.get("message"),
        "data_type": type(data).__name__,
    }
    if isinstance(data, list):
        preview["data_len"] = len(data)
    elif isinstance(data, dict):
        preview["data_keys"] = sorted(str(key) for key in data.keys())[:30]
        if "items" in data and isinstance(data["items"], list):
            preview["items_len"] = len(data["items"])
        if "summary" in data:
            preview["summary"] = data["summary"]
    return preview


def compare_results(old_base: str, compact_base: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for check in COMPARE_CHECKS:
        old_status, old_payload, old_ms = request_json(old_base, check.path, check.timeout_seconds)
        compact_status, compact_payload, compact_ms = request_json(compact_base, check.path, check.timeout_seconds)
        old_hash = canonical_hash(old_payload)
        compact_hash = canonical_hash(compact_payload)
        same = old_status == compact_status and (not check.compare_body or old_hash == compact_hash)
        old_api_code = old_payload.get("code") if isinstance(old_payload, dict) else None
        compact_api_code = compact_payload.get("code") if isinstance(compact_payload, dict) else None
        both_failed_same = check.allow_failure and old_api_code == compact_api_code and old_api_code not in (None, 200)
        ok = bool(same or both_failed_same or (check.allow_mismatch and old_status == compact_status))
        result = {
            "name": check.name,
            "path": check.path,
            "ok": ok,
            "allow_failure": check.allow_failure,
            "allow_mismatch": check.allow_mismatch,
            "old_status": old_status,
            "compact_status": compact_status,
            "old_api_code": old_api_code,
            "compact_api_code": compact_api_code,
            "old_elapsed_ms": old_ms,
            "compact_elapsed_ms": compact_ms,
            "body_equal": old_hash == compact_hash,
            "old_hash": old_hash,
            "compact_hash": compact_hash,
        }
        if not ok:
            result["old_preview"] = compact_payload_preview(old_payload)
            result["compact_preview"] = compact_payload_preview(compact_payload)
        results.append(result)
    return results


def summarize(results: List[Dict[str, Any]]) -> Dict[str, int]:
    required = [item for item in results if not item.get("allow_failure") and not item.get("allow_mismatch")]
    return {
        "total": len(results),
        "required": len(required),
        "required_failed": sum(1 for item in required if not item.get("ok")),
        "allowed_failed": sum(1 for item in results if item.get("allow_failure") and not item.get("ok")),
        "mismatched": sum(1 for item in results if not item.get("body_equal")),
    }


def main() -> int:
    args = parse_args()
    if not args.formal_db.exists():
        raise FileNotFoundError(f"formal DB not found: {args.formal_db}")
    if not args.compact_db.exists():
        raise FileNotFoundError(f"compact DB not found: {args.compact_db}")
    for port in (args.old_port, args.compact_port):
        if port_is_open(port):
            raise RuntimeError(f"port already in use: {port}")

    output_dir = args.out.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    base_env = os.environ.copy()
    base_env.update(
        {
            "ENABLE_BACKGROUND_RUNTIME": "false",
            "ENABLE_CLOUD_COLLECTOR": "false",
            "SELECTION_AUTO_REFRESH_ON_READ": "false",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    old_env = {
        **base_env,
        "PORT": str(args.old_port),
        "ATOMIC_MAINBOARD_DB_PATH": str(args.formal_db),
        "ATOMIC_DB_PATH": str(args.formal_db),
        "ENABLE_ATOMIC_COMPACT_READ": "false",
        "ATOMIC_COMPACT_DB_PATH": "",
    }
    compact_env = {
        **base_env,
        "PORT": str(args.compact_port),
        "ATOMIC_MAINBOARD_DB_PATH": str(args.formal_db),
        "ATOMIC_DB_PATH": str(args.formal_db),
        "ENABLE_ATOMIC_COMPACT_READ": "1",
        "ATOMIC_COMPACT_DB_PATH": str(args.compact_db),
    }

    old_proc: Optional[subprocess.Popen[str]] = None
    compact_proc: Optional[subprocess.Popen[str]] = None
    report: Dict[str, Any] = {
        "formal_db": str(args.formal_db),
        "compact_db": str(args.compact_db),
        "old_port": args.old_port,
        "compact_port": args.compact_port,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        old_proc = start_process([sys.executable, "-m", "backend.app.main"], old_env, output_dir / "backend_old.log")
        compact_proc = start_process([sys.executable, "-m", "backend.app.main"], compact_env, output_dir / "backend_compact.log")
        wait_for_url(f"http://127.0.0.1:{args.old_port}/api/health", 60)
        wait_for_url(f"http://127.0.0.1:{args.compact_port}/api/health", 60)
        results = compare_results(f"http://127.0.0.1:{args.old_port}", f"http://127.0.0.1:{args.compact_port}")
        report["results"] = results
        report["summary"] = summarize(results)
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not args.keep_running:
            terminate_process(compact_proc)
            terminate_process(old_proc)

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report.get("summary", {}).get("required_failed", 1) else 0


if __name__ == "__main__":
    raise SystemExit(main())
