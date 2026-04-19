import importlib
import sqlite3
from pathlib import Path

import pandas as pd


def _reload_modules(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "market_data.db"))
    monkeypatch.setenv("USER_DB_PATH", str(tmp_path / "user_data.db"))
    monkeypatch.setenv("SELECTION_DB_PATH", str(tmp_path / "selection_research.db"))
    import backend.app.core.config as config
    import backend.app.db.database as database
    import backend.app.db.selection_db as selection_db
    import backend.app.services.stock_events as stock_events

    importlib.reload(config)
    importlib.reload(database)
    importlib.reload(selection_db)
    importlib.reload(stock_events)
    return config, database, selection_db, stock_events


def _seed_local_history(db_path: Path, symbol: str, days: int = 90):
    conn = sqlite3.connect(str(db_path))
    try:
        rows = []
        price = 10.0
        for idx in range(days):
            trade_date = f"2025-01-{idx + 1:02d}" if idx < 31 else f"2025-02-{idx - 30:02d}" if idx < 59 else f"2025-03-{idx - 58:02d}"
            price += 0.08
            net_inflow = 2_000_000.0 + idx * 40_000.0
            main_buy = 18_000_000.0 + idx * 50_000.0
            main_sell = max(4_000_000.0, main_buy - net_inflow)
            rows.append((symbol, trade_date, net_inflow, main_buy, main_sell, price, 0.0, 30.0, 'fixed_200k_1m_v1'))
        conn.executemany(
            "INSERT OR REPLACE INTO local_history (symbol, date, net_inflow, main_buy_amount, main_sell_amount, close, change_pct, activity_ratio, config_signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _seed_stock_meta(db_path: Path, symbol: str, name: str):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO stock_universe_meta (symbol, name, market_cap, as_of_date, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (symbol, name, 1_000_000_000.0, "2025-04-19", "unit-test", "2025-04-19 20:00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def test_stock_event_tables_created_by_init_db(monkeypatch, tmp_path):
    config, database, _selection_db, _stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    conn = sqlite3.connect(config.DB_FILE)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    stock_event_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(stock_events)").fetchall()
    }
    conn.close()

    assert "stock_events" in tables
    assert "stock_event_entities" in tables
    assert "stock_event_ingest_runs" in tables
    assert "stock_event_daily_rollup" in tables
    assert "stock_symbol_aliases" in tables
    assert "source_type" in stock_event_columns
    assert "event_subtype" in stock_event_columns
    assert "published_at" in stock_event_columns
    assert "pdf_url" in stock_event_columns


