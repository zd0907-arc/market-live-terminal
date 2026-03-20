import asyncio

from backend.app import scheduler as scheduler_module


def test_is_postclose_tick_payload_stale():
    assert scheduler_module._is_postclose_tick_payload_stale(None) is True
    assert scheduler_module._is_postclose_tick_payload_stale("14:45:00") is True
    assert scheduler_module._is_postclose_tick_payload_stale("14:54:59") is True
    assert scheduler_module._is_postclose_tick_payload_stale("14:55:00") is False
    assert scheduler_module._is_postclose_tick_payload_stale("15:00:00") is False


def test_rehydrate_symbol_postclose_if_stale_skips_fresh(monkeypatch):
    fetch_called = {"count": 0}

    monkeypatch.setattr(
        scheduler_module,
        "get_latest_tick_time",
        lambda symbol, trade_date: "15:00:00",
    )

    async def fake_fetch(symbol):
        fetch_called["count"] += 1
        return []

    monkeypatch.setattr(scheduler_module, "fetch_live_ticks", fake_fetch)

    result = asyncio.run(
        scheduler_module._rehydrate_symbol_postclose_if_stale("sz000833", "2026-03-19")
    )

    assert result is False
    assert fetch_called["count"] == 0


def test_rehydrate_symbol_postclose_if_stale_heals_stale(monkeypatch):
    latest_times = iter([None, "15:00:00"])
    save_calls = []
    agg_calls = []
    preview_calls = []

    monkeypatch.setattr(
        scheduler_module,
        "get_latest_tick_time",
        lambda symbol, trade_date: next(latest_times),
    )

    async def fake_fetch(symbol):
        assert symbol == "sz000759"
        return [
            {
                "time": "14:59:59",
                "price": 7.12,
                "volume": 100,
                "amount": 71200.0,
                "type": "buy",
            }
        ]

    monkeypatch.setattr(scheduler_module, "fetch_live_ticks", fake_fetch)
    monkeypatch.setattr(
        scheduler_module,
        "save_ticks_daily_overwrite",
        lambda symbol, trade_date, rows: save_calls.append((symbol, trade_date, rows)),
    )
    monkeypatch.setattr(
        scheduler_module,
        "aggregate_intraday_1m",
        lambda symbol, trade_date: agg_calls.append((symbol, trade_date)),
    )
    monkeypatch.setattr(
        scheduler_module,
        "refresh_realtime_preview",
        lambda symbol, trade_date: preview_calls.append((symbol, trade_date)),
    )

    result = asyncio.run(
        scheduler_module._rehydrate_symbol_postclose_if_stale("sz000759", "2026-03-19")
    )

    assert result is True
    assert len(save_calls) == 1
    assert save_calls[0][0] == "sz000759"
    assert save_calls[0][1] == "2026-03-19"
    assert save_calls[0][2][0][1] == "14:59:59"
    assert agg_calls == [("sz000759", "2026-03-19")]
    assert preview_calls == [("sz000759", "2026-03-19")]


def test_run_postclose_tick_self_heal_only_processes_stale_symbols(monkeypatch):
    calls = []

    monkeypatch.setattr(
        scheduler_module.MarketClock,
        "get_market_context",
        lambda: {"market_status": "post_close", "natural_today": "2026-03-19"},
    )
    monkeypatch.setattr(
        scheduler_module,
        "get_all_symbols",
        lambda: ["sz000833", "sz000759"],
    )
    monkeypatch.setattr(
        scheduler_module,
        "get_latest_tick_time",
        lambda symbol, trade_date: "14:45:00" if symbol == "sz000833" else "15:00:00",
    )

    async def fake_rehydrate(symbol, trade_date):
        calls.append((symbol, trade_date))
        return True

    monkeypatch.setattr(scheduler_module, "_rehydrate_symbol_postclose_if_stale", fake_rehydrate)

    scheduler_module.run_postclose_tick_self_heal()

    assert calls == [("sz000833", "2026-03-19")]


def test_run_postclose_tick_self_heal_skips_outside_postclose(monkeypatch):
    monkeypatch.setattr(
        scheduler_module.MarketClock,
        "get_market_context",
        lambda: {"market_status": "trading", "natural_today": "2026-03-19"},
    )
    monkeypatch.setattr(
        scheduler_module,
        "get_all_symbols",
        lambda: (_ for _ in ()).throw(AssertionError("should not read watchlist outside post_close")),
    )

    scheduler_module.run_postclose_tick_self_heal()
