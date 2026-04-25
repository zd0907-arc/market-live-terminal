from fastapi import APIRouter, Depends, Query

from backend.app.core.security import require_write_access
from backend.app.db.selection_db import ensure_selection_schema
from backend.app.models.schemas import APIResponse, SelectionBacktestRunRequest
from backend.app.services.selection_research import (
    get_backtest_run,
    get_candidates,
    get_profile,
    get_selection_health,
    get_selection_trade_dates,
    list_backtest_runs,
    refresh_selection_research,
    run_selection_backtest,
)
from backend.app.services.selection_history_proxy import get_selection_multiframe_rows

router = APIRouter()
ensure_selection_schema()


@router.get("/selection/health", response_model=APIResponse)
def selection_health():
    return APIResponse(code=200, data=get_selection_health())


@router.get("/selection/candidates", response_model=APIResponse)
def selection_candidates(
    date: str = Query(None, description="交易日 YYYY-MM-DD，缺省为最新可用日"),
    strategy: str = Query("breakout", description="stealth / breakout / distribution"),
    limit: int = Query(10, ge=1, le=500),
):
    try:
        return APIResponse(code=200, data=get_candidates(date, strategy=strategy, limit=limit))
    except Exception as exc:
        return APIResponse(code=500, message=f"选股候选查询失败: {exc}", data=None)


@router.get("/selection/trade-dates", response_model=APIResponse)
def selection_trade_dates(
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    strategy: str = Query("breakout", description="stealth / breakout / distribution"),
):
    try:
        return APIResponse(code=200, data=get_selection_trade_dates(start_date, end_date, strategy=strategy))
    except Exception as exc:
        return APIResponse(code=500, message=f"选股交易日查询失败: {exc}", data=None)


@router.get("/selection/profile/{symbol}", response_model=APIResponse)
def selection_profile(symbol: str, date: str = Query(None, description="交易日 YYYY-MM-DD，缺省为最新可用日")):
    try:
        return APIResponse(code=200, data=get_profile(symbol, date))
    except Exception as exc:
        return APIResponse(code=500, message=f"选股画像查询失败: {exc}", data=None)


@router.get("/selection/history/multiframe", response_model=APIResponse)
def selection_history_multiframe(
    symbol: str,
    granularity: str = Query("1d"),
    days: int = Query(20, ge=1, le=400),
    start_date: str = Query(None),
    end_date: str = Query(None),
    include_today_preview: bool = Query(True),
):
    try:
        payload = get_selection_multiframe_rows(
            symbol=symbol,
            granularity=granularity,
            days=days,
            start_date=start_date,
            end_date=end_date,
            include_today_preview=include_today_preview,
        )
        return APIResponse(code=200, data=payload)
    except Exception as exc:
        return APIResponse(code=500, message=f"选股历史多维查询失败: {exc}", data=None)


@router.get("/selection/backtests", response_model=APIResponse)
def selection_backtests(limit: int = Query(20, ge=1, le=200)):
    try:
        return APIResponse(code=200, data={"items": list_backtest_runs(limit=limit)})
    except Exception as exc:
        return APIResponse(code=500, message=f"选股回测列表查询失败: {exc}", data=None)


@router.get("/selection/backtests/{run_id}", response_model=APIResponse)
def selection_backtest_detail(run_id: int):
    try:
        payload = get_backtest_run(run_id)
        if payload is None:
            return APIResponse(code=404, message="回测任务不存在", data=None)
        return APIResponse(code=200, data=payload)
    except Exception as exc:
        return APIResponse(code=500, message=f"选股回测详情查询失败: {exc}", data=None)


@router.post("/selection/backtests/run", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def selection_backtests_run(request: SelectionBacktestRunRequest):
    try:
        payload = run_selection_backtest(
            strategy_name=request.strategy_name,
            start_date=request.start_date,
            end_date=request.end_date,
            holding_days_set=request.holding_days_set,
            max_positions_per_day=request.max_positions_per_day,
            stop_loss_pct=request.stop_loss_pct,
            take_profit_pct=request.take_profit_pct,
        )
        return APIResponse(code=200, message="回测执行完成", data=payload)
    except Exception as exc:
        return APIResponse(code=500, message=f"选股回测执行失败: {exc}", data=None)


@router.post("/selection/refresh", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def selection_refresh(start_date: str = Query(None), end_date: str = Query(None)):
    try:
        result = refresh_selection_research(start_date=start_date, end_date=end_date)
        return APIResponse(
            code=200,
            data={
                "start_date": result.start_date,
                "end_date": result.end_date,
                "feature_rows": result.feature_rows,
                "signal_rows": result.signal_rows,
                "source_snapshot": result.source_snapshot,
            },
        )
    except Exception as exc:
        return APIResponse(code=500, message=f"选股数据刷新失败: {exc}", data=None)
