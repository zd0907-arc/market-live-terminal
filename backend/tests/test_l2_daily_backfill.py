import sqlite3
from pathlib import Path

from backend.scripts.l2_daily_backfill import backfill_day_package


def _write_csv(path: Path, content: str) -> None:
    path.write_text(content, encoding="gb18030")


def _build_sample_day(root: Path) -> Path:
    symbol_dir = root / "202603" / "20260311" / "000833.SZ"
    symbol_dir.mkdir(parents=True)
    _write_csv(
        symbol_dir / "行情.csv",
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,成交价,成交量,成交额,成交笔数,IOPV,成交标志,BS标志,当日累计成交量",
                "000833.SZ,000833,20260311,93000000,250000,1000,25000,10,0,,,1000",
            ]
        ),
    )
    _write_csv(
        symbol_dir / "逐笔委托.csv",
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,委托编号,交易所委托号,委托类型,委托代码,委托价格,委托数量",
                "000833.SZ,000833,20260311,93000000,1,1001,0,B,250000,10000",
                "000833.SZ,000833,20260311,93000000,2,2001,0,S,250000,10000",
                "000833.SZ,000833,20260311,93020000,5,1001,1,B,0,2000",
                "000833.SZ,000833,20260311,93020000,6,2001,1,S,0,1000",
                "000833.SZ,000833,20260311,93500000,3,1002,0,B,251000,30000",
                "000833.SZ,000833,20260311,93500000,4,2002,0,S,251000,30000",
                "000833.SZ,000833,20260311,93510000,7,2002,U,S,0,3000",
            ]
        ),
    )
    _write_csv(
        symbol_dir / "逐笔成交.csv",
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,成交编号,成交代码,委托代码,BS标志,成交价格,成交数量,叫卖序号,叫买序号",
                "000833.SZ,000833,20260311,93000000,1,C,0,B,250000,10000,2001,1001",
                "000833.SZ,000833,20260311,93010000,2,C,0,S,250000,10000,2001,1001",
                "000833.SZ,000833,20260311,93500000,3,C,0,B,251000,30000,2002,1002",
                "000833.SZ,000833,20260311,93520000,4,C,0,S,251000,30000,2002,1002",
            ]
        ),
    )
    return root / "202603" / "20260311"


def test_l2_daily_backfill_writes_5m_and_daily(monkeypatch, tmp_path):
    db_path = tmp_path / "market_data.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    package_path = _build_sample_day(tmp_path)

    report = backfill_day_package(package_path, mode="unit-test")

    assert report["trade_date"] == "2026-03-11"
    assert report["success_symbols"] == 1
    assert report["failed_symbols"] == 0
    assert report["rows_5m"] == 2
    assert report["rows_daily"] == 1

    conn = sqlite3.connect(db_path)
    rows_5m = conn.execute(
        """
        SELECT
            symbol, datetime, total_amount, total_volume,
            l2_main_buy, l2_main_sell,
            l2_add_buy_amount, l2_add_sell_amount,
            l2_cancel_buy_amount, l2_cancel_sell_amount,
            l2_cvd_delta, l2_oib_delta
        FROM history_5m_l2 ORDER BY datetime
        """
    ).fetchall()
    row_daily = conn.execute(
        "SELECT symbol, date, total_amount, l1_activity_ratio, l2_activity_ratio FROM history_daily_l2"
    ).fetchone()
    run_row = conn.execute(
        "SELECT trade_date, status, symbol_count, rows_5m, rows_daily FROM l2_daily_ingest_runs"
    ).fetchone()
    conn.close()

    assert rows_5m[0][0] == "sz000833"
    assert rows_5m[0][1] == "2026-03-11 09:30:00"
    assert rows_5m[0][2] == 500000.0
    assert rows_5m[0][3] == 20000.0
    assert rows_5m[0][6] == 250000.0
    assert rows_5m[0][7] == 250000.0
    assert rows_5m[0][8] == 50000.0
    assert rows_5m[0][9] == 25000.0
    assert rows_5m[0][10] == 0.0
    assert rows_5m[0][11] == -25000.0
    assert rows_5m[1][1] == "2026-03-11 09:35:00"
    assert rows_5m[1][3] == 60000.0
    assert rows_5m[1][6] == 753000.0
    assert rows_5m[1][7] == 753000.0
    assert rows_5m[1][8] == 0.0
    assert rows_5m[1][9] == 75300.0
    assert rows_5m[1][10] == 0.0
    assert rows_5m[1][11] == 75300.0
    assert row_daily == ("sz000833", "2026-03-11", 2006000.0, 100.0, 200.0)
    assert run_row == ("2026-03-11", "done", 1, 2, 1)


