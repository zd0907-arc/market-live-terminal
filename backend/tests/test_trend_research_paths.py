from pathlib import Path

from backend.app.services import trend_research


def test_source_path_accepts_external_market_data_path(tmp_path, monkeypatch):
    market_data_root = tmp_path / "market-data"
    source = market_data_root / "artifacts" / "selection" / "long_term_trends" / "storage" / "summary.csv"
    source.parent.mkdir(parents=True)
    source.write_text("x\n", encoding="utf-8")

    monkeypatch.setattr(trend_research, "FORMAL_MARKET_DATA_ROOT", str(market_data_root))

    assert trend_research._source_path(source) == "artifacts/selection/long_term_trends/storage/summary.csv"


def test_source_path_keeps_repo_relative_path():
    source = Path(trend_research.ROOT) / "docs" / "selection" / "long_term_trends" / "README.md"

    assert trend_research._source_path(source) == "docs/selection/long_term_trends/README.md"
