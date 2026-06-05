import backend.app.db.selection_db as selection_db_module
from backend.app.routers.selection import selection_daily_candidates
from backend.app.services.selection_daily_workbench import run_daily_selection_sources


def test_probe_sources_merge_into_daily_pool(monkeypatch, tmp_path):
    selection_db_path = tmp_path / "selection_research.db"
    monkeypatch.setenv("SELECTION_DB_PATH", str(selection_db_path))
    selection_db_module.SELECTION_DB_FILE = str(selection_db_path)

    import backend.app.services.selection_daily_workbench as workbench

    def fake_probe_generate(source_id, trade_date, limit):
        if source_id == "probe_day0_watch":
            return [
                {
                    "trade_date": trade_date,
                    "symbol": "sz000001",
                    "name": "平安银行",
                    "source_id": source_id,
                    "source_name": "试盘观察池",
                    "source_type": "rule_strategy",
                    "source_version": "probe_watch_v1",
                    "rank": 1,
                    "score": 82.0,
                    "horizon": "watch",
                    "suggested_action": "watch",
                    "action_label": "重点观察",
                    "entry_allowed": False,
                    "reason_summary": "首次试盘；盘中急拉后没有直接发动；回吐明显，像在摸上方抛压",
                    "risk_tags": ["当天回吐偏大"],
                    "entry_block_reasons": ["观察池信号，先看后续1到3日资金是否继续确认"],
                    "explain_factors": {
                        "probe_index": 1,
                        "probe_strength_score": 76.5,
                        "history_sample_count": 18,
                        "history_close_win_rate_5d": 0.6111,
                        "history_avg_return_5d_pct": 2.35,
                        "history_breakout_hit_+5_10d_rate": 0.4444,
                        "history_drawdown_hit_-5_5d_rate": 0.1667,
                        "history_summary_text": "过去 18 个同类首次试盘样本里，5日内约有 61% 收盘能站上成本，44% 会在10日内先冲到 +5%，但也有 17% 会在5日内先打到 -5%。",
                        "history_similar_cases": [
                            {"symbol": "sz000002", "name": "万科A", "trade_date": "2026-04-20", "sequence_label": "首次试盘", "close_5d_pct": 1.2, "max_high_10d_pct": 5.7, "min_low_5d_pct": -1.8}
                        ],
                    },
                    "raw_payload": {
                        "observe_date": trade_date,
                        "historical_similar_stats": {
                            "sample_count": 18,
                            "summary_text": "过去 18 个同类首次试盘样本里，5日内约有 61% 收盘能站上成本，44% 会在10日内先冲到 +5%，但也有 17% 会在5日内先打到 -5%。",
                            "similar_cases": [
                                {"symbol": "sz000002", "name": "万科A", "trade_date": "2026-04-20", "sequence_label": "首次试盘", "close_5d_pct": 1.2, "max_high_10d_pct": 5.7, "min_low_5d_pct": -1.8}
                            ],
                        },
                    },
                }
            ]
        if source_id == "probe_d3_confirmed":
            return [
                {
                    "trade_date": trade_date,
                    "symbol": "sz000001",
                    "name": "平安银行",
                    "source_id": source_id,
                    "source_name": "试盘D3确认池",
                    "source_type": "rule_strategy",
                    "source_version": "probe_confirm_v1",
                    "rank": 1,
                    "score": 95.0,
                    "horizon": "swing",
                    "suggested_action": "candidate_buy",
                    "action_label": "明日可买",
                    "entry_allowed": True,
                    "reason_summary": "首次试盘后进入D3确认；D3 OIB继续为正；超大单没有撤；盘口承接强于抛压",
                    "risk_tags": [],
                    "entry_block_reasons": [],
                    "explain_factors": {"probe_index": 1, "d3_oib_ratio": 0.2},
                    "raw_payload": {"observe_date": "2026-05-12", "entry_signal_date": trade_date, "entry_date": "2026-05-16"},
                }
            ]
        return []

    monkeypatch.setattr(workbench.probe_signal_selector, "generate_daily_candidates", fake_probe_generate)

    payload = run_daily_selection_sources("2026-05-15", source_ids=["probe_day0_watch", "probe_d3_confirmed"], include_exit_watchlist=False)
    assert payload["errors"] == {}
    assert payload["sources"]["probe_day0_watch"] == 1
    assert payload["sources"]["probe_d3_confirmed"] == 1
    assert payload["merged_count"] == 1

    resp = selection_daily_candidates(date="2026-05-15", limit=10)
    assert resp.code == 200
    item = resp.data["items"][0]
    assert item["symbol"] == "sz000001"
    assert item["entry_allowed"] is True
    assert item["primary_source_id"] == "probe_d3_confirmed"
    assert item["source_count"] == 2
    assert item["source_ids"] == ["probe_d3_confirmed", "probe_day0_watch"]
    watch_detail = next(detail for detail in item["source_details"] if detail["source_id"] == "probe_day0_watch")
    assert watch_detail["explain_factors"]["history_sample_count"] == 18
    assert watch_detail["explain_factors"]["history_summary_text"].startswith("过去 18 个同类首次试盘样本里")
    assert watch_detail["raw_payload"]["historical_similar_stats"]["similar_cases"][0]["symbol"] == "sz000002"
