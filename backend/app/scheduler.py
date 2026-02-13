from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.app.services.analysis import perform_aggregation, aggregate_intraday_30m
from backend.app.services.sentiment_crawler import sentiment_crawler
from backend.app.db.crud import get_all_symbols, get_watchlist_items
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def run_daily_sentiment_crawl():
    """
    每天定时抓取自选股的情绪数据 (深度抓取/增量抓取)
    """
    logger.info(">>> STARTING DAILY SENTIMENT CRAWL JOB <<<")
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

def init_scheduler():
    scheduler = BackgroundScheduler()
    
    # 1. 每日盘后聚合 (15:05)
    trigger_finalization = CronTrigger(hour=15, minute=5)
    scheduler.add_job(run_daily_finalization, trigger_finalization)
    
    # 2. 每日情绪抓取 (08:30) - 盘前预热
    trigger_sentiment = CronTrigger(hour=8, minute=30)
    scheduler.add_job(run_daily_sentiment_crawl, trigger_sentiment)
    
    scheduler.start()
    logger.info("Scheduler initialized. Jobs: [Finalization @ 15:05], [Sentiment Crawl @ 08:30]")
    return scheduler
