from typing import List, Optional, Tuple

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.app.core.security import require_write_access
from backend.app.routers.ingest import verify_token


def make_request(headers: Optional[List[Tuple[bytes, bytes]]] = None, query_string: bytes = b"") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/test",
        "headers": headers or [],
        "query_string": query_string,
    }
    return Request(scope)


def test_require_write_access_rejects_when_server_token_missing(monkeypatch):
    monkeypatch.delenv("WRITE_API_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        require_write_access(make_request())

    assert exc.value.status_code == 503


def test_require_write_access_rejects_bad_header(monkeypatch):
    monkeypatch.setenv("WRITE_API_TOKEN", "good-token")

    with pytest.raises(HTTPException) as exc:
        require_write_access(make_request(headers=[(b"x-write-token", b"bad-token")]))

    assert exc.value.status_code == 401


def test_require_write_access_accepts_matching_header(monkeypatch):
    monkeypatch.setenv("WRITE_API_TOKEN", "good-token")

    require_write_access(make_request(headers=[(b"x-write-token", b"good-token")]))


def test_require_write_access_accepts_matching_query_token(monkeypatch):
    monkeypatch.setenv("WRITE_API_TOKEN", "good-token")

    require_write_access(make_request(query_string=b"token=good-token"))


def test_verify_token_rejects_when_ingest_token_missing(monkeypatch):
    monkeypatch.delenv("INGEST_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        verify_token("anything")

    assert exc.value.status_code == 503


def test_verify_token_rejects_bad_token(monkeypatch):
    monkeypatch.setenv("INGEST_TOKEN", "good-token")

    with pytest.raises(HTTPException) as exc:
        verify_token("bad-token")

    assert exc.value.status_code == 401


def test_verify_token_accepts_matching_token(monkeypatch):
    monkeypatch.setenv("INGEST_TOKEN", "good-token")

    verify_token("good-token")
