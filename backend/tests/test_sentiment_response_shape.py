from datetime import datetime

from backend.app.routers.sentiment import (
    get_sentiment_feed,
    get_sentiment_heat_trend,
    get_sentiment_keywords,
    get_sentiment_overview,
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
        "backend.app.routers.sentiment.fetch_representative_comments",
        lambda *_args, **_kwargs: {
            "comments": [],
            "coverage_status": "no_recent_samples",
            "message": "No recent samples",
        },
    )

    resp = get_recent_comments("sh600519")
    assert resp.code == 200
    assert resp.message in {"No data found", "Symbol not covered", "No samples found", "No recent samples"}
    assert resp.data == []


def test_sentiment_keywords_wrapped_payload(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.build_keywords_payload",
        lambda *_args, **_kwargs: {
            "keywords": [{"word": "涨停", "count": 3, "sentiment_bias": "bullish"}],
            "topics": [{"label": "涨停预期", "count": 2}],
            "sample_count": 8,
            "latest_comment_time": "2026-03-22 10:00:00",
            "coverage_status": "covered",
        },
    )

    resp = get_sentiment_keywords("sh600519", window="72h")
    assert resp.code == 200
    assert resp.data["keywords"][0]["word"] == "涨停"
    assert resp.data["topics"][0]["label"] == "涨停预期"


def test_sentiment_trend_wrapped_with_data(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.build_sentiment_trend_payload",
        lambda *_args, **_kwargs: {
            "message": None,
            "data": [
                {
                    "time_bucket": datetime.now().replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:00"),
                    "total_heat": 12.3,
                    "post_count": 5,
                    "bull_vol": 3,
                    "bear_vol": 1,
                    "neutral_vol": 1,
                    "has_data": True,
                    "is_gap": False,
                    "price_close": 12.34,
                    "price_change_pct": 1.23,
                    "volume_proxy": 12345,
                    "has_price_data": True,
                    "bull_bear_ratio": 1.5,
                }
            ],
        },
    )

    resp = get_sentiment_trend("sh600519", interval="72h")
    assert resp.code == 200
    assert isinstance(resp.data, list)
    assert len(resp.data) > 0
    first_with_data = next(item for item in resp.data if bool(item["has_data"]))
    assert bool(first_with_data["has_data"]) is True
    assert bool(first_with_data["is_gap"]) is False
    assert first_with_data["has_price_data"] is True
    assert first_with_data["price_close"] == 12.34


def test_sentiment_trend_marks_gap_rows(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.build_sentiment_trend_payload",
        lambda *_args, **_kwargs: {
            "message": "No recent samples",
            "data": [
                {
                    "time_bucket": datetime.now().replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:00"),
                    "total_heat": 0.0,
                    "post_count": 0,
                    "bull_vol": 0,
                    "bear_vol": 0,
                    "neutral_vol": 0,
                    "has_data": False,
                    "is_gap": True,
                    "price_close": None,
                    "price_change_pct": None,
                    "volume_proxy": None,
                    "has_price_data": False,
                    "bull_bear_ratio": 0.0,
                }
            ],
        },
    )

    resp = get_sentiment_trend("sh600519", interval="72h")
    assert resp.code == 200
    gap_row = next(item for item in resp.data if not bool(item["has_data"]))
    assert bool(gap_row["has_data"]) is False
    assert bool(gap_row["is_gap"]) is True


def test_sentiment_trend_error_returns_api_response(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.app.routers.sentiment.build_sentiment_trend_payload", _raise)

    resp = get_sentiment_trend("sh600519")
    assert resp.code == 500
    assert resp.data == []


def test_sentiment_overview_v2_shape(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.build_overview_v2",
        lambda *_args, **_kwargs: {
            "symbol": "sh600519",
            "window": "5d",
            "window_label": "5D",
            "total_events": 18,
            "post_count": 5,
            "reply_count": 13,
            "relative_heat_index": 1.86,
            "relative_heat_label": "偏热",
            "baseline_daily_avg": 9.6,
            "latest_event_time": "2026-03-23 20:30:00",
            "active_source_count": 2,
            "active_sources": [{"source": "guba", "label": "股吧", "event_count": 16}],
            "coverage_status": "covered",
            "data_status_text": "已覆盖",
            "window_start": "2026-03-17",
            "window_end": "2026-03-23",
            "source_tabs": [{"source": "all", "label": "全部", "enabled": True}],
        },
    )

    payload = get_sentiment_overview("sh600519", window="5d")
    assert payload["symbol"] == "sh600519"
    assert payload["total_events"] == 18
    assert payload["relative_heat_index"] == 1.86


def test_sentiment_heat_trend_v2_shape(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.build_heat_trend_v2",
        lambda *_args, **_kwargs: [
            {
                "time_bucket": "2026-03-23",
                "bucket_label": "03-23",
                "event_count": 6,
                "post_count": 2,
                "reply_count": 4,
                "relative_heat_index": 1.6,
                "relative_heat_label": "偏热",
                "is_gap": False,
                "price_close": 12.34,
                "price_change_pct": -1.28,
                "volume_proxy": 123456.0,
                "has_price_data": True,
            }
        ],
    )

    payload = get_sentiment_heat_trend("sh600519", window="5d")
    assert isinstance(payload, list)
    assert payload[0]["event_count"] == 6
    assert payload[0]["has_price_data"] is True


def test_sentiment_feed_v2_shape(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routers.sentiment.build_feed_v2",
        lambda *_args, **_kwargs: {
            "items": [
                {
                    "event_id": "evt-1",
                    "source": "guba",
                    "source_label": "股吧",
                    "event_type": "post",
                    "event_type_label": "主帖",
                    "content": "测试内容",
                    "pub_time": "2026-03-23 20:30:00",
                    "view_count": 100,
                    "reply_count": 20,
                    "like_count": 0,
                    "repost_count": 0,
                }
            ],
            "coverage_status": "covered",
            "source_tabs": [{"source": "all", "label": "全部", "enabled": True}],
        },
    )

    payload = get_sentiment_feed("sh600519", window="5d", source="all", sort="latest", limit=20)
    assert payload["coverage_status"] == "covered"
    assert payload["items"][0]["source_label"] == "股吧"
