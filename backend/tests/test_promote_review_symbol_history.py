from backend.app.db.l2_history_db import query_l2_history_5m_rows, query_l2_history_daily_rows
from backend.app.db.sandbox_review_v2_db import ensure_symbol_review_5m_schema, upsert_symbol_review_rows
from backend.scripts.promote_review_symbol_history import backfill_review_symbol_history


def test_backfill_review_symbol_history_auto_prefers_existing_symbol_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))
    monkeypatch.setenv("SANDBOX_REVIEW_V2_ROOT", str(tmp_path / "review_v2"))

    ensure_symbol_review_5m_schema("sh603629")
    upsert_symbol_review_rows(
        "sh603629",
        [
            (
                "sh603629",
                "2026-02-03 09:30:00",
                10.0,
                10.2,
                9.9,
                10.1,
                1000000.0,
                300000.0,
                180000.0,
                120000.0,
                50000.0,
                360000.0,
                150000.0,
                140000.0,
                50000.0,
                "2026-02-03",
            ),
            (
                "sh603629",
                "2026-02-03 09:35:00",
                10.1,
                10.3,
                10.0,
                10.2,
                1200000.0,
                320000.0,
                200000.0,
                150000.0,
                60000.0,
                380000.0,
                180000.0,
                160000.0,
                60000.0,
                "2026-02-03",
            ),
        ],
    )

    report = backfill_review_symbol_history(
        symbol="sh603629",
        start_date="2026-02-03",
        end_date="2026-02-03",
        mode="auto",
    )

    assert report["actual_mode"] == "promote_existing"
    assert report["trade_day_count"] == 1
    assert report["rows_5m"] == 2
    assert report["rows_daily"] == 1

    rows_5m = query_l2_history_5m_rows("sh603629", start_date="2026-02-03", end_date="2026-02-03")
    assert len(rows_5m) == 2
    assert rows_5m[0]["source_date"] == "2026-02-03"
    rows_daily = query_l2_history_daily_rows("sh603629", start_date="2026-02-03", end_date="2026-02-03")
    assert len(rows_daily) == 1
    assert rows_daily[0]["l2_main_net"] == 410000.0
