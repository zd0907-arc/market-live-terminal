from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.app.services.analysis import perform_aggregation, aggregate_intraday_30m
from backend.app.services.sentiment_crawler import sentiment_crawler
from backend.app.db.crud import (
    get_all_symbols,
    get_watchlist_items,
    get_latest_tick_time,
    save_ticks_daily_overwrite,
)
from backend.app.services.analysis import aggregate_intraday_1m, refresh_realtime_preview
from backend.app.services.market import fetch_live_ticks
from backend.app.core.http_client import MarketClock
import logging
from datetime import datetime
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)
_POSTCLOSE_STALE_FLOOR = "14:55:00"


def _is_postclose_tick_payload_stale(latest_time: Optional[str]) -> bool:
    if not latest_time:
        return True
    return str(latest_time) < _POSTCLOSE_STALE_FLOOR


async def _rehydrate_symbol_postclose_if_stale(symbol: str, trade_date: str) -> bool:
    latest_before = await asyncio.to_thread(get_latest_tick_time, symbol, trade_date)
    if not _is_postclose_tick_payload_stale(latest_before):
        return False

    logger.info(
        "[PostCloseSweep] stale symbol detected: %s %s latest_before=%s",
        symbol,
        trade_date,
        latest_before,
    )

    records = await fetch_live_ticks(symbol)
    if not records:
        logger.warning(
            "[PostCloseSweep] live fetch returned empty: %s %s latest_before=%s",
            symbol,
            trade_date,
            latest_before,
        )
        return False

    data_to_insert = [
        (
            symbol,
            item["time"],
            float(item["price"]),
            int(item["volume"]),
            float(item["amount"]),
            str(item["type"]),
            trade_date,
        )
        for item in records
    ]

    await asyncio.to_thread(save_ticks_daily_overwrite, symbol, trade_date, data_to_insert)
    await asyncio.to_thread(aggregate_intraday_1m, symbol, trade_date)
    await asyncio.to_thread(refresh_realtime_preview, symbol, trade_date)

    latest_after = await asyncio.to_thread(get_latest_tick_time, symbol, trade_date)
    healed = not _is_postclose_tick_payload_stale(latest_after)
    logger.info(
        "[PostCloseSweep] symbol=%s trade_date=%s latest_before=%s latest_after=%s healed=%s",
        symbol,
        trade_date,
        latest_before,
        latest_after,
        healed,
    )
    return healed

def run_sentiment_crawl(mode="scheduler"):
    """
    定时抓取自选股的情绪数据 (深度抓取/增量抓取)
    """
    from backend.app.core.http_client import MarketClock
    
    # 如果是盘中轮询模式，但在非交易时间，则直接跳过
    if mode == "intraday" and not MarketClock.is_trading_time():
        return

    logger.info(f">>> STARTING SENTIMENT CRAWL JOB (Mode: {mode}) <<<")
    watchlist = get_watchlist_items()
    
    if not watchlist:
        logger.info("Watchlist is empty. Skipping sentiment crawl.")
        return

    for item in watchlist:
        symbol = item['symbol']
        name = item.get('name', '')
        logger.info(f"Auto-crawling sentiment for {symbol} ({name})...")
        try:
            # 同步调用，但在后台任务中无所谓阻塞
            new_count = sentiment_crawler.run_crawl(symbol, mode="scheduler")
            logger.info(f"[{symbol}] Crawl finished. New comments: {new_count}")
        except Exception as e:
            logger.error(f"[{symbol}] Crawl failed: {e}")
            
    logger.info(">>> DAILY SENTIMENT CRAWL COMPLETED <<<")

def run_daily_finalization():
    logger.info(">>> STARTING DAILY FINALIZATION JOB <<<")
    
    symbols = get_all_symbols()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for symbol in symbols:
        logger.info(f"Finalizing {symbol}...")
        try:
            # 1. Standard Aggregation (Daily)
            perform_aggregation(symbol, today_str)
            # 2. Intraday Aggregation (30m)
            aggregate_intraday_30m(symbol, today_str)
        except Exception as e:
            logger.error(f"Finalization failed for {symbol}: {e}")
            
    logger.info(">>> DAILY FINALIZATION COMPLETED <<<")

