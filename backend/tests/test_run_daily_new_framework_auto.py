import sqlite3

import backend.scripts.run_daily_new_framework as daily


def _create_atomic_db(path, trade_date):
    with sqlite3.connect(path) as conn:
        for table in (
            "atomic_trade_daily",
            "atomic_order_daily",
            "atomic_book_state_daily",
            "atomic_limit_state_daily",
        ):
            conn.execute(f"CREATE TABLE {table} (trade_date TEXT NOT NULL)")
            conn.execute(f"INSERT INTO {table} (trade_date) VALUES (?)", (trade_date,))
        conn.commit()


def _create_selection_db(path, trade_date, source_ids=()):
    with sqlite3.connect(path) as conn:
        for table in ("selection_feature_daily", "selection_signal_daily"):
            conn.execute(f"CREATE TABLE {table} (trade_date TEXT NOT NULL)")
            conn.execute(f"INSERT INTO {table} (trade_date) VALUES (?)", (trade_date,))
        conn.execute(
            """
            CREATE TABLE selection_strategy_runs (
                trade_date TEXT NOT NULL,
                source_id TEXT NOT NULL,
                run_status TEXT NOT NULL,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                finished_at TEXT
            )
            """
        )
        for source_id in source_ids:
            conn.execute(
                """
                INSERT INTO selection_strategy_runs (
                    trade_date, source_id, run_status, candidate_count, finished_at
                ) VALUES (?, ?, 'success', 0, CURRENT_TIMESTAMP)
                """,
                (trade_date, source_id),
            )
        conn.commit()


def _create_model_feature_db(path, trade_date):
    with sqlite3.connect(path) as conn:
        for table in ("model_feature_daily_v1", "model_feature_intraday_shape_v1"):
            conn.execute(f"CREATE TABLE {table} (trade_date TEXT NOT NULL)")
            conn.execute(f"INSERT INTO {table} (trade_date) VALUES (?)", (trade_date,))
        conn.commit()


def _wire_local_dbs(monkeypatch, tmp_path):
    monkeypatch.setattr(daily, "LOCAL_ATOMIC_DB", tmp_path / "atomic.db")
    monkeypatch.setattr(daily, "LOCAL_SELECTION_DB", tmp_path / "selection.db")
    monkeypatch.setattr(daily, "LOCAL_MODEL_FEATURE_DB", tmp_path / "model_feature.db")


def test_auto_detect_marks_date_missing_when_strategy_runs_are_absent(monkeypatch, tmp_path):
    trade_date = "2026-05-25"
    _wire_local_dbs(monkeypatch, tmp_path)
    _create_atomic_db(daily.LOCAL_ATOMIC_DB, trade_date)
    _create_selection_db(daily.LOCAL_SELECTION_DB, trade_date, source_ids=())
    _create_model_feature_db(daily.LOCAL_MODEL_FEATURE_DB, trade_date)
    monkeypatch.setattr(daily, "_list_windows_market_package_dates", lambda max_candidates: ["20260525"])

    report = daily.resolve_auto_trade_dates()

    assert report["status"] == "missing"
    assert report["selected_dates"] == ["20260525"]
    strategy_runs = report["checks"][0]["local_verify"]["selection_strategy_runs"]
    assert strategy_runs["missing_source_ids"] == daily.REQUIRED_SELECTION_SOURCE_IDS


def test_auto_detect_does_not_select_historical_missing_dates(monkeypatch, tmp_path):
    complete_date = "2026-05-25"
    historical_date = "2025-12-31"
    _wire_local_dbs(monkeypatch, tmp_path)
    _create_atomic_db(daily.LOCAL_ATOMIC_DB, complete_date)
    _create_selection_db(daily.LOCAL_SELECTION_DB, complete_date, source_ids=daily.REQUIRED_SELECTION_SOURCE_IDS)
    _create_model_feature_db(daily.LOCAL_MODEL_FEATURE_DB, complete_date)
    monkeypatch.setattr(daily, "_list_windows_market_package_dates", lambda max_candidates: ["20251231", "20260525"])

    report = daily.resolve_auto_trade_dates()

    assert report["status"] == "complete"
    assert report["missing_dates"] == ["20251231"]
    assert report["historical_missing_dates"] == ["20251231"]
    assert report["selected_dates"] == []


def test_auto_detect_noops_when_data_and_strategy_runs_are_complete(monkeypatch, tmp_path):
    trade_date = "2026-05-25"
    _wire_local_dbs(monkeypatch, tmp_path)
    _create_atomic_db(daily.LOCAL_ATOMIC_DB, trade_date)
    _create_selection_db(daily.LOCAL_SELECTION_DB, trade_date, source_ids=daily.REQUIRED_SELECTION_SOURCE_IDS)
    _create_model_feature_db(daily.LOCAL_MODEL_FEATURE_DB, trade_date)
    monkeypatch.setattr(daily, "_list_windows_market_package_dates", lambda max_candidates: ["20260525"])

    report = daily.resolve_auto_trade_dates()

    assert report["status"] == "complete"
    assert report["selected_dates"] == []
    assert report["latest_complete_date"] == "20260525"
