from fastapi import APIRouter, Depends, Query

from backend.app.core.security import require_write_access
from backend.app.models.schemas import APIResponse
from backend.app.services.stock_events import (
    audit_stock_event_collection,
    backfill_symbol_announcements,
    backfill_symbol_news,
    backfill_symbol_qa,
    get_stock_event_source_capabilities,
    get_stock_event_coverage,
    hydrate_symbol_event_context,
    list_stock_event_feed,
    run_watchlist_news_backfill,
    run_watchlist_announcement_backfill,
    run_watchlist_qa_backfill,
    sync_symbol_event_bundle,
    sync_major_news,
    sync_shanghai_qa,
    sync_shenzhen_qa,
    sync_symbol_announcements,
    sync_short_news,
)

router = APIRouter(prefix="/stock_events", tags=["Stock Events"])


@router.get("/capabilities", response_model=APIResponse)
def stock_event_capabilities():
    try:
        payload = get_stock_event_source_capabilities()
        return APIResponse(code=200, data=payload)
    except Exception as exc:
        return APIResponse(code=500, message=f"事件源能力查询失败: {exc}", data={})


@router.get("/feed/{symbol}", response_model=APIResponse)
def stock_event_feed(
    symbol: str,
    limit: int = Query(50, ge=1, le=200),
    source_type: str = Query(None),
    source: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
):
    try:
        payload = list_stock_event_feed(
            symbol,
            limit=limit,
            source_type=source_type,
            source=source,
            start_date=start_date,
            end_date=end_date,
        )
        return APIResponse(code=200, data=payload)
    except Exception as exc:
        return APIResponse(code=500, message=f"事件流查询失败: {exc}", data={"items": []})


@router.get("/coverage/{symbol}", response_model=APIResponse)
def stock_event_coverage(
    symbol: str,
    days: int = Query(365, ge=1, le=3650),
):
    try:
        payload = get_stock_event_coverage(symbol, days=days)
        return APIResponse(code=200, data=payload)
    except Exception as exc:
        return APIResponse(code=500, message=f"事件覆盖摘要查询失败: {exc}", data={})


@router.get("/audit/{symbol}", response_model=APIResponse)
def stock_event_audit(
    symbol: str,
    days: int = Query(365, ge=1, le=3650),
    recent_limit: int = Query(12, ge=1, le=100),
):
    try:
        payload = audit_stock_event_collection(symbol, days=days, recent_limit=recent_limit)
        return APIResponse(code=200, data=payload)
    except Exception as exc:
        return APIResponse(code=500, message=f"事件采集审计失败: {exc}", data={})


@router.post("/announcements/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_sync_announcements(
    symbol: str,
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
):
    try:
        result = sync_symbol_announcements(symbol, start_date=start_date, end_date=end_date, mode="manual")
        return APIResponse(code=200, message="公告同步完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"公告同步失败: {exc}", data={})


@router.post("/qa/shenzhen/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_sync_shenzhen_qa(
    symbol: str,
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
):
    try:
        result = sync_shenzhen_qa(symbol, start_date=start_date, end_date=end_date, mode="manual")
        return APIResponse(code=200, message="深市互动问答同步完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"深市互动问答同步失败: {exc}", data={})


@router.post("/qa/shanghai/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_sync_shanghai_qa(
    symbol: str,
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
):
    try:
        result = sync_shanghai_qa(symbol, start_date=start_date, end_date=end_date, mode="manual")
        return APIResponse(code=200, message="沪市互动问答同步完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"沪市互动问答同步失败: {exc}", data={})


@router.post("/news/short/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_sync_short_news(
    symbol: str,
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
):
    try:
        result = sync_short_news(symbol, start_date=start_date, end_date=end_date, mode="manual")
        return APIResponse(code=200, message="财经快讯同步完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"财经快讯同步失败: {exc}", data={})


@router.post("/news/major/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_sync_major_news(
    symbol: str,
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
):
    try:
        result = sync_major_news(symbol, start_date=start_date, end_date=end_date, mode="manual")
        return APIResponse(code=200, message="长篇资讯同步完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"长篇资讯同步失败: {exc}", data={})


@router.post("/bundle/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_sync_bundle(
    symbol: str,
    announcement_days: int = Query(365, ge=1, le=3650),
    qa_days: int = Query(180, ge=1, le=3650),
    news_days: int = Query(30, ge=1, le=3650),
):
    try:
        result = sync_symbol_event_bundle(
            symbol,
            announcement_days=announcement_days,
            qa_days=qa_days,
            news_days=news_days,
            mode="manual_bundle",
        )
        return APIResponse(code=200, message="单票事件包同步完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"单票事件包同步失败: {exc}", data={})


@router.post("/hydrate/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_hydrate(
    symbol: str,
    announcement_days: int = Query(365, ge=1, le=3650),
    qa_days: int = Query(180, ge=1, le=3650),
    news_days: int = Query(30, ge=1, le=3650),
    recent_limit: int = Query(12, ge=1, le=100),
):
    try:
        result = hydrate_symbol_event_context(
            symbol,
            announcement_days=announcement_days,
            qa_days=qa_days,
            news_days=news_days,
            recent_limit=recent_limit,
            mode="selection_candidate",
        )
        return APIResponse(code=200, message="单票事件上下文准备完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"单票事件上下文准备失败: {exc}", data={})


@router.post("/internal/backfill_announcements/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_backfill_announcements(symbol: str, days: int = Query(365, ge=1, le=3650)):
    try:
        result = backfill_symbol_announcements(symbol, days=days)
        return APIResponse(code=200, message="公告回补完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"公告回补失败: {exc}", data={})


@router.post("/internal/backfill_qa/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_backfill_qa(symbol: str, days: int = Query(180, ge=1, le=3650), market: str = Query("auto")):
    try:
        result = backfill_symbol_qa(symbol, days=days, market=market)
        return APIResponse(code=200, message="互动问答回补完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"互动问答回补失败: {exc}", data={})


@router.post("/internal/backfill_news/{symbol}", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_backfill_news(symbol: str, days: int = Query(30, ge=1, le=3650)):
    try:
        result = backfill_symbol_news(symbol, days=days)
        return APIResponse(code=200, message="财经资讯回补完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"财经资讯回补失败: {exc}", data={})


@router.post("/internal/run_watchlist_announcements", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_run_watchlist_announcements(days: int = Query(365, ge=1, le=3650)):
    try:
        result = run_watchlist_announcement_backfill(days=days)
        return APIResponse(code=200, message="Watchlist 公告回补完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"Watchlist 公告回补失败: {exc}", data={})


@router.post("/internal/run_watchlist_qa", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_run_watchlist_qa(days: int = Query(180, ge=1, le=3650)):
    try:
        result = run_watchlist_qa_backfill(days=days)
        return APIResponse(code=200, message="Watchlist 互动问答回补完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"Watchlist 互动问答回补失败: {exc}", data={})


@router.post("/internal/run_watchlist_news", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def stock_event_run_watchlist_news(days: int = Query(30, ge=1, le=3650)):
    try:
        result = run_watchlist_news_backfill(days=days)
        return APIResponse(code=200, message="Watchlist 财经资讯回补完成", data=result)
    except Exception as exc:
        return APIResponse(code=500, message=f"Watchlist 财经资讯回补失败: {exc}", data={})
