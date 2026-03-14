from backend.app.routers.monitor import get_active_symbols, register_heartbeat
from backend.app.services.monitor import heartbeat_registry


def setup_function():
    heartbeat_registry.active_watchers.clear()


def test_heartbeat_registry_splits_focus_and_warm():
    register_heartbeat(symbol="sh600519", mode="focus")
    register_heartbeat(symbol="sz000001", mode="warm")

    resp = get_active_symbols()

    assert resp.code == 200
    assert resp.data["focus_symbols"] == ["sh600519"]
    assert resp.data["warm_symbols"] == ["sz000001"]
    assert resp.data["all_symbols"] == ["sh600519", "sz000001"]


def test_heartbeat_invalid_mode_falls_back_to_warm():
    register_heartbeat(symbol="sh601318", mode="unexpected")

    resp = get_active_symbols()

    assert resp.code == 200
    assert resp.data["focus_symbols"] == []
    assert resp.data["warm_symbols"] == ["sh601318"]
