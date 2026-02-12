from fastapi import APIRouter
from typing import List
from backend.app.models.schemas import TickData, VerifyResult, APIResponse
from backend.app.services.market import fetch_live_ticks, fetch_tencent_snapshot
from backend.app.db.crud import get_ticks_by_date
from datetime import datetime

from backend.app.core.config import MOCK_DATA_DATE

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

@router.get("/verify_realtime", response_model=VerifyResult)
async def verify_realtime(symbol: str):
    """
    多源验证：同时拉取腾讯和东财的最新快照
    (Temporarily disabled due to refactor)
    """
    # return await verify_realtime_data(symbol)
    return VerifyResult(sina_price=0, tencent_price=0, diff=0, status="disabled")

from backend.app.services.analysis import calculate_realtime_aggregation

@router.get("/realtime/dashboard", response_model=APIResponse)
async def get_realtime_dashboard(symbol: str):
    """
    获取实时仪表盘聚合数据（分钟级资金流 + 最新Ticks）
    替代原有的 /ticks_full，解决前端计算压力和数据传输过大的问题。
    """
    if MOCK_DATA_DATE:
        today_str = MOCK_DATA_DATE
    else:
        today_str = datetime.now().strftime("%Y-%m-%d")

    data = calculate_realtime_aggregation(symbol, today_str)
    
    return APIResponse(code=200, data=data)