def run_daily_calendar_sync():
    """
    每天凌晨更新一次交易日历缓存
    """
    logger.info(">>> STARTING DAILY CALENDAR SYNC JOB <<<")
    try:
        from backend.app.core.calendar import TradeCalendar
        TradeCalendar.init(force=True)
    except Exception as e:
        logger.error(f"Daily calendar sync failed: {e}")
    logger.info(">>> DAILY CALENDAR SYNC COMPLETED <<<")


def run_postclose_tick_self_heal():
    """
    盘后短时间内主动扫描自选股，修复盘中个别股票停在 14:45/14:50 的情况，
    避免必须等用户打开页面时才触发 request-time stale rehydrate。
    """
    market_context = MarketClock.get_market_context()
    if str(market_context.get("market_status") or "") != "post_close":
        logger.info("[PostCloseSweep] skip: market_status=%s", market_context.get("market_status"))
        return

    symbols = get_all_symbols()
    if not symbols:
        logger.info("[PostCloseSweep] skip: watchlist empty")
        return

    trade_date = str(market_context.get("natural_today") or datetime.now().strftime("%Y-%m-%d"))
    logger.info("[PostCloseSweep] start: trade_date=%s symbols=%s", trade_date, len(symbols))

    healed_count = 0
    stale_count = 0
    for symbol in symbols:
        try:
            latest_before = get_latest_tick_time(symbol, trade_date)
            if not _is_postclose_tick_payload_stale(latest_before):
                continue
            stale_count += 1
            if asyncio.run(_rehydrate_symbol_postclose_if_stale(symbol, trade_date)):
                healed_count += 1
        except Exception as e:
            logger.error("[PostCloseSweep] failed for %s: %s", symbol, e)

    logger.info(
        "[PostCloseSweep] completed: trade_date=%s stale=%s healed=%s",
        trade_date,
        stale_count,
        healed_count,
    )

def init_scheduler():
    scheduler = BackgroundScheduler()
    
    # 1. 每日盘后聚合 (15:20) - 预留10-15分钟给 Windows 爬虫做 FINAL SWEEP
    trigger_finalization = CronTrigger(hour=15, minute=20)
    scheduler.add_job(run_daily_finalization, trigger_finalization)

    # 1.1 盘后自愈扫描（15:02/15:07/15:12/15:17）：
    # 主动修补个别股票停在 14:45/14:50 的分时，避免等页面访问才触发按需补数。
    trigger_postclose_self_heal = CronTrigger(day_of_week='mon-fri', hour=15, minute='2,7,12,17')
    scheduler.add_job(run_postclose_tick_self_heal, trigger_postclose_self_heal)
    
    # 2. 每日情绪抓取 (08:30) - 盘前预热全量
    trigger_sentiment = CronTrigger(hour=8, minute=30)
    scheduler.add_job(run_sentiment_crawl, trigger_sentiment, kwargs={"mode": "scheduler"})
    
    # 2.1 盘中情绪轮询 (每半小时) - 增量
    trigger_sentiment_intraday = CronTrigger(day_of_week='mon-fri', hour='9-14', minute='0,30')
    scheduler.add_job(run_sentiment_crawl, trigger_sentiment_intraday, kwargs={"mode": "intraday"})
    
    # 3. 每日交易日历自我刷新 (00:05) - 云端长效挂机维稳
    trigger_calendar = CronTrigger(hour=0, minute=5)
    scheduler.add_job(run_daily_calendar_sync, trigger_calendar)
    
    scheduler.start()
    logger.info(
        "Scheduler initialized. Jobs: [Calendar Sync @ 00:05], "
        "[Sentiment Crawl @ 08:30 & Intraday 30m], "
        "[PostClose SelfHeal @ 15:02/07/12/17], "
        "[Finalization @ 15:20]"
    )
    return scheduler
