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
import base64
import gzip
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Dict, List, Optional, Sequence, Set, Tuple


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MAC_DATA_ROOT = Path("/Users/dong/Desktop/AIGC/market-data")

WIN_HOST = os.getenv("L2_WIN_HOST", "")
WIN_HOST_CANDIDATES = [
    item.strip()
    for item in os.getenv("L2_WIN_HOST_CANDIDATES", "laqiyuan@192.168.3.108,laqiyuan@100.115.228.56").split(",")
    if item.strip()
]
CLOUD_HOST = os.getenv("L2_CLOUD_HOST", "ubuntu@111.229.144.202")
WIN_PROJECT_ROOT = os.getenv("L2_WIN_PROJECT_ROOT", r"D:\market-live-terminal")
WIN_PY_CMD = os.getenv("L2_WIN_PY_CMD", "py -3")
WIN_PYTHON_EXE = os.getenv(
    "L2_WIN_PYTHON_EXE",
    r"C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe",
)
WIN_MARKET_ROOT = os.getenv("L2_WIN_MARKET_ROOT", r"D:\MarketData")
WIN_STAGE_ROOT = os.getenv("L2_WIN_STAGE_ROOT", r"Z:\l2_stage")
WIN_OUTPUT_ROOT = os.getenv("L2_WIN_OUTPUT_ROOT", r"D:\market-live-terminal\.run\l2_postclose")
WIN_PREPARE_BAT = os.getenv("L2_WIN_PREPARE_BAT", r"D:\market-live-terminal\ops\win_prepare_l2_day.bat")
WIN_WORKER_BAT = os.getenv("L2_WIN_WORKER_BAT", r"D:\market-live-terminal\ops\win_run_l2_shard.bat")
WIN_MARKET_DB = os.getenv("L2_WIN_MARKET_DB", r"D:\market-live-terminal\data\market_data.db")
WIN_ATOMIC_DB = os.getenv("L2_WIN_ATOMIC_DB", r"D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_full_reverse.db")
WIN_SELECTION_DB = os.getenv("L2_WIN_SELECTION_DB", "")
CLOUD_PROJECT_ROOT = os.getenv("L2_CLOUD_PROJECT_ROOT", "~/market-live-terminal")
CLOUD_PROJECT_ROOT_ABS = os.getenv("L2_CLOUD_PROJECT_ROOT_ABS", "/home/ubuntu/market-live-terminal")
LOCAL_DATA_ROOT = Path(
    os.getenv("LOCAL_PROCESSED_DATA_ROOT")
    or os.getenv("MARKET_DATA_ROOT")
    or (str(DEFAULT_MAC_DATA_ROOT) if DEFAULT_MAC_DATA_ROOT.exists() else str(ROOT_DIR / "data"))
)
LOCAL_MARKET_DB = Path(os.getenv("LOCAL_MARKET_DB", str(LOCAL_DATA_ROOT / "market_data.db")))
LOCAL_ATOMIC_DB = Path(os.getenv("LOCAL_ATOMIC_DB", str(LOCAL_DATA_ROOT / "atomic_facts" / "market_atomic_mainboard_full_reverse.db")))
LOCAL_SELECTION_DB = Path(os.getenv("LOCAL_SELECTION_DB", str(LOCAL_DATA_ROOT / "selection" / "selection_research.db")))
LOCAL_PY_CMD = os.getenv("L2_LOCAL_PY_CMD", "").strip()
LAN_WINDOWS_HOST = os.getenv("L2_WIN_LAN_HOST", "192.168.3.108").strip()
CLOUD_PUBLIC_HTTP_HOST = os.getenv("L2_CLOUD_PUBLIC_HTTP_HOST", "111.229.144.202").strip()
LAN_SYNC_PORT = int(os.getenv("L2_LAN_SYNC_PORT", "18765"))
CLOUD_RELAY_PORT = int(os.getenv("L2_CLOUD_RELAY_PORT", "18766"))
HTTP_SYNC_TIMEOUT = int(os.getenv("L2_HTTP_SYNC_TIMEOUT", "1800"))
SYNC_ROOT_REL = ".run/postclose_sync"
SOFT_WARNING_PATTERNS = (
    "无有效 bar：交易时段内无可用逐笔",
)
PROGRESS_ENABLED = True
WINDOWS_REQUIRED_SCRIPTS = [
    "backend/scripts/export_l2_day_delta.py",
    "backend/scripts/export_atomic_day_delta.py",
    "backend/scripts/export_selection_day_delta.py",
    "backend/scripts/run_selection_research.py",
    "backend/scripts/postclose_http_relay.py",
]
CLOUD_REQUIRED_SCRIPTS = [
    "backend/scripts/postclose_http_relay.py",
]


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _progress(message: str) -> None:
    if PROGRESS_ENABLED:
        print(f"[postclose-l2] [{_now_text()}] {message}", flush=True)


def _run(cmd: Sequence[str], *, check: bool = True, capture_output: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=check, capture_output=capture_output, text=text)


def _extract_host_endpoint(host: str) -> str:
    text = str(host or "").strip()
    if not text:
        return ""
    if "@" in text:
        return text.split("@", 1)[1]
    return text


