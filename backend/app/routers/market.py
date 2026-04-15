from fastapi import APIRouter, Query
from typing import List, Optional
import asyncio
import threading
import time
import logging
from backend.app.models.schemas import TickData, VerifyResult, APIResponse
from backend.app.services.market import fetch_live_ticks, fetch_tencent_snapshot
from backend.app.db.crud import get_ticks_by_date, get_sentiment_history_aggregated
from datetime import datetime, timedelta, time as dt_time

from backend.app.core.config import MOCK_DATA_DATE
from backend.app.core.http_client import MarketClock
from backend.app.core.calendar import TradeCalendar
from backend.app.db.crud import save_ticks_daily_overwrite
from backend.app.db.l2_history_db import query_l2_history_5m_rows
from backend.app.db.realtime_preview_db import query_realtime_5m_preview_rows

router = APIRouter()
_STALE_HYDRATE_ATTEMPTS = {}
_STALE_HYDRATE_LOCK = threading.Lock()
_STALE_HYDRATE_COOLDOWN_SECONDS = 120
logger = logging.getLogger(__name__)


def _safe_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_intraday_fusion_mode(query_date: str, natural_today: str, has_finalized_today: bool) -> tuple[str, str]:
    if query_date != natural_today:
        return ("historical_dual_track", "历史 L1/L2 双轨")
    if has_finalized_today:
        return ("postclose_dual_track", "盘后 L1/L2 双轨")
    return ("intraday_l1_only", "盘中 L1 单轨")


def _map_finalized_fusion_bar(row: dict) -> dict:
    l1_main_buy = _safe_float(row.get("l1_main_buy")) or 0.0
    l1_main_sell = _safe_float(row.get("l1_main_sell")) or 0.0
    l2_main_buy = _safe_float(row.get("l2_main_buy")) or 0.0
    l2_main_sell = _safe_float(row.get("l2_main_sell")) or 0.0
    return {
        "datetime": str(row["datetime"]),
        "trade_date": str(row["source_date"]),
        "open": _safe_float(row.get("open")),
        "high": _safe_float(row.get("high")),
        "low": _safe_float(row.get("low")),
        "close": _safe_float(row.get("close")),
        "total_amount": _safe_float(row.get("total_amount")),
        "total_volume": _safe_float(row.get("total_volume")),
        "l1_main_buy": l1_main_buy,
        "l1_main_sell": l1_main_sell,
        "l1_super_buy": _safe_float(row.get("l1_super_buy")) or 0.0,
        "l1_super_sell": _safe_float(row.get("l1_super_sell")) or 0.0,
        "l1_net_inflow": l1_main_buy - l1_main_sell,
        "l2_main_buy": l2_main_buy,
        "l2_main_sell": l2_main_sell,
        "l2_super_buy": _safe_float(row.get("l2_super_buy")) or 0.0,
        "l2_super_sell": _safe_float(row.get("l2_super_sell")) or 0.0,
        "l2_net_inflow": l2_main_buy - l2_main_sell,
        "add_buy_amount": _safe_float(row.get("l2_add_buy_amount")),
        "add_sell_amount": _safe_float(row.get("l2_add_sell_amount")),
        "cancel_buy_amount": _safe_float(row.get("l2_cancel_buy_amount")),
        "cancel_sell_amount": _safe_float(row.get("l2_cancel_sell_amount")),
        "l2_cvd_delta": _safe_float(row.get("l2_cvd_delta")),
        "l2_oib_delta": _safe_float(row.get("l2_oib_delta")),
        "source": "l2_history",
        "is_finalized": True,
        "preview_level": None,
        "fallback_used": False,
    }


