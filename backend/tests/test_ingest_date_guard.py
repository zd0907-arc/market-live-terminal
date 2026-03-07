from backend.app.routers.ingest import normalize_ingest_date


def test_normalize_ingest_date_keep_trade_day(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.ingest.TradeCalendar.is_trade_day",
        lambda d: d == "2026-03-06",
    )
    monkeypatch.setattr(
        "backend.app.routers.ingest.MarketClock.get_display_date",
        lambda: "2026-03-06",
    )

    assert normalize_ingest_date("2026-03-06") == "2026-03-06"


def test_normalize_ingest_date_fallback_non_trade_day(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.ingest.TradeCalendar.is_trade_day",
        lambda d: False,
    )
    monkeypatch.setattr(
        "backend.app.routers.ingest.MarketClock.get_display_date",
        lambda: "2026-03-06",
    )

    assert normalize_ingest_date("2026-03-07") == "2026-03-06"
