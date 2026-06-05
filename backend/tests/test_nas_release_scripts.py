from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import textwrap
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_script(script_name: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["bash", f"ops/{script_name}", *args],
        cwd=ROOT_DIR,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def _create_db(path: Path, schema: str, inserts: list[tuple[str, tuple | None]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(schema)
        for sql, params in inserts or []:
            conn.execute(sql, params or ())
        conn.commit()
    finally:
        conn.close()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _create_release_root(root: Path, *, meta_atomic_db: str) -> None:
    root.mkdir(parents=True, exist_ok=True)

    _create_db(
        root / "atomic_facts" / "market_atomic_mainboard_compact_current.db",
        """
        CREATE TABLE atomic_trade_daily (trade_date TEXT);
        CREATE TABLE atomic_limit_state_daily (trade_date TEXT);
        """,
        [
            ("INSERT INTO atomic_trade_daily(trade_date) VALUES (?)", ("2026-05-28",)),
            ("INSERT INTO atomic_limit_state_daily(trade_date) VALUES (?)", ("2026-05-28",)),
        ],
    )
    _create_db(
        root / "selection" / "selection_research.db",
        """
        CREATE TABLE selection_candidate_daily (trade_date TEXT);
        CREATE TABLE selection_strategy_runs (id INTEGER PRIMARY KEY, trade_date TEXT);
        CREATE TABLE selection_feature_daily (trade_date TEXT);
        """,
        [
            ("INSERT INTO selection_candidate_daily(trade_date) VALUES (?)", ("2026-05-28",)),
            ("INSERT INTO selection_strategy_runs(trade_date) VALUES (?)", ("2026-05-28",)),
            ("INSERT INTO selection_feature_daily(trade_date) VALUES (?)", ("2026-05-28",)),
        ],
    )
    _create_db(
        root / "selection" / "model_feature_store.db",
        """
        CREATE TABLE model_feature_daily_v1 (trade_date TEXT);
        CREATE TABLE model_market_index_daily (trade_date TEXT);
        """,
        [
            ("INSERT INTO model_feature_daily_v1(trade_date) VALUES (?)", ("2026-05-28",)),
            ("INSERT INTO model_market_index_daily(trade_date) VALUES (?)", ("2026-05-28",)),
        ],
    )
    _create_db(
        root / "selection" / "model_market_index_daily.db",
        """
        CREATE TABLE model_market_index_daily (trade_date TEXT);
        """,
        [("INSERT INTO model_market_index_daily(trade_date) VALUES (?)", ("2026-05-28",))],
    )
    _create_db(
        root / "market_heat" / "fine_theme_heat_daily.db",
        """
        CREATE TABLE fine_theme_heat_daily (trade_date TEXT);
        CREATE TABLE fine_theme_member_daily (trade_date TEXT);
        """,
        [
            ("INSERT INTO fine_theme_heat_daily(trade_date) VALUES (?)", ("2026-05-28",)),
            ("INSERT INTO fine_theme_member_daily(trade_date) VALUES (?)", ("2026-05-28",)),
        ],
    )
    _create_db(
        root / "market_heat" / "fine_theme_heat_daily_v2.db",
        """
        CREATE TABLE fine_theme_heat_daily_v2 (trade_date TEXT);
        """,
        [("INSERT INTO fine_theme_heat_daily_v2(trade_date) VALUES (?)", ("2026-05-28",))],
    )
    _create_db(
        root / "market_heat" / "fine_theme_heat_forecast.db",
        """
        CREATE TABLE fine_theme_heat_forecast_predictions (prediction_date TEXT);
        CREATE TABLE fine_theme_heat_forecast_runs (prediction_date TEXT);
        """,
        [
            ("INSERT INTO fine_theme_heat_forecast_predictions(prediction_date) VALUES (?)", ("2026-05-28",)),
            ("INSERT INTO fine_theme_heat_forecast_runs(prediction_date) VALUES (?)", ("2026-05-28",)),
        ],
    )
    _create_db(
        root / "market_heat" / "stock_sector_map.db",
        """
        CREATE TABLE stock_sector_memberships (symbol TEXT);
        """,
        [("INSERT INTO stock_sector_memberships(symbol) VALUES (?)", ("sh600000",))],
    )
    _create_db(
        root / "market_heat" / "tradable_theme_map.db",
        """
        CREATE TABLE clean_sector_boards (board_code TEXT);
        CREATE TABLE clean_stock_sector_memberships (symbol TEXT);
        CREATE TABLE tradable_theme_memberships (symbol TEXT);
        """,
        [
            ("INSERT INTO clean_sector_boards(board_code) VALUES (?)", ("BK0001",)),
            ("INSERT INTO clean_stock_sector_memberships(symbol) VALUES (?)", ("sh600000",)),
            ("INSERT INTO tradable_theme_memberships(symbol) VALUES (?)", ("sh600000",)),
        ],
    )
    _create_db(
        root / "market_heat" / "hot_theme_low_position_l2_samples.db",
        """
        CREATE TABLE samples (trade_date TEXT);
        CREATE TABLE summary_json (payload TEXT);
        """,
        [
            ("INSERT INTO samples(trade_date) VALUES (?)", ("2026-05-28",)),
            ("INSERT INTO summary_json(payload) VALUES (?)", ('{"ok": true}',)),
        ],
    )

    _write_json(
        root / "market_heat" / "latest.json",
        {"meta": {"atomic_db": meta_atomic_db}, "items": []},
    )
    _write_json(root / "market_heat" / "stock_sector_map_latest.json", {"items": []})
    _write_json(root / "market_heat" / "sector_boards_latest.json", {"items": []})
    _write_json(root / "market_heat" / "tradable_theme_map_latest.json", {"items": []})
    _write_json(
        root / "market_heat" / "cache" / "fine_heat_snapshots_20260528_m1_demo.json",
        {"meta": {"atomic_db": meta_atomic_db}, "items": []},
    )
    _write_json(
        root / "market_heat" / "cache" / "fine_heat_snapshots_20260528_m2_demo.json",
        {"items": []},
    )


def _install_fake_remote_tools(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)

    _write_executable(
        bin_dir / "ssh",
        """#!/usr/bin/env bash
        set -euo pipefail
        cmd="${@: -1}"
        bash -c "$cmd"
        """,
    )
    _write_executable(
        bin_dir / "rsync",
        """#!/usr/bin/env bash
        set -euo pipefail
        files_from=""
        for arg in "$@"; do
          case "$arg" in
            --files-from=*) files_from="${arg#*=}" ;;
          esac
        done
        src="${@: -2:1}"
        dest="${@: -1}"
        dest="${dest#*:}"
        while IFS= read -r rel; do
          [ -n "$rel" ] || continue
          mkdir -p "$(dirname "$dest/$rel")"
          cp "$src/$rel" "$dest/$rel"
        done < "$files_from"
        """,
    )
    _write_executable(
        bin_dir / "scp",
        """#!/usr/bin/env bash
        set -euo pipefail
        while [ "$#" -gt 2 ]; do
          shift
        done
        src="$1"
        dest="$2"
        dest="${dest#*:}"
        mkdir -p "$(dirname "$dest")"
        cp "$src" "$dest"
        """,
    )
    _write_executable(
        bin_dir / "curl",
        """#!/usr/bin/env bash
        set -euo pipefail
        url="${@: -1}"
        case "$url" in
          */api/market_heat/fine_dashboard/refresh*)
            printf '{"ok": true, "refreshed": true}'
            ;;
          */api/health)
            printf '{"status": "ok"}'
            ;;
          */api/selection/health)
            printf '{"status": "ok"}'
            ;;
          */api/selection/daily-candidates*)
            printf '{"code": 200, "data": {"items": []}}'
            ;;
          */api/market_heat/latest)
            printf '{"code": 200, "data": {"items": []}}'
            ;;
          */api/trend-research/ideas)
            printf '{"code": 200, "data": {"items": []}}'
            ;;
          *)
            printf '{"ok": true}'
            ;;
        esac
        """,
    )


def test_build_manifest_and_local_check_for_flat_formal_root(tmp_path):
    formal_root = tmp_path / "market-data"
    _create_release_root(formal_root, meta_atomic_db="/legacy/full_reverse.db")
    run_root = tmp_path / ".run"

    env = {
        "FORMAL_MARKET_DATA_ROOT": str(formal_root),
        "RUN_ROOT": str(run_root),
    }

    build = _run_script("build_nas_research_release_manifest.sh", "test_release_flat", env=env)
    assert build.returncode == 0, build.stderr
    manifest = json.loads((run_root / "test_release_flat" / "release_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_mode"] == "formal_root_flat"
    assert manifest["member_count"] >= 12
    assert manifest["members"][0]["relative_path"].startswith(("atomic_facts/", "selection/", "market_heat/"))

    check = _run_script("check_nas_research_release.sh", str(formal_root), env=env)
    assert check.returncode == 0, check.stderr
    report = json.loads(check.stdout)
    assert report["enforce_release_metadata"] is False
    latest_meta = next(item for item in report["metadata_checks"] if item["path"].endswith("/market_heat/latest.json"))
    assert latest_meta["atomic_db"] == "/legacy/full_reverse.db"
    assert latest_meta["matches_expected"] is False


def test_rewrite_market_heat_release_metadata_updates_only_payloads_with_meta(tmp_path):
    release_root = tmp_path / "release"
    _create_release_root(release_root, meta_atomic_db="/legacy/full_reverse.db")

    result = _run_script("rewrite_market_heat_release_metadata.sh", str(release_root))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["rewritten_count"] == 2

    expected_atomic = str(release_root / "atomic_facts" / "market_atomic_mainboard_compact_current.db")
    latest = json.loads((release_root / "market_heat" / "latest.json").read_text(encoding="utf-8"))
    cache_with_meta = json.loads(
        (release_root / "market_heat" / "cache" / "fine_heat_snapshots_20260528_m1_demo.json").read_text(encoding="utf-8")
    )
    cache_without_meta = json.loads(
        (release_root / "market_heat" / "cache" / "fine_heat_snapshots_20260528_m2_demo.json").read_text(encoding="utf-8")
    )

    assert latest["meta"]["atomic_db"] == expected_atomic
    assert cache_with_meta["meta"]["atomic_db"] == expected_atomic
    assert "meta" not in cache_without_meta


def test_prepare_upload_publish_list_and_rollback_with_fake_remote(tmp_path):
    formal_root = tmp_path / "market-data"
    _create_release_root(formal_root, meta_atomic_db="/legacy/full_reverse.db")

    fake_bin = tmp_path / "fake-bin"
    _install_fake_remote_tools(fake_bin)

    nas_data_root = tmp_path / "nas-data"
    current_root = nas_data_root / "research" / "current"
    current_root.mkdir(parents=True, exist_ok=True)
    (current_root / "previous_marker.txt").write_text("old-current", encoding="utf-8")

    run_root = tmp_path / ".run"
    env = {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FORMAL_MARKET_DATA_ROOT": str(formal_root),
        "RUN_ROOT": str(run_root),
        "NAS_HOST": "fake-nas",
        "NAS_DATA_ROOT": str(nas_data_root),
        "NAS_PROJECT_ROOT": str(ROOT_DIR),
        "NAS_APP_ROOT": str(ROOT_DIR),
        "ARCHIVE_NAME": "archive_old_release",
        "FAILED_CURRENT_NAME": "failed_current_after_rollback",
    }

    prepared = _run_script("nas_prepare_research_dirs.sh", env=env)
    assert prepared.returncode == 0, prepared.stderr
    assert (nas_data_root / "live").is_dir()
    assert (nas_data_root / "research" / "staging").is_dir()
    assert (nas_data_root / "cache" / "market_heat").is_dir()

    uploaded = _run_script("upload_nas_research_release.sh", "20260602_postclose", env=env)
    assert uploaded.returncode == 0, uploaded.stderr
    staged_root = nas_data_root / "research" / "staging" / "20260602_postclose"
    assert (staged_root / "release_manifest.json").is_file()
    staged_latest = json.loads((staged_root / "market_heat" / "latest.json").read_text(encoding="utf-8"))
    assert staged_latest["meta"]["atomic_db"] == str(
        staged_root / "atomic_facts" / "market_atomic_mainboard_compact_current.db"
    )

    published = _run_script("nas_publish_research_release.sh", "20260602_postclose", env=env)
    assert published.returncode == 0, published.stderr
    published_current = nas_data_root / "research" / "current"
    assert (published_current / ".release_name").read_text(encoding="utf-8").strip() == "20260602_postclose"
    assert (nas_data_root / "research" / "archive" / "archive_old_release" / "previous_marker.txt").is_file()

    listed = _run_script("nas_list_research_releases.sh", env=env)
    assert listed.returncode == 0, listed.stderr
    assert "archive_old_release" in listed.stdout
    assert str(published_current) in listed.stdout

    rollback = _run_script("nas_rollback_research_release.sh", "archive_old_release", env=env)
    assert rollback.returncode == 0, rollback.stderr
    assert (published_current / "previous_marker.txt").is_file()
    assert (
        nas_data_root / "research" / "archive" / "failed_current_after_rollback" / ".release_name"
    ).is_file()


def test_phase_b_release_runner_prefers_research_current_and_runs_smoke_offline(tmp_path):
    formal_root = tmp_path / "market-data"
    research_current = formal_root / "research" / "current"
    _create_release_root(research_current, meta_atomic_db="/legacy/full_reverse.db")

    fake_bin = tmp_path / "fake-bin"
    _install_fake_remote_tools(fake_bin)

    nas_data_root = tmp_path / "nas-data"
    run_root = tmp_path / ".run"
    env = {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FORMAL_MARKET_DATA_ROOT": str(formal_root),
        "RUN_ROOT": str(run_root),
        "NAS_HOST": "fake-nas",
        "NAS_DATA_ROOT": str(nas_data_root),
        "NAS_PROJECT_ROOT": str(ROOT_DIR),
        "NAS_APP_ROOT": str(ROOT_DIR),
        "BACKEND_BASE_URL": "http://127.0.0.1:8000",
    }

    result = _run_script("nas_run_phase_b_release.sh", "20260602_runner", env=env)
    assert result.returncode == 0, result.stderr

    manifest = json.loads((run_root / "20260602_runner" / "release_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_mode"] == "research_current"

    current_root = nas_data_root / "research" / "current"
    assert (current_root / ".release_name").read_text(encoding="utf-8").strip() == "20260602_runner"
    current_latest = json.loads((current_root / "market_heat" / "latest.json").read_text(encoding="utf-8"))
    assert current_latest["meta"]["atomic_db"] == str(
        current_root / "atomic_facts" / "market_atomic_mainboard_compact_current.db"
    )
    assert not (nas_data_root / "research" / "staging" / "20260602_runner").exists()
    assert "phase B release flow finished" in result.stdout
    assert "== publish post-smoke ==" in result.stdout


def test_check_release_does_not_enforce_metadata_for_local_nested_research_current(tmp_path):
    formal_root = tmp_path / "market-data"
    research_current = formal_root / "research" / "current"
    _create_release_root(research_current, meta_atomic_db="/legacy/full_reverse.db")

    result = _run_script("check_nas_research_release.sh", str(formal_root))
    assert result.returncode == 0, result.stderr

    report = json.loads(result.stdout)
    assert report["source_mode"] == "formal_root_nested"
    assert report["enforce_mode"] == "auto"
    assert report["enforce_release_metadata"] is False


def test_check_release_enforces_metadata_for_published_current_with_release_marker(tmp_path):
    current_root = tmp_path / "research" / "current"
    _create_release_root(current_root, meta_atomic_db="/legacy/full_reverse.db")
    (current_root / ".release_name").write_text("20260602_postclose", encoding="utf-8")

    result = _run_script("check_nas_research_release.sh", str(current_root))
    assert result.returncode == 1

    report = json.loads(result.stdout)
    assert report["enforce_release_metadata"] is True