def _map_preview_fusion_bar(row: dict, source_override: str = None, preview_level_override: str = None) -> dict:
    l1_main_buy = _safe_float(row.get("l1_main_buy")) or 0.0
    l1_main_sell = _safe_float(row.get("l1_main_sell")) or 0.0
    return {
        "datetime": str(row["datetime"]),
        "trade_date": str(row["trade_date"]),
        "open": _safe_float(row.get("open")),
        "high": _safe_float(row.get("high")),
        "low": _safe_float(row.get("low")),
        "close": _safe_float(row.get("close")),
        "total_amount": _safe_float(row.get("total_amount")),
        "total_volume": _safe_float(row.get("total_volume")),
        "l1_main_buy": l1_main_buy,
        "l1_main_sell": l1_main_sell,
        "l1_super_buy": _safe_float(row.get("l1_super_buy")) or 0.0,
        "l1_super_sell": _safe_float(row.get("l1_super_sell")) or 0.0,
        "l1_net_inflow": l1_main_buy - l1_main_sell,
        "l2_main_buy": None,
        "l2_main_sell": None,
        "l2_super_buy": None,
        "l2_super_sell": None,
        "l2_net_inflow": None,
        "add_buy_amount": None,
        "add_sell_amount": None,
        "cancel_buy_amount": None,
        "cancel_sell_amount": None,
        "l2_cvd_delta": None,
        "l2_oib_delta": None,
        "source": str(source_override or row.get("source") or "realtime_ticks"),
        "is_finalized": False,
        "preview_level": str(preview_level_override or row.get("preview_level") or "l1_only"),
        "fallback_used": False,
    }


def _has_dashboard_payload(data) -> bool:
    if not data:
        return False
    return bool(
        data.get("chart_data")
        or data.get("cumulative_data")
        or data.get("latest_ticks")
        or data.get("bars")
    )


def _parse_intraday_time(value):
    text = str(value or "").strip()
    if not text:
        return None

    if " " in text:
        text = text.split(" ")[-1]

    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _extract_latest_intraday_time(data) -> Optional[dt_time]:
    if not data:
        return None

    latest_ticks = data.get("latest_ticks") or []
    if latest_ticks:
        parsed = _parse_intraday_time((latest_ticks[0] or {}).get("time"))
        if parsed:
            return parsed

    latest_tick = data.get("latest_tick") or {}
    parsed = _parse_intraday_time(latest_tick.get("time"))
    if parsed:
        return parsed

    chart_data = data.get("chart_data") or []
    if chart_data:
        parsed = _parse_intraday_time((chart_data[-1] or {}).get("time"))
        if parsed:
            return parsed

    bars = data.get("bars") or []
    if bars:
        parsed = _parse_intraday_time((bars[-1] or {}).get("datetime"))
        if parsed:
            return parsed

    return None


def _expected_floor_time(market_context: dict) -> Optional[dt_time]:
    market_status = str(market_context.get("market_status") or "")
    now = MarketClock._now_china()
    natural_today = str(market_context.get("natural_today") or "")
    actual_today = now.strftime("%Y-%m-%d")

    if market_status == "trading":
        if natural_today and natural_today != actual_today:
            return None
        current_floor = (now - timedelta(minutes=10)).time()
        if current_floor < dt_time(9, 25):
            return dt_time(9, 25)
        if dt_time(11, 30) < current_floor < dt_time(13, 0):
            return dt_time(11, 25)
        return current_floor

    if market_status == "lunch_break":
        return dt_time(11, 25)

    if market_status == "post_close":
        return dt_time(14, 55)

    return None


def _is_today_payload_stale(data, market_context: dict, query_date: str, natural_today: str) -> bool:
    if query_date != natural_today:
        return False
    if not _has_dashboard_payload(data):
        return False

    floor_time = _expected_floor_time(market_context)
    if floor_time is None:
        return False

    latest_time = _extract_latest_intraday_time(data)
    if latest_time is None:
        return True

    return latest_time < floor_time


def _mark_stale_hydrate_attempt(symbol: str, trade_date: str, force: bool = False) -> bool:
    key = (str(symbol), str(trade_date))
    now_ts = time.time()
    with _STALE_HYDRATE_LOCK:
        last_ts = _STALE_HYDRATE_ATTEMPTS.get(key, 0.0)
        if (not force) and now_ts - last_ts < _STALE_HYDRATE_COOLDOWN_SECONDS:
            return False
        _STALE_HYDRATE_ATTEMPTS[key] = now_ts
        return True


def _needs_postclose_forced_retry(market_context: dict) -> bool:
    return str(market_context.get("market_status") or "") == "post_close"


