#!/usr/bin/env bash
set -euo pipefail

TARGET_ROOT="${1:-}"

if [ -z "$TARGET_ROOT" ]; then
  echo "usage: bash ops/nas/rewrite_market_heat_release_metadata.sh <research_release_root>" >&2
  exit 1
fi

python3 - "$TARGET_ROOT" <<'PY'
import json
import os
import sys
from pathlib import Path

root = Path(os.path.abspath(os.path.expanduser(sys.argv[1])))
if not root.exists():
    raise SystemExit(f"missing target root: {root}")

atomic_db = root / "atomic_facts" / "market_atomic_mainboard_compact_current.db"
market_heat_dir = root / "market_heat"
cache_dir = market_heat_dir / "cache"

if not atomic_db.exists():
    raise SystemExit(f"missing atomic db: {atomic_db}")
if not market_heat_dir.is_dir():
    raise SystemExit(f"missing market_heat dir: {market_heat_dir}")

rewritten = []

def rewrite_json(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        meta = payload.get("meta")
        if isinstance(meta, dict):
            meta["atomic_db"] = str(atomic_db)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            rewritten.append(str(path))

latest = market_heat_dir / "latest.json"
if latest.exists():
    rewrite_json(latest)

if cache_dir.is_dir():
    for path in sorted(cache_dir.glob("fine_heat_snapshots_*_m*_*.json")):
        rewrite_json(path)

print(json.dumps({
    "root": str(root),
    "atomic_db": str(atomic_db),
    "rewritten_count": len(rewritten),
    "rewritten_files": rewritten,
}, ensure_ascii=False, indent=2))
PY
