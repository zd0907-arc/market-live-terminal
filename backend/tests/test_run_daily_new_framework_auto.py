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
        conn.execute(
            """
            CREATE TABLE model_market_index_daily (
                trade_date TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO model_market_index_daily (trade_date) VALUES (?)", (trade_date,))
        conn.execute(
            """
            CREATE TABLE model_market_state_daily_v1 (
                trade_date TEXT NOT NULL,
                has_index_data INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO model_market_state_daily_v1 (trade_date, has_index_data) VALUES (?, 1)",
            (trade_date,),
        )
        conn.execute(
            """
            CREATE TABLE model_feature_daily_v1 (
                trade_date TEXT NOT NULL,
                has_heat INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO model_feature_daily_v1 (trade_date, has_heat) VALUES (?, 1)",
            (trade_date,),
        )
        conn.execute("CREATE TABLE model_feature_intraday_shape_v1 (trade_date TEXT NOT NULL)")
        conn.execute("INSERT INTO model_feature_intraday_shape_v1 (trade_date) VALUES (?)", (trade_date,))
        conn.commit()


def _wire_local_dbs(monkeypatch, tmp_path):
    monkeypatch.setattr(daily, "LOCAL_ATOMIC_DB", tmp_path / "atomic.db")
    monkeypatch.setattr(daily, "LOCAL_SELECTION_DB", tmp_path / "selection.db")
    monkeypatch.setattr(daily, "LOCAL_MODEL_FEATURE_DB", tmp_path / "model_feature.db")
    monkeypatch.setattr(daily, "LOCAL_MODEL_INDEX_DB", tmp_path / "model_index.db")
    monkeypatch.setattr(daily, "LOCAL_MARKET_HEAT_DIR", tmp_path / "market_heat")
    monkeypatch.setattr(daily, "LOCAL_HEAT_V2_DB", tmp_path / "market_heat" / "fine_theme_heat_daily_v2.db")
    monkeypatch.setattr(daily, "LOCAL_MARKET_ENVIRONMENT_GATE_DIR", tmp_path / "market_environment_gate")
    monkeypatch.setattr(daily, "REPO_MARKET_ENVIRONMENT_GATE_DIR", tmp_path / "repo_market_environment_gate")


def _create_model_index_db(path, trade_date):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE model_market_index_daily (
                index_code TEXT NOT NULL,
                trade_date TEXT NOT NULL
            )
            """
        )
        for index_code in ("000852.SH", "000905.SH", "000300.SH", "000001.SH", "399006.SZ"):
            conn.execute(
                "INSERT INTO model_market_index_daily (index_code, trade_date) VALUES (?, ?)",
                (index_code, trade_date),
            )
        conn.commit()


def _create_market_heat_artifacts(root, trade_date):
    market_heat_dir = root / "market_heat"
    cache_dir = market_heat_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(market_heat_dir / "fine_theme_heat_daily_v2.db") as conn:
        conn.execute(
            """
            CREATE TABLE fine_theme_heat_daily_v2 (
                trade_date TEXT NOT NULL,
                theme_id TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO fine_theme_heat_daily_v2 (trade_date, theme_id) VALUES (?, 'theme.a')",
            (trade_date,),
        )
        conn.commit()
    cache_path = cache_dir / f"fine_heat_snapshots_{trade_date}_{trade_date}_m5_80.json"
    cache_path.write_text('{"meta":{"end_date":"' + trade_date + '"},"snapshots":{}}', encoding="utf-8")


def _create_market_environment_gate_artifacts(root, trade_date):
    out_dir = root / "market_environment_gate"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.joinpath("market_state_daily.csv").write_text(
        "trade_date,water_score,market_regime,market_detail,market_detail_label,default_action\n"
        f"{trade_date},50,caution,caution,谨慎,观察为主\n",
        encoding="utf-8",
    )


def _stub_run_daily_dependencies(monkeypatch):
    monkeypatch.setattr(daily, "resolve_windows_host", lambda: "fake-win")
    monkeypatch.setattr(daily, "_resolve_windows_data_path", lambda candidates: str(next(iter(candidates), "")))
    monkeypatch.setattr(daily, "_sync_required_windows_scripts", lambda: None)
    monkeypatch.setattr(daily, "_ensure_windows_heat_reference_inputs", lambda: {})
    monkeypatch.setattr(
        daily,
        "_run_windows_pipeline",
        lambda *args, **kwargs: {"remote_deltas": {}, "remote_artifacts": {}},
    )
    monkeypatch.setattr(daily, "_tcp_reachable", lambda *args, **kwargs: False)
    monkeypatch.setattr(daily, "_merge_local_deltas", lambda *args, **kwargs: {})
    monkeypatch.setattr(daily, "_run_local_daily_candidates", lambda trade_date: {"trade_date": trade_date})
    monkeypatch.setattr(daily, "_verify_full_local", lambda trade_date: {"trade_date": trade_date})
    monkeypatch.setattr(daily, "_is_local_core_complete", lambda verify: True)
    monkeypatch.setattr(daily, "_is_local_complete", lambda verify: True)
    monkeypatch.setattr(
        daily,
        "_run_local_market_environment_gate",
        lambda trade_date: {"status": "generated", "target_date": trade_date, "out_dir": str(daily.LOCAL_MARKET_ENVIRONMENT_GATE_DIR)},
    )
    monkeypatch.setattr(daily, "_cleanup_sync_context", lambda sync_context: None)
    monkeypatch.setattr(daily, "_write_report", lambda *args, **kwargs: None)


def test_auto_detect_marks_date_missing_when_strategy_runs_are_absent(monkeypatch, tmp_path):
    trade_date = "2026-05-25"
    _wire_local_dbs(monkeypatch, tmp_path)
    _create_atomic_db(daily.LOCAL_ATOMIC_DB, trade_date)
    _create_selection_db(daily.LOCAL_SELECTION_DB, trade_date, source_ids=())
    _create_model_feature_db(daily.LOCAL_MODEL_FEATURE_DB, trade_date)
    _create_model_index_db(daily.LOCAL_MODEL_INDEX_DB, trade_date)
    _create_market_heat_artifacts(tmp_path, trade_date)
    _create_market_environment_gate_artifacts(tmp_path, trade_date)
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
    _create_model_index_db(daily.LOCAL_MODEL_INDEX_DB, complete_date)
    _create_market_heat_artifacts(tmp_path, complete_date)
    _create_market_environment_gate_artifacts(tmp_path, complete_date)
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
    _create_model_index_db(daily.LOCAL_MODEL_INDEX_DB, trade_date)
    _create_market_heat_artifacts(tmp_path, trade_date)
    _create_market_environment_gate_artifacts(tmp_path, trade_date)
    monkeypatch.setattr(daily, "_list_windows_market_package_dates", lambda max_candidates: ["20260525"])

    report = daily.resolve_auto_trade_dates()

    assert report["status"] == "complete"
    assert report["selected_dates"] == []
    assert report["latest_complete_date"] == "20260525"


def test_auto_detect_marks_date_missing_when_heat_or_index_artifacts_absent(monkeypatch, tmp_path):
    trade_date = "2026-05-25"
    _wire_local_dbs(monkeypatch, tmp_path)
    _create_atomic_db(daily.LOCAL_ATOMIC_DB, trade_date)
    _create_selection_db(daily.LOCAL_SELECTION_DB, trade_date, source_ids=daily.REQUIRED_SELECTION_SOURCE_IDS)
    _create_model_feature_db(daily.LOCAL_MODEL_FEATURE_DB, trade_date)
    _create_market_environment_gate_artifacts(tmp_path, trade_date)
    monkeypatch.setattr(daily, "_list_windows_market_package_dates", lambda max_candidates: ["20260525"])

    report = daily.resolve_auto_trade_dates()

    assert report["status"] == "missing"
    verify = report["checks"][0]["local_verify"]
    assert verify["market_index_daily"]["index_code_count"] == 0
    assert verify["market_heat"]["heat_row_count"] == 0


def test_run_daily_runs_market_environment_before_local_live_sync_and_nas_release(monkeypatch, tmp_path):
    _wire_local_dbs(monkeypatch, tmp_path)
    monkeypatch.setattr(daily, "LOCAL_MARKET_DB", tmp_path / "live" / "market_data.db")
    _stub_run_daily_dependencies(monkeypatch)

    calls = []

    def _fake_market_environment(trade_date):
        calls.append(("market_environment", trade_date))
        return {"status": "generated", "target_date": trade_date, "out_dir": str(daily.LOCAL_MARKET_ENVIRONMENT_GATE_DIR)}

    def _fake_live_sync(trade_date):
        calls.append(("live_sync", trade_date))
        return {"status": "ok", "postclose_l2": {"day_reports": []}}

    def _fake_nas_postprocess(trade_date, local_live_sync_report, local_market_environment_report):
        calls.append(("nas_sync", trade_date, local_live_sync_report, local_market_environment_report))
        return {
            "status": "done",
            "live_sync": {"status": "synced"},
            "market_environment_gate": {"status": "synced"},
            "research_release": {
                "status": "skipped",
                "reason": "daily_sync_focuses_on_live_and_backup",
            },
            "snapshot": {"status": "snapshotted"},
        }

    monkeypatch.setattr(daily, "_run_local_market_environment_gate", _fake_market_environment)
    monkeypatch.setattr(daily, "_run_local_live_postprocess", _fake_live_sync)
    monkeypatch.setattr(daily, "_run_nas_postprocess", _fake_nas_postprocess)

    report = daily.run_daily("20260525", sync_nas=True)

    assert report["status"] == "pass"
    assert report["local_live_sync"]["status"] == "ok"
    assert report["local_market_environment_gate"]["status"] == "generated"
    assert report["nas_live_sync"] == {"status": "synced"}
    assert report["nas_market_environment_gate"] == {"status": "synced"}
    assert report["nas_release"] == {
        "status": "skipped",
        "reason": "daily_sync_focuses_on_live_and_backup",
    }
    assert report["nas_snapshot"] == {"status": "snapshotted"}
    assert calls == [
        ("market_environment", "20260525"),
        ("live_sync", "20260525"),
        ("nas_sync", "20260525", report["local_live_sync"], report["local_market_environment_gate"]),
    ]


def test_run_daily_live_sync_failure_does_not_block_market_environment_sync(monkeypatch, tmp_path):
    _wire_local_dbs(monkeypatch, tmp_path)
    monkeypatch.setattr(daily, "LOCAL_MARKET_DB", tmp_path / "live" / "market_data.db")
    _stub_run_daily_dependencies(monkeypatch)

    calls = []

    def _fake_market_environment(trade_date):
        calls.append(("market_environment", trade_date))
        return {"status": "generated", "target_date": trade_date, "out_dir": str(daily.LOCAL_MARKET_ENVIRONMENT_GATE_DIR)}

    def _fake_live_sync(_trade_date):
        calls.append(("live_sync", _trade_date))
        raise RuntimeError("postclose failed")

    def _fake_nas_postprocess(trade_date, local_live_sync_report, local_market_environment_report):
        calls.append(("nas_sync", trade_date, local_live_sync_report, local_market_environment_report))
        return {
            "status": "done",
            "live_sync": {"status": "skipped", "reason": "missing_local_live_sync"},
            "market_environment_gate": {"status": "synced"},
            "research_release": {"status": "skipped"},
            "snapshot": {"status": "snapshotted"},
        }

    monkeypatch.setattr(daily, "_run_local_market_environment_gate", _fake_market_environment)
    monkeypatch.setattr(daily, "_run_local_live_postprocess", _fake_live_sync)
    monkeypatch.setattr(daily, "_run_nas_postprocess", _fake_nas_postprocess)

    report = daily.run_daily("20260525", sync_nas=True)

    assert report["status"] == "pass"
    assert report["local_market_environment_gate"]["status"] == "generated"
    assert report["local_live_sync"]["status"] == "failed"
    assert "postclose failed" in report["local_live_sync"]["error"]
    assert report["nas_market_environment_gate"] == {"status": "synced"}
    assert calls == [
        ("market_environment", "20260525"),
        ("live_sync", "20260525"),
        ("nas_sync", "20260525", report["local_live_sync"], report["local_market_environment_gate"]),
    ]


def test_run_daily_skip_live_sync_keeps_mainline_but_skips_postprocess(monkeypatch, tmp_path):
    _wire_local_dbs(monkeypatch, tmp_path)
    monkeypatch.setattr(daily, "LOCAL_MARKET_DB", tmp_path / "live" / "market_data.db")
    _stub_run_daily_dependencies(monkeypatch)

    calls = []

    def _fake_nas_postprocess(trade_date, local_live_sync_report, local_market_environment_report):
        calls.append(("nas_sync", trade_date, local_live_sync_report, local_market_environment_report))
        return {
            "status": "done",
            "live_sync": {"status": "skipped", "reason": "missing_local_live_sync"},
            "market_environment_gate": {"status": "synced"},
            "research_release": {
                "status": "skipped",
                "reason": "daily_sync_focuses_on_live_and_backup",
            },
            "snapshot": {"status": "snapshotted"},
        }

    monkeypatch.setattr(daily, "_run_nas_postprocess", _fake_nas_postprocess)

    report = daily.run_daily("20260525", sync_nas=True, include_live_sync=False)

    assert report["status"] == "pass"
    assert report["local_live_sync"] == {"status": "skipped", "reason": "skip_live_sync"}
    assert report["local_market_environment_gate"]["status"] == "generated"
    assert report["nas_live_sync"] == {"status": "skipped", "reason": "missing_local_live_sync"}
    assert report["nas_market_environment_gate"] == {"status": "synced"}
    assert report["nas_release"] == {
        "status": "skipped",
        "reason": "daily_sync_focuses_on_live_and_backup",
    }
    assert report["nas_snapshot"] == {"status": "snapshotted"}
    assert calls == [("nas_sync", "20260525", report["local_live_sync"], report["local_market_environment_gate"])]
