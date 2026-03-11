import pandas as pd

from backend.app.db.sandbox_review_db import (
    ensure_sandbox_review_schema,
    get_review_5m_bars,
    get_sandbox_review_connection,
)
from backend.app.routers.sandbox_review import (
    SandboxEtlRequest,
    get_sandbox_review_data,
    get_sandbox_review_etl_status,
    normalize_review_symbol,
    run_sandbox_review_etl,
)
from backend.scripts.sandbox_review_etl import standardize_tick_dataframe
from backend.scripts.sandbox_review_etl import detect_volume_multiplier


def test_normalize_review_symbol():
    assert normalize_review_symbol("603629") == "sh603629"
    assert normalize_review_symbol("sz000833") == "sz000833"
    assert normalize_review_symbol("SH603629") == "sh603629"


def test_sandbox_review_query(monkeypatch, tmp_path):
    sandbox_db = tmp_path / "sandbox_review_test.db"
    monkeypatch.setenv("SANDBOX_REVIEW_DB_PATH", str(sandbox_db))

    ensure_sandbox_review_schema()
    conn = get_sandbox_review_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO review_5m_bars (
                symbol, datetime, open, high, low, close,
                total_amount,
                l1_main_buy, l1_main_sell, l1_main_net,
                l1_super_buy, l1_super_sell, l1_super_net,
                l2_main_buy, l2_main_sell, l2_main_net,
                l2_super_buy, l2_super_sell, l2_super_net, source_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sh603629",
                "2026-01-02 09:30:00",
                10.0,
                10.5,
                9.8,
                10.2,
                3000000.0,
                300000.0,
                100000.0,
                200000.0,
                1000000.0,
                200000.0,
                800000.0,
                500000.0,
                450000.0,
                50000.0,
                1200000.0,
                800000.0,
                400000.0,
                "2026-01-02",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    rows = get_review_5m_bars("sh603629", "2026-01-01", "2026-01-31")
    assert len(rows) == 1
    assert rows[0]["l2_main_net"] == 50000.0

    resp = get_sandbox_review_data("603629", "2026-01-01", "2026-01-31")
    assert resp.code == 200
    assert isinstance(resp.data, list)
    assert len(resp.data) == 1
    assert "total_amount" in resp.data[0]


def test_sandbox_etl_status_shape():
    resp = get_sandbox_review_etl_status()
    assert resp.code == 200
    assert isinstance(resp.data, dict)
    assert "running" in resp.data
    assert "log_tail" in resp.data


def test_run_sandbox_etl_invalid_mode():
    req = SandboxEtlRequest(mode="bad", symbol="sh603629", start_date="2026-01-01", end_date="2026-01-31")
    resp = run_sandbox_review_etl(req)
    assert resp.code == 400


def test_standardize_tick_dataframe_require_order_ids():
    raw_df = pd.DataFrame(
        [
            {
                "Time": "09:30:01",
                "Price": 10.0,
                "Volume": 1000,
                "Type": "买盘",
                "Amount": 10000,
            }
        ]
    )
    df, diag = standardize_tick_dataframe(raw_df, "2026-01-02", require_order_ids=True)
    assert df.empty
    assert "fatal_error" in diag
    assert "BuyOrderID" in diag["fatal_error"]
    assert "SaleOrderID" in diag["fatal_error"]


def test_standardize_tick_dataframe_allow_missing_order_ids():
    raw_df = pd.DataFrame(
        [
            {
                "Time": "09:30:01",
                "Price": 10.0,
                "Volume": 1000,
                "Type": "买盘",
                "Amount": 10000,
            }
        ]
    )
    df, diag = standardize_tick_dataframe(raw_df, "2026-01-02", require_order_ids=False)
    assert not df.empty
    assert "fatal_error" not in diag


def test_detect_volume_multiplier_loose_share_threshold():
    # ratio100 ~= 96.8%，应识别为“股”，避免被误判成“手”导致金额放大100倍
    values = [100 * (i + 1) for i in range(97)] + [123, 287, 341]
    series = pd.Series(values)
    multiplier, reason = detect_volume_multiplier(series, "Volume")
    assert multiplier == 1
    assert "检测为股" in reason


def test_sandbox_review_dedup_repeated_days(monkeypatch, tmp_path):
    sandbox_db = tmp_path / "sandbox_review_dedup.db"
    monkeypatch.setenv("SANDBOX_REVIEW_DB_PATH", str(sandbox_db))
    ensure_sandbox_review_schema()
    conn = get_sandbox_review_connection()
    try:
        base_rows = [
            ("2026-02-11 09:30:00", "2026-02-11"),
            ("2026-02-11 09:35:00", "2026-02-11"),
            ("2026-02-23 09:30:00", "2026-02-23"),
            ("2026-02-23 09:35:00", "2026-02-23"),
        ]
        for dt, source_date in base_rows:
            # 2月23日写入与2月11日完全一致的分时数值，模拟重复日问题
            time_suffix = dt[-8:]
            if source_date == "2026-02-23":
                dt = f"2026-02-23 {time_suffix}"
            conn.execute(
                """
                INSERT OR REPLACE INTO review_5m_bars (
                    symbol, datetime, open, high, low, close,
                    total_amount,
                    l1_main_buy, l1_main_sell, l1_main_net,
                    l1_super_buy, l1_super_sell, l1_super_net,
                    l2_main_buy, l2_main_sell, l2_main_net,
                    l2_super_buy, l2_super_sell, l2_super_net, source_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "sh603629",
                    dt,
                    10.0 if time_suffix == "09:30:00" else 10.2,
                    10.3,
                    9.9,
                    10.1 if time_suffix == "09:30:00" else 10.0,
                    500000.0,
                    100000.0,
                    80000.0,
                    20000.0,
                    20000.0,
                    10000.0,
                    10000.0,
                    300000.0,
                    250000.0,
                    50000.0,
                    80000.0,
                    50000.0,
                    30000.0,
                    source_date,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    resp = get_sandbox_review_data("sh603629", "2026-02-01", "2026-02-28")
    assert resp.code == 200
    assert isinstance(resp.data, list)
    # 重复日应被剔除，仅保留2月11日两条
    assert len(resp.data) == 2
    assert all(row["source_date"] == "2026-02-11" for row in resp.data)
    assert "已剔除" in (resp.message or "")