async def _rehydrate_today_if_stale(
    symbol: str,
    query_date: str,
    natural_today: str,
    market_context: dict,
    *,
    force: bool = False,
    max_attempts: int = 1,
) -> bool:
    if query_date != natural_today:
        return False
    if not _mark_stale_hydrate_attempt(symbol, query_date, force=force):
        return False

    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        try:
            hydrated = await _hydrate_today_ticks_on_demand(symbol, query_date)
        except Exception as exc:
            logger.warning(
                "stale intraday rehydrate failed: symbol=%s date=%s attempt=%s/%s err=%s",
                symbol,
                query_date,
                attempt,
                attempts,
                exc,
            )
            hydrated = False

        if hydrated:
            logger.info(
                "stale intraday rehydrate success: symbol=%s date=%s attempt=%s/%s",
                symbol,
                query_date,
                attempt,
                attempts,
            )
            return True

        if attempt < attempts:
            await asyncio.sleep(1)

    return False


async def _hydrate_today_ticks_on_demand(symbol: str, date_str: str) -> bool:
    """
    当用户查看“今天”的分时，但本地尚无该股票数据时，
    按需从外部源抓当天 full-day ticks 并写入本地，供后续聚合使用。
    """
    records = await fetch_live_ticks(symbol)
    if not records:
        return False

    data_to_insert = []
    for item in records:
        data_to_insert.append(
            (
                symbol,
                item["time"],
                float(item["price"]),
                int(item["volume"]),
                float(item["amount"]),
                str(item["type"]),
                date_str,
            )
        )

    await asyncio.to_thread(save_ticks_daily_overwrite, symbol, date_str, data_to_insert)

    from backend.app.services.analysis import aggregate_intraday_1m

    await asyncio.to_thread(aggregate_intraday_1m, symbol, date_str)
    return True


def _build_view_mode(query_date: str, market_context: dict) -> tuple[str, str]:
    natural_today = str(market_context["natural_today"])
    default_display_date = str(market_context["default_display_date"])
    market_status = str(market_context["market_status"])

    if query_date != default_display_date:
        return ("manual_date", f"手动查看指定日期数据（{query_date}）")

    if query_date != natural_today:
        return ("previous_trade_day", "默认展示上一交易日数据")

    if market_status == "trading":
        return ("today_realtime", "默认展示今日实时数据")

    if market_status == "lunch_break":
        return ("today_midday_review", "默认展示今日午间休市前已采集数据")

    if market_status == "post_close":
        return ("today_postclose_review", "默认展示今日收盘后数据")

    return ("today_non_realtime", "默认展示今日非实时数据")

@router.get("/sentiment", response_model=APIResponse)
async def get_sentiment_dashboard(symbol: str):
    """
    获取腾讯快照数据用于情绪仪表盘 (Tencent Sentiment Dashboard)
    """
    data = await fetch_tencent_snapshot(symbol)
    if data:
        return APIResponse(code=200, data=data)
    return APIResponse(code=500, message="Failed to fetch sentiment data", data=None)

@router.get("/sentiment/history", response_model=APIResponse)
async def get_sentiment_history_api(symbol: str, date: str = Query(None)):
    """
    V3.0: 获取分钟级聚合的历史资金博弈数据
    支持可选的 date 参数用于回溯历史数据。
    """
    if date:
        query_date = date
    else:
        query_date = MarketClock.get_display_date()
        # For testing, if MOCK_DATA_DATE is set, use it?
        if MOCK_DATA_DATE:
            query_date = MOCK_DATA_DATE
        
    data = await asyncio.to_thread(get_sentiment_history_aggregated, symbol, query_date)
    return APIResponse(code=200, data=data)

@router.get("/verify_realtime", response_model=VerifyResult)
async def verify_realtime(symbol: str):
    """
    多源验证：同时拉取腾讯和东财的最新快照
    (Temporarily disabled due to refactor)
    """
    # return await verify_realtime_data(symbol)
    return VerifyResult(tencent=None, eastmoney=None)

