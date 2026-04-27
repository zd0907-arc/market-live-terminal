from backend.app.routers.selection import selection_candidates, selection_profile, selection_trend_continuation_evaluate
from backend.app.services.selection_trend_continuation import STRATEGY_INTERNAL_ID


def test_trend_continuation_candidates_include_buy_and_observation():
    resp = selection_candidates(date="2026-03-11", strategy=STRATEGY_INTERNAL_ID, limit=20)
    assert resp.code == 200
    assert resp.data["strategy"] == STRATEGY_INTERNAL_ID
    assert resp.data["strategy_display_name"] == "趋势中继高质量回踩"
    assert resp.data["items"]
    assert any(item["action_label"] == "可买入" for item in resp.data["items"])
    assert any(item["action_label"] == "观察中" for item in resp.data["items"])


def test_trend_continuation_profile_explains_strategy():
    candidate = selection_candidates(date="2026-03-11", strategy=STRATEGY_INTERNAL_ID, limit=1).data["items"][0]
    resp = selection_profile(candidate["symbol"], date=candidate["trade_date"], strategy=STRATEGY_INTERNAL_ID)
    assert resp.code == 200
    assert resp.data["strategy_internal_id"] == STRATEGY_INTERNAL_ID
    assert resp.data["strategy_display_name"] == "趋势中继高质量回踩"
    assert resp.data["research"]["strategy_explanation"]


def test_trend_continuation_evaluate_matches_current_candidate():
    resp = selection_trend_continuation_evaluate(start_date="2026-03-02", end_date="2026-04-24")
    assert resp.code == 200
    summary = resp.data["summary"]
    assert summary["trade_count"] == 7
    assert summary["win_rate"] == 100.0
    assert summary["avg_return_pct"] == 20.19
    assert summary["median_return_pct"] == 19.36
