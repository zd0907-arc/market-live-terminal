from fastapi import APIRouter
from typing import List
from backend.app.models.schemas import TickData, VerifyResult, APIResponse
from backend.app.services.market import fetch_live_ticks, verify_realtime_data
from backend.app.db.crud import get_ticks_by_date
from datetime import datetime

router = APIRouter()

@router.get("/verify_realtime", response_model=VerifyResult)
def verify_realtime(symbol: str):
    """
    多源验证：同时拉取腾讯和东财的最新快照
    """
    return verify_realtime_data(symbol)

@router.get("/ticks_full", response_model=APIResponse)
def get_full_day_ticks(symbol: str):
    """
    获取某只股票当天的全量逐笔数据。
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. 尝试查库
    rows = get_ticks_by_date(symbol, today_str)

    if not rows:
        # 2. 如果库里没数据，尝试现场拉取 (Fall back to live fetch)
        records = fetch_live_ticks(symbol)
        if records:
            return APIResponse(code=200, data=records)
        else:
            return APIResponse(code=500, message="Live fetch failed", data=[])
            
    # 3. 库里有数据，格式化返回
    result = []
    for r in rows:
        t_type = 'neutral'
        if r[4] == '买盘': t_type = 'buy'
        elif r[4] == '卖盘': t_type = 'sell'
        
        result.append({
            "time": r[0],
            "price": r[1],
            "volume": r[2],
            "amount": r[3],
            "type": t_type
        })
        
    return APIResponse(code=200, data=result)
