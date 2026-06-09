from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote
import urllib.request

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MAC_FORMAL_ROOT = Path(os.getenv("FORMAL_MARKET_DATA_ROOT", "/Users/dong/Desktop/AIGC/market-data"))
DEFAULT_MAC_RESEARCH_ROOT = DEFAULT_MAC_FORMAL_ROOT / "research" / "current"
DEFAULT_MAC_LIVE_ROOT = DEFAULT_MAC_FORMAL_ROOT / "live"
DEFAULT_MAC_DATA_ROOT = DEFAULT_MAC_RESEARCH_ROOT if DEFAULT_MAC_RESEARCH_ROOT.exists() else DEFAULT_MAC_FORMAL_ROOT
DEFAULT_MAC_RUNTIME_ROOT = DEFAULT_MAC_LIVE_ROOT if DEFAULT_MAC_LIVE_ROOT.exists() else DEFAULT_MAC_FORMAL_ROOT

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
DEFAULT_WIN_SELECTION_DB = r"D:\market-live-terminal\data\selection\selection_research.db"
DEFAULT_WIN_MODEL_FEATURE_DB_ALIAS = r"D:\market-live-terminal\data\selection\model_feature_store.db"
WIN_ATOMIC_DB = os.getenv("DAILY_WIN_ATOMIC_DB", DEFAULT_WIN_ATOMIC_DB_ALIAS)
WIN_SELECTION_DB = os.getenv("DAILY_WIN_SELECTION_DB", DEFAULT_WIN_SELECTION_DB)
WIN_MODEL_FEATURE_DB = os.getenv("DAILY_WIN_MODEL_FEATURE_DB", DEFAULT_WIN_MODEL_FEATURE_DB_ALIAS)
WIN_MODEL_INDEX_DB = os.getenv(
    "DAILY_WIN_MODEL_INDEX_DB",
    r"D:\market-live-terminal\data\selection\model_market_index_daily.db",
)
WIN_DATA_DIR = os.getenv("DAILY_WIN_DATA_DIR", rf"{WIN_PROJECT_ROOT}\data")
WIN_MARKET_HEAT_DIR = os.getenv("DAILY_WIN_MARKET_HEAT_DIR", rf"{WIN_PROJECT_ROOT}\data\market_heat")
WIN_HEAT_V2_DB = os.getenv("DAILY_WIN_HEAT_V2_DB", rf"{WIN_MARKET_HEAT_DIR}\fine_theme_heat_daily_v2.db")
WIN_TRADABLE_THEME_DB = os.getenv("DAILY_WIN_TRADABLE_THEME_DB", rf"{WIN_MARKET_HEAT_DIR}\tradable_theme_map.db")
WIN_RUN_ROOT = os.getenv("DAILY_WIN_RUN_ROOT", r"D:\market-live-terminal\.run\daily_new_framework")

LOCAL_DATA_ROOT = Path(
    os.getenv("LOCAL_PROCESSED_DATA_ROOT")
    or os.getenv("RESEARCH_CURRENT_ROOT")
    or os.getenv("MARKET_DATA_ROOT")
    or str(DEFAULT_MAC_DATA_ROOT)
)
LOCAL_LIVE_DATA_ROOT = Path(os.getenv("DAILY_LOCAL_LIVE_DATA_ROOT") or os.getenv("LIVE_DATA_ROOT") or str(DEFAULT_MAC_RUNTIME_ROOT))
LOCAL_ATOMIC_DB = Path(
    os.getenv(
        "DAILY_LOCAL_ATOMIC_DB",
        str(LOCAL_DATA_ROOT / "atomic_facts" / "market_atomic_mainboard_compact_current.db"),
    )
)
LOCAL_SELECTION_DB = Path(os.getenv("DAILY_LOCAL_SELECTION_DB", str(LOCAL_DATA_ROOT / "selection" / "selection_research.db")))
LOCAL_MODEL_FEATURE_DB = Path(os.getenv("DAILY_LOCAL_MODEL_FEATURE_DB", str(LOCAL_DATA_ROOT / "selection" / "model_feature_store.db")))
LOCAL_MODEL_INDEX_DB = Path(os.getenv("DAILY_LOCAL_MODEL_INDEX_DB", str(LOCAL_DATA_ROOT / "selection" / "model_market_index_daily.db")))
LOCAL_MARKET_HEAT_DIR = Path(os.getenv("DAILY_LOCAL_MARKET_HEAT_DIR", str(LOCAL_DATA_ROOT / "market_heat")))
LOCAL_HEAT_V2_DB = Path(os.getenv("DAILY_LOCAL_HEAT_V2_DB", str(LOCAL_MARKET_HEAT_DIR / "fine_theme_heat_daily_v2.db")))
LOCAL_MARKET_DB = Path(os.getenv("DAILY_LOCAL_MARKET_DB", str(LOCAL_LIVE_DATA_ROOT / "market_data.db")))
LOCAL_USER_DB = Path(os.getenv("DAILY_LOCAL_USER_DB", str(LOCAL_LIVE_DATA_ROOT / "user_data.db")))

