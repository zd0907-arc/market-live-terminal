import sqlite3
from pathlib import Path

from backend.scripts import refresh_stock_universe_meta as refresh_script


def test_fetch_stock_universe_rows_from_eastmoney(monkeypatch):
    responses = [
        {
            "data": {
                "total": 3,
                "diff": [
                    {"f12": "600000", "f14": "浦发银行", "f20": 1234567890},
                    {"f12": "000001", "f14": "平安银行", "f20": 2234567890},
                ],
            }
        },
        {
            "data": {
                "diff": [
                    {"f12": "830001", "f14": "北证样本", "f20": 3234567890},
                ]
            }
        },
    ]

    def fake_fetch_json(url, params, timeout=20, retries=3):
        assert "fields" in params
        return responses.pop(0)

    monkeypatch.setattr(refresh_script, "_fetch_json", fake_fetch_json)
    as_of_date, rows, source = refresh_script.fetch_stock_universe_rows_from_eastmoney(page_size=2, include_bj=True)
    assert as_of_date
    assert source == "eastmoney.quote_clist"
    assert ("sh600000", "浦发银行", 1234567890.0) in rows
    assert ("sz000001", "平安银行", 2234567890.0) in rows
    assert ("bj830001", "北证样本", 3234567890.0) in rows


def test_fetch_stock_universe_rows_from_local_snapshot_prefers_company_profile(tmp_path: Path):
    market_db = tmp_path / "market_data.db"
    selection_db = tmp_path / "selection_research.db"

    market_conn = sqlite3.connect(str(market_db))
    try:
        market_conn.executescript(
            """
            CREATE TABLE stock_company_profiles (
                symbol TEXT,
                company_name TEXT,
                short_name TEXT
            );
            INSERT INTO stock_company_profiles(symbol, company_name, short_name)
            VALUES ('sh600000', '浦发银行股份有限公司', '浦发银行');
            """
        )
        market_conn.commit()
    finally:
        market_conn.close()

    selection_conn = sqlite3.connect(str(selection_db))
    try:
        selection_conn.executescript(
            """
            CREATE TABLE selection_feature_daily (
                symbol TEXT,
                trade_date TEXT,
                name TEXT,
                market_cap REAL
            );
            INSERT INTO selection_feature_daily(symbol, trade_date, name, market_cap)
            VALUES
              ('sh600000', '2026-06-08', 'sh600000', NULL),
              ('sz000001', '2026-06-08', '平安银行', 2234567890);
            """
        )
        selection_conn.commit()
    finally:
        selection_conn.close()

    as_of_date, rows, source = refresh_script.fetch_stock_universe_rows_from_local_snapshot(
        market_db_path=market_db,
        selection_db_path=selection_db,
    )
    row_map = {symbol: (name, market_cap) for symbol, name, market_cap in rows}
    assert as_of_date == "2026-06-08"
    assert source == "local.selection_feature_daily"
    assert row_map["sh600000"] == ("浦发银行", 0.0)
    assert row_map["sz000001"] == ("平安银行", 2234567890.0)
