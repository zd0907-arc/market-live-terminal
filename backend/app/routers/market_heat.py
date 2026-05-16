from fastapi import APIRouter, Query

from backend.app.models.schemas import APIResponse
from backend.app.services.market_heat import (
    build_fine_market_heat_dashboard,
    build_fine_theme_stock_detail,
    build_low_position_l2_sample_summary,
    build_market_heat_history_summary,
    build_market_heat_snapshot,
    get_low_position_l2_sample_detail,
    list_fine_heat_trade_dates,
    load_snapshot,
    query_low_position_l2_samples,
    refresh_fine_heat_snapshot_cache,
    write_snapshot,
)

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


@router.get('/market_heat/history', response_model=APIResponse)
def market_heat_history(
    end_date: str = Query(None, description='结束交易日 YYYY-MM-DD，默认最新'),
    days: int = Query(63, ge=5, le=260, description='回溯交易日数量'),
):
    try:
        return APIResponse(code=200, data=build_market_heat_history_summary(end_date=end_date, days=days))
    except Exception as exc:
        return APIResponse(code=500, message=f'市场热度历史获取失败: {exc}', data=None)


@router.get('/market_heat/fine_dashboard', response_model=APIResponse)
def market_heat_fine_dashboard(
    end_date: str = Query(None, description='结束交易日 YYYY-MM-DD，默认最新'),
    days: int = Query(63, ge=20, le=260, description='回溯交易日数量'),
    pool_size: int = Query(18, ge=8, le=50, description='动态展示池数量'),
):
    try:
        return APIResponse(code=200, data=build_fine_market_heat_dashboard(end_date=end_date, days=days, pool_size=pool_size))
    except Exception as exc:
        return APIResponse(code=500, message=f'细颗粒热点看板获取失败: {exc}', data=None)


@router.post('/market_heat/fine_dashboard/refresh', response_model=APIResponse)
def market_heat_fine_dashboard_refresh(
    end_date: str = Query(None, description='结束交易日 YYYY-MM-DD，默认最新'),
    days: int = Query(63, ge=20, le=260, description='重建回溯交易日数量'),
    force: bool = Query(True, description='是否强制重建缓存'),
):
    try:
        return APIResponse(code=200, data=refresh_fine_heat_snapshot_cache(end_date=end_date, days=days, force=force))
    except Exception as exc:
        return APIResponse(code=500, message=f'细颗粒热点缓存刷新失败: {exc}', data=None)


@router.get('/market_heat/fine_dates', response_model=APIResponse)
def market_heat_fine_dates(
    end_date: str = Query(None, description='结束交易日 YYYY-MM-DD，默认最新'),
    days: int = Query(260, ge=20, le=800, description='回溯交易日数量'),
):
    try:
        return APIResponse(code=200, data=list_fine_heat_trade_dates(end_date=end_date, days=days))
    except Exception as exc:
        return APIResponse(code=500, message=f'细颗粒热点日期获取失败: {exc}', data=None)


@router.get('/market_heat/fine_theme_stock_detail', response_model=APIResponse)
def market_heat_fine_theme_stock_detail(
    theme_id: str = Query(..., description='细颗粒主题ID'),
    end_date: str = Query(None, description='结束交易日 YYYY-MM-DD，默认最新'),
    history_days: int = Query(30, ge=20, le=60, description='单票微型K线回溯交易日数量'),
):
    try:
        return APIResponse(code=200, data=build_fine_theme_stock_detail(theme_id=theme_id, end_date=end_date, history_days=history_days))
    except Exception as exc:
        return APIResponse(code=500, message=f'细颗粒主题成分股详情获取失败: {exc}', data=None)


@router.get('/market_heat/low_position_l2_samples/summary', response_model=APIResponse)
def low_position_l2_samples_summary():
    try:
        return APIResponse(code=200, data=build_low_position_l2_sample_summary())
    except Exception as exc:
        return APIResponse(code=500, message=f'热点低位L2样本摘要获取失败: {exc}', data=None)


@router.get('/market_heat/low_position_l2_samples', response_model=APIResponse)
def low_position_l2_samples(
    start_date: str = Query(None, description='开始交易日 YYYY-MM-DD'),
    end_date: str = Query(None, description='结束交易日 YYYY-MM-DD'),
    outcome: str = Query('all', description='all/winner/positive/loser/negative'),
    theme: str = Query(None, description='板块名称'),
    sort: str = Query('date_desc', description='date_desc/date_asc/d5_desc/d5_asc/score_desc'),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    try:
        data = query_low_position_l2_samples(
            start_date=start_date,
            end_date=end_date,
            outcome=outcome,
            theme=theme,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        return APIResponse(code=200, data=data)
    except Exception as exc:
        return APIResponse(code=500, message=f'热点低位L2样本列表获取失败: {exc}', data=None)


@router.get('/market_heat/low_position_l2_samples/detail', response_model=APIResponse)
def low_position_l2_sample_detail(
    trade_date: str = Query(..., description='信号交易日 YYYY-MM-DD'),
    symbol: str = Query(..., description='股票代码，如 sz000001'),
):
    try:
        return APIResponse(code=200, data=get_low_position_l2_sample_detail(trade_date=trade_date, symbol=symbol))
    except Exception as exc:
        return APIResponse(code=500, message=f'热点低位L2样本详情获取失败: {exc}', data=None)
