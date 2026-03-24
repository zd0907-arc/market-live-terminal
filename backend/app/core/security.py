import os
import secrets
from fastapi import HTTPException, Request


def _is_local_request(request: Request) -> bool:
    host = str(getattr(request.client, "host", "") or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def require_write_access(request: Request):
    """
    Guard mutating endpoints with a shared write token.
    In local development, if WRITE_API_TOKEN is absent, allow localhost requests.
    """
    expected = os.getenv("WRITE_API_TOKEN", "").strip()
    if not expected:
        if _is_local_request(request):
            return
        raise HTTPException(
            status_code=503,
            detail="WRITE_API_TOKEN is not configured on server"
        )

    provided = (
        request.headers.get("X-Write-Token")
        or request.query_params.get("token", "")
    ).strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized write access")
