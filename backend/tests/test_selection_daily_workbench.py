import backend.app.db.selection_db as selection_db_module
from backend.app.routers.selection import selection_daily_candidates, selection_daily_trade_dates
from backend.app.services.selection_candidate_store import (
    rebuild_daily_candidates,
    replace_daily_exit_watchlist,
    replace_source_candidates,
    upsert_strategy_registry,
)
from backend.app.services.selection_daily_workbench import run_daily_selection_sources
from backend.app.services.selection_candidate_store import query_daily_exit_watchlist


def test_daily_candidate_pool_merges_sources(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)

    upsert_strategy_registry(
        [
            {
                "source_id": "spark_opportunity_selector",
                "source_name": "星火机会模型 1.0",
                "source_type": "model",
                "source_version": "1.0",
                "horizon": "22d",
                "status": "watch_only",
            },
            {
                "source_id": "stable_capital_callback",
                "source_name": "资金流回调稳健",
                "source_type": "rule_strategy",
                "source_version": "test",
                "horizon": "swing",
                "status": "active",
            },
        ]
    )

    spark_records = [
        {
            "trade_date": "2026-05-14",
            "symbol": "sh600769",
            "name": "祥龙电业",
            "source_id": "spark_opportunity_selector",
            "source_name": "星火机会模型 1.0",
            "source_type": "model",
            "source_version": "1.0",
            "rank": 1,
            "score": 39.0,
            "horizon": "22d",
            "suggested_action": "candidate_buy",
            "action_label": "明日可买",
            "entry_allowed": True,
            "reason_summary": "模型机会分靠前",
            "risk_tags": [],
            "entry_block_reasons": [],
            "explain_factors": {"model_score": 39.0, "breakout_score": 80.0},
            "raw_payload": {},
        }
    ]
    stable_records = [
        {
            "trade_date": "2026-05-14",
            "symbol": "sh600769",
            "name": "祥龙电业",
            "source_id": "stable_capital_callback",
            "source_name": "资金流回调稳健",
            "source_type": "rule_strategy",
            "source_version": "test",
            "rank": 1,
            "score": 88.0,
            "horizon": "swing",
            "suggested_action": "watch",
            "action_label": "观察",
            "entry_allowed": False,
            "reason_summary": "资金回调命中但需确认",
            "risk_tags": ["观察"],
            "entry_block_reasons": ["等待确认"],
            "explain_factors": {"setup_score": 88.0},
            "raw_payload": {},
        }
    ]

    assert replace_source_candidates("2026-05-14", "spark_opportunity_selector", spark_records) == 1
    assert replace_source_candidates("2026-05-14", "stable_capital_callback", stable_records) == 1
    assert rebuild_daily_candidates("2026-05-14") == 1

    resp = selection_daily_candidates(date="2026-05-14", limit=10)
    assert resp.code == 200
    assert resp.data["trade_date"] == "2026-05-14"
    assert len(resp.data["items"]) == 1
    item = resp.data["items"][0]
    assert item["symbol"] == "sh600769"
    assert item["source_count"] == 2
    assert item["source_ids"] == ["spark_opportunity_selector", "stable_capital_callback"]
    assert item["entry_allowed"] is True
    assert item["primary_source_name"] == "星火机会模型 1.0"