DAILY_INDEX_LOOKBACK_DAYS = int(os.getenv("DAILY_INDEX_LOOKBACK_DAYS", "10"))
DAILY_HEAT_LOOKBACK_DAYS = int(os.getenv("DAILY_HEAT_LOOKBACK_DAYS", "63"))


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
    "backend/scripts/build_fine_theme_heat_daily_v2.py",
    "backend/scripts/refresh_market_heat_cache.py",
    "backend/scripts/build_fine_theme_heat_daily.py",
    "backend/scripts/analyze_hot_sector_granularity.py",
    "backend/scripts/analyze_hot_theme_winner_lead_lag.py",
    "backend/app/core/config.py",
    "backend/app/services/market_heat.py",
    "data/market_heat/fine_hotspot_rules.json",
    "data/market_heat/theme_canonical_rules.json",
    "data/market_heat/themes.seed.json",
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
    "model_market_index_daily",
    "model_market_state_daily_v1",
    "selection_feature_daily",
    "selection_signal_daily",
    "model_feature_daily_v1",
    "model_feature_intraday_shape_v1",
]

REQUIRED_SELECTION_SOURCE_IDS = [
    "spark_opportunity_selector",
    "stable_capital_callback",
    "trend_continuation_callback",
    "probe_day0_watch",
    "probe_d3_confirmed",
]

DEFAULT_AUTO_DETECT_LIMIT = int(os.getenv("DAILY_AUTO_DETECT_LIMIT", "20"))
DEFAULT_SYNC_NAS = os.getenv("DAILY_SYNC_NAS", "").strip().lower() in {"1", "true", "yes"}
DEFAULT_NAS_RELEASE_PREFIX = os.getenv("DAILY_NAS_RELEASE_PREFIX", "nas_daily_new")
DEFAULT_INCLUDE_LIVE_SYNC = os.getenv("DAILY_INCLUDE_LIVE_SYNC", "1").strip().lower() not in {"0", "false", "no"}
NAS_HOST = os.getenv("NAS_HOST", "zhangdong@192.168.3.43").strip()
NAS_DATA_ROOT = os.getenv("NAS_DATA_ROOT", "/volume1/docker/market-live-terminal/data").strip()
NAS_PROJECT_ROOT = os.getenv("NAS_PROJECT_ROOT", "/volume1/docker/market-live-terminal/app").strip()
NAS_LIVE_MARKET_DB = os.getenv("NAS_LIVE_MARKET_DB", f"{NAS_DATA_ROOT}/live/market_data.db").strip()
NAS_INCOMING_ROOT = os.getenv("NAS_INCOMING_ROOT", f"{NAS_DATA_ROOT}/incoming").strip()
NAS_BACKUP_ROOT = os.getenv("NAS_BACKUP_ROOT", "/volume1/docker/market-live-terminal/backups/db_snapshots").strip()
NAS_SCP_PROTOCOL_OPT = os.getenv("SCP_PROTOCOL_OPT", "-O").strip() or "-O"
NAS_SSH_CONNECT_TIMEOUT = int(os.getenv("SSH_CONNECT_TIMEOUT", "8"))

HISTORY_5M_L2_COLUMNS = (
    "symbol, datetime, source_date, open, high, low, close, total_amount, "
    "l1_main_buy, l1_main_sell, l1_super_buy, l1_super_sell, "
    "l2_main_buy, l2_main_sell, l2_super_buy, l2_super_sell, quality_info"
)

HISTORY_DAILY_L2_COLUMNS = (
    "symbol, date, open, high, low, close, total_amount, "
    "l1_main_buy, l1_main_sell, l1_main_net, "
    "l1_super_buy, l1_super_sell, l1_super_net, "
    "l2_main_buy, l2_main_sell, l2_main_net, "
    "l2_super_buy, l2_super_sell, l2_super_net, "
    "l1_activity_ratio, l1_super_ratio, l2_activity_ratio, l2_super_ratio, "
    "l1_buy_ratio, l1_sell_ratio, l2_buy_ratio, l2_sell_ratio, quality_info"
)


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


def _make_nas_release_name(trade_date: str) -> str:
    return f"{DEFAULT_NAS_RELEASE_PREFIX}_{_compact_date(trade_date)}"


def _publish_to_nas(trade_date: str) -> Dict[str, object]:
    release_name = _make_nas_release_name(trade_date)
    _progress(f"[{trade_date}] NAS research/current 发布开始 release={release_name}")
    cmd = [
        "bash",
        str(ROOT_DIR / "ops" / "nas" / "nas_run_phase_b_release.sh"),
        release_name,
    ]
    result = _run(cmd, check=False)
    if result.returncode != 0:
        current_release = _run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=8",
                NAS_HOST,
                "cat /volume1/docker/market-live-terminal/data/research/current/.release_name 2>/dev/null || true",
            ],
            check=False,
        )
        current_name = str(current_release.stdout or "").strip()
        if current_name != release_name:
            raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
        _progress(f"[{trade_date}] NAS 发布脚本返回非零，但 current 已切到目标 release={release_name}，按成功处理")
    _progress(f"[{trade_date}] NAS research/current 发布完成 release={release_name}")
    return {
        "release_name": release_name,
        "command": f"bash ops/nas/nas_run_phase_b_release.sh {release_name}",
        "stdout": result.stdout,
        "return_code": result.returncode,
        "status": "published",
    }


