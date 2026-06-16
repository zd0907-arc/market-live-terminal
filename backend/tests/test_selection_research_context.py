from backend.app.services import selection_research_context as context


def test_select_profile_prefers_daily_candidate_profile(monkeypatch):
    def fake_daily_profile(symbol, trade_date):
        assert symbol == "sz002015"
        assert trade_date == "2026-06-15"
        return {
            "symbol": symbol,
            "name": "协鑫能科",
            "trade_date": trade_date,
            "primary_source_id": "spark_opportunity_selector",
            "primary_source_name": "星火模型",
            "action_label": "观察",
            "reason_summary": "cached daily profile",
        }

    def fail_dynamic_profile(*args, **kwargs):
        raise AssertionError("dynamic strategy profile should not be called")

    monkeypatch.setattr(context, "query_daily_candidate_profile", fake_daily_profile)
    monkeypatch.setattr(context, "get_stable_callback_profile", fail_dynamic_profile)

    profile, error = context._select_profile("SZ002015", "2026-06-15", "stable_capital_callback")

    assert error is None
    assert profile["symbol"] == "sz002015"
    assert profile["strategy_internal_id"] == "spark_opportunity_selector"
    assert profile["current_judgement"] == "观察"
    assert profile["trade_plan"]["signal_date"] == "2026-06-15"
    assert profile["series"] == []
