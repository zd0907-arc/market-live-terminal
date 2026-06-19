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


def test_market_heat_treats_windows_atomic_path_as_same_logical_source(monkeypatch, tmp_path):
    formal_root = tmp_path / "market-data"
    research_root = formal_root / "research" / "current"
    atomic_dir = research_root / "atomic_facts"
    atomic_dir.mkdir(parents=True, exist_ok=True)
    real_db = atomic_dir / "market_atomic_mainboard_compact_current.db"
    real_db.write_text("", encoding="utf-8")

    monkeypatch.setenv("FORMAL_MARKET_DATA_ROOT", str(formal_root))
    monkeypatch.setenv("RESEARCH_CURRENT_ROOT", str(research_root))
    monkeypatch.setenv("MARKET_HEAT_ATOMIC_DB", str(real_db))
    import backend.app.core.config as config
    import backend.app.services.market_heat as market_heat

    importlib.reload(config)
    importlib.reload(market_heat)

    snapshot = {
        "meta": {
            "trade_date": "2026-06-05",
            "atomic_db": r"D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_current.db",
        }
    }

    assert market_heat._snapshot_matches_current_sources(snapshot, "2026-06-05")


def test_market_heat_treats_nas_runtime_atomic_path_as_same_logical_source(monkeypatch, tmp_path):
    formal_root = tmp_path / "market-data"
    research_root = formal_root / "research" / "current"
    atomic_dir = research_root / "atomic_facts"
    atomic_dir.mkdir(parents=True, exist_ok=True)
    real_db = atomic_dir / "market_atomic_mainboard_compact_current.db"
    real_db.write_text("", encoding="utf-8")

    monkeypatch.setenv("FORMAL_MARKET_DATA_ROOT", str(formal_root))
    monkeypatch.setenv("RESEARCH_CURRENT_ROOT", str(research_root))
    monkeypatch.setenv("MARKET_HEAT_ATOMIC_DB", str(real_db))
    import backend.app.core.config as config
    import backend.app.services.market_heat as market_heat

    importlib.reload(config)
    importlib.reload(market_heat)

    snapshot = {
        "meta": {
            "trade_date": "2026-06-05",
            "atomic_db": "/runtime-data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db",
        }
    }

    assert market_heat._snapshot_matches_current_sources(snapshot, "2026-06-05")


def test_fine_heat_dates_include_cache_and_v2_history_when_atomic_is_latest_only(monkeypatch, tmp_path):
    formal_root = tmp_path / "market-data"
    research_root = formal_root / "research" / "current"
    atomic_dir = research_root / "atomic_facts"
    heat_dir = research_root / "market_heat"
    cache_dir = heat_dir / "cache"
    atomic_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    atomic_db = atomic_dir / "market_atomic_mainboard_compact_current.db"
    with sqlite3.connect(str(atomic_db)) as conn:
        conn.execute("CREATE TABLE atomic_trade_daily (trade_date TEXT)")
        conn.execute("INSERT INTO atomic_trade_daily VALUES ('2026-06-15')")
        conn.commit()

    heat_v2_db = heat_dir / "fine_theme_heat_daily_v2.db"
    with sqlite3.connect(str(heat_v2_db)) as conn:
        conn.execute("CREATE TABLE fine_theme_heat_daily_v2 (trade_date TEXT, theme_id TEXT)")
        conn.executemany(
            "INSERT INTO fine_theme_heat_daily_v2 VALUES (?, ?)",
            [
                ("2026-06-11", "theme_a"),
                ("2026-06-12", "theme_a"),
                ("2026-06-15", "theme_a"),
            ],
        )
        conn.commit()

    cache_payload = {
        "meta": {
            "source": "local atomic_trade_daily + canonical fine themes",
            "atomic_db": str(atomic_db),
        },
        "snapshots": {
            "2026-06-11": {"sectors": []},
            "2026-06-12": {"sectors": []},
            "2026-06-15": {"sectors": []},
        },
    }
    (cache_dir / "fine_heat_snapshots_2026-06-11_2026-06-15_m5_80.json").write_text(
        json.dumps(cache_payload),
        encoding="utf-8",
    )

    monkeypatch.setenv("FORMAL_MARKET_DATA_ROOT", str(formal_root))
    monkeypatch.setenv("RESEARCH_CURRENT_ROOT", str(research_root))
    monkeypatch.setenv("MARKET_HEAT_ATOMIC_DB", str(atomic_db))
    monkeypatch.setenv("FINE_THEME_HEAT_V2_DB", str(heat_v2_db))
    import backend.app.core.config as config
    import backend.app.services.market_heat as market_heat

    importlib.reload(config)
    importlib.reload(market_heat)

    result = market_heat.list_fine_heat_trade_dates(days=20)
    dates = {item["date"]: item for item in result["dates"]}

    assert result["latest_trade_date"] == "2026-06-15"
    assert result["latest_cached_date"] == "2026-06-15"
    assert set(dates) == {"2026-06-11", "2026-06-12", "2026-06-15"}
    assert dates["2026-06-11"]["has_cache"] is True
    assert dates["2026-06-11"]["selectable"] is True


