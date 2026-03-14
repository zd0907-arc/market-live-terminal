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

router = APIRouter()

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
        today_str = MOCK_DATA_DATE
        natural_today_str = MOCK_DATA_DATE
    else:
        # display_date：前端应展示的交易日期（可能是上一交易日）
        today_str = MarketClock.get_display_date()
        # natural_today：自然日，用于判断“是否真的应该走实时路径”
        natural_today_str = MarketClock._now_china().strftime("%Y-%m-%d")

    query_date = date if date else today_str

    should_use_realtime = (
        query_date == natural_today_str
        and TradeCalendar.is_trade_day(natural_today_str)
    )

    if should_use_realtime:
        # 仅在“自然日当天且为交易日”时走实时 ticks 聚合。
        # 周末/节假日/盘前回溯到上一交易日时，应走 history_1m 静态回放，
        # 否则会因为当前不在实时采集窗口而出现“当日分时为空”。
        from backend.app.services.analysis import calculate_realtime_aggregation
        data = calculate_realtime_aggregation(symbol, natural_today_str)
    else:
        # 历史日期，强解耦：直接查询预聚合好的 history_1m 静态表
        from backend.app.services.analysis import get_history_1m_dashboard
        data = await asyncio.to_thread(get_history_1m_dashboard, symbol, query_date)
        # Handle 404
        if data is None:
            return APIResponse(code=404, message="No pre-aggregated intraday data for this date", data=None)
    
    # Inject display date for frontend awareness
    if data:
        data['display_date'] = query_date
    
    return APIResponse(code=200, data=data)
