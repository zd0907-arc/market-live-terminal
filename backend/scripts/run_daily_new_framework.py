from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote
import urllib.request

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MAC_DATA_ROOT = Path("/Users/dong/Desktop/AIGC/market-data")

WIN_HOST_CANDIDATES = [
    item.strip()
    for item in os.getenv("DAILY_WIN_HOST_CANDIDATES", "laqiyuan@192.168.3.108,laqiyuan@100.115.228.56").split(",")
    if item.strip()
]
WIN_HOST = os.getenv("DAILY_WIN_HOST", "").strip()
WIN_PROJECT_ROOT = os.getenv("DAILY_WIN_PROJECT_ROOT", r"D:\market-live-terminal")
WIN_PYTHON_EXE = os.getenv("DAILY_WIN_PYTHON_EXE", r"C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe")
WIN_MARKET_ROOT = os.getenv("DAILY_WIN_MARKET_ROOT", r"D:\MarketData")
DEFAULT_WIN_ATOMIC_DB_ALIAS = r"D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_current.db"
DEFAULT_WIN_ATOMIC_DB_LEGACY = r"D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_smoke_20260401_20260515.db"
DEFAULT_WIN_SELECTION_DB = r"D:\market-live-terminal\data\selection\selection_research_windows.db"
DEFAULT_WIN_MODEL_FEATURE_DB_ALIAS = r"D:\market-live-terminal\data\selection\model_feature_store.db"
DEFAULT_WIN_MODEL_FEATURE_DB_LEGACY = r"D:\market-live-terminal\data\selection\model_feature_store_smoke_20260401_20260515.db"
WIN_ATOMIC_DB = os.getenv("DAILY_WIN_ATOMIC_DB", DEFAULT_WIN_ATOMIC_DB_ALIAS)
WIN_SELECTION_DB = os.getenv("DAILY_WIN_SELECTION_DB", DEFAULT_WIN_SELECTION_DB)
WIN_MODEL_FEATURE_DB = os.getenv("DAILY_WIN_MODEL_FEATURE_DB", DEFAULT_WIN_MODEL_FEATURE_DB_ALIAS)
WIN_MODEL_INDEX_DB = os.getenv(
    "DAILY_WIN_MODEL_INDEX_DB",
    r"D:\market-live-terminal\data\selection\model_market_index_daily.db",
)
WIN_RUN_ROOT = os.getenv("DAILY_WIN_RUN_ROOT", r"D:\market-live-terminal\.run\daily_new_framework")