def _tcp_reachable(host: str, port: int = 22, timeout: float = 1.5) -> bool:
    endpoint = _extract_host_endpoint(host)
    if not endpoint:
        return False
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((endpoint, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _ssh_reachable(host: str, timeout: int = 5) -> bool:
    text = str(host or "").strip()
    if not text:
        return False
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={timeout}",
            text,
            "echo ok",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and (result.stdout or "").strip() == "ok"


def _resolve_windows_host() -> str:
    explicit = str(WIN_HOST or "").strip()
    if explicit:
        return explicit
    for candidate in WIN_HOST_CANDIDATES:
        if _ssh_reachable(candidate, timeout=5):
            return candidate
    return WIN_HOST_CANDIDATES[0] if WIN_HOST_CANDIDATES else "laqiyuan@100.115.228.56"


WIN_HOST = _resolve_windows_host()
if not CLOUD_PUBLIC_HTTP_HOST:
    CLOUD_PUBLIC_HTTP_HOST = _extract_host_endpoint(CLOUD_HOST)


def _decode_maybe_gbk(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


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


def _resolve_local_python() -> str:
    if LOCAL_PY_CMD:
        return LOCAL_PY_CMD
    candidates = [
        str(ROOT_DIR / ".venv" / "bin" / "python"),
        "/Users/dong/.browser-use-env/bin/python3",
        shutil.which("python3") or "",
        sys.executable,
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and Path(text).exists() and _python_has_module(text, "pandas"):
            return text
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and Path(text).exists():
            return text
    return shutil.which("python3") or sys.executable


if not LOCAL_PY_CMD:
    LOCAL_PY_CMD = _resolve_local_python()


def _ssh(host: str, remote_command: str, *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["ssh", host, remote_command], check=False, capture_output=True, text=False)
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


def _powershell_encoded(script: str) -> str:
    encoded = base64.b64encode(str(script).encode("utf-16le")).decode("ascii")
    return f"powershell -NoProfile -EncodedCommand {encoded}"


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


def _compact_to_iso(trade_date: str) -> str:
    text = str(trade_date or "").replace("-", "").strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"非法 trade_date: {trade_date}")
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


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
        candidate = text[first:last + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"无法解析 JSON 输出: {text[:500]}")


def _resolve_windows_selection_db() -> str:
    if WIN_SELECTION_DB:
        return WIN_SELECTION_DB
    preferred = f"{WIN_PROJECT_ROOT}\data\selection\selection_research_windows.db"
    fallback = f"{WIN_PROJECT_ROOT}\data\selection\selection_research.db"
    cmd = f'cmd /c if exist "{preferred}" (echo {preferred}) else if exist "{fallback}" (echo {fallback})'
    result = _ssh(WIN_HOST, cmd)
    return str((result.stdout or "").strip().splitlines()[-1] if (result.stdout or "").strip() else "")


def _backup_local_file(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    path.replace(backup)


def _remote_file_stat(remote_path: str) -> Tuple[int, str]:
    py_path = str(remote_path).replace("\\", "\\\\")
    cmd = f'py -3 -c "import os; p=r\'{py_path}\'; print(str(os.path.getsize(p))+\'|\'+p)"'
    result = _ssh(WIN_HOST, cmd)
    text = str(result.stdout or "").strip().splitlines()[-1]
    size_text, _, real_path = text.partition("|")
    return int(size_text or 0), real_path or remote_path

def _run_windows_powershell(script: str, *, check: bool = True) -> subprocess.CompletedProcess:
    return _ssh(WIN_HOST, _powershell_encoded(script), check=check)


def _run_cloud_bash(command: str, *, check: bool = True) -> subprocess.CompletedProcess:
    return _ssh(CLOUD_HOST, command, check=check)


def _sync_required_cloud_scripts() -> None:
    for rel_path in CLOUD_REQUIRED_SCRIPTS:
        local_path = ROOT_DIR / rel_path
        remote_path = f"{CLOUD_PROJECT_ROOT_ABS}/{rel_path.replace(os.sep, '/')}"
        remote_dir = str(Path(remote_path).parent)
        _run_cloud_bash(f"mkdir -p {shlex.quote(remote_dir)}", check=False)
        _run(["scp", str(local_path), f"{CLOUD_HOST}:{remote_path}"], check=True)


def _http_healthcheck(base_url: str, token: str, *, retries: int = 10, sleep_seconds: float = 1.0) -> None:
    url = f"{base_url.rstrip('/')}/__health__"
    last_error: Optional[Exception] = None
    for _ in range(retries):
        req = urllib.request.Request(url, headers={"X-Relay-Token": token}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if int(getattr(resp, "status", 200)) == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(sleep_seconds)
    raise RuntimeError(f"HTTP relay 未就绪: {base_url}") from last_error


def _http_download_to_local(url: str, local_path: Path, token: str, expected_size: int) -> Dict[str, object]:
    _ensure_local_parent(local_path)
    tmp_path = local_path.with_name(f"{local_path.name}.part")
    if tmp_path.exists():
        tmp_path.unlink()
    last_error: Optional[Exception] = None
    for _ in range(3):
        req = urllib.request.Request(url, headers={"X-Relay-Token": token}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_SYNC_TIMEOUT) as resp, open(tmp_path, "wb") as fh:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
            local_size = tmp_path.stat().st_size if tmp_path.exists() else -1
            if expected_size >= 0 and local_size != expected_size:
                raise RuntimeError(f"download size mismatch: expected={expected_size} actual={local_size}")
            if local_path.exists():
                _backup_local_file(local_path)
            tmp_path.replace(local_path)
            return {"local": str(local_path), "bytes": local_size, "url": url}
        except Exception as exc:
            last_error = exc
            time.sleep(1)
            if tmp_path.exists():
                tmp_path.unlink()
    raise RuntimeError(f"HTTP 下载失败: {url}") from last_error


def _windows_relative_under_project(remote_path: str) -> str:
    remote = str(PureWindowsPath(str(remote_path))).replace("/", "\\")
    project = str(PureWindowsPath(WIN_PROJECT_ROOT)).replace("/", "\\").rstrip("\\")
    remote_lower = remote.lower()
    project_lower = project.lower()
    if remote_lower == project_lower:
        return ""
    prefix = project_lower + "\\"
    if not remote_lower.startswith(prefix):
        raise RuntimeError(f"文件不在 Windows 项目目录下，拒绝同步: {remote_path}")
    return remote[len(project) + 1 :].replace("\\", "/")


def _start_windows_http_relay(token: str) -> Dict[str, object]:
    sync_root = f"{WIN_PROJECT_ROOT}\\.run\\postclose_sync\\lan"
    script_path = f"{WIN_PROJECT_ROOT}\\backend\\scripts\\postclose_http_relay.py"
    _stop_windows_http_relay()
    _ssh(WIN_HOST, f'cmd /c if not exist "{sync_root}" mkdir "{sync_root}"', check=False)
    proc = subprocess.Popen(
        [
            "ssh",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=6",
            WIN_HOST,
            f'cmd /c "{WIN_PYTHON_EXE} {script_path} --root {WIN_PROJECT_ROOT} --host 0.0.0.0 --port {LAN_SYNC_PORT} --token {token}"',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    base_url = f"http://{LAN_WINDOWS_HOST}:{LAN_SYNC_PORT}"
    try:
        _http_healthcheck(base_url, token)
    except Exception as exc:
        proc.terminate()
        _, stderr = proc.communicate(timeout=5)
        raise RuntimeError(f"局域网 HTTP relay 未就绪: {base_url}; stderr={_decode_maybe_gbk(stderr)}") from exc
    return {
        "mode": "LAN_HTTP",
        "token": token,
        "base_url": base_url,
        "remote_root": WIN_PROJECT_ROOT,
        "port": LAN_SYNC_PORT,
        "process": proc,
    }


def _stop_windows_http_relay() -> None:
    _run_windows_powershell(
        rf"""
Get-CimInstance Win32_Process | Where-Object {{
  $_.CommandLine -like "*postclose_http_relay.py*" -and $_.CommandLine -like "*--port {LAN_SYNC_PORT}*"
}} | ForEach-Object {{ try {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }} catch {{}} }}
""",
        check=False,
    )


def _start_cloud_http_relay(session_id: str, token: str) -> Dict[str, object]:
    _sync_required_cloud_scripts()
    relay_root = f"{CLOUD_PROJECT_ROOT_ABS}/{SYNC_ROOT_REL}/{session_id}"
    script_path = f"{CLOUD_PROJECT_ROOT_ABS}/backend/scripts/postclose_http_relay.py"
    _stop_cloud_http_relay("")
    _run_cloud_bash(f"mkdir -p {shlex.quote(relay_root)}")
    proc = subprocess.Popen(
        [
            "ssh",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=6",
            CLOUD_HOST,
            f"python3 {shlex.quote(script_path)} --root {shlex.quote(relay_root)} --host 0.0.0.0 --port {CLOUD_RELAY_PORT} --token {shlex.quote(token)}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    base_url = f"http://{CLOUD_PUBLIC_HTTP_HOST}:{CLOUD_RELAY_PORT}"
    try:
        _http_healthcheck(base_url, token)
    except Exception as exc:
        proc.terminate()
        _, stderr = proc.communicate(timeout=5)
        raise RuntimeError(f"云中转 HTTP relay 未就绪: {base_url}; stderr={_decode_maybe_gbk(stderr)}") from exc
    return {
        "mode": "CLOUD_RELAY",
        "token": token,
        "base_url": base_url,
        "remote_root": relay_root,
        "port": CLOUD_RELAY_PORT,
        "session_id": session_id,
        "process": proc,
    }


def _stop_cloud_http_relay(session_id: str) -> None:
    if session_id:
        relay_root = f"{CLOUD_PROJECT_ROOT_ABS}/{SYNC_ROOT_REL}/{session_id}"
        _run_cloud_bash(f"rm -rf {shlex.quote(relay_root)}", check=False)
    # ssh 断开不一定会带走远端 python；先按端口清残留，避免下一次新 token
    # 健康检查打到旧 relay 时返回 401 / Address already in use。
    stop_cmd = f"""
pids=$(pgrep -f '[p]ostclose_http_relay.py.*--port {CLOUD_RELAY_PORT}' || true)
if [ -n "$pids" ]; then
  kill $pids >/dev/null 2>&1 || true
  sleep 1
  kill -9 $pids >/dev/null 2>&1 || true
fi
"""
    _run_cloud_bash(stop_cmd, check=False)


def _resolve_mac_sync_transport(trade_date: str) -> Dict[str, object]:
    token = uuid.uuid4().hex
    if _tcp_reachable(LAN_WINDOWS_HOST, port=LAN_SYNC_PORT, timeout=1.0) or _tcp_reachable(LAN_WINDOWS_HOST, port=22, timeout=1.0):
        try:
            context = _start_windows_http_relay(token)
            _progress(
                f"[{trade_date}] Mac 同步路径判定：mode=LAN_HTTP reason=局域网 HTTP 直拉"
            )
            return context
        except Exception as exc:
            _progress(
                f"[{trade_date}] Mac 同步路径判定：局域网不可用，回退云中转: {exc}"
            )
    context = _start_cloud_http_relay(session_id=trade_date, token=token)
    _progress(
        f"[{trade_date}] Mac 同步路径判定：mode=CLOUD_RELAY reason=局域网 HTTP 失败，已回退云中转"
    )
    return context


def _cleanup_sync_transport(sync_context: Optional[Dict[str, object]]) -> None:
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
    mode = str(sync_context.get("mode") or "").upper()
    if mode == "LAN_HTTP":
        _stop_windows_http_relay()
    elif mode == "CLOUD_RELAY":
        _stop_cloud_http_relay(str(sync_context.get("session_id") or ""))


def _upload_windows_file_to_cloud_relay(remote_path: str, remote_name: str, sync_context: Dict[str, object]) -> Dict[str, object]:
    url = f"{str(sync_context['base_url']).rstrip('/')}/{urllib.parse.quote(remote_name)}"
    win_remote_path = str(PureWindowsPath(str(remote_path))).replace("/", "\\")
    script = rf"""
$headers = @{{"X-Relay-Token"="{sync_context['token']}"}}
$resp = Invoke-WebRequest -Uri "{url}" -Method Post -InFile "{win_remote_path}" -Headers $headers -UseBasicParsing
$resp.Content
"""
    result = _run_windows_powershell(script)
    return _parse_json_output(result.stdout)


def _sync_windows_file_to_local(remote_path: str, local_path: Path, sync_context: Dict[str, object]) -> Dict[str, object]:
    remote_size, resolved_remote = _remote_file_stat(remote_path)
    if str(sync_context.get("mode")) == "LAN_HTTP":
        rel_path = _windows_relative_under_project(resolved_remote)
        url = f"{str(sync_context['base_url']).rstrip('/')}/{urllib.parse.quote(rel_path)}"
    else:
        remote_name = f"uploads/{PureWindowsPath(str(resolved_remote)).name}"
        _upload_windows_file_to_cloud_relay(resolved_remote, remote_name, sync_context)
        url = f"{str(sync_context['base_url']).rstrip('/')}/{urllib.parse.quote(remote_name)}"
    result = _http_download_to_local(url, local_path, str(sync_context["token"]), remote_size)
    result.update({"remote": resolved_remote})
    return result


def _copy_windows_file_to_local(remote_path: str, local_path: Path) -> Dict[str, object]:
    raise RuntimeError("已禁用 Windows->Mac SSH/scp 直拉，请改走局域网 HTTP 或云中转")


def _copy_windows_small_file_via_ssh(remote_path: str, local_path: Path) -> Dict[str, object]:
    raise RuntimeError("已禁用 Windows->Mac SSH 直拉，请改走局域网 HTTP 或云中转")


def _ensure_local_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _sync_required_windows_scripts() -> None:
    for rel_path in WINDOWS_REQUIRED_SCRIPTS:
        local_path = ROOT_DIR / rel_path
        remote_path = f"{WIN_PROJECT_ROOT}/{rel_path.replace(os.sep, '/')}"
        remote_dir = str(PureWindowsPath(str(Path(remote_path).parent))).replace("/", "\\")
        _ssh(WIN_HOST, f'cmd /c if not exist "{remote_dir}" mkdir "{remote_dir}"', check=False)
        _run(["scp", str(local_path), f"{WIN_HOST}:{_win_scp_path(remote_path)}"], check=True)


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


def _spawn_worker_process(manifest: Dict[str, object], shard: Dict[str, object], log_fh) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "ssh",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=6",
            WIN_HOST,
            _worker_command(
                day_root=str(manifest["day_root"]),
                symbols_file=str(shard["symbols_file"]),
                artifact_db=str(shard["artifact_db"]),
                trade_date=str(manifest["trade_date"]),
                worker=int(shard["worker"]),
            ),
        ],
        stdout=log_fh,
        stderr=log_fh,
        text=True,
    )


def _run_workers(manifest: Dict[str, object], local_day_root: Path) -> List[Dict[str, object]]:
    shards = manifest.get("shards", [])
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
        proc = _spawn_worker_process(manifest, shard, log_fh)
        processes.append(
            {
                "worker": worker,
                "shard": shard,
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
        _progress(f"[{manifest['trade_date']}] 检测到 {len(failed)} 个失败 worker，开始单独重试")
    recovered_workers = set()
    for item in failed:
        worker = int(item["worker"])
        shard = item["shard"]
        log_path = Path(item["log_path"])
        for attempt in range(1, 3):
            with open(log_path, "a", encoding="utf-8") as log_fh:
                log_fh.write(f"\n=== RETRY {attempt} START {_now_text()} ===\n")
                proc = _spawn_worker_process(manifest, shard, log_fh)
                rc = proc.wait()
                log_fh.write(f"\n=== RETRY {attempt} END rc={rc} {_now_text()} ===\n")
            if int(rc) == 0:
                item["return_code"] = 0
                recovered_workers.add(worker)
                _progress(f"[{manifest['trade_date']}] worker {worker} 重试成功 attempt={attempt}")
                break
            _progress(f"[{manifest['trade_date']}] worker {worker} 重试失败 attempt={attempt} rc={rc}")

    failed = [item for item in results if item["return_code"] != 0]
    if failed:
        raise RuntimeError(f"存在 worker 非零退出: {failed}")
    if recovered_workers:
        _progress(
            f"[{manifest['trade_date']}] 全部 worker 执行完成（含重试恢复: {','.join(str(x) for x in sorted(recovered_workers))}）"
        )
        return results
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


def _export_windows_l2_day_delta(trade_date: str, local_day_root: Path, sync_context: Dict[str, object]) -> Dict[str, object]:
    remote_delta_dir = f"{WIN_PROJECT_ROOT}\\.run\\postclose_l2\\{trade_date}\\processed"
    remote_delta = f"{remote_delta_dir}\\l2_day_delta_{trade_date}.db"
    _ssh(WIN_HOST, f'cmd /c if not exist "{remote_delta_dir}" mkdir "{remote_delta_dir}"', check=False)
    export_cmd = (
        f'cd /d {WIN_PROJECT_ROOT} && '
        f'{WIN_PY_CMD} backend\\scripts\\export_l2_day_delta.py {trade_date} '
        f'--source-db "{WIN_MARKET_DB}" --output-db "{remote_delta}"'
    )
    export_result = _ssh(WIN_HOST, f'cmd /c "{export_cmd}"')
    export_report = _parse_json_output(export_result.stdout)
    local_delta = local_day_root / "processed" / f"l2_day_delta_{trade_date}.db"
    local_delta.parent.mkdir(parents=True, exist_ok=True)
    _sync_windows_file_to_local(remote_delta, local_delta, sync_context)
    _progress(f"[{trade_date}] 已回传 Windows L2 单日 delta 到本地")
    return {
        "l2_delta_export": export_report,
        "local_delta_path": str(local_delta),
        "remote_delta_path": str(remote_delta),
    }


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


def _upload_single_file_to_cloud(trade_date: str, local_file: str, remote_name: str) -> str:
    _progress(f"[{trade_date}] 开始上传云端文件: {Path(local_file).name}")
    cloud_tmp_dir = f"{CLOUD_PROJECT_ROOT_ABS}/.run/l2_postclose/{trade_date}"
    _ssh(CLOUD_HOST, f"mkdir -p {cloud_tmp_dir}")
    remote_path = f"{cloud_tmp_dir}/{remote_name}"
    _run(["scp", str(local_file), f"{CLOUD_HOST}:{remote_path}"], check=True)
    _progress(f"[{trade_date}] 已上传云端文件: {remote_name}")
    return remote_path


def _merge_on_cloud(trade_date: str, cloud_artifacts: Sequence[str]) -> Dict[str, object]:
    _progress(f"[{trade_date}] 开始云端 merge 入正式库")
    artifacts_arg = ",".join(cloud_artifacts)
    cloud_tmp_dir = f"{CLOUD_PROJECT_ROOT_ABS}/.run/l2_postclose/{trade_date}"
    report_file = f"{cloud_tmp_dir}/cloud_merge_report.json"
    log_file = f"{cloud_tmp_dir}/cloud_merge.log"
    pid_file = f"{cloud_tmp_dir}/cloud_merge.pid"
    start_cmd = (
        f"mkdir -p {shlex.quote(cloud_tmp_dir)} && "
        f"rm -f {shlex.quote(report_file)} {shlex.quote(log_file)} {shlex.quote(pid_file)} && "
        f"cd {shlex.quote(CLOUD_PROJECT_ROOT_ABS)} && "
        f"nohup sudo -n python3 backend/scripts/merge_l2_day_delta.py {trade_date} "
        f"--artifacts {shlex.quote(artifacts_arg)} "
        f'--source-root {shlex.quote("postclose_l2_daily")} '
        f'--mode {shlex.quote("postclose_one_command")} --json '
        f"> {shlex.quote(report_file)} 2> {shlex.quote(log_file)} < /dev/null & echo $! > {shlex.quote(pid_file)}"
    )
    _run_cloud_bash(start_cmd)
    merge_report: Optional[Dict[str, object]] = None
    last_log = ""
    for _ in range(360):
        result = _run_cloud_bash(f"test -s {shlex.quote(report_file)} && cat {shlex.quote(report_file)}", check=False)
        stdout = str(result.stdout or "").strip()
        if result.returncode == 0 and stdout:
            merge_report = _parse_json_output(stdout)
            break
        log_result = _run_cloud_bash(f"test -f {shlex.quote(log_file)} && tail -n 20 {shlex.quote(log_file)}", check=False)
        last_log = str(log_result.stdout or "").strip()
        time.sleep(5)
    if merge_report is None:
        raise RuntimeError(f"[{trade_date}] 云端 merge 超时或无报告输出: {last_log}")
    _progress(
        f"[{trade_date}] 云端 merge 完成：status={merge_report.get('status')} "
        f"rows_daily={merge_report.get('rows_daily')} rows_5m={merge_report.get('rows_5m')} "
        f"failure_count={merge_report.get('failure_count')}"
    )
    return merge_report


def _merge_on_windows(trade_date: str, remote_artifacts: Sequence[str]) -> Dict[str, object]:
    _progress(f"[{trade_date}] 开始 merge 回 Windows 本地 market_data.db")
    artifacts_arg = ",".join(remote_artifacts)
    remote_cmd = (
        f'cd /d {WIN_PROJECT_ROOT} && '
        f'{WIN_PY_CMD} backend\\scripts\\merge_l2_day_delta.py {trade_date} '
        f'--artifacts "{artifacts_arg}" --db-path "{WIN_MARKET_DB}" --json'
    )
    result = _ssh(WIN_HOST, f'cmd /c "{remote_cmd}"')
    report = _parse_json_output(result.stdout)
    _progress(
        f"[{trade_date}] Windows merge 完成：status={report.get('status')} "
        f"rows_daily={report.get('rows_daily')} rows_5m={report.get('rows_5m')}"
    )
    return report


def _merge_on_local_market(trade_date: str, local_artifacts: Sequence[str]) -> Dict[str, object]:
    _progress(f"[{trade_date}] 开始 merge 回 Mac 本地 market_data.db")
    _ensure_local_parent(LOCAL_MARKET_DB)
    artifacts_arg = ",".join(str(Path(p)) for p in local_artifacts)
    result = _run(
        [
            LOCAL_PY_CMD,
            str(ROOT_DIR / "backend" / "scripts" / "merge_l2_day_delta.py"),
            trade_date,
            "--artifacts",
            artifacts_arg,
            "--db-path",
            str(LOCAL_MARKET_DB),
            "--json",
        ]
    )
    report = _parse_json_output(result.stdout)
    _progress(
        f"[{trade_date}] Mac market merge 完成：status={report.get('status')} "
        f"rows_daily={report.get('rows_daily')} rows_5m={report.get('rows_5m')}"
    )
    return report


def _write_windows_atomic_single_day_config(trade_date: str, local_day_root: Path) -> str:
    iso_date = _compact_to_iso(trade_date)
    kind = "l2" if trade_date >= "20260301" else "legacy"
    win_root_py = WIN_PROJECT_ROOT.replace("\\", "/")
    config = {
        "atomic_db": WIN_ATOMIC_DB.replace("\\", "/"),
        "market_root": WIN_MARKET_ROOT.replace("\\", "/"),
        "extract_root": r"Z:/atomic_stage",
        "workers": 12,
        "large_threshold": 200000.0,
        "super_threshold": 1000000.0,
        "include_bj": False,
        "include_star": False,
        "include_gem": False,
        "main_board_only": True,
        "stop_on_failure": True,
        "cleanup_extracted": True,
        "state_file": f"{win_root_py}/.run/postclose_atomic/{trade_date}/state.json",
        "report_file": f"{win_root_py}/.run/postclose_atomic/{trade_date}/report.json",
        "batches": [
            {
                "name": f"postclose_{trade_date}",
                "kind": kind,
                "date_from": iso_date,
                "date_to": iso_date,
            }
        ],
        "extractor": "tar",
    }
    local_config = local_day_root / "atomic_config.json"
    local_config.parent.mkdir(parents=True, exist_ok=True)
    local_config.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    remote_dir = f"{WIN_PROJECT_ROOT}\\.run\\postclose_atomic\\{trade_date}"
    remote_config = f"{WIN_PROJECT_ROOT}/.run/postclose_atomic/{trade_date}/atomic_config.json"
    _ssh(WIN_HOST, f'cmd /c if not exist "{remote_dir}" mkdir "{remote_dir}"', check=False)
    _run(["scp", str(local_config), f"{WIN_HOST}:{_win_scp_path(remote_config)}"], check=True)
    return remote_config


def _run_windows_atomic_pipeline(trade_date: str, local_day_root: Path, sync_context: Dict[str, object]) -> Dict[str, object]:
    _progress(f"[{trade_date}] 开始更新 Windows 本地 atomic 主库")
    remote_config = _write_windows_atomic_single_day_config(trade_date, local_day_root)
    remote_cmd = (
        f'cd /d {WIN_PROJECT_ROOT} && '
        f'{WIN_PY_CMD} backend\\scripts\\run_atomic_backfill_windows.py --config "{remote_config}"'
    )
    result = _ssh(WIN_HOST, f'cmd /c "{remote_cmd}"')
    report = _parse_json_output(result.stdout)
    _progress(
        f"[{trade_date}] Windows atomic 更新完成：status={report.get('status')} "
        f"completed_day_count={report.get('completed_day_count')}"
    )
    remote_delta = f"{WIN_PROJECT_ROOT}/.run/postclose_atomic/{trade_date}/atomic_day_delta_{trade_date}.db"
    export_cmd = (
        f'cd /d {WIN_PROJECT_ROOT} && '
        f'{WIN_PY_CMD} backend\\scripts\\export_atomic_day_delta.py {trade_date} '
        f'--source-db "{WIN_ATOMIC_DB}" --output-db "{remote_delta}"'
    )
    export_result = _ssh(WIN_HOST, f'cmd /c "{export_cmd}"')
    export_report = _parse_json_output(export_result.stdout)
    local_delta = local_day_root / "processed" / f"atomic_day_delta_{trade_date}.db"
    local_delta.parent.mkdir(parents=True, exist_ok=True)
    _sync_windows_file_to_local(remote_delta, local_delta, sync_context)
    merge_result = _run(
        [
            LOCAL_PY_CMD,
            str(ROOT_DIR / "backend" / "scripts" / "merge_atomic_day_delta.py"),
            trade_date,
            "--delta-db",
            str(local_delta),
            "--target-db",
            str(LOCAL_ATOMIC_DB),
        ]
    )
    merge_report = _parse_json_output(merge_result.stdout)
    _progress(
        f"[{trade_date}] Mac atomic 增量合并完成：tables={len(merge_report.get('row_counts', {}))}"
    )
    return {
        "windows_atomic": report,
        "atomic_delta_export": export_report,
        "local_atomic_merge": merge_report,
        "local_delta_path": str(local_delta),
    }


def _run_windows_selection_pipeline(trade_date: str, local_day_root: Path, sync_context: Dict[str, object]) -> Dict[str, object]:
    iso_date = _compact_to_iso(trade_date)
    selection_db = _resolve_windows_selection_db()
    if not selection_db:
        raise RuntimeError("Windows 未解析到 selection_research DB")
    _progress(f"[{trade_date}] 开始更新 Windows 本地 selection 主库")
    refresh_cmd = (
        f'cmd /c "set DB_PATH={WIN_MARKET_DB}&& '
        f'set ATOMIC_MAINBOARD_DB_PATH={WIN_ATOMIC_DB}&& '
        f'set ATOMIC_DB_PATH={WIN_ATOMIC_DB}&& '
        f'set SELECTION_DB_PATH={selection_db}&& '
        f'cd /d {WIN_PROJECT_ROOT} && '
        f'{WIN_PY_CMD} backend\\scripts\\run_selection_research.py refresh --start-date {iso_date} --end-date {iso_date}"'
    )
    refresh_result = _ssh(WIN_HOST, refresh_cmd)
    refresh_report = _parse_json_output(refresh_result.stdout)
    remote_delta_dir = f"{WIN_PROJECT_ROOT}\\.run\\postclose_atomic\\{trade_date}"
    remote_delta = f"{remote_delta_dir}\\selection_day_delta_{trade_date}.db"
    _ssh(WIN_HOST, f'cmd /c if not exist "{remote_delta_dir}" mkdir "{remote_delta_dir}"', check=False)
    export_cmd = (
        f'cmd /c "set SELECTION_DB_PATH={selection_db}&& '
        f'cd /d {WIN_PROJECT_ROOT} && '
        f'{WIN_PY_CMD} backend\\scripts\\export_selection_day_delta.py {trade_date} '
        f'--source-db "{selection_db}" --output-db "{remote_delta}""'
    )
    export_result = None
    last_error: Optional[Exception] = None
    for _ in range(3):
        try:
            export_result = _ssh(WIN_HOST, export_cmd)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    if export_result is None:
        raise RuntimeError(f"[{trade_date}] selection day delta 导出失败: {last_error}")
    export_report = _parse_json_output(export_result.stdout)
    local_delta = local_day_root / "processed" / f"selection_day_delta_{trade_date}.db"
    local_delta.parent.mkdir(parents=True, exist_ok=True)
    _sync_windows_file_to_local(remote_delta, local_delta, sync_context)
    merge_result = _run(
        [
            LOCAL_PY_CMD,
            str(ROOT_DIR / "backend" / "scripts" / "merge_selection_day_delta.py"),
            trade_date,
            "--delta-db",
            str(local_delta),
            "--target-db",
            str(LOCAL_SELECTION_DB),
        ]
    )
    merge_report = _parse_json_output(merge_result.stdout)
    _progress(f"[{trade_date}] Mac selection 增量合并完成")
    return {
        "windows_selection_refresh": refresh_report,
        "selection_delta_export": export_report,
        "local_selection_merge": merge_report,
        "local_delta_path": str(local_delta),
    }


def _bootstrap_mac_full_sync() -> Dict[str, object]:
    selection_db = _resolve_windows_selection_db()
    if not selection_db:
        raise RuntimeError("Windows 未解析到 selection_research DB")
    sync_context = _resolve_mac_sync_transport("bootstrap")
    mapping = [
        (WIN_MARKET_DB, LOCAL_MARKET_DB),
        (WIN_ATOMIC_DB, LOCAL_ATOMIC_DB),
        (selection_db, LOCAL_SELECTION_DB),
    ]
    copied: List[Dict[str, object]] = []
    try:
        for remote_path, local_path in mapping:
            _progress(f"[bootstrap] 同步全量库到 Mac: {remote_path} -> {local_path}")
            copied.append(_sync_windows_file_to_local(remote_path, local_path, sync_context))
        return {"status": "done", "host": WIN_HOST, "copied": copied, "sync_mode": sync_context.get("mode")}
    finally:
        _cleanup_sync_transport(sync_context)


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


def _query_local_scalar(db_path: Path, sql: str) -> int:
    import sqlite3

    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        conn.close()


def _try_reuse_completed_day(trade_date: str, local_day_root: Path) -> Optional[Dict[str, object]]:
    report_path = local_day_root / "report.json"
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    summary = report.get("execution_summary") or {}
    if str(summary.get("final_status") or "").upper() not in {"PASS", "PASS_WITH_WARNINGS"}:
        return None
    local_l2 = local_day_root / "processed" / f"l2_day_delta_{trade_date}.db"
    local_atomic = local_day_root / "processed" / f"atomic_day_delta_{trade_date}.db"
    local_selection = local_day_root / "processed" / f"selection_day_delta_{trade_date}.db"
    if not (local_l2.exists() and local_atomic.exists() and local_selection.exists()):
        return None

    trade_date_iso = _compact_to_iso(trade_date)
    rows_daily = _query_local_scalar(LOCAL_MARKET_DB, f"SELECT COUNT(*) FROM history_daily_l2 WHERE date='{trade_date_iso}'")
    rows_5m = _query_local_scalar(LOCAL_MARKET_DB, f"SELECT COUNT(*) FROM history_5m_l2 WHERE source_date='{trade_date_iso}'")
    atomic_rows = _query_local_scalar(LOCAL_ATOMIC_DB, f"SELECT COUNT(*) FROM atomic_trade_daily WHERE trade_date='{trade_date_iso}'")
    selection_rows = _query_local_scalar(LOCAL_SELECTION_DB, f"SELECT COUNT(*) FROM selection_feature_daily WHERE trade_date='{trade_date_iso}'")
    if min(rows_daily, rows_5m, atomic_rows, selection_rows) <= 0:
        return None

    verify_report = _verify_cloud_day(trade_date)
    if int(verify_report.get("rows_daily") or 0) <= 0 or int(verify_report.get("rows_5m") or 0) <= 0:
        return None

    report["verify_report"] = verify_report
    report["execution_summary"] = {
        "final_status": "PASS",
        "reason": "already_complete_reused",
        "warning_count": 0,
        "failure_summary": {},
        "is_production_ready": True,
    }
    _write_local_report(local_day_root, report)
    return report


def run_day(
    trade_date: str,
    workers: int,
    stable_seconds: int,
    skip_cloud_merge: bool = False,
    skip_mac_sync: bool = False,
) -> Dict[str, object]:
    local_day_root = ROOT_DIR / ".run" / "postclose_l2" / trade_date
    _progress(f"[{trade_date}] ===== 开始处理 =====")
    reused = _try_reuse_completed_day(trade_date, local_day_root)
    if reused is not None:
        _progress(f"[{trade_date}] 已检测到完整成功结果，直接复用，不重复跑全链路")
        return reused
    _sync_required_windows_scripts()
    sync_context = _resolve_mac_sync_transport(trade_date)
    prepared: Dict[str, object]
    worker_results: List[Dict[str, object]]
    windows_merge_report: Dict[str, object]
    l2_delta_report: Dict[str, object]
    local_delta: str
    local_market_merge_report: Dict[str, object]
    merge_report: Optional[Dict[str, object]] = None
    verify_report: Optional[Dict[str, object]] = None
    cloud_artifacts: List[str] = []
    atomic_sync_report: Optional[Dict[str, object]] = None
    selection_sync_report: Optional[Dict[str, object]] = None
    try:
        prepared = _prepare_day(trade_date=trade_date, workers=workers, stable_seconds=stable_seconds)
        worker_results = _run_workers(prepared, local_day_root=local_day_root)
        windows_merge_report = _merge_on_windows(
            trade_date=trade_date,
            remote_artifacts=[str(item["artifact_db"]) for item in worker_results],
        )
        l2_delta_report = _export_windows_l2_day_delta(
            trade_date=trade_date,
            local_day_root=local_day_root,
            sync_context=sync_context,
        )
        local_delta = str(l2_delta_report["local_delta_path"])
        local_market_merge_report = _merge_on_local_market(trade_date=trade_date, local_artifacts=[local_delta])

        if not skip_mac_sync:
            atomic_sync_report = _run_windows_atomic_pipeline(
                trade_date=trade_date,
                local_day_root=local_day_root,
                sync_context=sync_context,
            )
            selection_sync_report = _run_windows_selection_pipeline(
                trade_date=trade_date,
                local_day_root=local_day_root,
                sync_context=sync_context,
            )

        if not skip_cloud_merge:
            cloud_artifacts = [
                _upload_single_file_to_cloud(
                    trade_date=trade_date,
                    local_file=local_delta,
                    remote_name=Path(local_delta).name,
                )
            ]
            merge_report = _merge_on_cloud(trade_date=trade_date, cloud_artifacts=cloud_artifacts)
            verify_report = _verify_cloud_day(trade_date=trade_date)

        report = {
            "trade_date": trade_date,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "prepared": prepared,
            "worker_results": worker_results,
            "windows_merge_report": windows_merge_report,
            "l2_delta_report": l2_delta_report,
            "local_artifacts": [local_delta],
            "local_market_merge_report": local_market_merge_report,
            "cloud_artifacts": cloud_artifacts,
            "merge_report": merge_report,
            "verify_report": verify_report,
            "skip_cloud_merge": skip_cloud_merge,
            "skip_mac_sync": skip_mac_sync,
            "atomic_sync_report": atomic_sync_report,
            "selection_sync_report": selection_sync_report,
            "sync_context": {k: v for k, v in sync_context.items() if k not in {"token", "process"}},
        }
    finally:
        _cleanup_remote_day(trade_date)
        _cleanup_sync_transport(sync_context)

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
    parser.add_argument("--skip-mac-sync", action="store_true")
    parser.add_argument("--bootstrap-mac-full-sync", action="store_true")
    parser.add_argument("--bootstrap-only", action="store_true")
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

    bootstrap_requested = bool(args.bootstrap_mac_full_sync)

    if args.bootstrap_only:
        if args.dry_run:
            result = {
                "status": "dry_run",
                "ready_days": ready_days,
                "existing_cloud_days_count": len(existing_cloud_days),
                "message": "仅预演 Mac 全量同步",
                "bootstrap_mac_full_sync": bootstrap_requested,
                "windows_host": WIN_HOST,
            }
        else:
            bootstrap_report = _bootstrap_mac_full_sync() if bootstrap_requested else None
            result = {
                "status": "done" if bootstrap_report else "noop",
                "ready_days": ready_days,
                "existing_cloud_days_count": len(existing_cloud_days),
                "message": "仅执行 Mac 全量同步" if bootstrap_report else "未启用 Mac 全量同步",
                "bootstrap_mac_full_sync": bootstrap_report,
                "windows_host": WIN_HOST,
            }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"[postclose-l2] bootstrap_only host={WIN_HOST}")
        return

    if not target_days:
        if args.dry_run:
            result = {
                "status": "dry_run",
                "ready_days": ready_days,
                "existing_cloud_days_count": len(existing_cloud_days),
                "message": "无待跑交易日",
                "bootstrap_mac_full_sync": bootstrap_requested,
                "windows_host": WIN_HOST,
            }
        else:
            bootstrap_report = _bootstrap_mac_full_sync() if bootstrap_requested else None
            result = {
                "status": "done" if bootstrap_report else "noop",
                "ready_days": ready_days,
                "existing_cloud_days_count": len(existing_cloud_days),
                "message": "无待跑交易日" if not bootstrap_report else "无待跑交易日，但已完成 Mac 全量同步",
                "bootstrap_mac_full_sync": bootstrap_report,
                "windows_host": WIN_HOST,
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
            "bootstrap_mac_full_sync": bootstrap_requested,
            "windows_host": WIN_HOST,
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"[postclose-l2] dry_run target_days={','.join(target_days)}")
        return

    bootstrap_report = _bootstrap_mac_full_sync() if bootstrap_requested else None

    day_reports = [
        run_day(
            trade_date=day,
            workers=int(args.workers),
            stable_seconds=int(args.stable_seconds),
            skip_cloud_merge=bool(args.skip_cloud_merge),
            skip_mac_sync=bool(args.skip_mac_sync),
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
        "bootstrap_mac_full_sync": bootstrap_report,
    }
    if args.json:
        print(json.dumps(final_result, ensure_ascii=False, indent=2))
    else:
        _progress(f"全部完成：final_status={final_status} 完成交易日={','.join(target_days)}")
        for report in day_reports:
            summary = report.get("execution_summary") or {}
            verify = report.get("verify_report") or {}
            print(
                "[postclose-l2] summary "
                f"date={report.get('trade_date')} "
                f"status={summary.get('final_status')} "
                f"reason={summary.get('reason')} "
                f"rows_daily={verify.get('rows_daily')} "
                f"rows_5m={verify.get('rows_5m')}",
                flush=True,
            )


if __name__ == "__main__":
    main()
