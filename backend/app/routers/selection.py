from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query
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
from backend.app.services.selection_daily_workbench import (
    get_daily_selection_candidates,
    get_daily_selection_profile,
    get_daily_selection_trade_dates,
    run_daily_selection_sources,
)
from backend.app.services.intraday_evolution_lab import load_ppo_report_payload
from backend.app.services.selection_research_context import (
    get_selection_research_context,
    prepare_selection_research_context,
    prewarm_selection_research_contexts,
    quick_judge_selection_event,
)
from backend.app.services.selection_history_proxy import (
    get_selection_daily_kline_batch,
    get_selection_multiframe_batch,
    get_selection_multiframe_rows,
)
from backend.app.services.selection_market_environment_gate import (
    get_market_environment,
    get_market_environment_backtest_summary,
    get_market_environment_source_summary,
)
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


class SelectionResearchPrewarmRequest(BaseModel):
    date: Optional[str] = None
    strategy: Optional[str] = None
    limit: Optional[int] = 12
    items: List[Dict[str, Any]] = []


class SelectionPpoReportRequest(BaseModel):
    report_path: Optional[str] = None


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


@router.get("/selection/daily-candidates", response_model=APIResponse)
def selection_daily_candidates(
    date: str = Query(None, description="交易日 YYYY-MM-DD，缺省为最新统一候选日"),
    limit: int = Query(50, ge=1, le=500),
    source_type: str = Query(None, description="可选：model / rule_strategy"),
    include_exit_watchlist: bool = Query(False, description="是否同步计算星火退出观察池"),
):
    try:
        normalized_source_type = source_type if isinstance(source_type, str) and source_type else None
        normalized_include_exit_watchlist = include_exit_watchlist is True
        return APIResponse(
            code=200,
            data=get_daily_selection_candidates(
                date,
                limit=limit,
                source_type=normalized_source_type,
                include_exit_watchlist=normalized_include_exit_watchlist,
            ),
        )
    except Exception as exc:
        return APIResponse(code=500, message=f"每日选股候选查询失败: {exc}", data=None)


@router.get("/selection/market-environment", response_model=APIResponse)
def selection_market_environment(
    date: str = Query(None, description="交易日 YYYY-MM-DD，缺省为最新市场环境日"),
):
    try:
        return APIResponse(code=200, data=get_market_environment(date))
    except Exception as exc:
        return APIResponse(code=500, message=f"市场环境水位查询失败: {exc}", data=None)


@router.get("/selection/market-environment/backtest-summary", response_model=APIResponse)
def selection_market_environment_backtest_summary():
    try:
        return APIResponse(code=200, data=get_market_environment_backtest_summary())
    except Exception as exc:
        return APIResponse(code=500, message=f"市场环境门控回测摘要查询失败: {exc}", data=None)


@router.get("/selection/market-environment/source-regime-summary", response_model=APIResponse)
def selection_market_environment_source_regime_summary():
    try:
        return APIResponse(code=200, data=get_market_environment_source_summary())
    except Exception as exc:
        return APIResponse(code=500, message=f"市场环境来源矩阵查询失败: {exc}", data=None)


@router.get("/selection/daily-trade-dates", response_model=APIResponse)
def selection_daily_trade_dates(
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
):
    try:
        return APIResponse(code=200, data=get_daily_selection_trade_dates(start_date, end_date))
    except Exception as exc:
        return APIResponse(code=500, message=f"每日选股交易日查询失败: {exc}", data=None)


@router.get("/selection/daily-profile/{symbol}", response_model=APIResponse)
def selection_daily_profile(
    symbol: str,
    date: str = Query(..., description="交易日 YYYY-MM-DD"),
):
    try:
        return APIResponse(code=200, data=get_daily_selection_profile(symbol, date))
    except Exception as exc:
        return APIResponse(code=500, message=f"每日选股画像查询失败: {exc}", data=None)


@router.post("/selection/daily-refresh", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def selection_daily_refresh(
    date: str = Query(..., description="交易日 YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=500),
    sources: str = Query(None, description="逗号分隔 source_id；缺省运行全部 active P1 来源"),
):
    try:
        source_ids = [item.strip() for item in str(sources or "").split(",") if item.strip()] or None
        return APIResponse(code=200, data=run_daily_selection_sources(date, limit=limit, source_ids=source_ids))
    except Exception as exc:
        return APIResponse(code=500, message=f"每日选股候选刷新失败: {exc}", data=None)


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


@router.post("/selection/research-context/prewarm", response_model=APIResponse, dependencies=[Depends(require_write_access)])
def selection_research_context_prewarm(
    background_tasks: BackgroundTasks,
    request: SelectionResearchPrewarmRequest = Body(...),
):
    try:
        items = request.items or []
        limit = max(1, min(int(request.limit or 12), 30))
        background_tasks.add_task(
            prewarm_selection_research_contexts,
            items,
            trade_date=request.date,
            default_strategy=request.strategy or STABLE_CALLBACK_STRATEGY_ID,
            limit=limit,
        )
        return APIResponse(
            code=200,
            message="研究摘要预热已触发",
            data={"scheduled_count": min(len(items), limit)},
        )
    except Exception as exc:
        return APIResponse(code=500, message=f"研究摘要预热触发失败: {exc}", data=None)


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


@router.get("/selection/history/multiframe/batch", response_model=APIResponse)
def selection_history_multiframe_batch(
    symbols: str = Query(..., description="逗号分隔股票代码，如 sh600000,sz000001"),
    granularity: str = Query("1d"),
    days: int = Query(20, ge=1, le=400),
    start_date: str = Query(None),
    end_date: str = Query(None),
    include_today_preview: bool = Query(True),
    allow_cloud_fallback: bool = Query(False),
):
    try:
        symbol_list = [item.strip() for item in str(symbols or "").split(",") if item.strip()]
        if not symbol_list:
            return APIResponse(code=400, message="symbols 不能为空", data=None)
        normalized_granularity = str(granularity or "").strip().lower()
        if (
            normalized_granularity in {"1d", "day", "daily", "d"}
            and include_today_preview is False
            and allow_cloud_fallback is False
        ):
            return APIResponse(
                code=200,
                data=get_selection_daily_kline_batch(
                    symbols=symbol_list,
                    days=days,
                    start_date=start_date,
                    end_date=end_date,
                ),
            )
        return APIResponse(
            code=200,
            data=get_selection_multiframe_batch(
                symbols=symbol_list,
                granularity=granularity,
                days=days,
                start_date=start_date,
                end_date=end_date,
                include_today_preview=include_today_preview,
                allow_cloud_fallback=allow_cloud_fallback,
            ),
        )
    except Exception as exc:
        return APIResponse(code=500, message=f"选股历史多维批量查询失败: {exc}", data=None)


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


@router.get("/selection/ppo-backtest-report", response_model=APIResponse)
def selection_ppo_backtest_report(report_path: str = Query(None, description="PPO 回测结果 JSON 路径")):
    try:
        payload = load_ppo_report_payload(report_path or None)
        return APIResponse(code=200, data=payload)
    except Exception as exc:
        return APIResponse(code=500, message=f"PPO 回测报告读取失败: {exc}", data=None)


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
