#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-}"

if [ -z "$TARGET_DIR" ]; then
  echo "usage: bash ops/nas/check_nas_research_release.sh <release_dir_or_local_data_root>" >&2
  exit 1
fi

python3 - "$TARGET_DIR" <<'PY'
import json
import sqlite3
import os
import sys
from pathlib import Path

target = Path(os.path.abspath(os.path.expanduser(sys.argv[1])))
if not target.exists():
    raise SystemExit(f"missing target dir: {target}")

source_mode = "release_root"
if (target / "research" / "current").is_dir():
    root = target / "research" / "current"
    source_mode = "formal_root_nested"
elif (target / "atomic_facts").is_dir() and (target / "selection").is_dir():
    root = target
    source_mode = "formal_or_staging_root"
else:
    raise SystemExit(f"target dir does not look like a research release root: {target}")

enforce_mode = os.environ.get("ENFORCE_RELEASE_METADATA", "auto").strip().lower()
if enforce_mode not in {"auto", "true", "false"}:
    raise SystemExit(f"invalid ENFORCE_RELEASE_METADATA: {enforce_mode}")

if enforce_mode == "true":
    enforce_release_metadata = True
elif enforce_mode == "false":
    enforce_release_metadata = False
else:
    enforce_release_metadata = bool(
        (root / "release_manifest.json").exists()
        or target.parent.name in {"staging", "archive"}
        or ((root / ".release_name").exists() and target.name == "current")
    )

checks = [
    {
        "name": "atomic_compact_main",
        "path": root / "atomic_facts" / "market_atomic_mainboard_compact_current.db",
        "required_tables": ["atomic_trade_daily", "atomic_limit_state_daily"],
        "queries": {
            "max_trade_date": "SELECT MAX(trade_date) FROM atomic_trade_daily",
        },
    },
    {
        "name": "selection_research_main",
        "path": root / "selection" / "selection_research.db",
        "required_tables": ["selection_candidate_daily", "selection_strategy_runs", "selection_feature_daily"],
        "queries": {
            "candidate_trade_date": "SELECT MAX(trade_date) FROM selection_candidate_daily",
            "strategy_run_count": "SELECT COUNT(*) FROM selection_strategy_runs",
        },
    },
    {
        "name": "model_feature_store_main",
        "path": root / "selection" / "model_feature_store.db",
        "required_tables": ["model_feature_daily_v1", "model_market_index_daily"],
        "queries": {
            "feature_trade_date": "SELECT MAX(trade_date) FROM model_feature_daily_v1",
        },
    },
    {
        "name": "model_market_index_main",
        "path": root / "selection" / "model_market_index_daily.db",
        "required_tables": ["model_market_index_daily"],
        "queries": {
            "index_trade_date": "SELECT MAX(trade_date) FROM model_market_index_daily",
        },
    },
    {
        "name": "market_heat_v1",
        "path": root / "market_heat" / "fine_theme_heat_daily.db",
        "required_tables": ["fine_theme_heat_daily", "fine_theme_member_daily"],
        "queries": {
            "heat_v1_trade_date": "SELECT MAX(trade_date) FROM fine_theme_heat_daily",
        },
    },
    {
        "name": "market_heat_v2",
        "path": root / "market_heat" / "fine_theme_heat_daily_v2.db",
        "required_tables": ["fine_theme_heat_daily_v2"],
        "queries": {
            "heat_v2_trade_date": "SELECT MAX(trade_date) FROM fine_theme_heat_daily_v2",
        },
    },
    {
        "name": "market_heat_forecast",
        "path": root / "market_heat" / "fine_theme_heat_forecast.db",
        "required_tables": ["fine_theme_heat_forecast_predictions", "fine_theme_heat_forecast_runs"],
        "queries": {
            "forecast_prediction_date": "SELECT MAX(prediction_date) FROM fine_theme_heat_forecast_runs",
        },
    },
    {
        "name": "stock_sector_map",
        "path": root / "market_heat" / "stock_sector_map.db",
        "required_tables": ["stock_sector_memberships"],
        "queries": {
            "membership_count": "SELECT COUNT(*) FROM stock_sector_memberships",
        },
    },
    {
        "name": "tradable_theme_map",
        "path": root / "market_heat" / "tradable_theme_map.db",
        "required_tables": ["clean_sector_boards", "clean_stock_sector_memberships", "tradable_theme_memberships"],
        "queries": {
            "clean_sector_count": "SELECT COUNT(*) FROM clean_sector_boards",
        },
    },
    {
        "name": "hot_theme_low_position_l2_samples",
        "path": root / "market_heat" / "hot_theme_low_position_l2_samples.db",
        "required_tables": ["samples", "summary_json"],
        "queries": {
            "samples_trade_date": "SELECT MAX(trade_date) FROM samples",
        },
    },
]

optional_files = [
    root / "market_heat" / "latest.json",
    root / "market_heat" / "stock_sector_map_latest.json",
    root / "market_heat" / "sector_boards_latest.json",
    root / "market_heat" / "tradable_theme_map_latest.json",
]

report = {
    "target": str(target),
    "root": str(root),
    "source_mode": source_mode,
    "enforce_mode": enforce_mode,
    "enforce_release_metadata": enforce_release_metadata,
    "checks": [],
    "optional_files": [],
    "metadata_checks": [],
}

for path in optional_files:
    report["optional_files"].append({
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    })

failed = False

for item in checks:
    path = item["path"]
    row = {
        "name": item["name"],
        "path": str(path),
        "exists": path.exists(),
        "required_tables": item["required_tables"],
        "resolved_tables": [],
        "queries": {},
    }
    if not path.exists():
        row["error"] = "missing db file"
        report["checks"].append(row)
        failed = True
        continue

    conn = sqlite3.connect(str(path))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        row["resolved_tables"] = sorted(tables)
        missing_tables = [name for name in item["required_tables"] if name not in tables]
        if missing_tables:
            row["error"] = f"missing tables: {', '.join(missing_tables)}"
            failed = True
        for label, sql in item["queries"].items():
            try:
                value = conn.execute(sql).fetchone()[0]
            except Exception as exc:
                value = f"ERROR: {exc}"
                failed = True
            row["queries"][label] = value
    finally:
        conn.close()
    report["checks"].append(row)

expected_atomic = str(root / "atomic_facts" / "market_atomic_mainboard_compact_current.db")

def inspect_meta(path: Path) -> None:
    global failed
    row = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        report["metadata_checks"].append(row)
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("meta") if isinstance(payload, dict) else None
        atomic_db = meta.get("atomic_db") if isinstance(meta, dict) else None
        row["atomic_db"] = atomic_db
        row["expected_atomic_db"] = expected_atomic
        row["matches_expected"] = atomic_db == expected_atomic
        row["has_meta"] = isinstance(meta, dict)
        if enforce_release_metadata and path.name == "latest.json" and atomic_db != expected_atomic:
            failed = True
            row["error"] = "atomic_db meta mismatch"
    except Exception as exc:
        failed = True
        row["error"] = str(exc)
    report["metadata_checks"].append(row)

inspect_meta(root / "market_heat" / "latest.json")
for path in sorted((root / "market_heat" / "cache").glob("fine_heat_snapshots_*_m*_*.json"))[:5]:
    inspect_meta(path)

print(json.dumps(report, ensure_ascii=False, indent=2))

if failed:
    raise SystemExit(1)
PY
