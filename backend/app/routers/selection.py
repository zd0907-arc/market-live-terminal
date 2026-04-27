from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

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
from backend.app.services.selection_research_context import (
    get_selection_research_context,
    prepare_selection_research_context,
    quick_judge_selection_event,
)
from backend.app.services.selection_history_proxy import get_selection_multiframe_rows
from backend.app.services.selection_strategy_v2 import (
    evaluate_strategy_range_v2,
    get_candidates_v2_api,
    get_profile_v2_api,
    get_selection_v2_trade_dates,
)
from backend.app.services.selection_stable_callback import (
    STRATEGY_INTERNAL_ID as STABLE_CALLBACK_STRATEGY_ID,
    evaluate_stable_callback_range,
    get_stable_callback_candidates,
    get_stable_callback_profile,
    get_stable_callback_trade_dates,
)
from backend.app.services.selection_trend_continuation import (
    STRATEGY_INTERNAL_ID as TREND_CONTINUATION_STRATEGY_ID,
    evaluate_trend_continuation_range,
    get_trend_continuation_candidates,
    get_trend_continuation_profile,
    get_trend_continuation_trade_dates,
)

router = APIRouter()
ensure_selection_schema()


class SelectionQuickEventJudgeRequest(BaseModel):
    message_text: str
    symbol: Optional[str] = None
    date: Optional[str] = None
    strategy: Optional[str] = None


@router.get("/selection/health", response_model=APIResponse)
def selection_health():
    return APIResponse(code=200, data=get_selection_health())


@router.get("/selection/candidates", response_model=APIResponse)
def selection_candidates(
    date: str = Query(None, description="交易日 YYYY-MM-DD，缺省为最新可用日"),
    strategy: str = Query(STABLE_CALLBACK_STRATEGY_ID, description="stable_capital_callback / trend_continuation_callback / v2 / stealth / breakout / distribution"),
    limit: int = Query(10, ge=1, le=500),
    replay_validation: bool = Query(False, description="仅 v2 实验验证使用：按 Layer3 回放结果排序"),
):
    try:
        normalized_strategy = str(strategy).lower()
        if normalized_strategy == STABLE_CALLBACK_STRATEGY_ID:
            return APIResponse(code=200, data=get_stable_callback_candidates(date, limit=limit))
        if normalized_strategy == TREND_CONTINUATION_STRATEGY_ID:
            return APIResponse(code=200, data=get_trend_continuation_candidates(date, limit=limit))
        if normalized_strategy == "v2":
            return APIResponse(code=200, data=get_candidates_v2_api(date, limit=limit, replay_validation=replay_validation))
        return APIResponse(code=200, data=get_candidates(date, strategy=strategy, limit=limit))
    except Exception as exc:
        return APIResponse(code=500, message=f"选股候选查询失败: {exc}", data=None)


@router.get("/selection/trade-dates", response_model=APIResponse)
def selection_trade_dates(
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    strategy: str = Query(STABLE_CALLBACK_STRATEGY_ID, description="stable_capital_callback / trend_continuation_callback / v2 / stealth / breakout / distribution"),
):
    try:
        normalized_strategy = str(strategy).lower()
        if normalized_strategy == STABLE_CALLBACK_STRATEGY_ID:
            return APIResponse(code=200, data=get_stable_callback_trade_dates(start_date, end_date))
        if normalized_strategy == TREND_CONTINUATION_STRATEGY_ID:
            return APIResponse(code=200, data=get_trend_continuation_trade_dates(start_date, end_date))
        if normalized_strategy == "v2":
            return APIResponse(code=200, data=get_selection_v2_trade_dates(start_date, end_date))
        return APIResponse(code=200, data=get_selection_trade_dates(start_date, end_date, strategy=strategy))
    except Exception as exc:
        return APIResponse(code=500, message=f"选股交易日查询失败: {exc}", data=None)


@router.get("/selection/profile/{symbol}", response_model=APIResponse)
def selection_profile(
    symbol: str,
    date: str = Query(None, description="交易日 YYYY-MM-DD，缺省为最新可用日"),
    strategy: str = Query(STABLE_CALLBACK_STRATEGY_ID, description="stable_capital_callback / trend_continuation_callback / v2 / breakout / stealth / distribution"),
):
    try:
        normalized_strategy = str(strategy).lower()
        if normalized_strategy == STABLE_CALLBACK_STRATEGY_ID:
            return APIResponse(code=200, data=get_stable_callback_profile(symbol, date))
        if normalized_strategy == TREND_CONTINUATION_STRATEGY_ID:
            return APIResponse(code=200, data=get_trend_continuation_profile(symbol, date))
        if normalized_strategy == "v2":
            return APIResponse(code=200, data=get_profile_v2_api(symbol, date))
        return APIResponse(code=200, data=get_profile(symbol, date))
    except Exception as exc:
        return APIResponse(code=500, message=f"选股画像查询失败: {exc}", data=None)