def test_l2_daily_backfill_dry_run_does_not_write(monkeypatch, tmp_path):
    db_path = tmp_path / "market_data.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    package_path = _build_sample_day(tmp_path)

    report = backfill_day_package(package_path, mode="unit-test", dry_run=True)

    assert report["dry_run"] is True
    assert report["run_id"] is None
    assert db_path.exists() is False


def test_l2_daily_backfill_records_failure(monkeypatch, tmp_path):
    db_path = tmp_path / "market_data.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    package_path = _build_sample_day(tmp_path)
    bad_trade = package_path / "000833.SZ" / "逐笔成交.csv"
    _write_csv(
        bad_trade,
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,成交编号,成交代码,委托代码,BS标志,成交价格,成交数量,叫卖序号,叫买序号",
                "000833.SZ,000833,20260311,93000000,1,C,0,B,250000,1000,9999,8888",
            ]
        ),
    )

    report = backfill_day_package(package_path, mode="unit-test")

    assert report["success_symbols"] == 0
    assert report["failed_symbols"] == 1

    conn = sqlite3.connect(db_path)
    failure_row = conn.execute(
        "SELECT trade_date, symbol, error_message FROM l2_daily_ingest_failures"
    ).fetchone()
    run_row = conn.execute(
        "SELECT trade_date, status, symbol_count FROM l2_daily_ingest_runs"
    ).fetchone()
    conn.close()

    assert failure_row[0] == "2026-03-11"
    assert failure_row[1] == "sz000833"
    assert "OrderID 无法在逐笔委托中对齐" in failure_row[2]
    assert run_row == ("2026-03-11", "partial_done", 0)


def test_l2_daily_backfill_allows_partial_order_alignment(monkeypatch, tmp_path):
    db_path = tmp_path / "market_data.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    package_path = _build_sample_day(tmp_path)
    trade_path = package_path / "000833.SZ" / "逐笔成交.csv"
    _write_csv(
        trade_path,
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,成交编号,成交代码,委托代码,BS标志,成交价格,成交数量,叫卖序号,叫买序号",
                "000833.SZ,000833,20260311,93000000,1,C,0,B,250000,10000,2001,1001",
                "000833.SZ,000833,20260311,93010000,2,C,0,S,250000,10000,9999,1001",
            ]
        ),
    )

    report = backfill_day_package(package_path, mode="unit-test")

    assert report["success_symbols"] == 1
    assert report["failed_symbols"] == 0

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT l2_main_buy, l2_main_sell FROM history_5m_l2 WHERE symbol='sz000833' AND source_date='2026-03-11'"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] > 0
    assert row[1] > 0


def test_l2_daily_backfill_allows_single_side_zero_overlap(monkeypatch, tmp_path):
    db_path = tmp_path / "market_data.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    package_path = _build_sample_day(tmp_path)
    trade_path = package_path / "000833.SZ" / "逐笔成交.csv"
    _write_csv(
        trade_path,
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,成交编号,成交代码,委托代码,BS标志,成交价格,成交数量,叫卖序号,叫买序号",
                "000833.SZ,000833,20260311,93000000,1,C,0,B,250000,10000,2001,9991",
                "000833.SZ,000833,20260311,93010000,2,C,0,B,250000,10000,2001,9991",
                "000833.SZ,000833,20260311,93500000,3,C,0,B,251000,30000,2002,9992",
                "000833.SZ,000833,20260311,93520000,4,C,0,B,251000,30000,2002,9992",
            ]
        ),
    )

    report = backfill_day_package(package_path, mode="unit-test")

    assert report["success_symbols"] == 1
    assert report["failed_symbols"] == 0

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT datetime, l2_main_buy, l2_main_sell, quality_info FROM history_5m_l2 WHERE symbol='sz000833' ORDER BY datetime"
    ).fetchall()
    daily_row = conn.execute(
        "SELECT quality_info FROM history_daily_l2 WHERE symbol='sz000833' AND date='2026-03-11'"
    ).fetchone()
    conn.close()

    assert len(rows) == 2
    assert rows[0][1] > 0
    assert rows[0][2] > 0
    assert rows[0][3] is not None
    assert rows[1][1] > 0
    assert rows[1][2] > 0
    assert daily_row is not None
    assert daily_row[0] is not None