def _nas_ssh(remote_command: str, *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["ssh", "-o", f"ConnectTimeout={NAS_SSH_CONNECT_TIMEOUT}", NAS_HOST, remote_command],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
    return result


def _sync_file_to_nas(local_path: Path, remote_path: str) -> Dict[str, object]:
    if not local_path.exists():
        raise FileNotFoundError(f"本地文件不存在，无法同步到 NAS: {local_path}")
    remote_dir = str(Path(remote_path).parent)
    _nas_ssh(f"mkdir -p {shlex.quote(remote_dir)}")
    cmd = ["scp", NAS_SCP_PROTOCOL_OPT, "-o", f"ConnectTimeout={NAS_SSH_CONNECT_TIMEOUT}", str(local_path), f"{NAS_HOST}:{remote_path}"]
    _run(cmd)
    remote_size_result = _nas_ssh(f"stat -c %s {shlex.quote(remote_path)}")
    remote_size = int(str(remote_size_result.stdout or "").strip() or "0")
    local_size = local_path.stat().st_size
    if remote_size != local_size:
        raise RuntimeError(f"NAS 同步后文件大小不一致: local={local_size} remote={remote_size} path={remote_path}")
    return {
        "local": str(local_path),
        "remote": remote_path,
        "bytes": remote_size,
    }


def _extract_postclose_local_delta(postclose_report: Dict[str, object], trade_date: str) -> Path:
    target_date = _compact_date(trade_date)
    for day_report in postclose_report.get("day_reports") or []:
        day_trade_date = str(day_report.get("trade_date") or "").strip()
        if not day_trade_date:
            continue
        if _compact_date(day_trade_date) != target_date:
            continue
        local_artifacts = day_report.get("local_artifacts") or []
        if local_artifacts:
            return Path(str(local_artifacts[0]))
    fallback = ROOT_DIR / ".run" / "postclose_l2" / target_date / "processed" / f"l2_day_delta_{target_date}.db"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"未找到本地 postclose L2 日增量: trade_date={trade_date}")


def _build_stock_universe_meta_sync_db(trade_date: str) -> Dict[str, object]:
    target_date = _compact_date(trade_date)
    sync_db = ROOT_DIR / ".run" / "daily_new_framework" / target_date / "processed" / f"stock_universe_meta_sync_{target_date}.db"
    sync_db.parent.mkdir(parents=True, exist_ok=True)
    sync_db.unlink(missing_ok=True)
    with sqlite3.connect(str(LOCAL_MARKET_DB)) as source_conn:
        create_row = source_conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='stock_universe_meta'"
        ).fetchone()
        if not create_row or not create_row[0]:
            raise RuntimeError("Mac 本地 live 库缺少 stock_universe_meta 表")
        columns = [str(row[1]) for row in source_conn.execute("PRAGMA table_info(stock_universe_meta)").fetchall()]
        if not columns:
            raise RuntimeError("无法解析 stock_universe_meta 列定义")
        rows = source_conn.execute(f"SELECT {', '.join(columns)} FROM stock_universe_meta").fetchall()
    if not rows:
        raise RuntimeError("Mac 本地 stock_universe_meta 为空，拒绝同步到 NAS")
    with sqlite3.connect(str(sync_db)) as target_conn:
        target_conn.execute(str(create_row[0]))
        placeholders = ",".join(["?"] * len(columns))
        target_conn.executemany(
            f"INSERT INTO stock_universe_meta ({', '.join(columns)}) VALUES ({placeholders})",
            rows,
        )
        target_conn.commit()
    return {
        "path": str(sync_db),
        "rows": len(rows),
    }


def _verify_nas_live_state(trade_date: str) -> Dict[str, int]:
    trade_date_iso = _compact_to_iso(trade_date)
    sql = (
        f"SELECT COUNT(*) FROM history_daily_l2 WHERE date='{trade_date_iso}'; "
        f"SELECT COUNT(*) FROM history_5m_l2 WHERE source_date='{trade_date_iso}'; "
        "SELECT COUNT(*) FROM stock_universe_meta;"
    )
    result = _nas_ssh(f"sqlite3 {shlex.quote(NAS_LIVE_MARKET_DB)} {shlex.quote(sql)}")
    lines = [line.strip() for line in str(result.stdout or "").splitlines()]
    while len(lines) < 3:
        lines.append("0")
    return {
        "rows_daily": int(lines[0] or 0),
        "rows_5m": int(lines[1] or 0),
        "stock_universe_meta_rows": int(lines[2] or 0),
    }


