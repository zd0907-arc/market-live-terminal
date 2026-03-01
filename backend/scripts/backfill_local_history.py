import sys
import os
import sqlite3
import logging

# Ensure backend module is found
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

from backend.app.services.analysis import perform_aggregation
from backend.app.core.config import DB_FILE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backfill_local_history():
    logger.info(">>> Starting Local History Data Backfill (Daily & 30m) <<<")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Get all symbols that have ticks
    c.execute("SELECT DISTINCT symbol FROM trade_ticks")
    symbols = [r[0] for r in c.fetchall()]
    
    logger.info(f"Found {len(symbols)} symbols to aggregate into local_history.")
    
    for symbol in symbols:
        # Get distinct dates for this symbol
        c.execute("SELECT DISTINCT date FROM trade_ticks WHERE symbol=? ORDER BY date", (symbol,))
        dates = [r[0] for r in c.fetchall()]
        logger.info(f"Processing {symbol}: {len(dates)} dates found.")
        
        for date_str in dates:
            try:
                logger.info(f"  Aggregating {symbol} for {date_str}...")
                res = perform_aggregation(symbol, date_str)
                if res.get('code') != 200:
                    logger.warning(f"   Failed {symbol} {date_str}: {res}")
                else:
                    logger.info(f"   Success {symbol} {date_str}")
            except Exception as e:
                logger.error(f"   Error {symbol} {date_str}: {e}")
                
    conn.close()
    logger.info(">>> Local History Backfill Completed <<<")

if __name__ == "__main__":
    backfill_local_history()