def test_l2_daily_backfill_supports_vendor_ad_order_codes(monkeypatch, tmp_path):
    db_path = tmp_path / "market_data.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    package_path = _build_sample_day(tmp_path)
    order_path = package_path / "000833.SZ" / "逐笔委托.csv"
    _write_csv(
        order_path,
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,委托编号,交易所委托号,委托类型,委托代码,委托价格,委托数量",
                "000833.SZ,000833,20260311,93000000,1,1001,A,B,250000,10000",
                "000833.SZ,000833,20260311,93000000,2,2001,A,S,250000,10000",
                "000833.SZ,000833,20260311,93020000,5,1001,D,B,0,2000",
                "000833.SZ,000833,20260311,93020000,6,2001,D,S,0,1000",
            ]
        ),
    )

    report = backfill_day_package(package_path, mode="unit-test")

    assert report["success_symbols"] == 1
    assert report["failed_symbols"] == 0

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT
            l2_add_buy_amount, l2_add_sell_amount,
            l2_cancel_buy_amount, l2_cancel_sell_amount,
            l2_oib_delta
        FROM history_5m_l2
        WHERE symbol='sz000833' AND datetime='2026-03-11 09:30:00'
        """
    ).fetchone()
    conn.close()

    assert row == (250000.0, 250000.0, 50000.0, 25000.0, -25000.0)


def test_l2_daily_backfill_still_fails_when_both_sides_zero_overlap(monkeypatch, tmp_path):
    db_path = tmp_path / "market_data.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    package_path = _build_sample_day(tmp_path)
    bad_trade = package_path / "000833.SZ" / "逐笔成交.csv"
    _write_csv(
        bad_trade,
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,成交编号,成交代码,委托代码,BS标志,成交价格,成交数量,叫卖序号,叫买序号",
                "000833.SZ,000833,20260311,93000000,1,C,0,B,250000,10000,9999,8888",
                "000833.SZ,000833,20260311,93010000,2,C,0,S,250000,10000,9999,8888",
            ]
        ),
    )

    report = backfill_day_package(package_path, mode="unit-test")

    assert report["success_symbols"] == 0
    assert report["failed_symbols"] == 1

def test_l2_daily_backfill_records_empty_bar_review_item(monkeypatch, tmp_path):
    db_path = tmp_path / "market_data.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    package_path = _build_sample_day(tmp_path)
    trade_path = package_path / "000833.SZ" / "逐笔成交.csv"
    _write_csv(
        trade_path,
        "\n".join(
            [
                "万得代码,交易所代码,自然日,时间,成交编号,成交代码,委托代码,BS标志,成交价格,成交数量,叫卖序号,叫买序号",
                "000833.SZ,000833,20260311,08000000,1,C,0,B,250000,10000,2001,1001",
            ]
        ),
    )

    report = backfill_day_package(package_path, mode="unit-test")

    assert report["success_symbols"] == 0
    assert report["empty_symbols"] == 1
    assert report["failed_symbols"] == 1
    assert report["rows_5m"] == 0
    assert report["rows_daily"] == 0

    conn = sqlite3.connect(db_path)
    failure_row = conn.execute(
        "SELECT trade_date, symbol, error_message FROM l2_daily_ingest_failures"
    ).fetchone()
    run_row = conn.execute(
        "SELECT trade_date, status, symbol_count, rows_daily, message FROM l2_daily_ingest_runs"
    ).fetchone()
    written_5m = conn.execute("SELECT COUNT(*) FROM history_5m_l2").fetchone()[0]
    written_daily = conn.execute("SELECT COUNT(*) FROM history_daily_l2").fetchone()[0]
    conn.close()

    assert failure_row[0] == "2026-03-11"
    assert failure_row[1] == "sz000833"
    assert "无有效 bar" in failure_row[2]
    assert run_row == ("2026-03-11", "partial_done", 0, 0, "success=0, failed=1, empty=1")
    assert written_5m == 0
    assert written_daily == 0
