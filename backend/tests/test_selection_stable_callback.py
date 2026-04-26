from backend.app.routers.selection import selection_candidates, selection_profile, selection_stable_callback_evaluate
from backend.app.services.selection_stable_callback import STRATEGY_INTERNAL_ID, evaluate_stable_callback_range


def test_stable_callback_candidates_expose_product_fields():
    resp = selection_candidates(date="2026-03-10", strategy=STRATEGY_INTERNAL_ID, limit=10)
    assert resp.code == 200
    assert resp.data["strategy"] == STRATEGY_INTERNAL_ID
    assert resp.data["strategy_display_name"] == "资金流回调稳健"
    assert resp.data["items"]
    first = resp.data["items"][0]
    assert first["strategy_internal_id"] == STRATEGY_INTERNAL_ID
    assert first["strategy_display_name"] == "资金流回调稳健"
    assert first["entry_signal_date"] == first["trade_date"]
    assert "risk_count" in first
    assert "setup_reason" in first
    assert "exit_plan_summary" in first


def test_stable_callback_candidates_deduplicate_same_symbol_same_buy_day():
    resp_326 = selection_candidates(date="2026-03-26", strategy=STRATEGY_INTERNAL_ID, limit=10)
    resp_327 = selection_candidates(date="2026-03-27", strategy=STRATEGY_INTERNAL_ID, limit=10)
    assert resp_326.code == 200
    assert resp_327.code == 200
    symbols_326 = [item["symbol"] for item in resp_326.data["items"]]
    symbols_327 = [item["symbol"] for item in resp_327.data["items"]]
    assert len(symbols_326) == len(set(symbols_326)) == 5
    assert len(symbols_327) == len(set(symbols_327)) == 8


def test_stable_callback_profile_explains_entry_and_risk():
    candidate = selection_candidates(date="2026-03-10", strategy=STRATEGY_INTERNAL_ID, limit=1).data["items"][0]
    resp = selection_profile(candidate["symbol"], date=candidate["trade_date"], strategy=STRATEGY_INTERNAL_ID)
    assert resp.code == 200
    assert resp.data["strategy_internal_id"] == STRATEGY_INTERNAL_ID
    assert resp.data["current_judgement"] == "可买入"
    assert resp.data["risk_count"] == candidate["risk_count"]
    assert resp.data["research"]["strategy_explanation"]


def test_stable_callback_range_matches_research_acceptance_numbers():
    payload = evaluate_stable_callback_range("2026-03-02", "2026-04-24")
    summary = payload["summary"]
    assert summary["trade_count"] == 35
    assert summary["win_rate"] == 88.57
    assert summary["avg_return_pct"] == 10.76
    assert summary["median_return_pct"] == 8.21
    assert summary["big_loss_count"] == 1


def test_stable_callback_evaluate_route():
    resp = selection_stable_callback_evaluate(start_date="2026-03-02", end_date="2026-04-24", top_n=10)
    assert resp.code == 200
    assert resp.data["strategy_internal_id"] == STRATEGY_INTERNAL_ID
    assert resp.data["summary"]["trade_count"] == 35
