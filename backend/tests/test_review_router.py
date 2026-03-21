from backend.app.db.l2_history_db import (
    replace_history_5m_l2_rows,
    replace_history_daily_l2_row,
    replace_stock_universe_meta,
)
from backend.app.routers.review import get_review_data, get_review_stock_pool


def test_review_pool_filters_and_returns_bounds(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))

    replace_history_daily_l2_row(
        "sh603629",
        "2025-01-02",
        (
            "sh603629", "2025-01-02", 10.0, 10.5, 9.8, 10.2, 1000000.0,
            100.0, 80.0, 20.0, 50.0, 30.0, 20.0,
            120.0, 70.0, 50.0, 60.0, 20.0, 40.0,
            18.0, 8.0, 19.0, 9.0, 10.0, 8.0, 12.0, 7.0,
            None,
        ),
    )
    replace_history_daily_l2_row(
        "sh603629",
        "2026-03-20",
        (
            "sh603629", "2026-03-20", 11.0, 11.2, 10.8, 11.1, 1200000.0,
            110.0, 85.0, 25.0, 55.0, 35.0, 20.0,
            140.0, 75.0, 65.0, 70.0, 25.0, 45.0,
            18.0, 8.0, 20.0, 9.0, 11.0, 8.5, 13.0, 7.0,
            None,
        ),
    )
    replace_history_daily_l2_row(
        "sz000833",
        "2026-03-18",
        (
            "sz000833", "2026-03-18", 25.0, 25.5, 24.8, 25.2, 1500000.0,
            210.0, 160.0, 50.0, 80.0, 45.0, 35.0,
            240.0, 140.0, 100.0, 90.0, 35.0, 55.0,
            20.0, 9.0, 22.0, 10.0, 14.0, 10.0, 16.0, 9.0,
            None,
        ),
    )
    replace_history_daily_l2_row(
        "sz000001",
        "2026-03-18",
        (
            "sz000001", "2026-03-18", 12.0, 12.2, 11.8, 12.1, 800000.0,
            90.0, 70.0, 20.0, 40.0, 20.0, 20.0,
            110.0, 60.0, 50.0, 50.0, 15.0, 35.0,
            20.0, 8.0, 22.0, 9.0, 12.0, 8.0, 14.0, 7.0,
            None,
        ),
    )
    replace_history_daily_l2_row(
        "sh900001",
        "2026-03-18",
        (
            "sh900001", "2026-03-18", 5.0, 5.1, 4.9, 5.0, 300000.0,
            10.0, 9.0, 1.0, 5.0, 3.0, 2.0,
            12.0, 8.0, 4.0, 6.0, 2.0, 4.0,
            10.0, 5.0, 11.0, 5.0, 5.0, 5.0, 6.0, 4.0,
            None,
        ),
    )

    replace_stock_universe_meta(
        [
            ("sh603629", "利通电子", 8_800_000_000.0),
            ("sz000833", "粤桂股份", 7_600_000_000.0),
            ("sz000001", "ST平安测试", 9_900_000_000.0),
        ],
        as_of_date="2026-03-21",
        source="unit-test",
    )

    resp = get_review_stock_pool("", 10)
    assert resp.code == 200
    assert resp.data["as_of_date"] == "2026-03-21"
    assert resp.data["latest_date"] == "2026-03-20"
    assert [item["symbol"] for item in resp.data["items"]] == ["sh603629", "sz000833"]
    assert resp.data["items"][0]["min_date"] == "2025-01-02"
    assert resp.data["items"][0]["max_date"] == "2026-03-20"
    assert resp.data["items"][0]["latest_date"] == "2026-03-20"


def test_review_data_returns_aggregated_formal_rows(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))

    replace_history_5m_l2_rows(
        "sz000833",
        "2026-03-18",
        [
            (
                "sz000833",
                "2026-03-18 09:30:00",
                "2026-03-18",
                25.0,
                25.2,
                24.9,
                25.1,
                1000000.0,
                1000.0,
                300000.0,
                180000.0,
                120000.0,
                40000.0,
                360000.0,
                150000.0,
                140000.0,
                50000.0,
                None,
            ),
            (
                "sz000833",
                "2026-03-18 09:35:00",
                "2026-03-18",
                25.1,
                25.3,
                25.0,
                25.2,
                1200000.0,
                1100.0,
                320000.0,
                200000.0,
                150000.0,
                50000.0,
                380000.0,
                180000.0,
                160000.0,
                60000.0,
                None,
            ),
        ],
    )

    resp_15m = get_review_data("sz000833", "2026-03-18", "2026-03-18", "15m")
    assert resp_15m.code == 200
    assert len(resp_15m.data) == 1
    row = resp_15m.data[0]
    assert row["bucket_granularity"] == "15m"
    assert row["datetime"] == "2026-03-18 09:30:00"
    assert row["open"] == 25.0
    assert row["close"] == 25.2
    assert row["total_amount"] == 2200000.0
    assert row["l1_main_net"] == 240000.0
    assert row["l2_main_net"] == 410000.0
    assert row["source_date"] == "2026-03-18"

    replace_history_daily_l2_row(
        "sz000833",
        "2026-03-18",
        (
            "sz000833", "2026-03-18", 25.0, 25.3, 24.9, 25.2, 2200000.0,
            620000.0, 380000.0, 240000.0, 270000.0, 90000.0, 180000.0,
            740000.0, 330000.0, 410000.0, 300000.0, 110000.0, 190000.0,
            45.0, 16.0, 49.0, 18.0, 28.0, 17.0, 33.0, 15.0,
            None,
        ),
    )

    resp_daily = get_review_data("sz000833", "2026-03-18", "2026-03-18", "1d")
    assert resp_daily.code == 200
    assert len(resp_daily.data) == 1
    daily = resp_daily.data[0]
    assert daily["bucket_granularity"] == "1d"
    assert daily["datetime"] == "2026-03-18 15:00:00"
    assert daily["l1_super_net"] == 180000.0
    assert daily["l2_super_net"] == 190000.0
