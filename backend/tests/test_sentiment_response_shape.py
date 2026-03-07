import pandas as pd

from backend.app.routers.sentiment import (
    get_recent_comments,
    get_sentiment_trend,
    get_summary_history,
)


class _DummyConn:
    def __init__(self, rows=None):
        self._rows = rows or []

    def cursor(self):
        rows = self._rows

        class _Cursor:
            def execute(self, *_args, **_kwargs):
                return None

            def fetchall(self):
                return rows

        return _Cursor()

    def close(self):
        return None


def test_summary_history_empty_returns_api_response(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.get_db_connection",
        lambda: _DummyConn(rows=[]),
    )

    resp = get_summary_history("sh600519")
    assert resp.code == 200
    assert resp.message == "No data found"
    assert resp.data == []


def test_recent_comments_empty_returns_api_response(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.get_db_connection",
        lambda: _DummyConn(),
    )
    monkeypatch.setattr(
        "backend.app.routers.sentiment.pd.read_sql",
        lambda *_args, **_kwargs: pd.DataFrame(
            columns=[
                "id",
                "content",
                "pub_time",
                "read_count",
                "reply_count",
                "sentiment_score",
                "heat_score",
            ]
        ),
    )

    resp = get_recent_comments("sh600519")
    assert resp.code == 200
    assert resp.message == "No data found"
    assert resp.data == []


def test_sentiment_trend_wrapped_with_data(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.get_db_connection",
        lambda: _DummyConn(),
    )
    monkeypatch.setattr(
        "backend.app.routers.sentiment.pd.read_sql",
        lambda *_args, **_kwargs: pd.DataFrame(
            [
                {
                    "time_bucket": "2026-03-06 09:00",
                    "total_heat": 12.3,
                    "post_count": 5,
                    "bull_vol": 3,
                    "bear_vol": 1,
                }
            ]
        ),
    )

    resp = get_sentiment_trend("sh600519", interval="72h")
    assert resp.code == 200
    assert isinstance(resp.data, list)
    assert len(resp.data) > 0


def test_sentiment_trend_error_returns_api_response(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.get_db_connection",
        lambda: _DummyConn(),
    )

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.app.routers.sentiment.pd.read_sql", _raise)

    resp = get_sentiment_trend("sh600519")
    assert resp.code == 500
    assert resp.data == []