def test_daily_trade_dates_are_selectable_with_features_even_without_candidates(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)
    selection_db_module.ensure_selection_schema()

    conn = selection_db_module.get_selection_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO selection_feature_daily (
                    symbol, trade_date, feature_version, source_snapshot, close, name
                ) VALUES ('sh600000', '2026-05-15', 'test', '{}', 10.0, '浦发银行')
                """
            )
    finally:
        conn.close()

    resp = selection_daily_trade_dates(start_date="2026-05-15", end_date="2026-05-15")
    assert resp.code == 200
    assert resp.data["items"][0]["date"] == "2026-05-15"
    assert resp.data["items"][0]["selectable"] is True
    assert resp.data["items"][0]["signal_count"] == 0
    assert resp.data["items"][0]["has_feature"] is True
    assert resp.data["items"][0]["has_candidates"] is False
    assert resp.data["items"][0]["can_generate"] is True
    assert resp.data["items"][0]["disabled_reason"] == "当天无候选"


def test_daily_trade_dates_truncates_to_recent_window(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)
    selection_db_module.ensure_selection_schema()

    conn = selection_db_module.get_selection_connection()
    try:
        with conn:
            for date_text in ("2024-09-02", "2026-02-24", "2026-05-20", "2026-05-22"):
                conn.execute(
                    """
                    INSERT INTO selection_feature_daily (
                        symbol, trade_date, feature_version, source_snapshot, close, name
                    ) VALUES (?, ?, 'test', '{}', 10.0, '测试')
                    """,
                    (f"sh{date_text.replace('-', '')[-6:]}", date_text),
                )
    finally:
        conn.close()

    resp = selection_daily_trade_dates(start_date="2024-09-02", end_date="2026-05-22")
    assert resp.code == 200
    assert resp.data["truncated"] is True
    assert resp.data["end_date"] == "2026-05-22"
    dates = {item["date"]: item for item in resp.data["items"]}
    assert "2026-05-20" in dates
    assert "2026-05-22" in dates
    assert "2024-09-02" not in dates
    assert dates["2026-05-20"]["selectable"] is True


def test_daily_trade_dates_marks_zero_result_runs(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)
    selection_db_module.ensure_selection_schema()

    conn = selection_db_module.get_selection_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO selection_feature_daily (
                    symbol, trade_date, feature_version, source_snapshot, close, name
                ) VALUES ('sh600000', '2026-05-18', 'test', '{}', 10.0, '浦发银行')
                """
            )
    finally:
        conn.close()

    assert replace_source_candidates("2026-05-18", "spark_opportunity_selector", []) == 0
    resp = selection_daily_trade_dates(start_date="2026-05-18", end_date="2026-05-18")
    assert resp.code == 200
    item = resp.data["items"][0]
    assert item["has_run"] is True
    assert item["run_count"] == 1
    assert item["successful_run_count"] == 1
    assert item["run_candidate_count"] == 0
    assert item["has_candidates"] is False


def test_spark_source_uses_top3_daily_limit(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)

    import backend.app.services.selection_daily_workbench as workbench

    def fake_generate(source_id, trade_date, *, limit=50):
        assert source_id == "spark_opportunity_selector"
        return [
            {
                "trade_date": trade_date,
                "symbol": f"sh60000{idx}",
                "name": f"测试{idx}",
                "source_id": source_id,
                "source_name": "星火机会模型 1.0",
                "source_type": "model",
                "source_version": "1.0",
                "rank": idx,
                "score": 100 - idx,
                "suggested_action": "candidate_buy",
                "action_label": "明日可买",
                "entry_allowed": True,
            }
            for idx in range(1, limit + 1)
        ]

    monkeypatch.setattr(workbench, "generate_source_candidates", fake_generate)
    payload = run_daily_selection_sources("2026-05-14", limit=30, source_ids=["spark_opportunity_selector"])
    assert payload["sources"]["spark_opportunity_selector"] == 3
    assert payload["merged_count"] == 3


def test_rule_strategy_candidates_use_requested_trade_date(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)

    import backend.app.services.selection_daily_workbench as workbench

    monkeypatch.setattr(
        workbench,
        "get_stable_callback_candidates",
        lambda trade_date, limit=10: {
            "trade_date": trade_date,
            "items": [
                {
                    "trade_date": "",
                    "symbol": "sz002361",
                    "name": "神剑股份",
                    "score": 97.49,
                    "entry_allowed": True,
                    "action_label": "可买入",
                    "reason_summary": "no_launch；风险标签 0 个",
                    "discovery_date": trade_date,
                }
            ],
        },
    )

    payload = run_daily_selection_sources("2026-05-25", source_ids=["stable_capital_callback"])
    assert payload["errors"] == {}
    assert payload["sources"]["stable_capital_callback"] == 1
    assert payload["merged_count"] == 1

    conn = selection_db_module.get_selection_connection()
    try:
        row = conn.execute(
            """
            SELECT trade_date, symbol, source_id
            FROM selection_candidate_sources
            WHERE source_id='stable_capital_callback'
            """
        ).fetchone()
    finally:
        conn.close()
    assert dict(row) == {
        "trade_date": "2026-05-25",
        "symbol": "sz002361",
        "source_id": "stable_capital_callback",
    }


