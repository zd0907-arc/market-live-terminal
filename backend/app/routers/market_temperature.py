from fastapi import APIRouter, Query

from backend.app.models.schemas import APIResponse
from backend.app.services.market_temperature import get_market_temperature_snapshot


router = APIRouter()


@router.get("/market_temperature/snapshot", response_model=APIResponse)
def market_temperature_snapshot(
    date: str = Query(None, description="交易日 YYYY-MM-DD，默认最新"),
    days: int = Query(120, ge=5, le=520, description="回溯交易日数量"),
):
    try:
        return APIResponse(code=200, data=get_market_temperature_snapshot(date=date, days=days))
    except Exception as exc:
        return APIResponse(code=500, message=f"市场温度快照获取失败: {exc}", data=None)
