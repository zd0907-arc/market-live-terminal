import json
from pathlib import Path

from backend.app.services.agentic_company_research import get_agentic_company_research_artifact


def _write_run(runs_dir: Path, run_id: str, symbol: str, generated_at: str) -> None:
    ui_dir = runs_dir / run_id / "ui"
    ui_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "subject": symbol,
        "company_name": "实益达",
        "as_of_date": generated_at[:10],
        "generated_at": generated_at,
        "status": "candidate_only",
        "compact": {"path": "ui/compact.html", "title": "实益达研究摘要"},
        "full": {"path": "ui/full.html", "title": "实益达完整研究"},
        "data_path": "ui/data.json",
        "promotion_readiness": "candidate_only",
    }
    (ui_dir / "research_ui_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (ui_dir / "compact.html").write_text("<!doctype html><title>compact</title>", encoding="utf-8")
    (ui_dir / "full.html").write_text("<!doctype html><title>full</title>", encoding="utf-8")
    (ui_dir / "data.json").write_text('{"identity":{"symbol":"sz002137"}}', encoding="utf-8")


def test_get_agentic_company_research_artifact_reads_latest_matching_run(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir, "20260615-0000-sz002137-company", "sz002137", "2026-06-15T20:00:00+08:00")
    _write_run(runs_dir, "20260616-0000-sz002137-company", "002137", "2026-06-16T20:00:00+08:00")
    _write_run(runs_dir, "20260616-0000-sh600519-company", "sh600519", "2026-06-16T20:00:00+08:00")

    payload = get_agentic_company_research_artifact("sz002137", runs_dir=runs_dir)

    assert payload["available"] is True
    assert payload["run_id"] == "20260616-0000-sz002137-company"
    assert payload["compact_html"].startswith("<!doctype html>")
    assert payload["full_html"].startswith("<!doctype html>")
    assert payload["data"]["identity"]["symbol"] == "sz002137"


def test_get_agentic_company_research_artifact_blocks_manifest_path_escape(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    run_id = "20260616-0000-sz002137-company"
    ui_dir = runs_dir / run_id / "ui"
    ui_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "subject": "sz002137",
        "compact": {"path": "../secret.html"},
        "full": {"path": "ui/full.html"},
        "data_path": "ui/data.json",
    }
    (ui_dir / "research_ui_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (runs_dir / run_id / "secret.html").write_text("secret", encoding="utf-8")
    (ui_dir / "full.html").write_text("<!doctype html><title>full</title>", encoding="utf-8")
    (ui_dir / "data.json").write_text("{}", encoding="utf-8")

    payload = get_agentic_company_research_artifact("sz002137", runs_dir=runs_dir)

    assert payload["available"] is False
    assert payload["reason"] == "artifact_incomplete"
    assert payload["compact_html"] is None
