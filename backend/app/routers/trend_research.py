from fastapi import APIRouter

from backend.app.models.schemas import APIResponse
from backend.app.services.trend_research import get_trend_dashboard, list_trend_ideas

router = APIRouter()


@router.get("/trend-research/ideas", response_model=APIResponse)
def trend_research_ideas():
    try:
        return APIResponse(code=200, data=list_trend_ideas())
    except Exception as exc:
        return APIResponse(code=500, message=f"趋势线索列表查询失败: {exc}", data=None)


@router.get("/trend-research/ideas/{idea_id}/dashboard", response_model=APIResponse)
def trend_research_dashboard(idea_id: str):
    try:
        return APIResponse(code=200, data=get_trend_dashboard(idea_id))
    except Exception as exc:
        return APIResponse(code=500, message=f"趋势线索看板查询失败: {exc}", data=None)
