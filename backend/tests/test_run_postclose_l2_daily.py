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


def test_prepare_day_passes_reuse_day_root_and_seed_exclusion_to_windows_prepare(monkeypatch):
    postclose = _load_postclose_module(monkeypatch)
    commands = []

    monkeypatch.setattr(postclose, "_resolve_windows_prepare_bat", lambda: postclose.DEFAULT_WIN_PREPARE_BAT)

    def _fake_ssh(host, remote_command, check=True):
        commands.append(remote_command)
        payload = {
            "trade_date": "20260618",
            "archive_size": 1,
            "symbol_count": 1,
            "worker_count": 1,
            "reused_extract": True,
        }
        return subprocess.CompletedProcess(["ssh"], 0, postclose.json.dumps(payload), "")

    monkeypatch.setattr(postclose, "_ssh", _fake_ssh)

    report = postclose._prepare_day(
        trade_date="20260618",
        workers=8,
        stable_seconds=30,
        reuse_day_root=r"Z:\atomic_stage\daily_new_20260618\20260618\20260618",
        exclude_artifact_db=r"D:\market-live-terminal\.run\daily_new_framework\20260618\postclose_seed_l2_20260618.db",
    )

    assert report["reused_extract"] is True
    assert any("--reuse-day-root" in command for command in commands)
    assert any("--exclude-artifact-db" in command for command in commands)


def test_l2_postclose_prepare_balances_shards_by_input_size(tmp_path):
    from backend.scripts import l2_postclose_prepare_day as prepare

    trade_date = "20260618"
    market_root = tmp_path / "market"
    archive = market_root / trade_date[:6] / f"{trade_date}.7z"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"dummy")

    day_root = tmp_path / "reuse" / trade_date
    sizes = {
        "sz000001": 100,
        "sz000002": 90,
        "sz000003": 10,
        "sz000004": 10,
    }
    for symbol, size in sizes.items():
        symbol_dir = day_root / symbol
        symbol_dir.mkdir(parents=True)
        (symbol_dir / "ticks.csv").write_bytes(b"x" * size)

    report = prepare.prepare_day(
        trade_date=trade_date,
        market_root=market_root,
        stage_root=tmp_path / "stage",
        output_root=tmp_path / "out",
        workers=2,
        stable_seconds=0,
        reuse_day_root=day_root,
    )

    shard_weights = sorted(int(shard["estimated_input_bytes"]) for shard in report["shards"])
    assert report["shard_strategy"] == "input_size_balanced"
    assert shard_weights == [100, 110]
