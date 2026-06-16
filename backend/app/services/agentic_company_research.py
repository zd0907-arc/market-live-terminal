from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.services.stock_events import normalize_stock_event_symbol


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNS_DIR = REPO_ROOT / "agentic_finance_agents" / "runs"
MAX_ARTIFACT_BYTES = 2_000_000


def _safe_json_loads(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _manifest_symbol(manifest: Dict[str, Any]) -> str:
    return normalize_stock_event_symbol(
        str(manifest.get("subject") or manifest.get("symbol") or "").strip()
    ) or ""


def _resolve_artifact_path(run_dir: Path, value: Any) -> Optional[Path]:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = (run_dir / text).resolve()
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return candidate


def _read_text_artifact(path: Optional[Path]) -> Optional[str]:
    if not path or not path.exists() or not path.is_file():
        return None
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        return None
    return path.read_text(encoding="utf-8")


def _read_json_artifact(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if not path or not path.exists() or not path.is_file():
        return None
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        return None
    payload = _safe_json_loads(path)
    return payload or None


def _sort_key(item: Dict[str, Any]) -> tuple:
    manifest = item.get("manifest") or {}
    generated_at = str(manifest.get("generated_at") or "")
    as_of_date = str(manifest.get("as_of_date") or "")
    run_id = str(manifest.get("run_id") or item.get("run_id") or "")
    return generated_at, as_of_date, run_id


def get_agentic_company_research_artifact(
    symbol: str,
    *,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    include_html: bool = True,
) -> Dict[str, Any]:
    normalized = normalize_stock_event_symbol(symbol) or str(symbol or "").strip().lower()
    if not runs_dir.exists():
        return {"available": False, "symbol": normalized, "reason": "runs_dir_missing"}

    matches = []
    for manifest_path in runs_dir.glob("*/ui/research_ui_manifest.json"):
        run_dir = manifest_path.parents[1]
        resolved_run_dir = run_dir.resolve()
        manifest = _safe_json_loads(manifest_path)
        if not manifest:
            continue
        if _manifest_symbol(manifest) != normalized:
            continue
        run_id = str(manifest.get("run_id") or run_dir.name)
        compact_path = _resolve_artifact_path(run_dir, (manifest.get("compact") or {}).get("path"))
        full_path = _resolve_artifact_path(run_dir, (manifest.get("full") or {}).get("path"))
        data_path = _resolve_artifact_path(run_dir, manifest.get("data_path"))
        matches.append(
            {
                "available": True,
                "symbol": normalized,
                "run_id": run_id,
                "manifest": manifest,
                "artifact_paths": {
                    "compact": str(compact_path.relative_to(resolved_run_dir)) if compact_path else None,
                    "full": str(full_path.relative_to(resolved_run_dir)) if full_path else None,
                    "data": str(data_path.relative_to(resolved_run_dir)) if data_path else None,
                    "manifest": "ui/research_ui_manifest.json",
                },
                "_run_dir": run_dir,
                "_compact_path": compact_path,
                "_full_path": full_path,
                "_data_path": data_path,
            }
        )

    if not matches:
        return {"available": False, "symbol": normalized, "reason": "artifact_not_found"}

    selected = sorted(matches, key=_sort_key, reverse=True)[0]
    compact_html = _read_text_artifact(selected.pop("_compact_path")) if include_html else None
    full_html = _read_text_artifact(selected.pop("_full_path")) if include_html else None
    data = _read_json_artifact(selected.pop("_data_path"))
    selected.pop("_run_dir", None)
    selected["compact_html"] = compact_html
    selected["full_html"] = full_html
    selected["data"] = data
    selected["available"] = bool((not include_html or (compact_html and full_html)) and selected.get("manifest"))
    if not selected["available"]:
        selected["reason"] = "artifact_incomplete"
    return selected
