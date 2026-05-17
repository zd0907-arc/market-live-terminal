#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKET_DATA_ROOT = Path("/Users/dong/Desktop/AIGC/market-data")
DEFAULT_COMPACT_DB = (
    DEFAULT_MARKET_DATA_ROOT
    / "atomic_facts"
    / "shadow"
    / "market_atomic_mainboard_compact_20250102_20260514.db"
)
DEFAULT_API_TIMEOUT_SECONDS = 45
URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass(frozen=True)
class ApiCheck:
    name: str
    path: str
    expect_code: int = 200
    expect_api_code: Optional[int] = 200
    required_data_keys: tuple[str, ...] = ()
    allow_failure: bool = False
    timeout_seconds: int = DEFAULT_API_TIMEOUT_SECONDS


@dataclass(frozen=True)
class PageCheck:
    name: str
    path: str
    allow_console_error: bool = True
    timeout_seconds: int = 120


API_CHECKS = [
    ApiCheck("health", "/api/health", expect_api_code=None),
    ApiCheck("watchlist", "/api/watchlist", expect_api_code=None),
    ApiCheck("review_pool", "/api/review/pool?limit=20", required_data_keys=("items",)),
    ApiCheck(
        "review_5m_2026",
        "/api/review/data?symbol=sh601138&start_date=2026-05-12&end_date=2026-05-15&granularity=5m",
    ),
    ApiCheck(
        "review_1d_2025",
        "/api/review/data?symbol=sh601138&start_date=2025-01-02&end_date=2025-01-06&granularity=1d",
    ),
    ApiCheck(
        "history_multiframe_5m",
        "/api/history/multiframe?symbol=sh601138&start_date=2026-05-12&end_date=2026-05-15&granularity=5m&include_today_preview=false",
        required_data_keys=("items",),
    ),
    ApiCheck("selection_health", "/api/selection/health"),
    ApiCheck(
        "selection_candidates_stable",
        "/api/selection/candidates?strategy=stable_capital_callback&date=2026-05-15&limit=10",
    ),
    ApiCheck(
        "selection_candidates_v2",
        "/api/selection/candidates?strategy=v2&date=2026-05-15&limit=10",
    ),
    ApiCheck(
        "selection_profile_v2",
        "/api/selection/profile/sh601138?date=2026-05-15&strategy=v2",
    ),
    ApiCheck(
        "selection_multiframe",
        "/api/selection/history/multiframe?symbol=sh601138&start_date=2026-05-12&end_date=2026-05-15&granularity=5m&include_today_preview=false",
        required_data_keys=("items",),
    ),
    ApiCheck(
        "selection_v2_evaluate",
        "/api/selection/v2/evaluate?start_date=2026-05-12&end_date=2026-05-15&top_n=5",
        timeout_seconds=180,
    ),
    ApiCheck(
        "selection_stable_evaluate",
        "/api/selection/stable-callback/evaluate?start_date=2026-05-12&end_date=2026-05-15&top_n=5",
        timeout_seconds=120,
    ),
    ApiCheck("selection_backtests", "/api/selection/backtests", required_data_keys=("items",)),
    ApiCheck("selection_ppo_report", "/api/selection/ppo-backtest-report", allow_failure=True),
    ApiCheck("stock_event_feed", "/api/stock_events/feed/sh601138?limit=5"),
    ApiCheck("stock_event_coverage", "/api/stock_events/coverage/sh601138?days=365"),
    ApiCheck("market_heat_latest", "/api/market_heat/latest?date=2026-05-14"),
    ApiCheck("market_heat_history", "/api/market_heat/history?end_date=2026-05-14&days=20"),
    ApiCheck("market_heat_fine_dates", "/api/market_heat/fine_dates?end_date=2026-05-14&days=60"),
    ApiCheck(
        "market_heat_fine_dashboard",
        "/api/market_heat/fine_dashboard?end_date=2026-05-15&days=20&pool_size=8",
        allow_failure=True,
    ),
    ApiCheck("low_position_summary", "/api/market_heat/low_position_l2_samples/summary"),
    ApiCheck("low_position_list", "/api/market_heat/low_position_l2_samples?limit=10"),
    ApiCheck("trend_ideas", "/api/trend-research/ideas"),
    ApiCheck("sentiment", "/api/sentiment?symbol=sh601138", allow_failure=True),
]


