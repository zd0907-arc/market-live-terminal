from fastapi import APIRouter, Query
from typing import List
import asyncio
from backend.app.models.schemas import TickData, VerifyResult, APIResponse
from backend.app.services.market import fetch_live_ticks, fetch_tencent_snapshot
from backend.app.db.crud import get_ticks_by_date, get_sentiment_history_aggregated
from datetime import datetime

from backend.app.core.config import MOCK_DATA_DATE
from backend.app.core.http_client import MarketClock
from backend.app.core.calendar import TradeCalendar
from backend.app.db.crud import save_ticks_daily_overwrite

router = APIRouter()


def _has_dashboard_payload(data) -> bool:
    if not data:
        return False
    return bool(data.get("chart_data") or data.get("cumulative_data") or data.get("latest_ticks"))


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
