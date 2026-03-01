import sys
import os
import sqlite3
import logging

# Ensure backend module is found
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

from backend.app.services.analysis import aggregate_intraday_1m
from backend.app.core.config import DB_FILE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backfill_1m():
    logger.info(">>> Starting 1-Minute Historical Data Backfill <<<")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Get all symbols
    c.execute("SELECT DISTINCT symbol FROM trade_ticks")
    symbols = [r[0] for r in c.fetchall()]
    
    logger.info(f"Found {len(symbols)} symbols to backfill into history_1m.")
    
    for symbol in symbols:
        # Get dates for this symbol
        c.execute("SELECT DISTINCT date FROM trade_ticks WHERE symbol=? ORDER BY date", (symbol,))
        dates = [r[0] for r in c.fetchall()]
        logger.info(f"Processing {symbol}: {len(dates)} dates found.")
        
        for date_str in dates:
            try:
                res = aggregate_intraday_1m(symbol, date_str)
                if res.get('code') != 200:
                    logger.warning(f"   Failed {symbol} {date_str}: {res}")
            except Exception as e:
                logger.error(f"   Error {symbol} {date_str}: {e}")
                
    conn.close()
    logger.info(">>> 1m Backfill Completed <<<")

if __name__ == "__main__":
    backfill_1m()
