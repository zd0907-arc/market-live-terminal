from fastapi import APIRouter, Query

from backend.app.models.schemas import APIResponse
from backend.app.services.market_heat import build_market_heat_snapshot, load_snapshot, write_snapshot

router = APIRouter()


@router.get('/market_heat/latest', response_model=APIResponse)
def market_heat_latest(
    date: str = Query(None, description='交易日 YYYY-MM-DD，默认最新'),
    refresh: bool = Query(False, description='是否强制重新生成快照'),
):
    try:
        if refresh:
            snapshot = build_market_heat_snapshot(date)
            write_snapshot(snapshot)
        else:
            snapshot = load_snapshot(date, auto_generate=True)
        return APIResponse(code=200, data=snapshot)
    except Exception as exc:
        return APIResponse(code=500, message=f'市场热度快照获取失败: {exc}', data=None)
