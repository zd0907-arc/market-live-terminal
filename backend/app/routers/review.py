from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Query

from backend.app.db.l2_history_db import (
    aggregate_l2_history_5m_rows,
    query_l2_history_5m_rows,
    query_l2_history_daily_rows,
    query_review_pool,
)
from backend.app.models.schemas import APIResponse


router = APIRouter()


def normalize_review_symbol(symbol: str) -> str:
    raw = (symbol or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8:
        return raw
    if raw.isdigit() and len(raw) == 6:
        if raw.startswith(("6", "5")):
            return f"sh{raw}"
        if raw.startswith(("0", "3")):
            return f"sz{raw}"
        if raw.startswith(("4", "8", "9")):
            return f"bj{raw}"
    return raw


def _validate_date(value: str) -> None:
    datetime.strptime(value, "%Y-%m-%d")


def _normalize_granularity(value: str) -> str:
    text = str(value or "5m").strip().lower()
    aliases = {
        "60m": "1h",
        "1d": "1d",
        "day": "1d",
        "daily": "1d",
    }
    normalized = aliases.get(text, text)
    if normalized not in {"5m", "15m", "30m", "1h", "1d"}:
        raise ValueError("granularity 仅支持 5m/15m/30m/60m/1d")
    return normalized


def _public_granularity(value: str) -> str:
    return "60m" if value == "1h" else value


def _to_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _map_review_5m_row(row: Dict[str, object], granularity: str) -> Dict[str, object]:
    l1_main_buy = _to_float(row.get("l1_main_buy"))
    l1_main_sell = _to_float(row.get("l1_main_sell"))
    l1_super_buy = _to_float(row.get("l1_super_buy"))
    l1_super_sell = _to_float(row.get("l1_super_sell"))
    l2_main_buy = _to_float(row.get("l2_main_buy"))
    l2_main_sell = _to_float(row.get("l2_main_sell"))
    l2_super_buy = _to_float(row.get("l2_super_buy"))
    l2_super_sell = _to_float(row.get("l2_super_sell"))
    return {
        "symbol": str(row.get("symbol") or ""),
        "datetime": str(row.get("datetime") or ""),
        "bucket_granularity": _public_granularity(granularity),
        "open": _to_float(row.get("open")),
        "high": _to_float(row.get("high")),
        "low": _to_float(row.get("low")),
        "close": _to_float(row.get("close")),
        "total_amount": _to_float(row.get("total_amount")),
        "l1_main_buy": l1_main_buy,
        "l1_main_sell": l1_main_sell,
        "l1_main_net": l1_main_buy - l1_main_sell,
        "l1_super_buy": l1_super_buy,
        "l1_super_sell": l1_super_sell,
        "l1_super_net": l1_super_buy - l1_super_sell,
        "l2_main_buy": l2_main_buy,
        "l2_main_sell": l2_main_sell,
        "l2_main_net": l2_main_buy - l2_main_sell,
        "l2_super_buy": l2_super_buy,
        "l2_super_sell": l2_super_sell,
        "l2_super_net": l2_super_buy - l2_super_sell,
        "source_date": str(row.get("source_date") or ""),
        "quality_info": row.get("quality_info"),
    }


def _map_review_daily_row(row: Dict[str, object]) -> Dict[str, object]:
    l1_main_buy = _to_float(row.get("l1_main_buy"))
    l1_main_sell = _to_float(row.get("l1_main_sell"))
    l1_super_buy = _to_float(row.get("l1_super_buy"))
    l1_super_sell = _to_float(row.get("l1_super_sell"))
    l2_main_buy = _to_float(row.get("l2_main_buy"))
    l2_main_sell = _to_float(row.get("l2_main_sell"))
    l2_super_buy = _to_float(row.get("l2_super_buy"))
    l2_super_sell = _to_float(row.get("l2_super_sell"))
    source_date = str(row.get("date") or "")
    l1_main_net = row.get("l1_main_net")
    l1_super_net = row.get("l1_super_net")
    l2_main_net = row.get("l2_main_net")
    l2_super_net = row.get("l2_super_net")
    return {
        "symbol": str(row.get("symbol") or ""),
        "datetime": f"{source_date} 15:00:00",
        "bucket_granularity": "1d",
        "open": _to_float(row.get("open")),
        "high": _to_float(row.get("high")),
        "low": _to_float(row.get("low")),
        "close": _to_float(row.get("close")),
        "total_amount": _to_float(row.get("total_amount")),
        "l1_main_buy": l1_main_buy,
        "l1_main_sell": l1_main_sell,
        "l1_main_net": _to_float(l1_main_net) if l1_main_net is not None else (l1_main_buy - l1_main_sell),
        "l1_super_buy": l1_super_buy,
        "l1_super_sell": l1_super_sell,
        "l1_super_net": _to_float(l1_super_net) if l1_super_net is not None else (l1_super_buy - l1_super_sell),
        "l2_main_buy": l2_main_buy,
        "l2_main_sell": l2_main_sell,
        "l2_main_net": _to_float(l2_main_net) if l2_main_net is not None else (l2_main_buy - l2_main_sell),
        "l2_super_buy": l2_super_buy,
        "l2_super_sell": l2_super_sell,
        "l2_super_net": _to_float(l2_super_net) if l2_super_net is not None else (l2_super_buy - l2_super_sell),
        "source_date": source_date,
        "quality_info": row.get("quality_info"),
    }


@router.get("/pool", response_model=APIResponse)
def get_review_stock_pool(
    keyword: str = Query("", description="关键词过滤（symbol/name）"),
    limit: int = Query(0, ge=0, le=10000, description="返回数量上限，0表示不限制"),
):
    try:
        result = query_review_pool(keyword=keyword, limit=limit if limit > 0 else None)
        if result.get("total", 0) <= 0:
            return APIResponse(code=200, message="正式复盘股票池为空，请先迁移历史数据并刷新股票元数据", data=result)
        return APIResponse(code=200, data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"正式复盘股票池查询失败: {exc}", data=None)


@router.get("/data", response_model=APIResponse)
def get_review_data(
    symbol: str = Query(..., description="股票代码，如 sh603629"),
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    granularity: str = Query("5m", description="5m/15m/30m/60m/1d"),
):
    try:
        normalized_symbol = normalize_review_symbol(symbol)
        if not normalized_symbol.startswith(("sh", "sz", "bj")):
            return APIResponse(code=400, message="股票代码格式错误", data=[])

        _validate_date(start_date)
        _validate_date(end_date)
        if end_date < start_date:
            return APIResponse(code=400, message="结束日期必须大于等于开始日期", data=[])

        resolved_granularity = _normalize_granularity(granularity)
        if resolved_granularity == "1d":
            rows_daily = query_l2_history_daily_rows(normalized_symbol, start_date=start_date, end_date=end_date)
            if not rows_daily:
                return APIResponse(code=200, message="无数据", data=[])
            return APIResponse(code=200, data=[_map_review_daily_row(row) for row in rows_daily])

        rows_5m = query_l2_history_5m_rows(normalized_symbol, start_date=start_date, end_date=end_date)
        if not rows_5m:
            return APIResponse(code=200, message="无数据", data=[])
        aggregated = aggregate_l2_history_5m_rows(rows_5m, granularity=resolved_granularity)
        return APIResponse(code=200, data=[_map_review_5m_row(row, resolved_granularity) for row in aggregated])
    except ValueError as exc:
        return APIResponse(code=400, message=str(exc), data=[])
    except Exception as exc:
        return APIResponse(code=500, message=f"正式复盘查询失败: {exc}", data=[])
