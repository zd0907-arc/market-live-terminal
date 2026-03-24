from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool
from backend.app.services.sentiment_crawler import sentiment_crawler
from backend.app.services.retail_sentiment import (
    backfill_starred_symbol_history,
    build_feed_v2,
    build_dashboard_payload,
    build_daily_score_series,
    build_heat_trend_v2,
    build_keywords_payload,
    build_overview_v2,
    build_sentiment_trend_payload,
    fetch_representative_comments,
    generate_daily_sentiment_score,
    generate_summary_cache,
    run_starred_daily_scores,
    run_starred_sentiment_crawl,
    sentiment_symbol_candidates,
)
from backend.app.db.database import get_db_connection
from backend.app.models.schemas import APIResponse
from backend.app.core.security import require_write_access
import logging

router = APIRouter(prefix="/sentiment", tags=["Retail Sentiment"])
logger = logging.getLogger(__name__)

@router.post("/crawl/{symbol}", dependencies=[Depends(require_write_access)], response_model=APIResponse)
async def trigger_crawl(symbol: str):
    """
    触发抓取任务 (同步等待模式)
    """
    try:
        # 在线程池中运行以避免阻塞事件循环
        new_count = await run_in_threadpool(sentiment_crawler.run_crawl, symbol, mode="manual")
        return APIResponse(
            code=200,
            message="Crawl completed",
            data={"new_count": new_count}
        )
    except Exception as e:
        logger.error(f"Crawl failed for {symbol}: {e}")
        return APIResponse(code=500, message=str(e), data={"new_count": 0})

@router.get("/dashboard/{symbol}")
def get_dashboard_data(symbol: str):
    """
    获取情绪仪表盘数据
    """
    return build_dashboard_payload(symbol)


@router.get("/overview/{symbol}")
def get_sentiment_overview(symbol: str, window: str = "5d"):
    """
    V2：热度主导总览
    """
    return build_overview_v2(symbol, window=window)


@router.get("/heat_trend/{symbol}")
def get_sentiment_heat_trend(symbol: str, window: str = "5d"):
    """
    V2：热度 + 相对热度 + 价格联动趋势
    """
    return build_heat_trend_v2(symbol, window=window)


@router.get("/feed/{symbol}")
def get_sentiment_feed(symbol: str, window: str = "5d", source: str = "guba", sort: str = "latest", limit: int = 50):
    """
    V2：统一事件原文流
    """
    return build_feed_v2(symbol, window=window, source=source, sort=sort, limit=limit)


@router.get("/daily_scores/{symbol}")
def get_sentiment_daily_scores(symbol: str, window: str = "20d"):
    """
    V3：窗口期 AI 日级评分序列
    """
    return build_daily_score_series(symbol, window=window)


@router.post("/internal/sentiment/backfill_starred/{symbol}", dependencies=[Depends(require_write_access)], response_model=APIResponse)
def trigger_backfill_starred(symbol: str):
    try:
        result = backfill_starred_symbol_history(symbol)
        return APIResponse(code=200, message="Backfill completed", data=result)
    except Exception as e:
        logger.error("Backfill failed for %s: %s", symbol, e)
        return APIResponse(code=500, message=str(e), data={})


@router.post("/internal/sentiment/score_daily/{symbol}", dependencies=[Depends(require_write_access)], response_model=APIResponse)
def trigger_daily_score(symbol: str, trade_date: str):
    try:
        result = generate_daily_sentiment_score(symbol, trade_date, force=True)
        return APIResponse(code=200, message="Daily score completed", data=result)
    except Exception as e:
        logger.error("Daily score failed for %s %s: %s", symbol, trade_date, e)
        return APIResponse(code=500, message=str(e), data={})


@router.post("/internal/sentiment/run_starred_crawl", dependencies=[Depends(require_write_access)], response_model=APIResponse)
def trigger_starred_crawl(mode: str = "nightly"):
    try:
        result = run_starred_sentiment_crawl(mode=mode)
        return APIResponse(code=200, message="Starred crawl completed", data=result)
    except Exception as e:
        logger.error("Starred crawl failed: %s", e)
        return APIResponse(code=500, message=str(e), data={})


