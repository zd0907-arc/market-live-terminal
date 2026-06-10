import os
from typing import Dict, List, Optional

import requests

from backend.app.db.l2_history_db import query_l2_history_daily_rows
from backend.app.routers.analysis import _annotate_multiframe_change_pct, _build_multiframe_rows, _map_finalized_daily_row

SELECTION_CLOUD_API_BASE = os.getenv("SELECTION_CLOUD_API_BASE", "http://111.229.144.202/api").rstrip("/")
SELECTION_CLOUD_TIMEOUT = float(os.getenv("SELECTION_CLOUD_TIMEOUT", "8"))


def _env_flag(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _cloud_history_fallback_enabled() -> bool:
    # 选股多周期页面在本地只有占位数据时，默认允许回退云端补齐；
    # 如需强制关闭，可显式设置 SELECTION_ENABLE_CLOUD_HISTORY_FALLBACK=false。
    return _env_flag("SELECTION_ENABLE_CLOUD_HISTORY_FALLBACK", "true")


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
    allow_cloud_fallback: Optional[bool] = None,
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

    cloud_enabled = _cloud_history_fallback_enabled() if allow_cloud_fallback is None else bool(allow_cloud_fallback)
    if not cloud_enabled:
        return {
            "symbol": symbol,
            "granularity": granularity,
            "start_date": start_date,
            "end_date": end_date,
            "days": max(1, int(days)),
            "data_origin": "none",
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


def get_selection_multiframe_batch(
    symbols: List[str],
    granularity: str = "1d",
    days: int = 20,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_today_preview: bool = True,
    allow_cloud_fallback: bool = False,
) -> Dict[str, object]:
    normalized_symbols: List[str] = []
    seen = set()
    for symbol in symbols:
        normalized = str(symbol or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_symbols.append(normalized)

    items_by_symbol: Dict[str, Dict[str, object]] = {}
    errors: Dict[str, str] = {}
    for symbol in normalized_symbols:
        try:
            items_by_symbol[symbol] = get_selection_multiframe_rows(
                symbol=symbol,
                granularity=granularity,
                days=days,
                start_date=start_date,
                end_date=end_date,
                include_today_preview=include_today_preview,
                allow_cloud_fallback=allow_cloud_fallback,
            )
        except Exception as exc:
            errors[symbol] = str(exc)
            items_by_symbol[symbol] = {
                "symbol": symbol,
                "granularity": granularity,
                "start_date": start_date,
                "end_date": end_date,
                "days": max(1, int(days)),
                "data_origin": "error",
                "items": [],
                "warning": str(exc),
            }

    return {
        "symbols": normalized_symbols,
        "granularity": granularity,
        "start_date": start_date,
        "end_date": end_date,
        "days": max(1, int(days)),
        "include_today_preview": include_today_preview,
        "allow_cloud_fallback": allow_cloud_fallback,
        "items_by_symbol": items_by_symbol,
        "errors": errors,
    }


def get_selection_daily_kline_batch(
    symbols: List[str],
    days: int = 90,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, object]:
    normalized_symbols: List[str] = []
    seen = set()
    for symbol in symbols:
        normalized = str(symbol or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_symbols.append(normalized)

    items_by_symbol: Dict[str, Dict[str, object]] = {}
    errors: Dict[str, str] = {}
    normalized_days = max(1, int(days))
    limit_days = None if (start_date or end_date) else normalized_days
    for symbol in normalized_symbols:
        try:
            rows = query_l2_history_daily_rows(
                symbol,
                start_date=start_date,
                end_date=end_date,
                limit_days=limit_days,
            )
            mapped_rows = [_map_finalized_daily_row(row) for row in rows]
            if not start_date and not end_date:
                mapped_rows = mapped_rows[-normalized_days:]
            mapped_rows.sort(key=lambda item: str(item["datetime"]))
            mapped_rows = _annotate_multiframe_change_pct(mapped_rows, "1d")
            items_by_symbol[symbol] = {
                "symbol": symbol,
                "granularity": "1d",
                "start_date": start_date,
                "end_date": end_date,
                "days": normalized_days,
                "data_origin": "local" if _has_meaningful_rows(mapped_rows) else "none",
                "items": mapped_rows,
            }
        except Exception as exc:
            errors[symbol] = str(exc)
            items_by_symbol[symbol] = {
                "symbol": symbol,
                "granularity": "1d",
                "start_date": start_date,
                "end_date": end_date,
                "days": normalized_days,
                "data_origin": "error",
                "items": [],
                "warning": str(exc),
            }

    return {
        "symbols": normalized_symbols,
        "granularity": "1d",
        "start_date": start_date,
        "end_date": end_date,
        "days": normalized_days,
        "include_today_preview": False,
        "allow_cloud_fallback": False,
        "items_by_symbol": items_by_symbol,
        "errors": errors,
    }