def test_fine_theme_stock_detail_falls_back_to_live_history_when_atomic_is_latest_only(monkeypatch, tmp_path):
    formal_root = tmp_path / "market-data"
    research_root = formal_root / "research" / "current"
    heat_dir = research_root / "market_heat"
    atomic_dir = research_root / "atomic_facts"
    live_dir = formal_root / "live"
    heat_dir.mkdir(parents=True, exist_ok=True)
    atomic_dir.mkdir(parents=True, exist_ok=True)
    live_dir.mkdir(parents=True, exist_ok=True)

    atomic_db = atomic_dir / "market_atomic_mainboard_compact_current.db"
    with sqlite3.connect(str(atomic_db)) as conn:
        conn.execute("CREATE TABLE atomic_trade_daily (trade_date TEXT)")
        conn.execute("INSERT INTO atomic_trade_daily VALUES ('2026-06-15')")
        conn.commit()

    theme_db = heat_dir / "tradable_theme_map.db"
    symbols = [f"sz00000{idx}" for idx in range(1, 6)]
    with sqlite3.connect(str(theme_db)) as conn:
        conn.executescript(
            """
            CREATE TABLE clean_sector_boards (
                sector_code TEXT NOT NULL,
                sector_name TEXT NOT NULL,
                sector_type TEXT NOT NULL,
                clean_status TEXT NOT NULL,
                clean_reason TEXT,
                weight REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                PRIMARY KEY (sector_code, sector_type)
            );
            CREATE TABLE clean_stock_sector_memberships (
                symbol TEXT NOT NULL,
                name TEXT,
                sector_code TEXT NOT NULL,
                sector_name TEXT NOT NULL,
                sector_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                PRIMARY KEY (symbol, sector_code, sector_type)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO clean_sector_boards (
                sector_code, sector_name, sector_type, clean_status, source, generated_at
            ) VALUES ('BK0001', '测试主题', 'concept', 'active', 'test', '2026-06-12')
            """
        )
        for idx, symbol in enumerate(symbols, start=1):
            conn.execute(
                """
                INSERT INTO clean_stock_sector_memberships (
                    symbol, name, sector_code, sector_name, sector_type, source, generated_at
                ) VALUES (?, ?, 'BK0001', '测试主题', 'concept', 'test', '2026-06-12')
                """,
                (symbol, f"测试{idx}"),
            )
        conn.commit()

    live_db = live_dir / "market_data.db"
    with sqlite3.connect(str(live_db)) as conn:
        conn.execute(
            """
            CREATE TABLE history_daily_l2 (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                total_amount REAL,
                l2_main_net REAL,
                PRIMARY KEY (symbol, date)
            )
            """
        )
        day_rows = [
            ("sz000001", 11.0, 11.0, 10.6, 11.0, 300000000.0, 50000000.0),
            ("sz000002", 10.2, 11.0, 10.1, 10.4, 200000000.0, -10000000.0),
            ("sz000003", 10.0, 10.3, 9.9, 10.2, 100000000.0, 2000000.0),
            ("sz000004", 9.9, 10.1, 9.7, 9.8, 90000000.0, -3000000.0),
            ("sz000005", 10.1, 10.8, 10.0, 10.6, 120000000.0, 8000000.0),
        ]
        for symbol in symbols:
            conn.execute(
                """
                INSERT INTO history_daily_l2 (
                    symbol, date, open, high, low, close, total_amount, l2_main_net
                ) VALUES (?, '2026-06-11', 10, 10, 10, 10, 100000000, 0)
                """,
                (symbol,),
            )
        conn.executemany(
            """
            INSERT INTO history_daily_l2 (
                symbol, date, open, high, low, close, total_amount, l2_main_net
            ) VALUES (?, '2026-06-12', ?, ?, ?, ?, ?, ?)
            """,
            day_rows,
        )
        conn.commit()

    monkeypatch.setenv("FORMAL_MARKET_DATA_ROOT", str(formal_root))
    monkeypatch.setenv("RESEARCH_CURRENT_ROOT", str(research_root))
    monkeypatch.setenv("MARKET_HEAT_ATOMIC_DB", str(atomic_db))
    monkeypatch.setenv("TRADABLE_THEME_MAP_DB", str(theme_db))
    monkeypatch.setenv("DB_PATH", str(live_db))
    monkeypatch.setenv("MARKET_HEAT_LIVE_DB", str(live_db))
    import backend.app.core.config as config
    import backend.app.services.market_heat as market_heat

    importlib.reload(config)
    importlib.reload(market_heat)

    result = market_heat.build_fine_theme_stock_detail("fine:concept:BK0001", "2026-06-12", history_days=20)
    summary = result["stock_summary"]
    stocks = {item["symbol"]: item for item in result["stocks"]}

    assert summary["stock_count"] == 5
    assert summary["limit_up_count"] == 1
    assert summary["touch_limit_up_count"] == 2
    assert summary["broken_limit_up_count"] == 1
    assert stocks["sz000001"]["is_limit_up"] is True
    assert stocks["sz000002"]["broken_limit_up"] is True
    assert len(stocks["sz000001"]["history"]) == 2
