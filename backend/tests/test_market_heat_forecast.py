import importlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_build_fine_theme_heat_forecast_reads_latest_version(monkeypatch, tmp_path):
    forecast_db = tmp_path / "fine_theme_heat_forecast.db"
    conn = sqlite3.connect(str(forecast_db))
    try:
        conn.executescript(
            """
            CREATE TABLE fine_theme_heat_forecast_predictions (
                trade_date TEXT NOT NULL,
                model_version TEXT NOT NULL,
                target TEXT NOT NULL,
                horizon_days INTEGER NOT NULL,
                rank_band INTEGER NOT NULL,
                theme_id TEXT NOT NULL,
                theme_name TEXT NOT NULL,
                sector_code TEXT,
                sector_type TEXT,
                current_rank INTEGER NOT NULL,
                current_hot_score REAL NOT NULL,
                probability REAL NOT NULL,
                score_rank INTEGER NOT NULL,
                probability_percentile REAL NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (trade_date, model_version, target, theme_id)
            );
            CREATE TABLE fine_theme_heat_forecast_runs (
                model_version TEXT PRIMARY KEY,
                train_start_date TEXT NOT NULL,
                train_end_date TEXT NOT NULL,
                validation_start_date TEXT,
                validation_end_date TEXT,
                prediction_date TEXT NOT NULL,
                feature_columns_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                model_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fine_theme_heat_forecast_runs
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "model_a",
                "2025-01-02",
                "2026-05-06",
                "2026-02-25",
                "2026-05-06",
                "2026-05-13",
                json.dumps(["rank_today", "hot_score"]),
                json.dumps({"future_mainline_extension_5d": {"precision_at_5": 0.5}}),
                "/tmp/model.joblib",
                "2026-05-14T00:00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO fine_theme_heat_forecast_predictions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-13",
                "model_a",
                "future_mainline_extension_5d",
                5,
                15,
                "fine:concept:BK0001",
                "测试主题",
                "BK0001",
                "concept",
                12,
                88.8,
                0.73,
                1,
                1.0,
                "2026-05-14T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("FINE_THEME_HEAT_FORECAST_DB", str(forecast_db))
    import backend.app.services.market_heat as market_heat

    importlib.reload(market_heat)
    result = market_heat.build_fine_theme_heat_forecast("2026-05-13", "future_mainline_extension_5d", limit=5)

    assert result["meta"]["model_version"] == "model_a"
    assert result["meta"]["horizon_days"] == 5
    assert result["meta"]["rank_band"] == 15
    assert result["metrics"]["precision_at_5"] == 0.5
    assert result["items"][0]["theme_name"] == "测试主题"
    assert result["items"][0]["probability_pct"] == 73.0


def test_market_heat_treats_symlink_and_real_atomic_db_as_same_source(monkeypatch, tmp_path):
    atomic_dir = tmp_path / "research" / "current" / "atomic_facts"
    atomic_dir.mkdir(parents=True, exist_ok=True)
    real_db = atomic_dir / "market_atomic_mainboard_compact_current.db"
    real_db.write_text("", encoding="utf-8")

    legacy_root = tmp_path / "legacy-root"
    legacy_root.mkdir(parents=True, exist_ok=True)
    symlink_db = legacy_root / "market_atomic_mainboard_compact_current.db"
    symlink_db.symlink_to(real_db)

    monkeypatch.setenv("MARKET_HEAT_ATOMIC_DB", str(real_db))
    import backend.app.services.market_heat as market_heat

    importlib.reload(market_heat)

    snapshot = {
        "meta": {
            "trade_date": "2026-06-05",
            "atomic_db": str(symlink_db),
        }
    }

    assert market_heat._snapshot_matches_current_sources(snapshot, "2026-06-05")


def test_market_heat_treats_deleted_legacy_alias_and_canonical_atomic_db_as_same_source(monkeypatch, tmp_path):
    formal_root = tmp_path / "market-data"
    research_root = formal_root / "research" / "current"
    atomic_dir = research_root / "atomic_facts"
    atomic_dir.mkdir(parents=True, exist_ok=True)
    real_db = atomic_dir / "market_atomic_mainboard_compact_current.db"
    real_db.write_text("", encoding="utf-8")

    legacy_alias = formal_root / "atomic_facts" / "market_atomic_mainboard_compact_current.db"

    monkeypatch.setenv("FORMAL_MARKET_DATA_ROOT", str(formal_root))
    monkeypatch.delenv("RESEARCH_CURRENT_ROOT", raising=False)
    monkeypatch.setenv("MARKET_HEAT_ATOMIC_DB", str(real_db))
    import backend.app.core.config as config
    import backend.app.services.market_heat as market_heat

    importlib.reload(config)
    importlib.reload(market_heat)

    snapshot = {
        "meta": {
            "trade_date": "2026-06-05",
            "atomic_db": str(legacy_alias),
        }
    }

    assert market_heat._snapshot_matches_current_sources(snapshot, "2026-06-05")
