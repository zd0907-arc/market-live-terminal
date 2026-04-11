from backend.app.services import selection_history_proxy


def test_selection_multiframe_prefers_local(monkeypatch):
    monkeypatch.setattr(
        selection_history_proxy,
        "_build_multiframe_rows",
        lambda **kwargs: [
            {
                "datetime": "2026-02-27 15:00:00",
                "trade_date": "2026-02-27",
                "close": 10.0,
                "l1_main_buy": 1.0,
                "l1_main_sell": 2.0,
                "is_placeholder": False,
                "source": "l2_history",
            }
        ],
    )

    called = {"value": False}

    def _cloud(**kwargs):
        called["value"] = True
        return []

    monkeypatch.setattr(selection_history_proxy, "_fetch_cloud_multiframe", _cloud)
    payload = selection_history_proxy.get_selection_multiframe_rows("sz000001", "1d", 20, None, None, True)
    assert payload["data_origin"] == "local"
    assert len(payload["items"]) == 1
    assert called["value"] is False


def test_selection_multiframe_falls_back_to_cloud(monkeypatch):
    monkeypatch.setattr(
        selection_history_proxy,
        "_build_multiframe_rows",
        lambda **kwargs: [
            {
                "datetime": "2026-02-27 15:00:00",
                "trade_date": "2026-02-27",
                "close": None,
                "l1_main_buy": None,
                "l1_main_sell": None,
                "is_placeholder": True,
                "source": "placeholder",
            }
        ],
    )
    monkeypatch.setattr(
        selection_history_proxy,
        "_fetch_cloud_multiframe",
        lambda **kwargs: [
            {
                "datetime": "2026-02-27 15:00:00",
                "trade_date": "2026-02-27",
                "close": 12.3,
                "l1_main_buy": 3.0,
                "l1_main_sell": 1.0,
                "is_placeholder": False,
                "source": "cloud::l2_history",
                "fallback_used": True,
            }
        ],
    )
    payload = selection_history_proxy.get_selection_multiframe_rows("sz000001", "1d", 20, None, None, True)
    assert payload["data_origin"] == "cloud"
    assert payload["items"][0]["source"] == "cloud::l2_history"