@router.get("/realtime/dashboard", response_model=APIResponse)
async def get_realtime_dashboard(symbol: str, date: str = Query(None)):
    """
    获取实时仪表盘聚合数据（分钟级资金流 + 最新Ticks）
    支持传入 date 来秒切历史 1分钟预聚合分时图。
    """
    if MOCK_DATA_DATE:
        market_context = {
            "natural_today": MOCK_DATA_DATE,
            "is_trade_day": True,
            "market_status": "mock",
            "market_status_label": "Mock 日期",
            "default_display_date": MOCK_DATA_DATE,
            "default_display_scope": "today",
            "default_display_scope_label": "Mock 展示今日数据",
            "should_use_realtime_path": False,
        }
    else:
        market_context = MarketClock.get_market_context()

    today_str = str(market_context["default_display_date"])
    natural_today_str = str(market_context["natural_today"])

    query_date = date if date else today_str

    should_use_realtime = (
        query_date == natural_today_str
        and bool(market_context.get("should_use_realtime_path"))
    )

    if should_use_realtime:
        # 仅在“自然日当天且为交易日”时走实时 ticks 聚合。
        # 周末/节假日/盘前回溯到上一交易日时，应走 history_1m 静态回放，
        # 否则会因为当前不在实时采集窗口而出现“当日分时为空”。
        from backend.app.services.analysis import calculate_realtime_aggregation, get_sentiment_fallback_dashboard
        data = calculate_realtime_aggregation(symbol, natural_today_str)
        if _is_today_payload_stale(data, market_context, query_date, natural_today_str):
            hydrated = await _rehydrate_today_if_stale(
                symbol,
                query_date,
                natural_today_str,
                market_context,
                force=_needs_postclose_forced_retry(market_context),
                max_attempts=2 if _needs_postclose_forced_retry(market_context) else 1,
            )
            if hydrated:
                data = calculate_realtime_aggregation(symbol, natural_today_str)
        if not _has_dashboard_payload(data):
            hydrated = await _hydrate_today_ticks_on_demand(symbol, natural_today_str)
            if hydrated:
                data = calculate_realtime_aggregation(symbol, natural_today_str)
        if not _has_dashboard_payload(data):
            fallback = get_sentiment_fallback_dashboard(symbol, natural_today_str)
            if fallback is not None:
                data = fallback
    else:
        # 历史/回溯日期：
        # 1) 优先读预聚合 history_1m；
        # 2) 若 history_1m 缺失，则尝试正式 L2 历史 5m；
        # 3) 若仍缺失，但 trade_ticks 已存在，则回退用该日 ticks 现场聚合。
        from backend.app.services.analysis import (
            get_history_1m_dashboard,
            get_history_l2_dashboard,
            calculate_realtime_aggregation,
            get_sentiment_fallback_dashboard,
        )
        data = await asyncio.to_thread(get_history_1m_dashboard, symbol, query_date)
        if _is_today_payload_stale(data, market_context, query_date, natural_today_str):
            fallback = calculate_realtime_aggregation(symbol, query_date)
            if _has_dashboard_payload(fallback):
                data = fallback
            if _is_today_payload_stale(data, market_context, query_date, natural_today_str):
                hydrated = await _rehydrate_today_if_stale(
                    symbol,
                    query_date,
                    natural_today_str,
                    market_context,
                    force=_needs_postclose_forced_retry(market_context),
                    max_attempts=2 if _needs_postclose_forced_retry(market_context) else 1,
                )
                if hydrated:
                    data = calculate_realtime_aggregation(symbol, query_date)
        if data is None:
            data = await asyncio.to_thread(get_history_l2_dashboard, symbol, query_date)
        if data is None:
            fallback = calculate_realtime_aggregation(symbol, query_date)
            if _has_dashboard_payload(fallback):
                data = fallback
        if data is None and query_date == natural_today_str:
            hydrated = await _hydrate_today_ticks_on_demand(symbol, natural_today_str)
            if hydrated:
                data = await asyncio.to_thread(get_history_1m_dashboard, symbol, query_date)
                if data is None:
                    fallback = calculate_realtime_aggregation(symbol, query_date)
                    if _has_dashboard_payload(fallback):
                        data = fallback
        if data is None and query_date == natural_today_str:
            fallback = get_sentiment_fallback_dashboard(symbol, query_date)
            if fallback is not None:
                data = fallback
        if data is None:
            return APIResponse(code=404, message="No pre-aggregated intraday data for this date", data=None)
    
    # Inject display date for frontend awareness
    if data:
        data['display_date'] = query_date
        data['natural_today'] = natural_today_str
        data['market_status'] = market_context['market_status']
        data['market_status_label'] = market_context['market_status_label']
        data['default_display_date'] = today_str
        data['default_display_scope'] = market_context['default_display_scope']
        data['default_display_scope_label'] = market_context['default_display_scope_label']
        view_mode, view_mode_label = _build_view_mode(query_date, market_context)
        data['view_mode'] = view_mode
        data['view_mode_label'] = view_mode_label
        data['is_realtime_session'] = bool(market_context.get('should_use_realtime_path'))
    
    return APIResponse(code=200, data=data)


