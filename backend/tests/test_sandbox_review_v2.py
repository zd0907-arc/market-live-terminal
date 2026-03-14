from backend.app.db.sandbox_review_v2_db import (
    create_month_run,
    ensure_sandbox_review_v2_schema,
    ensure_symbol_review_5m_schema,
    finish_month_run,
    get_latest_month_run,
    get_symbol_review_dates,
    get_stock_pool,
    query_review_bars,
    replace_stock_pool,
    symbol_has_review_date_rows,
    upsert_symbol_review_rows,
)
from backend.app.routers.sandbox_review import (
    get_sandbox_review_data,
    get_sandbox_stock_pool,
)


def test_sandbox_v2_pool_replace_and_query(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_REVIEW_V2_ROOT", str(tmp_path / "review_v2"))
    ensure_sandbox_review_v2_schema()

    count = replace_stock_pool(
        [
            ("sh600001", "测试A", 8_000_000_000),
            ("sz000001", "测试B", 12_000_000_000),
        ],
        as_of_date="2026-03-11",
        source="unit-test",
    )
    assert count == 2

    pool = get_stock_pool()
    assert pool["total"] == 2
    assert len(pool["items"]) == 2
    assert pool["items"][0]["market_cap"] >= pool["items"][1]["market_cap"]


def test_sandbox_v2_query_granularity(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_REVIEW_V2_ROOT", str(tmp_path / "review_v2"))
    ensure_symbol_review_5m_schema("sh603629")

    upsert_symbol_review_rows(
        "sh603629",
        [
            (
                "sh603629",
                "2026-01-06 09:30:00",
                10.0,
                10.2,
                9.9,
                10.1,
                1000000.0,
                300000.0,
                120000.0,
                120000.0,
                80000.0,
                500000.0,
                300000.0,
                150000.0,
                60000.0,
                "2026-01-06",
            ),
            (
                "sh603629",
                "2026-01-06 09:35:00",
                10.1,
                10.3,
                10.0,
                10.2,
                1500000.0,
                280000.0,
                100000.0,
                100000.0,
                70000.0,
                450000.0,
                250000.0,
                180000.0,
                80000.0,
                "2026-01-06",
            ),
        ],
    )

    rows_15m = query_review_bars("sh603629", "2026-01-06", "2026-01-06", "15m")
    assert len(rows_15m) == 1
    row = rows_15m[0]
    assert row["open"] == 10.0
    assert row["close"] == 10.2
    assert row["high"] == 10.3
    assert row["low"] == 9.9
    assert row["total_amount"] == 2500000.0
    assert row["l1_main_net"] == 360000.0
    assert row["l2_main_net"] == 400000.0
    assert row["bucket_granularity"] == "15m"


def test_sandbox_router_pool_and_window(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_REVIEW_V2_ROOT", str(tmp_path / "review_v2"))
    ensure_sandbox_review_v2_schema()
    replace_stock_pool(
        [("sh600111", "测试股", 9_500_000_000)],
        as_of_date="2026-03-11",
        source="unit-test",
    )

    pool_resp = get_sandbox_stock_pool("", 10)
    assert pool_resp.code == 200
    assert pool_resp.data["total"] == 1

    bad_window = get_sandbox_review_data("sh600111", "2024-12-31", "2025-01-05", "5m")
    assert bad_window.code == 400
    assert "2025-01-01" in (bad_window.message or "")


def test_sandbox_v2_review_date_resume_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_REVIEW_V2_ROOT", str(tmp_path / "review_v2"))
    ensure_symbol_review_5m_schema("sh603629")
    upsert_symbol_review_rows(
        "sh603629",
        [
            (
                "sh603629",
                "2026-02-03 09:30:00",
                10.0,
                10.1,
                9.9,
                10.0,
                1000000.0,
                200000.0,
                100000.0,
                0.0,
                0.0,
                300000.0,
                120000.0,
                0.0,
                0.0,
                "2026-02-03",
            )
        ],
    )

    assert symbol_has_review_date_rows("sh603629", "2026-02-03") is True
    assert symbol_has_review_date_rows("sh603629", "2026-02-04") is False
    assert get_symbol_review_dates("sh603629", "2026-02-01", "2026-02-28") == {"2026-02-03"}


def test_sandbox_v2_month_run_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_REVIEW_V2_ROOT", str(tmp_path / "review_v2"))
    ensure_sandbox_review_v2_schema()
    month_run_id = create_month_run(
        month="2026-02",
        workers=12,
        trade_day_count=20,
        symbol_count=2788,
        message="unit-test",
    )
    finish_month_run(
        month_run_id=month_run_id,
        status="done",
        total_rows=1234,
        failed_count=0,
        message="ok",
    )

    import sqlite3
    db_path = tmp_path / "review_v2" / "meta.db"
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT month,status,total_rows,failed_count FROM sandbox_backfill_month_runs WHERE id=?",
        (month_run_id,),
    ).fetchone()
    conn.close()
    assert row == ("2026-02", "done", 1234, 0)


def test_sandbox_v2_get_latest_month_run(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_REVIEW_V2_ROOT", str(tmp_path / "review_v2"))
    ensure_sandbox_review_v2_schema()
    first_id = create_month_run(
        month="2026-01",
        workers=8,
        trade_day_count=22,
        symbol_count=100,
        message="first",
    )
    finish_month_run(
        month_run_id=first_id,
        status="failed",
        total_rows=10,
        failed_count=2,
        message="first failed",
    )
    second_id = create_month_run(
        month="2026-01",
        workers=12,
        trade_day_count=22,
        symbol_count=100,
        message="second",
    )
    finish_month_run(
        month_run_id=second_id,
        status="done",
        total_rows=20,
        failed_count=0,
        message="second ok",
    )

    latest = get_latest_month_run("2026-01")
    assert latest is not None
    assert latest["id"] == second_id
    assert latest["status"] == "done"
    assert latest["total_rows"] == 20


def test_sandbox_v2_run_all_months_helpers():
    from backend.scripts.sandbox_review_v2_run_all_months import _clip_month_window, _month_range_desc

    assert _month_range_desc("2025-01-01", "2025-03-31") == ["2025-03", "2025-02", "2025-01"]
    assert _clip_month_window("2025-02", "2025-01-15", "2025-02-20") == ("2025-02-01", "2025-02-20")
    assert _clip_month_window("2025-01", "2025-01-15", "2025-02-20") == ("2025-01-15", "2025-01-31")
