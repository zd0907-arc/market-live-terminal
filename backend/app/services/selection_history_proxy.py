import os
from typing import Dict, List, Optional

import requests

from backend.app.routers.analysis import _build_multiframe_rows

SELECTION_CLOUD_API_BASE = os.getenv("SELECTION_CLOUD_API_BASE", "http://111.229.144.202/api").rstrip("/")
SELECTION_CLOUD_TIMEOUT = float(os.getenv("SELECTION_CLOUD_TIMEOUT", "8"))


def _has_meaningful_rows(rows: List[Dict[str, object]]) -> bool:
    if not rows:
        return False
    for row in rows:
        if bool(row.get("is_placeholder")):
            continue
        if any(
            row.get(key) is not None
            for key in ("close", "l1_main_buy", "l1_main_sell", "l2_main_buy", "l2_main_sell")
        ):
            return True
    return False


def _tag_cloud_rows(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    tagged: List[Dict[str, object]] = []
    for item in items:
        row = dict(item)
        source = str(row.get("source") or "history")
        row["source"] = f"cloud::{source}"
        row["fallback_used"] = True
        tagged.append(row)
    return tagged


def _fetch_cloud_multiframe(
    symbol: str,
    granularity: str,
    days: int,
    start_date: Optional[str],
    end_date: Optional[str],
    include_today_preview: bool,
) -> List[Dict[str, object]]:
    params = {
        "symbol": symbol,
        "granularity": granularity,
        "days": str(int(days)),
        "include_today_preview": "true" if include_today_preview else "false",
    }
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    response = requests.get(
        f"{SELECTION_CLOUD_API_BASE}/history/multiframe",
        params=params,
        timeout=SELECTION_CLOUD_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json() or {}
    data = payload.get("data") or {}
    items = data.get("items") or []
    if not isinstance(items, list):
        return []
    return _tag_cloud_rows(items)


def get_selection_multiframe_rows(
    symbol: str,
    granularity: str = "1d",
    days: int = 20,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_today_preview: bool = True,
) -> Dict[str, object]:
    local_rows = _build_multiframe_rows(
        symbol=symbol,
        granularity=granularity,
        days=max(1, int(days)),
        start_date=start_date,
        end_date=end_date,
        include_today_preview=include_today_preview,
    )
    if _has_meaningful_rows(local_rows):
        return {
            "symbol": symbol,
            "granularity": granularity,
            "start_date": start_date,
            "end_date": end_date,
            "days": max(1, int(days)),
            "data_origin": "local",
            "items": local_rows,
        }

    try:
        cloud_rows = _fetch_cloud_multiframe(
            symbol=symbol,
            granularity=granularity,
            days=max(1, int(days)),
            start_date=start_date,
            end_date=end_date,
            include_today_preview=include_today_preview,
        )
        if _has_meaningful_rows(cloud_rows):
            return {
                "symbol": symbol,
                "granularity": granularity,
                "start_date": start_date,
                "end_date": end_date,
                "days": max(1, int(days)),
                "data_origin": "cloud",
                "items": cloud_rows,
            }
    except Exception as exc:
        return {
            "symbol": symbol,
            "granularity": granularity,
            "start_date": start_date,
            "end_date": end_date,
            "days": max(1, int(days)),
            "data_origin": "none",
            "items": local_rows,
            "warning": f"cloud_fallback_failed: {exc}",
        }

    return {
        "symbol": symbol,
        "granularity": granularity,
        "start_date": start_date,
        "end_date": end_date,
        "days": max(1, int(days)),
        "data_origin": "none",
        "items": local_rows,
    }