@router.post("/internal/sentiment/run_starred_scores", dependencies=[Depends(require_write_access)], response_model=APIResponse)
def trigger_starred_scores(mode: str = "nightly"):
    try:
        result = run_starred_daily_scores(mode=mode)
        return APIResponse(code=200, message="Starred daily scores completed", data=result)
    except Exception as e:
        logger.error("Starred daily scores failed: %s", e)
        return APIResponse(code=500, message=str(e), data={})

@router.post("/summary/{symbol}", dependencies=[Depends(require_write_access)], response_model=APIResponse)
def generate_summary(symbol: str):
    """
    手动触发 AI 摘要生成并保存
    """
    try:
        result = generate_summary_cache(symbol, force=True, min_samples=1, stale_hours=0)
        if result["status"] == "skipped" and result["reason"] == "no_recent_samples":
            return APIResponse(code=200, message="No data for summary", data={"content": "暂无足够数据生成摘要。"})
        if result["status"] != "generated":
            return APIResponse(code=500, message=f"Summary generation failed: {result['reason']}")
        return APIResponse(
            code=200,
            message="Summary generated",
            data={"content": result.get("content"), "created_at": result.get("created_at")},
        )
    except Exception as e:
        logger.error(f"Generate summary error: {e}")
        # Return 200 with error message in body so frontend can display it gracefully
        return APIResponse(code=500, message=str(e))

@router.get("/summary/history/{symbol}", response_model=APIResponse)
def get_summary_history(symbol: str):
    """
    获取历史 AI 摘要
    """
    conn = get_db_connection()
    try:
        candidates = sentiment_symbol_candidates(symbol)
        placeholders = ",".join(["?"] * max(1, len(candidates)))
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, content, created_at, model_used FROM sentiment_summaries WHERE stock_code IN ({placeholders}) ORDER BY created_at DESC LIMIT 10",
            tuple(candidates or [symbol])
        )
        rows = cursor.fetchall()
        result = [
            {"id": r[0], "content": r[1], "created_at": r[2], "model": r[3]} 
            for r in rows
        ]
        if not result:
            return APIResponse(code=200, message="No data found", data=[])
        return APIResponse(code=200, data=result)
    finally:
        conn.close()

@router.get("/trend/{symbol}", response_model=APIResponse)
def get_sentiment_trend(symbol: str, interval: str = "72h"):
    """
    获取情绪趋势数据
    :param interval: '72h' (按小时) or '14d' (按天)
    """
    try:
        payload = build_sentiment_trend_payload(symbol, interval=interval)
        return APIResponse(code=200, message=payload.get("message"), data=payload.get("data", []))
    except Exception as e:
        logger.error(f"Trend query error: {e}")
        return APIResponse(code=500, message=f"Trend query failed: {e}", data=[])

@router.get("/comments/{symbol}", response_model=APIResponse)
def get_recent_comments(symbol: str, limit: int = 12, sort: str = "latest", window: str = "72h"):
    """
    获取最近的评论列表 (原始数据)
    """
    try:
        result = fetch_representative_comments(symbol, limit=limit, sort=sort, window=window)
        return APIResponse(code=200, message=result.get("message"), data=result.get("comments", []))
    except Exception as e:
        logger.error(f"Comments query error: {e}")
        return APIResponse(code=500, message=f"Comments query failed: {e}", data=[])


@router.get("/keywords/{symbol}", response_model=APIResponse)
def get_sentiment_keywords(symbol: str, window: str = "72h"):
    """
    获取关键词/主题词聚合
    """
    try:
        payload = build_keywords_payload(symbol, window=window)
        return APIResponse(code=200, data=payload)
    except Exception as e:
        logger.error(f"Keywords query error: {e}")
        return APIResponse(code=500, message=f"Keywords query failed: {e}", data={})
