import importlib
import sqlite3
from pathlib import Path


def _reload_l2_modules(monkeypatch, db_path: Path):
    monkeypatch.setenv("DB_PATH", str(db_path))
    import backend.app.core.config as config
    import backend.app.db.l2_history_db as l2_history_db
    import backend.app.db.database as database

    importlib.reload(config)
    importlib.reload(l2_history_db)
    importlib.reload(database)
    return l2_history_db, database, config


def _seed_artifact_db(monkeypatch, artifact_path: Path, symbol: str, with_failure: bool = False):
    l2_history_db, database, _ = _reload_l2_modules(monkeypatch, artifact_path)
    database.init_db()

    rows_5m = [
        (
            symbol,
            "2026-03-16 09:30:00",
            "2026-03-16",
            10.0,
            10.2,
            9.9,
            10.1,
            100000.0,
            11.0,
            12.0,
            1.0,
            2.0,
            21.0,
            22.0,
            3.0,
            4.0,
            "L2 买边单边回退，数值可能偏小" if with_failure else None,
        )
    ]
    row_daily = (
        symbol, "2026-03-16", 10.0, 10.5, 9.8, 10.2, 500000.0,
        11.0, 12.0, -1.0, 5.0, 6.0, -1.0,
        21.0, 22.0, -1.0, 7.0, 8.0, -1.0,
        0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8,
        "L2 买边单边回退，数值可能偏小" if with_failure else None,
    )

    l2_history_db.replace_history_5m_l2_rows(symbol, "2026-03-16", rows_5m)
    l2_history_db.replace_history_daily_l2_row(symbol, "2026-03-16", row_daily)
    run_id = l2_history_db.create_l2_daily_ingest_run("2026-03-16", str(artifact_path.parent), mode="worker", message="")
    if with_failure:
        l2_history_db.add_l2_daily_ingest_failures(
            run_id,
            [(symbol, "2026-03-16", str(artifact_path), "sample failure")],
        )
    l2_history_db.finish_l2_daily_ingest_run(
        run_id,
        status="partial_done" if with_failure else "done",
        symbol_count=1,
        rows_5m=1,
        rows_daily=1,
        message="artifact seeded",
    )


def test_merge_l2_day_delta_merges_artifacts_and_failures(monkeypatch, tmp_path):
    artifact1 = tmp_path / "artifact_1.db"
    artifact2 = tmp_path / "artifact_2.db"
    live_db = tmp_path / "live.db"

    _seed_artifact_db(monkeypatch, artifact1, "sz000833", with_failure=False)
    _seed_artifact_db(monkeypatch, artifact2, "sh600519", with_failure=True)

    monkeypatch.setenv("DB_PATH", str(live_db))
    import backend.scripts.merge_l2_day_delta as merge_script

    importlib.reload(merge_script)
    report = merge_script.merge_l2_day_delta(
        trade_date="20260316",
        artifact_paths=[str(artifact1), str(artifact2)],
        db_path=str(live_db),
        source_root="unit-test",
        mode="unit-test",
    )

    conn = sqlite3.connect(live_db)
    daily_rows = conn.execute(
        "SELECT symbol, quality_info FROM history_daily_l2 WHERE date='2026-03-16' ORDER BY symbol"
    ).fetchall()
    rows_5m = conn.execute(
        "SELECT symbol FROM history_5m_l2 WHERE source_date='2026-03-16' ORDER BY symbol"
    ).fetchall()
    latest_run = conn.execute(
        "SELECT status, symbol_count, rows_5m, rows_daily FROM l2_daily_ingest_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    failure_count = conn.execute(
        "SELECT COUNT(*) FROM l2_daily_ingest_failures WHERE trade_date='2026-03-16'"
    ).fetchone()[0]
    conn.close()

    assert report["status"] == "partial_done"
    assert report["rows_5m"] == 2
    assert report["rows_daily"] == 2
    assert daily_rows == [
        ("sh600519", "L2 买边单边回退，数值可能偏小"),
        ("sz000833", None),
    ]
    assert rows_5m == [("sh600519",), ("sz000833",)]
    assert latest_run == ("partial_done", 2, 2, 2)
    assert failure_count == 1