def test_sync_tushare_announcements_inserts_events_and_rollups(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    class _FakePro:
        @staticmethod
        def anns_d(**_kwargs):
            return pd.DataFrame(
                [
                    {
                        "ann_date": "20250412",
                        "ts_code": "000833.SZ",
                        "name": "粤桂股份",
                        "title": "粤桂股份:2025年年度报告",
                        "url": "https://example.com/annual.pdf",
                        "rec_time": "2025-04-12 20:30:00",
                    },
                    {
                        "ann_date": "20250412",
                        "ts_code": "000833.SZ",
                        "name": "粤桂股份",
                        "title": "粤桂股份:第九届董事会第四十三次会议决议公告",
                        "url": "https://example.com/board.pdf",
                        "rec_time": "2025-04-12 20:40:00",
                    },
                ]
            )

    monkeypatch.setattr(stock_events, "_get_tushare_pro", lambda: _FakePro())
    result = stock_events.sync_tushare_announcements(
        "sz000833",
        start_date="2025-04-01",
        end_date="2025-04-12",
        mode="unit_test",
    )

    assert result["fetched_count"] == 2
    assert result["upserted_count"] == 2

    conn = sqlite3.connect(config.DB_FILE)
    try:
        rows = conn.execute(
            "SELECT source_type, event_subtype, title, pdf_url FROM stock_events WHERE symbol = 'sz000833' ORDER BY published_at ASC"
        ).fetchall()
        rollup = conn.execute(
            "SELECT total_events, announcement_count, report_count, latest_event_time FROM stock_event_daily_rollup WHERE symbol = 'sz000833' AND trade_date = '2025-04-12'"
        ).fetchone()
    finally:
        conn.close()

    assert rows[0][0] == "report"
    assert rows[0][1] == "annual_report"
    assert rows[1][0] == "announcement"
    assert rows[1][1] == "board_resolution"
    assert rows[0][3] == "https://example.com/annual.pdf"
    assert rollup == (2, 1, 1, "2025-04-12 20:40:00")


def test_sync_public_sina_announcements_without_token(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sz000833", "粤桂股份")

    html = """
    <html><body><table><tr><td>快速通道:
    2026-04-13 <a href='/corp/view/vCB_AllBulletinDetail.php?stockid=000833&id=12081908'>粤桂股份：2026年第一季度业绩预告</a><br>
    2026-04-08 <a href='/corp/view/vCB_AllBulletinDetail.php?stockid=000833&id=12070000'>粤桂股份：关于举办2025年度网上业绩说明会的公告</a><br>
    </td></tr></table></body></html>
    """
    monkeypatch.setattr(stock_events, "_fetch_public_html", lambda _url: html)
    result = stock_events.sync_symbol_announcements("sz000833", start_date="2026-04-01", end_date="2026-04-19", mode="unit_test")

    assert result["source_mode"] == "public_fallback"
    assert result["upserted_count"] >= 2
    conn = sqlite3.connect(config.DB_FILE)
    try:
        rows = conn.execute(
            "SELECT source, source_type, title FROM stock_events WHERE symbol='sz000833' ORDER BY published_at DESC"
        ).fetchall()
    finally:
        conn.close()
    assert any(row[0] == "public_sina_announcements" and "业绩说明会" in row[2] for row in rows)


def test_sync_public_sina_announcements_supports_pagination_and_per_item_dates(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sz000833", "粤桂股份")

    page1 = """
    <html><body><div class="datelist"><ul>
    2026-04-13&nbsp;<a href='/corp/view/vCB_AllBulletinDetail.php?stockid=000833&id=12081908'>粤桂股份：2026年第一季度业绩预告</a><br>
    2026-04-08&nbsp;<a href='/corp/view/vCB_AllBulletinDetail.php?stockid=000833&id=12070000'>粤桂股份：关于举办2025年度网上业绩说明会的公告</a><br>
    </ul></div>
    <a href='http://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletin.php?stockid=000833&Page=2'>下一页</a>
    </body></html>
    """
    page2 = """
    <html><body><div class="datelist"><ul>
    2026-04-02&nbsp;<a href='/corp/view/vCB_AllBulletinDetail.php?stockid=000833&id=12060000'>粤桂股份：第九届董事会第四十三次会议决议公告</a><br>
    </ul></div></body></html>
    """

    def _fake_fetch(url: str) -> str:
        if "Page=2" in url:
            return page2
        return page1

    monkeypatch.setattr(stock_events, "_fetch_public_html", _fake_fetch)
    result = stock_events.sync_symbol_announcements("sz000833", start_date="2026-04-01", end_date="2026-04-19", mode="unit_test")

    assert result["source_mode"] == "public_fallback"
    assert result["upserted_count"] >= 3
    conn = sqlite3.connect(config.DB_FILE)
    try:
        rows = conn.execute(
            "SELECT title, substr(published_at, 1, 10) FROM stock_events WHERE symbol='sz000833' AND source='public_sina_announcements' ORDER BY published_at DESC"
        ).fetchall()
    finally:
        conn.close()
    assert ("粤桂股份：2026年第一季度业绩预告", "2026-04-13") in rows
    assert ("粤桂股份：关于举办2025年度网上业绩说明会的公告", "2026-04-08") in rows
    assert ("粤桂股份：第九届董事会第四十三次会议决议公告", "2026-04-02") in rows


def test_sync_public_sina_earnings_forecast_without_token(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sz000833", "粤桂股份")

    html = """
    <a name="2026-04-13"></a><div align="center"><strong>公告日期</strong></div></td>
    <td>2026-04-13</td>
    <tr><td><div align="center"><strong>报告期</strong></div></td><td>2026-03-31</td></tr>
    <tr><td><div align="center">类型</div></td><td>预增</td></tr>
    <tr><td><div align="center">业绩预告摘要</div></td><td>预计2026年1-3月归属于上市公司股东的净利润同比增长。</td></tr>
    <tr><td><div align="center">业绩预告内容</div></td><td>预计2026年1-3月归属于上市公司股东的净利润同比增长，主要受益于经营改善。</td></tr>
    """
    monkeypatch.setattr(stock_events, "_fetch_public_html", lambda _url: html)
    result = stock_events.sync_public_sina_earnings_forecast("sz000833", start_date="2026-04-01", end_date="2026-04-19", mode="unit_test")

    assert result["upserted_count"] == 1
    conn = sqlite3.connect(config.DB_FILE)
    try:
        row = conn.execute(
            "SELECT source, source_type, event_subtype, title, content_text FROM stock_events WHERE symbol='sz000833' AND source='public_sina_earnings_notice'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "public_sina_earnings_notice"
    assert row[1] == "report"
    assert row[2] == "earnings_forecast"
    assert "2026-03-31业绩预告" in row[3]


def test_selection_profile_timeline_includes_stock_events(monkeypatch, tmp_path):
    config, database, selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    _seed_local_history(Path(config.DB_FILE), "sz000833")

    conn = sqlite3.connect(config.DB_FILE)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO stock_events
            (event_id, source, source_type, event_subtype, symbol, ts_code, title, content_text, raw_url, pdf_url, published_at, ingested_at, importance, is_official, source_event_id, hash_digest, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt-ann-1",
                "tushare_anns_d",
                "report",
                "annual_report",
                "sz000833",
                "000833.SZ",
                "粤桂股份:2025年年度报告",
                "粤桂股份:2025年年度报告",
                "https://example.com/annual.pdf",
                "https://example.com/annual.pdf",
                "2025-03-27 20:30:00",
                "2025-03-27 20:31:00",
                95,
                1,
                "evt-ann-1",
                "digest-1",
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    import backend.app.services.selection_research as selection_research
    importlib.reload(selection_research)
    selection_db.ensure_selection_schema()
    selection_research.refresh_selection_research(start_date="2025-01-15", end_date="2025-03-27")

    payload = selection_research.get_profile("sz000833", "2025-03-27")
    assert payload["symbol"] == "sz000833"
    assert any(
        item.get("source") == "tushare_anns_d" and "年度报告" in str(item.get("content") or "")
        for item in payload.get("event_timeline", [])
    )


def test_sync_shenzhen_qa_inserts_events_and_rollups(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    class _FakePro:
        @staticmethod
        def irm_qa_sz(**_kwargs):
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000833.SZ",
                        "name": "粤桂股份",
                        "q": "请问公司一季度业绩如何？",
                        "a": "公司会按规定披露一季度报告，请关注后续公告。",
                        "pub_time": "2025-04-15 19:20:00",
                    }
                ]
            )

    monkeypatch.setattr(stock_events, "_get_tushare_pro", lambda: _FakePro())
    result = stock_events.sync_shenzhen_qa(
        "sz000833",
        start_date="2025-04-01",
        end_date="2025-04-15",
        mode="unit_test",
    )

    assert result["fetched_count"] == 1
    assert result["upserted_count"] == 1

    conn = sqlite3.connect(config.DB_FILE)
    try:
        row = conn.execute(
            "SELECT source, source_type, event_subtype, question_text, answer_text FROM stock_events WHERE symbol='sz000833'"
        ).fetchone()
        rollup = conn.execute(
            "SELECT qa_count, total_events FROM stock_event_daily_rollup WHERE symbol='sz000833' AND trade_date='2025-04-15'"
        ).fetchone()
    finally:
        conn.close()

    assert row == (
        "tushare_irm_sz",
        "qa",
        "qa_material",
        "请问公司一季度业绩如何？",
        "公司会按规定披露一季度报告，请关注后续公告。",
    )
    assert rollup == (1, 1)


def test_sync_shanghai_qa_inserts_events(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    class _FakePro:
        @staticmethod
        def irm_qa_sh(**_kwargs):
            return pd.DataFrame(
                [
                    {
                        "ts_code": "600519.SH",
                        "name": "贵州茅台",
                        "q": "近期是否有回购计划？",
                        "a": "如有相关计划，公司将及时履行信息披露义务。",
                        "pub_time": "2025-04-16 20:10:00",
                    }
                ]
            )

    monkeypatch.setattr(stock_events, "_get_tushare_pro", lambda: _FakePro())
    result = stock_events.sync_shanghai_qa(
        "sh600519",
        start_date="2025-04-01",
        end_date="2025-04-16",
        mode="unit_test",
    )

    assert result["fetched_count"] == 1
    assert result["upserted_count"] == 1

    conn = sqlite3.connect(config.DB_FILE)
    try:
        row = conn.execute(
            "SELECT source, source_type, question_text, answer_text FROM stock_events WHERE symbol='sh600519'"
        ).fetchone()
    finally:
        conn.close()

    assert row == (
        "tushare_irm_sh",
        "qa",
        "近期是否有回购计划？",
        "如有相关计划，公司将及时履行信息披露义务。",
    )


def test_sync_short_news_filters_single_symbol(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sz000833", "粤桂股份")

    class _FakePro:
        @staticmethod
        def news(**kwargs):
            src = kwargs.get("src")
            if src == "eastmoney":
                return pd.DataFrame(
                    [
                        {
                            "title": "粤桂股份发布季度经营进展，市场关注度提升",
                            "content": "粤桂股份今晚披露经营情况，资金关注度明显提升。",
                            "datetime": "2025-04-18 20:15:00",
                            "channels": "A股",
                        },
                        {
                            "title": "另一家公司获得大单",
                            "content": "与目标股票无关",
                            "datetime": "2025-04-18 20:20:00",
                            "channels": "A股",
                        },
                    ]
                )
            return pd.DataFrame([])

    monkeypatch.setattr(stock_events, "_get_tushare_pro", lambda: _FakePro())
    result = stock_events.sync_short_news("sz000833", start_date="2025-04-18", end_date="2025-04-18", mode="unit_test")

    assert result["matched_count"] == 1
    assert result["upserted_count"] == 1
    conn = sqlite3.connect(config.DB_FILE)
    try:
        row = conn.execute(
            "SELECT source, source_type, event_subtype, title, source_event_id, extra_json FROM stock_events WHERE symbol='sz000833' AND source='tushare_news'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0:4] == (
        "tushare_news",
        "news",
        "news_general",
        "粤桂股份发布季度经营进展，市场关注度提升",
    )
    assert row[4].startswith("sz000833:")
    assert "\"_match_method\"" in str(row[5] or "")


def test_sync_major_news_filters_single_symbol(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sh600519", "贵州茅台")

    class _FakePro:
        @staticmethod
        def major_news(**kwargs):
            src = kwargs.get("src")
            if src == "财联社":
                return pd.DataFrame(
                    [
                        {
                            "title": "贵州茅台回应渠道调整传闻",
                            "content": "贵州茅台表示如有重大事项将依法披露。",
                            "pub_time": "2025-04-17 21:00:00",
                            "src": "财联社",
                        }
                    ]
                )
            return pd.DataFrame([])

    monkeypatch.setattr(stock_events, "_get_tushare_pro", lambda: _FakePro())
    result = stock_events.sync_major_news("sh600519", start_date="2025-04-17", end_date="2025-04-17", mode="unit_test")

    assert result["matched_count"] == 1
    assert result["upserted_count"] == 1
    conn = sqlite3.connect(config.DB_FILE)
    try:
        row = conn.execute(
            "SELECT source, source_type, title FROM stock_events WHERE symbol='sh600519' AND source='tushare_major_news'"
        ).fetchone()
    finally:
        conn.close()
    assert row == (
        "tushare_major_news",
        "news",
        "贵州茅台回应渠道调整传闻",
    )


def test_news_match_supports_suffix_stripping(monkeypatch, tmp_path):
    _config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()
    db_path = tmp_path / "market_data.db"
    _seed_stock_meta(db_path, "sz000833", "粤桂股份")

    matched, method, confidence, aliases = stock_events._score_news_match(
        "sz000833",
        "粤桂发布经营进展",
        "粤桂今晚公告一季度经营情况",
    )

    assert matched is True
    assert method in {"name_only", "multi_alias_name", "code_and_name"}
    assert confidence >= 0.72
    assert any(alias.startswith("粤桂") for alias in aliases)


def test_alias_seed_file_extends_symbol_aliases(monkeypatch, tmp_path):
    _config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()
    alias_rows = stock_events._load_alias_rows(["sz000833"])
    aliases = {row[0] for row in alias_rows.get("sz000833", [])}

    assert "广西粤桂广业控股股份有限公司" in aliases
    assert "粤桂广业" in aliases


def test_sync_news_adds_related_symbol_entities(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sz000833", "粤桂股份")
    _seed_stock_meta(Path(config.DB_FILE), "sh600519", "贵州茅台")

    user_conn = sqlite3.connect(config.USER_DB_FILE)
    try:
        user_conn.execute(
            "INSERT OR REPLACE INTO watchlist (symbol, name) VALUES (?, ?)",
            ("sh600519", "贵州茅台"),
        )
        user_conn.commit()
    finally:
        user_conn.close()

    class _FakePro:
        @staticmethod
        def news(**kwargs):
            src = kwargs.get("src")
            if src == "eastmoney":
                return pd.DataFrame(
                    [
                        {
                            "title": "粤桂股份与贵州茅台同被市场关注",
                            "content": "粤桂股份披露经营情况，贵州茅台也回应渠道传闻。",
                            "datetime": "2025-04-18 20:15:00",
                            "channels": "A股",
                        }
                    ]
                )
            return pd.DataFrame([])

    monkeypatch.setattr(stock_events, "_get_tushare_pro", lambda: _FakePro())
    stock_events.sync_short_news("sz000833", start_date="2025-04-18", end_date="2025-04-18", mode="unit_test")

    conn = sqlite3.connect(config.DB_FILE)
    try:
        rows = conn.execute(
            """
            SELECT symbol, relation_role, match_method
            FROM stock_event_entities
            WHERE event_id IN (SELECT event_id FROM stock_events WHERE symbol='sz000833' AND source='tushare_news')
            ORDER BY relation_role, symbol
            """
        ).fetchall()
    finally:
        conn.close()

    assert ("sz000833", "primary", "name_only") in rows or any(row[0] == "sz000833" and row[1] == "primary" for row in rows)
    assert any(row[0] == "sh600519" and row[1] == "related" for row in rows)


def test_sync_news_does_not_overwrite_different_target_symbols(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sz000833", "粤桂股份")
    _seed_stock_meta(Path(config.DB_FILE), "sh600519", "贵州茅台")

    class _FakePro:
        @staticmethod
        def news(**kwargs):
            src = kwargs.get("src")
            if src == "eastmoney":
                return pd.DataFrame(
                    [
                        {
                            "id": "same-article",
                            "title": "粤桂股份与贵州茅台同被市场关注",
                            "content": "粤桂股份披露经营情况，贵州茅台也回应渠道传闻。",
                            "datetime": "2025-04-18 20:15:00",
                            "channels": "A股",
                        }
                    ]
                )
            return pd.DataFrame([])

    monkeypatch.setattr(stock_events, "_get_tushare_pro", lambda: _FakePro())
    stock_events.sync_short_news("sz000833", start_date="2025-04-18", end_date="2025-04-18", mode="unit_test")
    stock_events.sync_short_news("sh600519", start_date="2025-04-18", end_date="2025-04-18", mode="unit_test")

    conn = sqlite3.connect(config.DB_FILE)
    try:
        rows = conn.execute(
            """
            SELECT symbol, source_event_id
            FROM stock_events
            WHERE source='tushare_news'
            ORDER BY symbol
            """
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert rows[0][1] != rows[1][1]
    assert rows[0][1].startswith(rows[0][0] + ":")
    assert rows[1][1].startswith(rows[1][0] + ":")


def test_sync_symbol_event_bundle_aggregates_all_sources(monkeypatch, tmp_path):
    _config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()

    monkeypatch.setattr(
        stock_events,
        "backfill_symbol_announcements",
        lambda symbol, days=365, mode="manual": {"symbol": symbol, "upserted_count": 2},
    )
    monkeypatch.setattr(
        stock_events,
        "backfill_symbol_qa",
        lambda symbol, days=180, market="auto", mode="manual": {"symbol": symbol, "upserted_count": 3},
    )
    monkeypatch.setattr(
        stock_events,
        "backfill_symbol_news",
        lambda symbol, days=30, mode="manual": {"symbol": symbol, "upserted_count": 4, "matched_count": 5},
    )

    result = stock_events.sync_symbol_event_bundle("sz000833", announcement_days=30, qa_days=20, news_days=10)

    assert result["symbol"] == "sz000833"
    assert result["summary"]["upserted_count"] == 9
    assert result["summary"]["matched_news_count"] == 5


def test_stock_event_coverage_summary(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sz000833", "粤桂股份")
    stock_events.rebuild_symbol_aliases(["sz000833"])

    conn = sqlite3.connect(config.DB_FILE)
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO stock_events
            (event_id, source, source_type, event_subtype, symbol, ts_code, title, content_text, published_at, ingested_at, importance, is_official, source_event_id, hash_digest, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "evt-r1",
                    "tushare_anns_d",
                    "report",
                    "annual_report",
                    "sz000833",
                    "000833.SZ",
                    "粤桂股份:2025年年度报告",
                    "粤桂股份:2025年年度报告",
                    "2026-04-10 20:30:00",
                    "2026-04-10 20:31:00",
                    95,
                    1,
                    "evt-r1",
                    "digest-r1",
                    None,
                ),
                (
                    "evt-q1",
                    "tushare_irm_sz",
                    "qa",
                    "qa_material",
                    "sz000833",
                    "000833.SZ",
                    "请问公司一季度业绩如何？",
                    "问：请问公司一季度业绩如何？\n答：请关注公告。",
                    "2026-04-11 19:20:00",
                    "2026-04-11 19:21:00",
                    74,
                    1,
                    "evt-q1",
                    "digest-q1",
                    None,
                ),
                (
                    "evt-n1",
                    "tushare_news",
                    "news",
                    "news_general",
                    "sz000833",
                    "000833.SZ",
                    "粤桂股份发布经营进展",
                    "粤桂股份今晚披露经营情况。",
                    "2026-04-12 20:10:00",
                    "2026-04-12 20:11:00",
                    60,
                    0,
                    "evt-n1",
                    "digest-n1",
                    None,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    payload = stock_events.get_stock_event_coverage("sz000833", days=30)

    assert payload["coverage_status"] == "covered"
    assert payload["alias_count"] >= 3
    assert any(item["module"] == "report" and item["covered"] for item in payload["modules"])
    assert any(item["module"] == "qa" and item["covered"] for item in payload["modules"])
    assert any(item["module"] == "news" and item["covered"] for item in payload["modules"])


def test_stock_event_collection_audit(monkeypatch, tmp_path):
    config, database, _selection_db, stock_events = _reload_modules(monkeypatch, tmp_path)
    database.init_db()
    _seed_stock_meta(Path(config.DB_FILE), "sz000833", "粤桂股份")
    stock_events.rebuild_symbol_aliases(["sz000833"])

    conn = sqlite3.connect(config.DB_FILE)
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO stock_events
            (event_id, source, source_type, event_subtype, symbol, ts_code, title, content_text, published_at, ingested_at, importance, is_official, source_event_id, hash_digest, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("evt-report", "tushare_anns_d", "report", "annual_report", "sz000833", "000833.SZ", "粤桂股份:2025年年度报告", "粤桂股份:2025年年度报告", "2026-04-01 20:00:00", "2026-04-01 20:01:00", 95, 1, "evt-report", "digest-report", None),
                ("evt-qa", "tushare_irm_sz", "qa", "qa_material", "sz000833", "000833.SZ", "请问公司一季度业绩如何？", "问：请问公司一季度业绩如何？", "2026-04-02 19:00:00", "2026-04-02 19:01:00", 74, 1, "evt-qa", "digest-qa", None),
                ("evt-news", "tushare_news", "news", "news_general", "sz000833", "000833.SZ", "粤桂股份发布经营进展", "粤桂股份今晚披露经营情况。", "2026-04-03 20:00:00", "2026-04-03 20:01:00", 60, 0, "evt-news", "digest-news", None),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    payload = stock_events.audit_stock_event_collection("sz000833", days=30, recent_limit=5)

    assert payload["collection_status"] == "partial"
    assert payload["group_counts"]["official"] >= 1
    assert payload["group_counts"]["company"] >= 1
    assert payload["group_counts"]["media"] >= 1
    assert any(item["code"] == "announcement_missing" for item in payload["audit_flags"])
