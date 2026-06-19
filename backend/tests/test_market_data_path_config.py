import importlib
from pathlib import Path


def test_config_prefers_live_and_research_current_roots(monkeypatch, tmp_path):
    formal_root = tmp_path / "market-data"
    live_root = formal_root / "live"
    research_root = formal_root / "research" / "current"
    (live_root / "market_data.db").parent.mkdir(parents=True, exist_ok=True)
    (research_root / "selection").mkdir(parents=True, exist_ok=True)
    (research_root / "atomic_facts").mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("LIVE_DATA_ROOT", raising=False)
    monkeypatch.delenv("RESEARCH_CURRENT_ROOT", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("USER_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_MAINBOARD_DB_PATH", raising=False)
    monkeypatch.delenv("ATOMIC_COMPACT_DB_PATH", raising=False)
    monkeypatch.setenv("FORMAL_MARKET_DATA_ROOT", str(formal_root))

    import backend.app.core.config as config

    importlib.reload(config)

    assert Path(config.LIVE_DATA_ROOT) == live_root
    assert Path(config.RESEARCH_CURRENT_ROOT) == research_root
    assert Path(config.DB_FILE) == live_root / "market_data.db"
    assert Path(config.USER_DB_FILE) == live_root / "user_data.db"
    assert Path(config.ATOMIC_FACTS_DIR) == research_root / "atomic_facts"
    assert Path(config.ARTIFACTS_ROOT) == formal_root / "artifacts"
    assert Path(config.SELECTION_ARTIFACTS_ROOT) == formal_root / "artifacts" / "selection"
    assert Path(config.RESEARCH_PAYLOADS_ROOT) == formal_root / "artifacts" / "research_payloads"
    assert Path(config.RUNS_ROOT) == formal_root / "runs"
