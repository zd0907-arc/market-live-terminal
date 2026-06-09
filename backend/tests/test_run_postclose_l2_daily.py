from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_postclose_module(monkeypatch):
    monkeypatch.setenv("L2_WIN_HOST", "fake-win")
    import backend.scripts.run_postclose_l2_daily as postclose

    return importlib.reload(postclose)


def test_resolve_windows_prepare_bat_falls_back_to_legacy_ops_layout(monkeypatch):
    postclose = _load_postclose_module(monkeypatch)

    def _fake_ssh(host, remote_command, check=True):
        if postclose.DEFAULT_WIN_PREPARE_BAT in remote_command:
            return subprocess.CompletedProcess(["ssh"], 1, "", "")
        if postclose.LEGACY_WIN_PREPARE_BAT in remote_command:
            return subprocess.CompletedProcess(["ssh"], 0, f"{postclose.LEGACY_WIN_PREPARE_BAT}\n", "")
        raise AssertionError(remote_command)

    monkeypatch.setattr(postclose, "_ssh", _fake_ssh)
    monkeypatch.setattr(postclose, "_RESOLVED_WIN_PREPARE_BAT", None)

    assert postclose._resolve_windows_prepare_bat() == postclose.LEGACY_WIN_PREPARE_BAT


def test_resolve_windows_worker_bat_prefers_nested_ops_windows_layout(monkeypatch):
    postclose = _load_postclose_module(monkeypatch)

    def _fake_ssh(host, remote_command, check=True):
        if postclose.DEFAULT_WIN_WORKER_BAT in remote_command:
            return subprocess.CompletedProcess(["ssh"], 0, f"{postclose.DEFAULT_WIN_WORKER_BAT}\n", "")
        if postclose.LEGACY_WIN_WORKER_BAT in remote_command:
            return subprocess.CompletedProcess(["ssh"], 0, f"{postclose.LEGACY_WIN_WORKER_BAT}\n", "")
        raise AssertionError(remote_command)

    monkeypatch.setattr(postclose, "_ssh", _fake_ssh)
    monkeypatch.setattr(postclose, "_RESOLVED_WIN_WORKER_BAT", None)

    assert postclose._resolve_windows_worker_bat() == postclose.DEFAULT_WIN_WORKER_BAT


def test_classify_day_report_accepts_local_only_market_sync(monkeypatch):
    postclose = _load_postclose_module(monkeypatch)

    summary = postclose._classify_day_report(
        {
            "skip_cloud_merge": True,
            "worker_results": [{"return_code": 0}],
            "local_market_merge_report": {
                "rows_daily": 3192,
                "rows_5m": 155675,
            },
        }
    )

    assert summary["final_status"] == "PASS"
    assert summary["reason"] == "local_market_sync_complete"
    assert summary["is_production_ready"] is False


def test_classify_day_report_rejects_empty_local_only_market_sync(monkeypatch):
    postclose = _load_postclose_module(monkeypatch)

    summary = postclose._classify_day_report(
        {
            "skip_cloud_merge": True,
            "worker_results": [{"return_code": 0}],
            "local_market_merge_report": {
                "rows_daily": 0,
                "rows_5m": 0,
            },
        }
    )

    assert summary["final_status"] == "FAIL"
    assert "本地 live 库未写入有效结果" in summary["reason"]