def test_daily_candidates_include_exit_watchlist(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)

    upsert_strategy_registry(
        [
            {
                "source_id": "spark_opportunity_selector",
                "source_name": "星火机会模型 1.0",
                "source_type": "model",
                "source_version": "1.0",
                "horizon": "22d",
                "status": "watch_only",
            }
        ]
    )
    spark_records = [
        {
            "trade_date": "2026-05-14",
            "symbol": "sh600001",
            "name": "测试一",
            "source_id": "spark_opportunity_selector",
            "source_name": "星火机会模型 1.0",
            "source_type": "model",
            "source_version": "1.0",
            "rank": 1,
            "score": 88.0,
            "horizon": "22d",
            "suggested_action": "candidate_buy",
            "action_label": "明日可买",
            "entry_allowed": True,
            "reason_summary": "模型机会分靠前",
            "risk_tags": [],
            "entry_block_reasons": [],
            "explain_factors": {"model_score": 88.0},
            "raw_payload": {"entry_signal_date": "2026-05-14"},
        }
    ]
    assert replace_source_candidates("2026-05-14", "spark_opportunity_selector", spark_records) == 1
    assert rebuild_daily_candidates("2026-05-14") == 1

    assert replace_daily_exit_watchlist(
        "2026-05-14",
        {
            "trade_date": "2026-05-14",
            "policy_id": "pc_model_th6_stop12",
            "policy_name": "星火进攻版",
            "items": [
                {
                    "symbol": "sh600001",
                    "name": "测试一",
                    "trade_date": "2026-05-14",
                    "entry_signal_date": "2026-05-14",
                    "entry_date": "2026-05-15",
                    "exit_signal_date": "2026-05-14",
                    "exit_date": "2026-05-15",
                    "exit_plan_summary": "盘后建议次日卖出",
                    "entry_allowed": False,
                    "current_judgement": "次日卖出",
                }
            ],
        },
    ) == 1

    resp = selection_daily_candidates(date="2026-05-14", limit=10, include_exit_watchlist=True)
    assert resp.code == 200
    assert resp.data["exit_watchlist"]["policy_id"] == "pc_model_th6_stop12"
    assert len(resp.data["exit_watchlist"]["items"]) == 1
    assert resp.data["exit_watchlist"]["items"][0]["exit_signal_date"] == "2026-05-14"


def test_daily_candidates_skip_exit_watchlist_by_default(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)

    import backend.app.services.selection_daily_workbench as workbench

    monkeypatch.setattr(
        workbench,
        "get_daily_exit_watchlist",
        lambda trade_date: (_ for _ in ()).throw(AssertionError("exit watchlist should be opt-in")),
    )

    resp = selection_daily_candidates(date="2026-05-14", limit=10)
    assert resp.code == 200
    assert resp.data["items"] == []
    assert resp.data["exit_watchlist"]["skipped"] is True


def test_run_daily_sources_persists_exit_watchlist(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)

    import backend.app.services.selection_daily_workbench as workbench

    monkeypatch.setattr(workbench, "generate_source_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        workbench,
        "get_daily_exit_watchlist",
        lambda trade_date, use_cache=False: {
            "trade_date": trade_date,
            "policy_id": "pc_model_th6_stop12",
            "policy_name": "星火进攻版",
            "items": [
                {
                    "symbol": "sh600001",
                    "name": "测试一",
                    "trade_date": trade_date,
                    "rank": 1,
                    "score": 88.0,
                    "signal": 1,
                    "signal_label": "spark_exit_sell_next_open",
                    "current_judgement": "次日卖出",
                    "reason_summary": "盘后建议次日卖出",
                    "risk_level": "high",
                    "action_label": "次日卖出",
                    "lifecycle_phase": "sell",
                    "lifecycle_phase_label": "次日卖出",
                    "entry_signal_date": "2026-05-14",
                    "entry_date": "2026-05-15",
                    "exit_signal_date": trade_date,
                    "exit_date": "2026-05-15",
                    "exit_plan_summary": "盘后建议次日卖出",
                    "entry_allowed": False,
                    "source_ids": ["spark_opportunity_selector"],
                    "source_types": ["model"],
                    "source_details": [{"source_id": "spark_opportunity_selector", "score": 88.0}],
                    "primary_source_id": "spark_opportunity_selector",
                    "primary_source_name": "星火机会模型 1.0",
                    "primary_source_type": "model",
                }
            ],
        },
    )

    payload = run_daily_selection_sources("2026-05-14", source_ids=["spark_opportunity_selector"])
    assert payload["exit_watchlist_count"] == 1
    watchlist = query_daily_exit_watchlist("2026-05-14")
    assert len(watchlist["items"]) == 1
    assert watchlist["items"][0]["exit_signal_date"] == "2026-05-14"