def _sync_nas_live_market_db(trade_date: str, local_live_sync_report: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    postclose_report = (local_live_sync_report or {}).get("postclose_l2") if isinstance(local_live_sync_report, dict) else None
    if not isinstance(postclose_report, dict):
        return {"status": "skipped", "reason": "missing_local_live_sync"}

    target_date = _compact_date(trade_date)
    trade_date_iso = _compact_to_iso(target_date)
    local_delta = _extract_postclose_local_delta(postclose_report, target_date)
    meta_sync_db = _build_stock_universe_meta_sync_db(target_date)
    remote_dir = f"{NAS_INCOMING_ROOT.rstrip('/')}/daily_new_framework/{target_date}"
    remote_l2_delta = f"{remote_dir}/{local_delta.name}"
    remote_meta_delta = f"{remote_dir}/{Path(meta_sync_db['path']).name}"

    l2_sync_result = _sync_file_to_nas(local_delta, remote_l2_delta)
    meta_sync_result = _sync_file_to_nas(Path(str(meta_sync_db["path"])), remote_meta_delta)

    remote_sql = f"""
PRAGMA busy_timeout=5000;
ATTACH DATABASE '{remote_l2_delta.replace("'", "''")}' AS delta;
ATTACH DATABASE '{remote_meta_delta.replace("'", "''")}' AS meta;
BEGIN IMMEDIATE;
DELETE FROM history_5m_l2 WHERE source_date='{trade_date_iso}';
DELETE FROM history_daily_l2 WHERE date='{trade_date_iso}';
INSERT INTO history_5m_l2 ({HISTORY_5M_L2_COLUMNS})
SELECT {HISTORY_5M_L2_COLUMNS}
FROM delta.history_5m_l2
WHERE source_date='{trade_date_iso}';
INSERT INTO history_daily_l2 ({HISTORY_DAILY_L2_COLUMNS})
SELECT {HISTORY_DAILY_L2_COLUMNS}
FROM delta.history_daily_l2
WHERE date='{trade_date_iso}';
CREATE TABLE IF NOT EXISTS stock_universe_meta AS
SELECT *
FROM meta.stock_universe_meta
WHERE 0;
DELETE FROM stock_universe_meta;
INSERT INTO stock_universe_meta
SELECT *
FROM meta.stock_universe_meta;
COMMIT;
DETACH DATABASE delta;
DETACH DATABASE meta;
"""
    _nas_ssh(
        f"sqlite3 {shlex.quote(NAS_LIVE_MARKET_DB)} <<'SQL'\n{remote_sql}\nSQL\nrm -rf {shlex.quote(remote_dir)}"
    )
    verify = _verify_nas_live_state(target_date)
    if int(verify.get("rows_daily") or 0) <= 0 or int(verify.get("rows_5m") or 0) <= 0:
        raise RuntimeError(
            f"NAS live 同步后校验失败: rows_daily={verify.get('rows_daily')} rows_5m={verify.get('rows_5m')}"
        )
    if int(verify.get("stock_universe_meta_rows") or 0) <= 0:
        raise RuntimeError("NAS stock_universe_meta 同步后为空")
    return {
        "status": "synced",
        "trade_date": target_date,
        "l2_delta": l2_sync_result,
        "stock_universe_meta_sync": {
            **meta_sync_result,
            "rows": int(meta_sync_db["rows"]),
        },
        "verify": verify,
    }


def _snapshot_nas_runtime_dbs() -> Dict[str, object]:
    running = _nas_ssh("ps -ef | grep '[n]as_backup_runtime_db_snapshot.sh' || true")
    running_lines = [line.strip() for line in str(running.stdout or "").splitlines() if line.strip()]
    if running_lines:
        return {
            "status": "running",
            "processes": running_lines,
        }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_root = f"{NAS_BACKUP_ROOT.rstrip('/')}/{stamp}"
    log_dir = f"{NAS_INCOMING_ROOT.rstrip('/')}/daily_new_framework/backup_logs"
    log_path = f"{log_dir}/nas_backup_runtime_db_snapshot_{stamp}.log"
    command = (
        f"mkdir -p {shlex.quote(log_dir)} && "
        f"cd {shlex.quote(NAS_PROJECT_ROOT)} && "
        f"STAMP={shlex.quote(stamp)} nohup bash ops/nas/nas_backup_runtime_db_snapshot.sh "
        f"> {shlex.quote(log_path)} 2>&1 < /dev/null & echo $!"
    )
    result = _nas_ssh(command)
    pid = str(result.stdout or "").strip().splitlines()[-1].strip()
    if not pid.isdigit():
        raise RuntimeError(f"NAS 快照后台启动失败: {result.stdout or result.stderr}")
    return {
        "status": "started",
        "pid": int(pid),
        "target_root": target_root,
        "log_path": log_path,
    }


def _run_nas_postprocess(trade_date: str, local_live_sync_report: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    live_sync = _sync_nas_live_market_db(trade_date, local_live_sync_report)
    snapshot = _snapshot_nas_runtime_dbs()
    return {
        "status": "done",
        "live_sync": live_sync,
        "research_release": {
            "status": "skipped",
            "reason": "daily_sync_focuses_on_live_and_backup",
        },
        "snapshot": snapshot,
    }


def _run_json_command(cmd: Sequence[str]) -> Dict[str, object]:
    result = _run(cmd, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"命令失败: {shlex.join(list(cmd))} ; {detail[:500]}")
    return _parse_json_output(result.stdout)


def _run_local_postclose_l2_sync(trade_date: str) -> Dict[str, object]:
    script_path = ROOT_DIR / "backend" / "scripts" / "run_postclose_l2_daily.py"
    report = _run_json_command(
        [
            LOCAL_PYTHON,
            str(script_path),
            "--date",
            _compact_date(trade_date),
            "--skip-cloud-merge",
            "--skip-mac-sync",
            "--json",
        ]
    )
    final_status = str(report.get("final_status") or "")
    if report.get("status") != "done" or final_status == "FAIL":
        raise RuntimeError(
            f"postclose L2 同步失败: status={report.get('status')} final_status={final_status or 'unknown'}"
        )
    return report


def _refresh_local_stock_universe_meta() -> Dict[str, object]:
    script_path = ROOT_DIR / "backend" / "scripts" / "refresh_stock_universe_meta.py"
    report = _run_json_command(
        [
            LOCAL_PYTHON,
            str(script_path),
            "--db-path",
            str(LOCAL_MARKET_DB),
            "--json",
        ]
    )
    if int(report.get("rows") or 0) <= 0:
        raise RuntimeError(f"stock_universe_meta 刷新结果异常: rows={report.get('rows')}")
    return report


def _run_local_live_postprocess(trade_date: str) -> Dict[str, object]:
    return {
        "postclose_l2": _run_local_postclose_l2_sync(trade_date),
        "stock_universe_meta": _refresh_local_stock_universe_meta(),
    }


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


def _remote_file_size(remote_path: str) -> Optional[int]:
    try:
        size, _resolved = _remote_file_stat(remote_path)
        return size
    except Exception:
        return None


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


def _upload_windows_file(local_path: Path, remote_path: str) -> Dict[str, object]:
    if not local_path.exists():
        raise FileNotFoundError(f"本地文件不存在，无法同步到 Windows: {local_path}")
    host = resolve_windows_host()
    remote_dir = str(PureWindowsPath(remote_path).parent).replace("/", "\\")
    _ssh(host, f'cmd /c if not exist "{remote_dir}" mkdir "{remote_dir}"', check=False)
    _run(["scp", str(local_path), f"{host}:{_win_scp_path(remote_path)}"])
    remote_size, resolved_remote = _remote_file_stat(remote_path)
    local_size = local_path.stat().st_size
    if remote_size != local_size:
        raise RuntimeError(f"Windows 同步后文件大小不一致: local={local_size} remote={remote_size} path={remote_path}")
    return {
        "local": str(local_path),
        "remote": resolved_remote,
        "bytes": remote_size,
    }


def _ensure_windows_heat_reference_inputs() -> Dict[str, object]:
    results: Dict[str, object] = {}
    local_theme_map = LOCAL_MARKET_HEAT_DIR / "tradable_theme_map.db"
    local_size = local_theme_map.stat().st_size if local_theme_map.exists() else 0
    remote_size = _remote_file_size(WIN_TRADABLE_THEME_DB)
    needs_sync = (not local_theme_map.exists()) or local_size <= 0
    if needs_sync:
        raise FileNotFoundError(f"Mac 正式热点主题映射库不存在或为空: {local_theme_map}")
    if remote_size != local_size:
        _progress("[heat-ref] Windows 热点主题映射库缺失或版本不一致，开始同步")
        results["tradable_theme_map"] = _upload_windows_file(local_theme_map, WIN_TRADABLE_THEME_DB)
    else:
        results["tradable_theme_map"] = {
            "local": str(local_theme_map),
            "remote": WIN_TRADABLE_THEME_DB,
            "bytes": local_size,
            "synced": False,
        }
    return results


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


def _windows_env_prefix(values: Dict[str, str]) -> str:
    return " ".join(f"set {key}={value}&&" for key, value in values.items())


def _windows_data_env(
    *,
    win_atomic_db: Optional[str] = None,
    win_selection_db: Optional[str] = None,
    win_model_index_db: Optional[str] = None,
) -> Dict[str, str]:
    env = {
        "DATA_DIR": WIN_DATA_DIR,
        "MARKET_HEAT_DIR": WIN_MARKET_HEAT_DIR,
        "FINE_THEME_HEAT_V2_DB": WIN_HEAT_V2_DB,
        "FINE_THEME_HEAT_DB": WIN_HEAT_V2_DB,
        "TRADABLE_THEME_MAP_DB": WIN_TRADABLE_THEME_DB,
        "ENABLE_ATOMIC_COMPACT_READ": "true",
    }
    if win_atomic_db:
        env["ATOMIC_MAINBOARD_DB_PATH"] = win_atomic_db
        env["ATOMIC_DB_PATH"] = win_atomic_db
        env["ATOMIC_COMPACT_DB_PATH"] = win_atomic_db
        env["MARKET_HEAT_ATOMIC_DB"] = win_atomic_db
    if win_selection_db:
        env["SELECTION_DB_PATH"] = win_selection_db
    if win_model_index_db:
        env["MODEL_INDEX_DB"] = win_model_index_db
    return env


def _run_windows_index_refresh(trade_date: str, *, win_model_index_db: str) -> Dict[str, object]:
    iso_date = _compact_to_iso(trade_date)
    _progress(f"[{trade_date}] Windows 指数刷新开始")
    cmd = (
        f"{_windows_env_prefix(_windows_data_env(win_model_index_db=win_model_index_db))} "
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\sync_model_market_index_daily.py '
        f'--out-db "{win_model_index_db}" '
        f"--source baostock --daily --lookback-days {DAILY_INDEX_LOOKBACK_DAYS} --sleep 1.2 --end-date {iso_date}"
    )
    report = _run_windows_cmd(cmd)
    _progress(f"[{trade_date}] Windows 指数刷新完成")
    return report


def _run_windows_heat_refresh(trade_date: str, *, win_atomic_db: str) -> Dict[str, object]:
    iso_date = _compact_to_iso(trade_date)
    env_prefix = _windows_env_prefix(_windows_data_env(win_atomic_db=win_atomic_db))
    _progress(f"[{trade_date}] Windows 热点长表计算开始")
    heat_v2_report = _run_windows_cmd(
        f"{env_prefix} "
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\build_fine_theme_heat_daily_v2.py '
        f"--end-date {iso_date} --days {DAILY_HEAT_LOOKBACK_DAYS}"
    )
    _progress(f"[{trade_date}] Windows 热点页面缓存刷新开始")
    cache_report = _run_windows_cmd(
        f"{env_prefix} "
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\refresh_market_heat_cache.py '
        f"--end-date {iso_date} --days {DAILY_HEAT_LOOKBACK_DAYS}"
    )
    _progress(f"[{trade_date}] Windows 热点计算完成")
    return {
        "fine_theme_heat_v2": heat_v2_report,
        "fine_heat_cache": cache_report,
    }


def _run_windows_pipeline(
    trade_date: str,
    local_run_root: Path,
    *,
    win_atomic_db: str,
    win_selection_db: str,
    win_model_feature_db: str,
    win_model_index_db: str,
) -> Dict[str, object]:
    iso_date = _compact_to_iso(trade_date)
    remote_config = _write_atomic_config(
        trade_date,
        local_run_root,
        win_atomic_db=win_atomic_db,
        win_selection_db=win_selection_db,
    )
    remote_run_dir = f"{WIN_RUN_ROOT}\\{trade_date}"
    with ThreadPoolExecutor(max_workers=2) as executor:
        atomic_future = executor.submit(
            _run_windows_cmd,
            f'"{WIN_PYTHON_EXE}" backend\\scripts\\run_atomic_backfill_windows.py --config "{remote_config}"',
        )
        index_future = executor.submit(
            _run_windows_index_refresh,
            trade_date,
            win_model_index_db=win_model_index_db,
        )
        _progress(f"[{trade_date}] Windows atomic 开始")
        atomic_report = atomic_future.result()
        index_report = index_future.result()

    _progress(f"[{trade_date}] Windows selection refresh 开始")
    selection_env = _windows_data_env(
        win_atomic_db=win_atomic_db,
        win_selection_db=win_selection_db,
        win_model_index_db=win_model_index_db,
    )
    selection_cmd = (
        f"{_windows_env_prefix(selection_env)} "
        f'set DB_PATH={WIN_PROJECT_ROOT}\\data\\market_data.db&& '
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\run_selection_research.py refresh '
        f"--start-date {iso_date} --end-date {iso_date} --skip-daily-candidates"
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        selection_future = executor.submit(_run_windows_cmd, selection_cmd)
        heat_future = executor.submit(_run_windows_heat_refresh, trade_date, win_atomic_db=win_atomic_db)
        selection_report = selection_future.result()
        heat_report = heat_future.result()

    _progress(f"[{trade_date}] Windows model_feature_store build 开始")
    feature_cmd = (
        f"{_windows_env_prefix(selection_env)} "
        f'"{WIN_PYTHON_EXE}" backend\\scripts\\build_model_feature_store.py '
        f"--date {iso_date} "
        f'--atomic-db "{win_atomic_db}" '
        f'--selection-db "{win_selection_db}" '
        f'--target-db "{win_model_feature_db}" '
        f'--index-db "{win_model_index_db}" '
        f'--heat-v2-db "{WIN_HEAT_V2_DB}" '
        f'--tradable-theme-db "{WIN_TRADABLE_THEME_DB}" '
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
        "index_report": index_report,
        "heat_report": heat_report,
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
        "remote_artifacts": {
            "model_market_index": win_model_index_db,
            "fine_theme_heat_v2": WIN_HEAT_V2_DB,
            "fine_heat_cache": ((heat_report.get("fine_heat_cache") or {}).get("cache_path") if isinstance(heat_report.get("fine_heat_cache"), dict) else None),
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
    env["DATA_DIR"] = str(LOCAL_DATA_ROOT)
    env["RESEARCH_CURRENT_ROOT"] = str(LOCAL_DATA_ROOT)
    env["LIVE_DATA_ROOT"] = str(LOCAL_LIVE_DATA_ROOT)
    env["DB_PATH"] = str(LOCAL_MARKET_DB)
    env["USER_DB_PATH"] = str(LOCAL_USER_DB)
    env["SELECTION_DB_PATH"] = str(LOCAL_SELECTION_DB)
    env["ATOMIC_MAINBOARD_DB_PATH"] = str(LOCAL_ATOMIC_DB)
    env["ATOMIC_DB_PATH"] = str(LOCAL_ATOMIC_DB)
    env["ATOMIC_COMPACT_DB_PATH"] = str(LOCAL_ATOMIC_DB)
    env["ENABLE_ATOMIC_COMPACT_READ"] = "true"
    env["SPARK_OPPORTUNITY_HEAT_DB"] = str(LOCAL_HEAT_V2_DB)
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


def _query_sum(db_path: Path, table: str, column: str, date_col: str, trade_date: str) -> int:
    if not db_path.exists():
        return 0
    iso_date = _compact_to_iso(trade_date)
    try:
        with sqlite3.connect(db_path) as conn:
            return int(
                conn.execute(
                    f"SELECT COALESCE(SUM(COALESCE({column}, 0)), 0) FROM {table} WHERE {date_col}=?",
                    (iso_date,),
                ).fetchone()[0]
                or 0
            )
    except sqlite3.Error:
        return 0


def _latest_trade_date_in_table(db_path: Path, table: str, date_col: str) -> Optional[str]:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(f"SELECT MAX({date_col}) FROM {table}").fetchone()
            value = row[0] if row else None
            return str(value) if value else None
    except sqlite3.Error:
        return None


def _query_index_verify(trade_date: str) -> Dict[str, object]:
    if not LOCAL_MODEL_INDEX_DB.exists():
        return {"trade_date": _compact_to_iso(trade_date), "row_count": 0, "index_code_count": 0}
    iso_date = _compact_to_iso(trade_date)
    try:
        with sqlite3.connect(LOCAL_MODEL_INDEX_DB) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS row_count, COUNT(DISTINCT index_code) AS index_code_count
                FROM model_market_index_daily
                WHERE trade_date=?
                """,
                (iso_date,),
            ).fetchone()
            return {
                "trade_date": iso_date,
                "row_count": int(row[0] or 0) if row else 0,
                "index_code_count": int(row[1] or 0) if row else 0,
            }
    except sqlite3.Error:
        return {"trade_date": iso_date, "row_count": 0, "index_code_count": 0}


def _query_heat_verify(trade_date: str) -> Dict[str, object]:
    iso_date = _compact_to_iso(trade_date)
    heat_row_count = 0
    if LOCAL_HEAT_V2_DB.exists():
        try:
            with sqlite3.connect(LOCAL_HEAT_V2_DB) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM fine_theme_heat_daily_v2 WHERE trade_date=?",
                    (iso_date,),
                ).fetchone()
                heat_row_count = int(row[0] or 0) if row else 0
        except sqlite3.Error:
            heat_row_count = 0

    cache_dir = LOCAL_MARKET_HEAT_DIR / "cache"
    cache_covering: List[str] = []
    latest_cache_end: Optional[str] = None
    if cache_dir.exists():
        pattern = re.compile(r"fine_heat_snapshots_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_m\d+_\d+\.json$")
        for path in cache_dir.glob("fine_heat_snapshots_*_m*_*.json"):
            match = pattern.match(path.name)
            if not match:
                continue
            start_date, end_date = match.groups()
            latest_cache_end = max(latest_cache_end, end_date) if latest_cache_end else end_date
            if start_date <= iso_date <= end_date:
                cache_covering.append(path.name)
    return {
        "trade_date": iso_date,
        "heat_row_count": heat_row_count,
        "cache_covering_count": len(cache_covering),
        "cache_files": sorted(cache_covering)[-3:],
        "latest_cache_end_date": latest_cache_end,
    }


def _verify_local(trade_date: str) -> Dict[str, object]:
    return {
        "atomic_trade_daily": _query_count(LOCAL_ATOMIC_DB, "atomic_trade_daily", "trade_date", trade_date),
        "atomic_order_daily": _query_count(LOCAL_ATOMIC_DB, "atomic_order_daily", "trade_date", trade_date),
        "atomic_book_state_daily": _query_count(LOCAL_ATOMIC_DB, "atomic_book_state_daily", "trade_date", trade_date),
        "atomic_limit_state_daily": _query_count(LOCAL_ATOMIC_DB, "atomic_limit_state_daily", "trade_date", trade_date),
        "model_market_index_daily": _query_count(LOCAL_MODEL_FEATURE_DB, "model_market_index_daily", "trade_date", trade_date),
        "model_market_state_daily_v1": _query_count(LOCAL_MODEL_FEATURE_DB, "model_market_state_daily_v1", "trade_date", trade_date),
        "model_market_state_has_index_data": _query_sum(LOCAL_MODEL_FEATURE_DB, "model_market_state_daily_v1", "has_index_data", "trade_date", trade_date),
        "selection_feature_daily": _query_count(LOCAL_SELECTION_DB, "selection_feature_daily", "trade_date", trade_date),
        "selection_signal_daily": _query_count(LOCAL_SELECTION_DB, "selection_signal_daily", "trade_date", trade_date),
        "model_feature_daily_v1": _query_count(LOCAL_MODEL_FEATURE_DB, "model_feature_daily_v1", "trade_date", trade_date),
        "model_feature_has_heat": _query_sum(LOCAL_MODEL_FEATURE_DB, "model_feature_daily_v1", "has_heat", "trade_date", trade_date),
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
    verify["market_index_daily"] = _query_index_verify(trade_date)
    verify["market_heat"] = _query_heat_verify(trade_date)
    return verify


def _is_local_complete(verify: Dict[str, object]) -> bool:
    strategy_runs = verify.get("selection_strategy_runs") if isinstance(verify, dict) else None
    index_verify = verify.get("market_index_daily") if isinstance(verify, dict) else None
    heat_verify = verify.get("market_heat") if isinstance(verify, dict) else None
    return (
        all(int((verify or {}).get(key) or 0) > 0 for key in REQUIRED_LOCAL_VERIFY_KEYS)
        and isinstance(strategy_runs, dict)
        and not strategy_runs.get("missing_source_ids")
        and isinstance(index_verify, dict)
        and int(index_verify.get("index_code_count") or 0) > 0
        and isinstance(heat_verify, dict)
        and int(heat_verify.get("heat_row_count") or 0) > 0
        and int(heat_verify.get("cache_covering_count") or 0) > 0
        and int((verify or {}).get("model_market_state_has_index_data") or 0) > 0
        and int((verify or {}).get("model_feature_has_heat") or 0) > 0
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


def run_daily(
    trade_date: str,
    *,
    dry_run: bool = False,
    skip_candidates: bool = False,
    sync_nas: bool = DEFAULT_SYNC_NAS,
    include_live_sync: bool = DEFAULT_INCLUDE_LIVE_SYNC,
) -> Dict[str, object]:
    trade_date = _compact_date(trade_date)
    local_run_root = ROOT_DIR / ".run" / "daily_new_framework" / trade_date
    local_run_root.mkdir(parents=True, exist_ok=True)
    if dry_run:
        host = WIN_HOST or (WIN_HOST_CANDIDATES[0] if WIN_HOST_CANDIDATES else "")
        win_atomic_db = WIN_ATOMIC_DB
        win_selection_db = WIN_SELECTION_DB
        win_model_feature_db = WIN_MODEL_FEATURE_DB
        win_model_index_db = WIN_MODEL_INDEX_DB
    else:
        host = resolve_windows_host()
        win_atomic_db = _resolve_windows_data_path(
            _windows_existing_path_candidates(WIN_ATOMIC_DB, DEFAULT_WIN_ATOMIC_DB_ALIAS)
        )
        win_selection_db = _resolve_windows_data_path(
            _windows_existing_path_candidates(WIN_SELECTION_DB, DEFAULT_WIN_SELECTION_DB)
        )
        win_model_feature_db = _resolve_windows_data_path(
            _windows_existing_path_candidates(
                WIN_MODEL_FEATURE_DB,
                DEFAULT_WIN_MODEL_FEATURE_DB_ALIAS,
            )
        )
        win_model_index_db = WIN_MODEL_INDEX_DB
    report: Dict[str, object] = {
        "trade_date": trade_date,
        "generated_at": _now_text(),
        "windows_host": host,
        "windows_paths": {
            "atomic_db": win_atomic_db,
            "selection_db": win_selection_db,
            "model_feature_db": win_model_feature_db,
            "model_index_db": win_model_index_db,
            "fine_theme_heat_v2_db": WIN_HEAT_V2_DB,
            "market_heat_dir": WIN_MARKET_HEAT_DIR,
            "market_root": WIN_MARKET_ROOT,
        },
        "local_paths": {
            "market_db": str(LOCAL_MARKET_DB),
            "user_db": str(LOCAL_USER_DB),
            "atomic_db": str(LOCAL_ATOMIC_DB),
            "selection_db": str(LOCAL_SELECTION_DB),
            "model_feature_db": str(LOCAL_MODEL_FEATURE_DB),
            "model_index_db": str(LOCAL_MODEL_INDEX_DB),
            "fine_theme_heat_v2_db": str(LOCAL_HEAT_V2_DB),
            "market_heat_dir": str(LOCAL_MARKET_HEAT_DIR),
            "python": LOCAL_PYTHON,
        },
    }
    if dry_run:
        report["status"] = "dry_run"
        _write_report(trade_date, report)
        return report

    _sync_required_windows_scripts()
    report["windows_reference_inputs"] = _ensure_windows_heat_reference_inputs()
    sync_context: Optional[Dict[str, object]] = None
    try:
        windows_report = _run_windows_pipeline(
            trade_date,
            local_run_root,
            win_atomic_db=win_atomic_db,
            win_selection_db=win_selection_db,
            win_model_feature_db=win_model_feature_db,
            win_model_index_db=win_model_index_db,
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
        artifact_targets = {
            "model_market_index": LOCAL_MODEL_INDEX_DB,
            "fine_theme_heat_v2": LOCAL_HEAT_V2_DB,
        }
        heat_cache_path = ((windows_report.get("remote_artifacts") or {}).get("fine_heat_cache") if isinstance(windows_report.get("remote_artifacts"), dict) else None)
        if heat_cache_path:
            artifact_targets["fine_heat_cache"] = LOCAL_MARKET_HEAT_DIR / "cache" / PureWindowsPath(str(heat_cache_path)).name
        artifact_sync_results: Dict[str, object] = {}
        for key, local_path in artifact_targets.items():
            remote_path = (windows_report.get("remote_artifacts") or {}).get(key) if isinstance(windows_report.get("remote_artifacts"), dict) else None
            if not remote_path:
                continue
            artifact_sync_results[key] = _download_windows_file(str(remote_path), Path(local_path), sync_context)
        report["artifact_sync_results"] = artifact_sync_results
        report["local_merges"] = _merge_local_deltas(trade_date, local_deltas)
        if not skip_candidates:
            report["local_daily_candidates"] = _run_local_daily_candidates(trade_date)
        report["local_verify"] = _verify_full_local(trade_date)
        ok = _is_local_complete(report["local_verify"] or {})
        if ok and include_live_sync:
            report["local_live_sync"] = _run_local_live_postprocess(trade_date)
        elif not include_live_sync:
            report["local_live_sync"] = {"status": "skipped", "reason": "skip_live_sync"}
        if ok and sync_nas:
            nas_sync = _run_nas_postprocess(
                trade_date,
                report["local_live_sync"] if isinstance(report.get("local_live_sync"), dict) else None,
            )
            report["nas_sync"] = nas_sync
            report["nas_live_sync"] = nas_sync.get("live_sync")
            report["nas_release"] = nas_sync.get("research_release")
            report["nas_snapshot"] = nas_sync.get("snapshot")
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
    sync_nas: bool = DEFAULT_SYNC_NAS,
    include_live_sync: bool = DEFAULT_INCLUDE_LIVE_SYNC,
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
        report = run_daily(
            trade_date,
            dry_run=dry_run,
            skip_candidates=skip_candidates,
            sync_nas=sync_nas,
            include_live_sync=include_live_sync,
        )
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
    parser.add_argument("--sync-nas", action="store_true", default=DEFAULT_SYNC_NAS, help="成功后把本地正式研究库发布到 NAS research/current")
    parser.add_argument("--skip-nas", action="store_true", help="本次跳过 NAS 发布")
    parser.add_argument("--skip-live-sync", action="store_true", help="本次跳过 Mac 本地 live/market_data.db 的 L2 历史补齐与 stock_universe_meta 刷新")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    sync_nas = bool(args.sync_nas and not args.skip_nas)
    include_live_sync = not bool(args.skip_live_sync)
    try:
        if args.date:
            report = run_daily(
                args.date,
                dry_run=args.dry_run,
                skip_candidates=args.skip_candidates,
                sync_nas=sync_nas,
                include_live_sync=include_live_sync,
            )
        else:
            report = run_auto_daily(
                dry_run=args.dry_run,
                skip_candidates=args.skip_candidates,
                max_candidates=args.auto_detect_limit,
                sync_nas=sync_nas,
                include_live_sync=include_live_sync,
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