@router.get("/realtime/intraday_fusion", response_model=APIResponse)
async def get_intraday_fusion(symbol: str, date: str = Query(None), include_today_preview: bool = Query(True)):
    """
    当日分时页统一双轨接口：
    - 盘中：L1 5m preview
    - 当天盘后 finalized 到位：L1/L2 finalized 5m
    - 历史日期：L1/L2 finalized 5m
    """
    if MOCK_DATA_DATE:
        market_context = {
            "natural_today": MOCK_DATA_DATE,
            "is_trade_day": True,
            "market_status": "mock",
            "market_status_label": "Mock 日期",
            "default_display_date": MOCK_DATA_DATE,
            "default_display_scope": "today",
            "default_display_scope_label": "Mock 展示今日数据",
            "should_use_realtime_path": False,
        }
    else:
        market_context = MarketClock.get_market_context()

    natural_today = str(market_context["natural_today"])
    query_date = date if date else str(market_context["default_display_date"])

    finalized_rows = await asyncio.to_thread(
        query_l2_history_5m_rows,
        symbol,
        query_date,
        query_date,
        None,
    )
    has_finalized_today = query_date == natural_today and len(finalized_rows) > 0
    mode, mode_label = _build_intraday_fusion_mode(query_date, natural_today, has_finalized_today)

    bars = []
    source = "l2_history"
    is_l2_finalized = mode != "intraday_l1_only"

    if mode == "intraday_l1_only":
        from backend.app.services.analysis import refresh_realtime_preview

        if include_today_preview and query_date == natural_today:
            await asyncio.to_thread(refresh_realtime_preview, symbol, query_date)
        preview_rows = await asyncio.to_thread(
            query_realtime_5m_preview_rows,
            symbol,
            query_date,
            query_date,
            None,
        )
        preview_payload = {"bars": [_map_preview_fusion_bar(row) for row in preview_rows]}
        if include_today_preview and _is_today_payload_stale(preview_payload, market_context, query_date, natural_today):
            hydrated = await _rehydrate_today_if_stale(
                symbol,
                query_date,
                natural_today,
                market_context,
                force=_needs_postclose_forced_retry(market_context),
                max_attempts=2 if _needs_postclose_forced_retry(market_context) else 1,
            )
            if hydrated:
                await asyncio.to_thread(refresh_realtime_preview, symbol, query_date)
                preview_rows = await asyncio.to_thread(
                    query_realtime_5m_preview_rows,
                    symbol,
                    query_date,
                    query_date,
                    None,
                )
        if not preview_rows and query_date == natural_today:
            hydrated = await _hydrate_today_ticks_on_demand(symbol, natural_today)
            if hydrated:
                await asyncio.to_thread(refresh_realtime_preview, symbol, query_date)
                preview_rows = await asyncio.to_thread(
                    query_realtime_5m_preview_rows,
                    symbol,
                    query_date,
                    query_date,
                    None,
                )
        bars = [_map_preview_fusion_bar(row) for row in preview_rows]
        source = "realtime_preview"
        is_l2_finalized = False
    else:
        if finalized_rows:
            bars = [_map_finalized_fusion_bar(row) for row in finalized_rows]
        else:
            from backend.app.services.analysis import refresh_realtime_preview

            await asyncio.to_thread(refresh_realtime_preview, symbol, query_date)
            preview_rows = await asyncio.to_thread(
                query_realtime_5m_preview_rows,
                symbol,
                query_date,
                query_date,
                None,
            )
            if preview_rows:
                bars = [
                    _map_preview_fusion_bar(
                        row,
                        source_override="history_l1_fallback",
                        preview_level_override="historical_l1_fallback",
                    )
                    for row in preview_rows
                ]
                source = "history_l1_fallback"
                is_l2_finalized = False
            else:
                bars = []

    return APIResponse(
        code=200,
        data={
            "symbol": symbol,
            "trade_date": query_date,
            "mode": mode,
            "mode_label": mode_label,
            "bucket_granularity": "5m",
            "is_l2_finalized": is_l2_finalized,
            "source": source,
            "fallback_used": source == "history_l1_fallback",
            "bars": bars,
        },
    )