LOCAL_DATA_ROOT = Path(os.getenv("LOCAL_PROCESSED_DATA_ROOT") or os.getenv("MARKET_DATA_ROOT") or str(DEFAULT_MAC_DATA_ROOT))
LOCAL_ATOMIC_DB = Path(
    os.getenv(
        "DAILY_LOCAL_ATOMIC_DB",
        str(LOCAL_DATA_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"),
    )
)
LOCAL_SELECTION_DB = Path(os.getenv("DAILY_LOCAL_SELECTION_DB", str(LOCAL_DATA_ROOT / "selection" / "selection_research.db")))
LOCAL_MODEL_FEATURE_DB = Path(os.getenv("DAILY_LOCAL_MODEL_FEATURE_DB", str(LOCAL_DATA_ROOT / "selection" / "model_feature_store.db")))


def _python_has_module(python_cmd: str, module: str) -> bool:
    if not python_cmd:
        return False
    result = subprocess.run(
        [python_cmd, "-c", f"import {module}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _python_has_modules(python_cmd: str, modules: Sequence[str]) -> bool:
    return all(_python_has_module(python_cmd, module) for module in modules)


def _resolve_local_python() -> str:
    explicit = os.getenv("DAILY_LOCAL_PYTHON", "").strip()
    if explicit:
        return explicit
    required = ("pandas", "sklearn", "joblib")
    candidates = [
        str(ROOT_DIR / ".venv" / "bin" / "python"),
        "/usr/bin/python3",
        "/opt/homebrew/bin/python3",
        shutil.which("python3") or "",
        sys.executable,
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and Path(text).exists() and _python_has_modules(text, required):
            return text
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and Path(text).exists():
            return text
    return sys.executable


LOCAL_PYTHON = _resolve_local_python()

LAN_WINDOWS_HOST = os.getenv("DAILY_WIN_LAN_HOST", "192.168.3.108")
LAN_SYNC_PORT = int(os.getenv("DAILY_LAN_SYNC_PORT", "18767"))
HTTP_SYNC_TIMEOUT = int(os.getenv("DAILY_HTTP_SYNC_TIMEOUT", "1800"))

WINDOWS_REQUIRED_SCRIPTS = [
    "backend/scripts/run_daily_new_framework.py",
    "backend/scripts/run_atomic_backfill_windows.py",
    "backend/scripts/run_selection_research.py",
    "backend/scripts/build_limit_state_from_atomic.py",
    "backend/scripts/build_model_feature_store.py",
    "backend/scripts/sync_model_market_index_daily.py",
    "backend/scripts/validate_model_feature_store.py",
    "backend/scripts/export_atomic_day_delta.py",
    "backend/scripts/export_selection_day_delta.py",
    "backend/scripts/export_model_feature_store_day_delta.py",
    "backend/scripts/postclose_http_relay.py",
    "backend/scripts/run_windows_new_framework_months.py",
    "backend/scripts/sql/model_feature_store_schema.sql",
    "backend/scripts/sql/limit_state_schema.sql",
    "backend/scripts/sql/atomic_fact_p0_schema.sql",
    "backend/scripts/sql/book_state_schema.sql",
    "backend/scripts/sql/open_auction_schema.sql",
    "backend/scripts/sql/open_auction_phase_schema.sql",
]

REQUIRED_LOCAL_VERIFY_KEYS = [
    "atomic_trade_daily",
    "atomic_order_daily",
    "atomic_book_state_daily",
    "atomic_limit_state_daily",
    "selection_feature_daily",
    "selection_signal_daily",
    "model_feature_daily_v1",
    "model_feature_intraday_shape_v1",
]

REQUIRED_SELECTION_SOURCE_IDS = [
    "spark_opportunity_selector",
    "stable_capital_callback",
    "trend_continuation_callback",
]

DEFAULT_AUTO_DETECT_LIMIT = int(os.getenv("DAILY_AUTO_DETECT_LIMIT", "20"))


def _windows_existing_path_candidates(primary: str, *fallbacks: str) -> List[str]:
    values = [str(item or "").strip() for item in (primary, *fallbacks)]
    seen = set()
    ordered: List[str] = []
    for item in values:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _resolve_windows_data_path(path_candidates: Sequence[str]) -> str:
    host = resolve_windows_host()
    probe = []
    for candidate in path_candidates:
        escaped = candidate.replace("\\", "\\\\").replace('"', '\\"')
        probe.append(
            f'if (Test-Path -LiteralPath "{escaped}") '
            f'{{ Write-Output "{escaped}"; exit 0 }}'
        )
    script = "$ErrorActionPreference='Stop'; " + " ; ".join(probe) + " ; exit 1"
    result = _ssh(host, _powershell_encoded(script), check=False)
    if result.returncode == 0:
        text = (result.stdout or "").strip().splitlines()
        if text:
            return text[-1].strip()
    return str(path_candidates[0])


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _progress(message: str) -> None:
    print(f"[daily-new] [{_now_text()}] {message}", flush=True)


def _compact_date(trade_date: str) -> str:
    text = str(trade_date or "").replace("-", "").strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"非法 trade_date: {trade_date}")
    return text


def _compact_to_iso(trade_date: str) -> str:
    text = _compact_date(trade_date)
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _run(cmd: Sequence[str], *, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=check, capture_output=True, text=text)


def _decode_maybe_gbk(data: bytes) -> str:
    if not data:
        return ""
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _ssh(host: str, remote_command: str, *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["ssh", host, remote_command], check=False, capture_output=True, text=False)
    decoded = subprocess.CompletedProcess(
        result.args,
        result.returncode,
        _decode_maybe_gbk(result.stdout),
        _decode_maybe_gbk(result.stderr),
    )
    if check and decoded.returncode != 0:
        raise subprocess.CalledProcessError(decoded.returncode, decoded.args, output=decoded.stdout, stderr=decoded.stderr)
    return decoded


def _powershell_encoded(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return f"powershell -NoProfile -EncodedCommand {encoded}"


def _powershell_single_quoted(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _run_windows_powershell(script: str, *, check: bool = True) -> subprocess.CompletedProcess:
    return _ssh(resolve_windows_host(), _powershell_encoded(script), check=check)


def _list_windows_market_package_dates(max_candidates: int = DEFAULT_AUTO_DETECT_LIMIT) -> List[str]:
    safe_limit = max(1, int(max_candidates or DEFAULT_AUTO_DETECT_LIMIT))
    root = str(PureWindowsPath(WIN_MARKET_ROOT)).replace("/", "\\")
    script = f"""
$ErrorActionPreference = 'Stop'
$root = {_powershell_single_quoted(root)}
if (-not (Test-Path -LiteralPath $root)) {{
  throw "Windows market root not found: $root"
}}
Get-ChildItem -LiteralPath $root -Recurse -File |
  Where-Object {{ ($_.Extension -in '.7z', '.zip') -and ($_.BaseName -match '^\\d{{8}}$') }} |
  Sort-Object BaseName -Descending |
  Select-Object -First {safe_limit} |
  ForEach-Object {{ $_.BaseName }}
"""
    result = _run_windows_powershell(script)
    dates: List[str] = []
    seen = set()
    for line in (result.stdout or "").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            trade_date = _compact_date(text)
        except ValueError:
            continue
        if trade_date in seen:
            continue
        seen.add(trade_date)
        dates.append(trade_date)
    return sorted(dates)


def _host_endpoint(host: str) -> str:
    return host.split("@", 1)[1] if "@" in host else host


def _tcp_reachable(host: str, port: int = 22, timeout: float = 1.5) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((_host_endpoint(host), port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _ssh_reachable(host: str) -> bool:
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "echo ok"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "ok"


def resolve_windows_host() -> str:
    global WIN_HOST
    if WIN_HOST:
        return WIN_HOST
    for candidate in WIN_HOST_CANDIDATES:
        if _ssh_reachable(candidate):
            WIN_HOST = candidate
            return candidate
    if WIN_HOST_CANDIDATES:
        WIN_HOST = WIN_HOST_CANDIDATES[0]
        return WIN_HOST
    raise RuntimeError("未配置 Windows host")


def _win_scp_path(path: str) -> str:
    return str(path).replace("\\", "/")


def _parse_json_output(stdout: str) -> Dict[str, object]:
    text = str(stdout or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        return json.loads(text[first : last + 1])
    raise ValueError(f"无法解析 JSON 输出: {text[:500]}")


def _ensure_local_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _remote_file_stat(remote_path: str) -> Tuple[int, str]:
    win_path = str(PureWindowsPath(remote_path)).replace("/", "\\")
    script = rf"""
$p = "{win_path}"
$item = Get-Item -LiteralPath $p
Write-Output "$($item.Length)|$($item.FullName)"
"""
    result = _run_windows_powershell(script)
    text = result.stdout.strip().splitlines()[-1]
    size_text, _, full_path = text.partition("|")
    return int(size_text), full_path


def _windows_relative_under_project(remote_path: str) -> str:
    remote = str(PureWindowsPath(remote_path)).replace("/", "\\")
    project = str(PureWindowsPath(WIN_PROJECT_ROOT)).replace("/", "\\").rstrip("\\")
    if not remote.lower().startswith(project.lower() + "\\"):
        raise RuntimeError(f"文件不在 Windows 项目目录下，拒绝同步: {remote_path}")
    return remote[len(project) + 1 :].replace("\\", "/")


def _http_healthcheck(base_url: str, token: str) -> None:
    last_error: Optional[Exception] = None
    for _ in range(10):
        req = urllib.request.Request(f"{base_url.rstrip('/')}/__health__", headers={"X-Relay-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if int(getattr(resp, "status", 200)) == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"HTTP relay 未就绪: {base_url}") from last_error


def _stop_windows_http_relay() -> None:
    _run_windows_powershell(
        rf"""
Get-CimInstance Win32_Process | Where-Object {{
  $_.CommandLine -like "*postclose_http_relay.py*" -and $_.CommandLine -like "*--port {LAN_SYNC_PORT}*"
}} | ForEach-Object {{ try {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }} catch {{}} }}
""",
        check=False,
    )


def _start_windows_http_relay(token: str) -> Dict[str, object]:
    _stop_windows_http_relay()
    script_path = f"{WIN_PROJECT_ROOT}\\backend\\scripts\\postclose_http_relay.py"
    proc = subprocess.Popen(
        [
            "ssh",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=6",
            resolve_windows_host(),
            f'cmd /c ""{WIN_PYTHON_EXE}" "{script_path}" --root "{WIN_PROJECT_ROOT}" --host 0.0.0.0 --port {LAN_SYNC_PORT} --token {token}"',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    base_url = f"http://{LAN_WINDOWS_HOST}:{LAN_SYNC_PORT}"
    try:
        _http_healthcheck(base_url, token)
    except Exception:
        proc.terminate()
        raise
    return {"mode": "LAN_HTTP", "token": token, "base_url": base_url, "process": proc}


def _cleanup_sync_context(sync_context: Optional[Dict[str, object]]) -> None:
    if not sync_context:
        return
    proc = sync_context.get("process")
    if proc is not None:
        try:
            proc.terminate()
            proc.communicate(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    _stop_windows_http_relay()


def _download_windows_file(remote_path: str, local_path: Path, sync_context: Dict[str, object]) -> Dict[str, object]:
    remote_size, resolved_remote = _remote_file_stat(remote_path)
    _ensure_local_parent(local_path)
    tmp_path = local_path.with_name(f"{local_path.name}.part")
    tmp_path.unlink(missing_ok=True)
    if sync_context.get("mode") == "LAN_HTTP":
        rel_path = quote(_windows_relative_under_project(resolved_remote))
        url = f"{sync_context['base_url'].rstrip('/')}/{rel_path}"
        req = urllib.request.Request(url, headers={"X-Relay-Token": str(sync_context["token"])})
        with urllib.request.urlopen(req, timeout=HTTP_SYNC_TIMEOUT) as resp, open(tmp_path, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    else:
        _run(["scp", f"{resolve_windows_host()}:{_win_scp_path(resolved_remote)}", str(tmp_path)])
    if tmp_path.stat().st_size != remote_size:
        raise RuntimeError(f"download size mismatch: {remote_path}")
    if local_path.exists():
        local_path.unlink()
    tmp_path.replace(local_path)
    return {"remote": resolved_remote, "local": str(local_path), "bytes": remote_size, "mode": sync_context.get("mode")}


def _sync_required_windows_scripts() -> None:
    host = resolve_windows_host()
    for rel_path in WINDOWS_REQUIRED_SCRIPTS:
        local_path = ROOT_DIR / rel_path
        if not local_path.exists():
            continue
        remote_path = f"{WIN_PROJECT_ROOT}/{rel_path.replace(os.sep, '/')}"
        remote_dir = str(PureWindowsPath(str(Path(remote_path).parent))).replace("/", "\\")
        _ssh(host, f'cmd /c if not exist "{remote_dir}" mkdir "{remote_dir}"', check=False)
        _run(["scp", str(local_path), f"{host}:{_win_scp_path(remote_path)}"])


def _write_atomic_config(trade_date: str, local_run_root: Path, *, win_atomic_db: str, win_selection_db: str) -> str:
    iso_date = _compact_to_iso(trade_date)
    run_name = f"daily_new_{trade_date}"
    win_run_py = WIN_RUN_ROOT.replace("\\", "/")
    config = {
        "atomic_db": win_atomic_db.replace("\\", "/"),
        "selection_db": win_selection_db.replace("\\", "/"),
        "market_root": WIN_MARKET_ROOT.replace("\\", "/"),
        "extract_root": "Z:/atomic_stage",
        "workers": 12,
        "large_threshold": 200000.0,
        "super_threshold": 1000000.0,
        "include_bj": False,
        "include_star": False,
        "include_gem": False,
        "main_board_only": True,
        "stop_on_failure": True,
        "cleanup_extracted": True,
        "prefetch_next_day_extract": False,
        "reuse_extracted_day_if_exists": False,
        "state_file": f"{win_run_py}/{trade_date}/atomic_state.json",
        "report_file": f"{win_run_py}/{trade_date}/atomic_report.json",
        "batches": [{"name": run_name, "kind": "l2", "date_from": iso_date, "date_to": iso_date}],
        "extractor": "tar",
    }
    local_config = local_run_root / "atomic_config.json"
    local_config.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    remote_dir = f"{WIN_RUN_ROOT}\\{trade_date}"
    remote_config = f"{WIN_RUN_ROOT}\\{trade_date}\\atomic_config.json"
    host = resolve_windows_host()
    _ssh(host, f'cmd /c if not exist "{remote_dir}" mkdir "{remote_dir}"', check=False)
    _run(["scp", str(local_config), f"{host}:{_win_scp_path(remote_config)}"])
    return remote_config


def _run_windows_cmd(cmd: str) -> Dict[str, object]:
    result = _ssh(resolve_windows_host(), f'cmd /c "cd /d {WIN_PROJECT_ROOT} && {cmd}"')
    return _parse_json_output(result.stdout)


def _run_windows_pipeline(
    trade_date: str,
    local_run_root: Path,
    *,
    win_atomic_db: str,
    win_selection_db: str,
    win_model_feature_db: str,
) -> Dict[str, object]:
    iso_date = _compact_to_iso(trade_date)
    remote_config = _write_atomic_config(
        trade_date,
        local_run_root,
        win_atomic_db=win_atomic_db,
        win_selection_db=win_selection_db,
    )
    remote_run_dir = f"{WIN_RUN_ROOT}\\{trade_date}"
    _progress(f"[{trade_date}] Windows atomic 开始")
    atomic_report = _run_windows_cmd(f'"{WIN_PYTHON_EXE}" backend\\scripts\\run_atomic_backfill_windows.py --config "{remote_config}"')

    _progress(f"[{trade_date}] Windows selection refresh 开始")
    selection_cmd = (
        f'set DB_PATH={WIN_PROJECT_ROOT}\\data\\market_data.db&& '
        f'set ATOMIC_MAINBOARD_DB_PATH={win_atomic_db}&& '
        f'set ATOMIC_DB_PATH={win_atomic_db}&& '
        f'set SELECTION_DB_PATH={win_selection_db}&& '
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\run_selection_research.py refresh '
        f"--start-date {iso_date} --end-date {iso_date} --skip-daily-candidates"
    )
    selection_report = _run_windows_cmd(selection_cmd)

    _progress(f"[{trade_date}] Windows model_feature_store build 开始")
    feature_cmd = (
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\build_model_feature_store.py '
        f"--date {iso_date} "
        f'--atomic-db "{win_atomic_db}" '
        f'--selection-db "{win_selection_db}" '
        f'--target-db "{win_model_feature_db}" '
        f"--skip-labels"
    )
    feature_report = _run_windows_cmd(feature_cmd)

    _progress(f"[{trade_date}] Windows 导出三类 day delta")
    atomic_delta = f"{remote_run_dir}\\atomic_day_delta_{trade_date}.db"
    selection_delta = f"{remote_run_dir}\\selection_day_delta_{trade_date}.db"
    feature_delta = f"{remote_run_dir}\\model_feature_store_day_delta_{trade_date}.db"
    atomic_export = _run_windows_cmd(
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\export_atomic_day_delta.py {trade_date} '
        f'--source-db "{win_atomic_db}" --output-db "{atomic_delta}"'
    )
    selection_export = _run_windows_cmd(
        f'set SELECTION_DB_PATH={win_selection_db}&& "{WIN_PYTHON_EXE}" '
        f'backend\\scripts\\export_selection_day_delta.py {trade_date} '
        f'--source-db "{win_selection_db}" --output-db "{selection_delta}"'
    )
    feature_export = _run_windows_cmd(
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\export_model_feature_store_day_delta.py {trade_date} '
        f'--source-db "{win_model_feature_db}" --output-db "{feature_delta}"'
    )

    return {
        "atomic_report": atomic_report,
        "selection_report": selection_report,
        "feature_report": feature_report,
        "exports": {
            "atomic": atomic_export,
            "selection": selection_export,
            "model_feature_store": feature_export,
        },
        "remote_deltas": {
            "atomic": atomic_delta,
            "selection": selection_delta,
            "model_feature_store": feature_delta,
        },
    }


def _merge_local_deltas(trade_date: str, local_paths: Dict[str, str]) -> Dict[str, object]:
    _progress(f"[{trade_date}] Mac 合并 atomic/selection/model_feature_store delta")
    atomic_merge = _run(
        [
            LOCAL_PYTHON,
            str(ROOT_DIR / "backend" / "scripts" / "merge_atomic_day_delta.py"),
            trade_date,
            "--delta-db",
            local_paths["atomic"],
            "--target-db",
            str(LOCAL_ATOMIC_DB),
        ]
    )
    selection_merge = _run(
        [
            LOCAL_PYTHON,
            str(ROOT_DIR / "backend" / "scripts" / "merge_selection_day_delta.py"),
            trade_date,
            "--delta-db",
            local_paths["selection"],
            "--target-db",
            str(LOCAL_SELECTION_DB),
        ]
    )
    feature_merge = _run(
        [
            LOCAL_PYTHON,
            str(ROOT_DIR / "backend" / "scripts" / "merge_model_feature_store_day_delta.py"),
            trade_date,
            "--delta-db",
            local_paths["model_feature_store"],
            "--target-db",
            str(LOCAL_MODEL_FEATURE_DB),
        ]
    )
    return {
        "atomic": _parse_json_output(atomic_merge.stdout),
        "selection": _parse_json_output(selection_merge.stdout),
        "model_feature_store": _parse_json_output(feature_merge.stdout),
    }


def _run_local_daily_candidates(trade_date: str) -> Dict[str, object]:
    iso_date = _compact_to_iso(trade_date)
    env = os.environ.copy()
    env["SELECTION_DB_PATH"] = str(LOCAL_SELECTION_DB)
    env["ATOMIC_MAINBOARD_DB_PATH"] = str(LOCAL_ATOMIC_DB)
    env["ATOMIC_DB_PATH"] = str(LOCAL_ATOMIC_DB)
    env["ATOMIC_COMPACT_DB_PATH"] = str(LOCAL_ATOMIC_DB)
    env["ENABLE_ATOMIC_COMPACT_READ"] = "true"
    result = subprocess.run(
        [
            LOCAL_PYTHON,
            str(ROOT_DIR / "backend" / "scripts" / "run_daily_model_signals.py"),
            "--date",
            iso_date,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    payload: Dict[str, object] = {"return_code": result.returncode}
    if result.stdout.strip():
        try:
            payload["report"] = _parse_json_output(result.stdout)
        except Exception:
            payload["stdout"] = result.stdout[-2000:]
    if result.stderr.strip():
        payload["stderr"] = result.stderr[-2000:]
    return payload


def _query_count(db_path: Path, table: str, date_col: str, trade_date: str) -> int:
    if not db_path.exists():
        return 0
    iso_date = _compact_to_iso(trade_date)
    try:
        with sqlite3.connect(db_path) as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {date_col}=?", (iso_date,)).fetchone()[0] or 0)
    except sqlite3.Error:
        return 0


def _verify_local(trade_date: str) -> Dict[str, object]:
    return {
        "atomic_trade_daily": _query_count(LOCAL_ATOMIC_DB, "atomic_trade_daily", "trade_date", trade_date),
        "atomic_order_daily": _query_count(LOCAL_ATOMIC_DB, "atomic_order_daily", "trade_date", trade_date),
        "atomic_book_state_daily": _query_count(LOCAL_ATOMIC_DB, "atomic_book_state_daily", "trade_date", trade_date),
        "atomic_limit_state_daily": _query_count(LOCAL_ATOMIC_DB, "atomic_limit_state_daily", "trade_date", trade_date),
        "selection_feature_daily": _query_count(LOCAL_SELECTION_DB, "selection_feature_daily", "trade_date", trade_date),
        "selection_signal_daily": _query_count(LOCAL_SELECTION_DB, "selection_signal_daily", "trade_date", trade_date),
        "model_feature_daily_v1": _query_count(LOCAL_MODEL_FEATURE_DB, "model_feature_daily_v1", "trade_date", trade_date),
        "model_feature_intraday_shape_v1": _query_count(LOCAL_MODEL_FEATURE_DB, "model_feature_intraday_shape_v1", "trade_date", trade_date),
    }


def _verify_selection_strategy_runs(trade_date: str) -> Dict[str, object]:
    if not LOCAL_SELECTION_DB.exists():
        return {
            "required_source_ids": REQUIRED_SELECTION_SOURCE_IDS,
            "successful_source_ids": [],
            "missing_source_ids": REQUIRED_SELECTION_SOURCE_IDS,
            "total_candidate_count": 0,
        }
    iso_date = _compact_to_iso(trade_date)
    placeholders = ",".join("?" for _ in REQUIRED_SELECTION_SOURCE_IDS)
    with sqlite3.connect(LOCAL_SELECTION_DB) as conn:
        try:
            rows = conn.execute(
                f"""
                SELECT source_id, MAX(finished_at) AS last_finished_at, SUM(candidate_count) AS candidate_count
                FROM selection_strategy_runs
                WHERE trade_date=?
                  AND run_status='success'
                  AND source_id IN ({placeholders})
                GROUP BY source_id
                """,
                [iso_date, *REQUIRED_SELECTION_SOURCE_IDS],
            ).fetchall()
        except sqlite3.Error:
            rows = []
    successful_source_ids = sorted(str(row[0]) for row in rows)
    successful = set(successful_source_ids)
    candidate_counts = {str(row[0]): int(row[2] or 0) for row in rows}
    missing_source_ids = [source_id for source_id in REQUIRED_SELECTION_SOURCE_IDS if source_id not in successful]
    return {
        "required_source_ids": REQUIRED_SELECTION_SOURCE_IDS,
        "successful_source_ids": successful_source_ids,
        "missing_source_ids": missing_source_ids,
        "candidate_counts": candidate_counts,
        "total_candidate_count": sum(candidate_counts.values()),
    }


def _verify_full_local(trade_date: str) -> Dict[str, object]:
    verify = _verify_local(trade_date)
    verify["selection_strategy_runs"] = _verify_selection_strategy_runs(trade_date)
    return verify


def _is_local_complete(verify: Dict[str, object]) -> bool:
    strategy_runs = verify.get("selection_strategy_runs") if isinstance(verify, dict) else None
    return (
        all(int((verify or {}).get(key) or 0) > 0 for key in REQUIRED_LOCAL_VERIFY_KEYS)
        and isinstance(strategy_runs, dict)
        and not strategy_runs.get("missing_source_ids")
    )


def resolve_auto_trade_dates(max_candidates: int = DEFAULT_AUTO_DETECT_LIMIT) -> Dict[str, object]:
    package_dates = _list_windows_market_package_dates(max_candidates)
    if not package_dates:
        return {
            "status": "no_package_dates",
            "package_dates": [],
            "missing_dates": [],
            "latest_complete_date": None,
        }

    checks: List[Dict[str, object]] = []
    latest_complete_date: Optional[str] = None
    for trade_date in package_dates:
        verify = _verify_full_local(trade_date)
        complete = _is_local_complete(verify)
        checks.append({"trade_date": trade_date, "complete": complete, "local_verify": verify})
        if complete:
            latest_complete_date = trade_date if latest_complete_date is None else max(latest_complete_date, trade_date)

    missing_dates = [str(item["trade_date"]) for item in checks if not item["complete"]]
    selected_dates = [
        trade_date
        for trade_date in missing_dates
        if latest_complete_date is None or trade_date > latest_complete_date
    ]
    historical_missing_dates = [
        trade_date
        for trade_date in missing_dates
        if latest_complete_date is not None and trade_date <= latest_complete_date
    ]

    return {
        "status": "missing" if selected_dates else "complete",
        "package_dates": package_dates,
        "missing_dates": missing_dates,
        "selected_dates": sorted(selected_dates),
        "historical_missing_dates": sorted(historical_missing_dates),
        "latest_package_date": max(package_dates),
        "latest_complete_date": latest_complete_date,
        "checks": checks,
    }


def _write_report(trade_date: str, report: Dict[str, object]) -> None:
    run_root = ROOT_DIR / ".run" / "daily_new_framework" / trade_date
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = ROOT_DIR / ".run" / "daily_new_framework" / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def run_daily(trade_date: str, *, dry_run: bool = False, skip_candidates: bool = False) -> Dict[str, object]:
    trade_date = _compact_date(trade_date)
    local_run_root = ROOT_DIR / ".run" / "daily_new_framework" / trade_date
    local_run_root.mkdir(parents=True, exist_ok=True)
    if dry_run:
        host = WIN_HOST or (WIN_HOST_CANDIDATES[0] if WIN_HOST_CANDIDATES else "")
        win_atomic_db = WIN_ATOMIC_DB
        win_selection_db = WIN_SELECTION_DB
        win_model_feature_db = WIN_MODEL_FEATURE_DB
    else:
        host = resolve_windows_host()
        win_atomic_db = _resolve_windows_data_path(
            _windows_existing_path_candidates(WIN_ATOMIC_DB, DEFAULT_WIN_ATOMIC_DB_ALIAS, DEFAULT_WIN_ATOMIC_DB_LEGACY)
        )
        win_selection_db = _resolve_windows_data_path(
            _windows_existing_path_candidates(WIN_SELECTION_DB, DEFAULT_WIN_SELECTION_DB)
        )
        win_model_feature_db = _resolve_windows_data_path(
            _windows_existing_path_candidates(
                WIN_MODEL_FEATURE_DB,
                DEFAULT_WIN_MODEL_FEATURE_DB_ALIAS,
                DEFAULT_WIN_MODEL_FEATURE_DB_LEGACY,
            )
        )
    report: Dict[str, object] = {
        "trade_date": trade_date,
        "generated_at": _now_text(),
        "windows_host": host,
        "windows_paths": {
            "atomic_db": win_atomic_db,
            "selection_db": win_selection_db,
            "model_feature_db": win_model_feature_db,
            "market_root": WIN_MARKET_ROOT,
        },
        "local_paths": {
            "atomic_db": str(LOCAL_ATOMIC_DB),
            "selection_db": str(LOCAL_SELECTION_DB),
            "model_feature_db": str(LOCAL_MODEL_FEATURE_DB),
            "python": LOCAL_PYTHON,
        },
    }
    if dry_run:
        report["status"] = "dry_run"
        _write_report(trade_date, report)
        return report

    _sync_required_windows_scripts()
    sync_context: Optional[Dict[str, object]] = None
    try:
        windows_report = _run_windows_pipeline(
            trade_date,
            local_run_root,
            win_atomic_db=win_atomic_db,
            win_selection_db=win_selection_db,
            win_model_feature_db=win_model_feature_db,
        )
        report["windows"] = windows_report
        token = base64.urlsafe_b64encode(os.urandom(18)).decode("ascii").rstrip("=")
        if _tcp_reachable(LAN_WINDOWS_HOST, 22, 1.0):
            try:
                sync_context = _start_windows_http_relay(token)
            except Exception as exc:
                _progress(f"[{trade_date}] LAN HTTP 不可用，回退 LAN SCP: {exc}")
                sync_context = {"mode": "LAN_SCP"}
        else:
            sync_context = {"mode": "LAN_SCP"}
        report["sync_context"] = {k: v for k, v in sync_context.items() if k not in {"token", "process"}}
        local_delta_root = local_run_root / "processed"
        local_deltas: Dict[str, str] = {}
        sync_results: Dict[str, object] = {}
        for key, remote_path in (windows_report.get("remote_deltas") or {}).items():
            local_path = local_delta_root / PureWindowsPath(str(remote_path)).name
            sync_results[key] = _download_windows_file(str(remote_path), local_path, sync_context)
            local_deltas[key] = str(local_path)
        report["sync_results"] = sync_results
        report["local_deltas"] = local_deltas
        report["local_merges"] = _merge_local_deltas(trade_date, local_deltas)
        if not skip_candidates:
            report["local_daily_candidates"] = _run_local_daily_candidates(trade_date)
        report["local_verify"] = _verify_full_local(trade_date)
        ok = _is_local_complete(report["local_verify"] or {})
        report["status"] = "pass" if ok else "fail"
    except Exception as exc:
        report["status"] = "fail"
        report["error"] = str(exc)
        raise
    finally:
        _cleanup_sync_context(sync_context)
        _write_report(trade_date, report)
    return report


def run_auto_daily(
    *,
    dry_run: bool = False,
    skip_candidates: bool = False,
    max_candidates: int = DEFAULT_AUTO_DETECT_LIMIT,
) -> Dict[str, object]:
    auto_detect = resolve_auto_trade_dates(max_candidates)
    selected_dates = list(auto_detect.get("selected_dates") or [])
    if not selected_dates:
        message = (
            "Windows 未检测到可用日包"
            if auto_detect.get("status") == "no_package_dates"
            else "Windows 已有日包在 Mac 本地都已完整，无需补跑"
        )
        report: Dict[str, object] = {
            "status": "noop",
            "generated_at": _now_text(),
            "auto_detect": auto_detect,
            "message": message,
        }
        _write_report("auto", report)
        return report

    reports: List[Dict[str, object]] = []
    for trade_date in selected_dates:
        _progress(f"自动检测到未完整日期: {trade_date}")
        report = run_daily(trade_date, dry_run=dry_run, skip_candidates=skip_candidates)
        report["auto_detect"] = {
            "status": auto_detect.get("status"),
            "selected_dates": selected_dates,
            "package_dates": auto_detect.get("package_dates"),
        }
        reports.append(report)
        if report.get("status") not in {"pass", "dry_run"}:
            break

    if len(reports) == 1:
        return reports[0]
    if dry_run and all(item.get("status") == "dry_run" for item in reports):
        combined_status = "dry_run"
    else:
        combined_status = "pass" if all(item.get("status") == "pass" for item in reports) else "fail"
    combined: Dict[str, object] = {
        "status": combined_status,
        "generated_at": _now_text(),
        "auto_detect": auto_detect,
        "reports": reports,
    }
    _write_report("auto", combined)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description="新框架每日盘后跑数：Windows 跑，Mac 拉当天 delta 合并")
    parser.add_argument("--date", help="YYYYMMDD or YYYY-MM-DD；不传则自动检测 Windows 有包但 Mac 未完整的日期")
    parser.add_argument("--auto-detect-limit", type=int, default=DEFAULT_AUTO_DETECT_LIMIT, help="自动检测时最多检查最近多少个 Windows 日包")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-candidates", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.date:
            report = run_daily(args.date, dry_run=args.dry_run, skip_candidates=args.skip_candidates)
        else:
            report = run_auto_daily(
                dry_run=args.dry_run,
                skip_candidates=args.skip_candidates,
                max_candidates=args.auto_detect_limit,
            )
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "fail", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        verify = report.get("local_verify") or {}
        _progress(
            f"完成 status={report.get('status')} date={report.get('trade_date')} "
            f"atomic={verify.get('atomic_trade_daily')} selection={verify.get('selection_feature_daily')} "
            f"feature={verify.get('model_feature_daily_v1')}"
        )


if __name__ == "__main__":
    main()
