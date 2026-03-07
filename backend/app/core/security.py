import os
import secrets
from fastapi import HTTPException, Request


def require_write_access(request: Request):
    """
    Guard mutating endpoints with a shared write token.
    """
    expected = os.getenv("WRITE_API_TOKEN", "").strip()
    if not expected:
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
