import sys
import os
import asyncio
from datetime import datetime
import logging

# Ensure backend module is found
sys.path.append(os.getcwd())

from backend.app.services.collector import collector
from backend.app.services.analysis import perform_aggregation
from backend.app.db.crud import get_all_symbols

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def finalize_data():
    logger.info(">>> Starting Market Data Finalization <<<")
    
    symbols = get_all_symbols()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if not symbols:
        logger.warning("No symbols in watchlist.")
        return

    # 1. Force Fetch Ticks (Sync Mode)
    logger.info(f"1. Fetching Full Ticks for {len(symbols)} stocks...")
    # Use collector's internal method directly
    collector._poll_watchlist()
    
    # 2. Aggregate History
    logger.info("2. Aggregating Daily History...")
    for symbol in symbols:
        try:
            res = perform_aggregation(symbol, today_str)
            if res['code'] == 200:
                data = res['data']
                logger.info(f"   [{symbol}] Aggregated: Inflow={data['net_inflow']:.2f}, Activity={data['activity_ratio']:.2f}%")
            else:
                logger.warning(f"   [{symbol}] Aggregation Failed: {res['message']}")
        except Exception as e:
            logger.error(f"   [{symbol}] Error: {e}")

    logger.info(">>> Finalization Complete. Data is safe in SQLite. <<<")

if __name__ == "__main__":
    finalize_data()