@router.get("/selection/research-context/{symbol}", response_model=APIResponse)
def selection_research_context(
    symbol: str,
    date: str = Query(None, description="交易日 YYYY-MM-DD，缺省为画像可用日"),
    strategy: str = Query(STABLE_CALLBACK_STRATEGY_ID, description="stable_capital_callback / trend_continuation_callback / v2 / breakout / stealth / distribution"),
    event_limit: int = Query(50, ge=1, le=200),
    event_days: int = Query(365, ge=1, le=3650),
    series_days: int = Query(60, ge=1, le=240),
):
    try:
        return APIResponse(
            code=200,
            data=get_selection_research_context(
                symbol,
                trade_date=date,
                strategy=strategy,
                event_limit=event_limit,
                event_days=event_days,
                series_days=series_days,
            ),
        )
    except Exception as exc:
        return APIResponse(code=500, message=f"选股研究上下文查询失败: {exc}", data=None)


@router.post("/selection/research-context/{symbol}/prepare", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def selection_research_context_prepare(
    symbol: str,
    date: str = Query(None, description="交易日 YYYY-MM-DD，事件结果会按该日截断展示"),
    strategy: str = Query(STABLE_CALLBACK_STRATEGY_ID, description="stable_capital_callback / trend_continuation_callback / v2 / breakout / stealth / distribution"),
    use_llm: bool = Query(True, description="是否在事件补拉后尝试生成公司研究卡"),
    announcement_days: int = Query(365, ge=1, le=3650),
    qa_days: int = Query(180, ge=1, le=3650),
    news_days: int = Query(45, ge=1, le=3650),
    event_limit: int = Query(50, ge=1, le=200),
    series_days: int = Query(60, ge=1, le=240),
):
    try:
        return APIResponse(
            code=200,
            message="选股研究上下文准备完成",
            data=prepare_selection_research_context(
                symbol,
                trade_date=date,
                strategy=strategy,
                use_llm=use_llm,
                announcement_days=announcement_days,
                qa_days=qa_days,
                news_days=news_days,
                event_limit=event_limit,
                series_days=series_days,
            ),
        )
    except Exception as exc:
        return APIResponse(code=500, message=f"选股研究上下文准备失败: {exc}", data=None)


@router.post("/selection/quick-event-judge", response_model=APIResponse)
def selection_quick_event_judge(request: SelectionQuickEventJudgeRequest = Body(...)):
    try:
        return APIResponse(
            code=200,
            data=quick_judge_selection_event(
                message_text=request.message_text,
                symbol=request.symbol,
                trade_date=request.date,
                strategy=request.strategy or STABLE_CALLBACK_STRATEGY_ID,
            ),
        )
    except Exception as exc:
        return APIResponse(code=500, message=f"消息快速研判失败: {exc}", data=None)


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


@router.get("/selection/v2/evaluate", response_model=APIResponse)
def selection_v2_evaluate(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    top_n: int = Query(10, ge=1, le=50),
):
    try:
        return APIResponse(code=200, data=evaluate_strategy_range_v2(start_date=start_date, end_date=end_date, top_n=top_n))
    except Exception as exc:
        return APIResponse(code=500, message=f"V2 策略评估失败: {exc}", data=None)


@router.get("/selection/stable-callback/evaluate", response_model=APIResponse)
def selection_stable_callback_evaluate(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    top_n: int = Query(10, ge=1, le=50),
):
    try:
        return APIResponse(code=200, data=evaluate_stable_callback_range(start_date=start_date, end_date=end_date, top_n=top_n))
    except Exception as exc:
        return APIResponse(code=500, message=f"资金流回调稳健策略评估失败: {exc}", data=None)


@router.get("/selection/trend-continuation/evaluate", response_model=APIResponse)
def selection_trend_continuation_evaluate(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    top_n: int = Query(20, ge=1, le=50),
):
    try:
        top_n_value = int(top_n) if isinstance(top_n, (int, str)) else 20
        return APIResponse(code=200, data=evaluate_trend_continuation_range(start_date=start_date, end_date=end_date, top_n=top_n_value))
    except Exception as exc:
        return APIResponse(code=500, message=f"趋势中继高质量回踩策略评估失败: {exc}", data=None)


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
