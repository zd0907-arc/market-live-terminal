from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.app.services.analysis import perform_aggregation, aggregate_intraday_30m
from backend.app.db.crud import get_all_symbols
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

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
    # Run at 15:05 every day
    trigger = CronTrigger(hour=15, minute=5)
    scheduler.add_job(run_daily_finalization, trigger)
    scheduler.start()
    logger.info("Scheduler initialized (Job: Daily Finalization at 15:05)")
    return scheduler