PAGE_CHECKS = [
    PageCheck("home", "/?symbol=sh601138"),
    PageCheck("review", "/review?symbol=sh601138"),
    PageCheck("selection_research", "/selection-research"),
    PageCheck("selection_ppo_report", "/selection-ppo-report"),
    PageCheck("selection_opportunity_review", "/selection-opportunity-review"),
    PageCheck("market_heat", "/market-heat"),
    PageCheck("market_heat_low_position_samples", "/market-heat/low-position-samples"),
    PageCheck("trend_research", "/trend-research"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test local research station against compact atomic DB.")
    parser.add_argument("--compact-db", type=Path, default=DEFAULT_COMPACT_DB)
    parser.add_argument("--backend-port", type=int, default=8012)
    parser.add_argument("--frontend-port", type=int, default=3012)
    parser.add_argument("--out", type=Path, default=Path("/tmp/market-live-terminal-compact-smoke/report.json"))
    parser.add_argument("--screenshots-dir", type=Path, default=Path("/tmp/market-live-terminal-compact-smoke/screenshots"))
    parser.add_argument("--skip-pages", action="store_true")
    parser.add_argument("--skip-apis", action="store_true")
    parser.add_argument("--keep-running", action="store_true")
    return parser.parse_args()


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


def request_json(base_url: str, path: str, timeout: int = DEFAULT_API_TIMEOUT_SECONDS) -> tuple[int, Any]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with URL_OPENER.open(request, timeout=timeout) as response:
            raw = response.read()
            return int(response.status), json.loads(raw.decode("utf-8") or "null")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body: Any = json.loads(raw.decode("utf-8") or "null")
        except json.JSONDecodeError:
            body = raw.decode("utf-8", errors="replace")
        return int(exc.code), body
    except Exception as exc:  # noqa: BLE001
        return 0, {"code": 0, "message": f"{type(exc).__name__}: {exc}", "data": None}


def has_data_keys(payload: Any, keys: Iterable[str]) -> bool:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not keys:
        return True
    if not isinstance(data, dict):
        return False
    return all(key in data for key in keys)


def run_api_checks(base_url: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for check in API_CHECKS:
        started = time.time()
        status, payload = request_json(base_url, check.path, timeout=check.timeout_seconds)
        api_code = payload.get("code") if isinstance(payload, dict) else None
        ok = status == check.expect_code
        if check.expect_api_code is not None:
            ok = ok and api_code == check.expect_api_code
        ok = ok and has_data_keys(payload, check.required_data_keys)
        result = {
            "name": check.name,
            "path": check.path,
            "status": status,
            "api_code": api_code,
            "ok": bool(ok),
            "allow_failure": check.allow_failure,
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        }
        if not ok:
            result["message"] = payload.get("message") if isinstance(payload, dict) else str(payload)[:500]
        results.append(result)
    return results


def find_chrome() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "chromium",
    ]
    for candidate in candidates:
        if "/" not in candidate:
            return candidate
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Chrome/Chromium executable not found")


def run_page_checks(base_url: str, screenshots_dir: Path) -> List[Dict[str, Any]]:
    chrome = find_chrome()
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []
    for check in PAGE_CHECKS:
        url = urllib.parse.urljoin(base_url.rstrip("/") + "/", check.path.lstrip("/"))
        screenshot = screenshots_dir / f"{check.name}.png"
        started = time.time()
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-proxy-server",
            "--window-size=1440,1000",
            f"--screenshot={screenshot}",
            "--virtual-time-budget=8000",
            url,
        ]
        timed_out = False
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=check.timeout_seconds,
            )
            returncode: Optional[int] = completed.returncode
            stderr_tail = completed.stderr[-1000:]
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = None
            stderr_tail = str(exc)[-1000:]
        size = screenshot.stat().st_size if screenshot.exists() else 0
        ok = (returncode == 0 or timed_out) and size > 10_000
        result = {
            "name": check.name,
            "path": check.path,
            "url": url,
            "ok": bool(ok),
            "returncode": returncode,
            "timed_out": timed_out,
            "screenshot": str(screenshot),
            "screenshot_bytes": size,
            "elapsed_ms": round((time.time() - started) * 1000, 1),
            "stderr_tail": stderr_tail,
            "probe_mode": "chrome_screenshot",
        }
        if not ok:
            fallback_started = time.time()
            cdp_screenshot = screenshots_dir / f"{check.name}.cdp.png"
            cdp_port = find_free_port()
            probe_script = REPO_ROOT / "scripts" / "probe_page_cdp.mjs"
            probe_cmd = [
                "node",
                str(probe_script),
                f"--url={url}",
                f"--screenshot={cdp_screenshot}",
                f"--port={cdp_port}",
                "--timeoutMs=90000",
                "--settleMs=70000",
            ]
            try:
                probe = subprocess.run(
                    probe_cmd,
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=100,
                )
                parsed = json.loads(probe.stdout or "{}")
                if parsed.get("ok"):
                    result.update(
                        {
                            "ok": True,
                            "probe_mode": "cdp_fallback",
                            "screenshot": str(cdp_screenshot),
                            "screenshot_bytes": int(parsed.get("screenshot_bytes") or 0),
                            "body_length": parsed.get("body_length"),
                            "body_preview": parsed.get("body_preview"),
                            "error_text": parsed.get("error_text"),
                            "fallback_elapsed_ms": round((time.time() - fallback_started) * 1000, 1),
                        }
                    )
                else:
                    result["fallback_error"] = parsed or (probe.stderr[-1000:] if probe.stderr else probe.stdout[-1000:])
            except Exception as exc:  # noqa: BLE001
                result["fallback_error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results


def summarize(results: List[Dict[str, Any]]) -> Dict[str, int]:
    required = [item for item in results if not item.get("allow_failure")]
    allowed = [item for item in results if item.get("allow_failure")]
    return {
        "total": len(results),
        "required": len(required),
        "required_failed": sum(1 for item in required if not item.get("ok")),
        "allowed_failed": sum(1 for item in allowed if not item.get("ok")),
    }


def main() -> int:
    args = parse_args()
    if not args.compact_db.exists():
        raise FileNotFoundError(f"compact DB not found: {args.compact_db}")
    if port_is_open(args.backend_port):
        raise RuntimeError(f"backend port already in use: {args.backend_port}")
    if port_is_open(args.frontend_port):
        raise RuntimeError(f"frontend port already in use: {args.frontend_port}")

    output_dir = args.out.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    base_env = os.environ.copy()
    base_env.update(
        {
            "PORT": str(args.backend_port),
            "BACKEND_PORT": str(args.backend_port),
            "FRONTEND_PORT": str(args.frontend_port),
            "ENABLE_ATOMIC_COMPACT_READ": "1",
            "ATOMIC_COMPACT_DB_PATH": str(args.compact_db),
            "ENABLE_BACKGROUND_RUNTIME": "false",
            "ENABLE_CLOUD_COLLECTOR": "false",
            "SELECTION_AUTO_REFRESH_ON_READ": "false",
            "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{args.backend_port}",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )

    backend: Optional[subprocess.Popen[str]] = None
    frontend: Optional[subprocess.Popen[str]] = None
    report: Dict[str, Any] = {
        "compact_db": str(args.compact_db),
        "backend_port": args.backend_port,
        "frontend_port": args.frontend_port,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    exit_code = 0
    try:
        backend = start_process(
            [sys.executable, "-m", "backend.app.main"],
            base_env,
            output_dir / "backend.log",
        )
        wait_for_url(f"http://127.0.0.1:{args.backend_port}/api/health", 45)
        frontend = start_process(
            ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", str(args.frontend_port)],
            base_env,
            output_dir / "frontend.log",
        )
        wait_for_url(f"http://127.0.0.1:{args.frontend_port}/", 45)

        if not args.skip_apis:
            api_results = run_api_checks(f"http://127.0.0.1:{args.backend_port}")
            report["api_results"] = api_results
            report["api_summary"] = summarize(api_results)
            if report["api_summary"]["required_failed"] > 0:
                exit_code = 1

        if not args.skip_pages:
            page_results = run_page_checks(f"http://127.0.0.1:{args.frontend_port}", args.screenshots_dir)
            report["page_results"] = page_results
            report["page_summary"] = summarize(page_results)
            if report["page_summary"]["required_failed"] > 0:
                exit_code = 1
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not args.keep_running:
            terminate_process(frontend)
            terminate_process(backend)

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
