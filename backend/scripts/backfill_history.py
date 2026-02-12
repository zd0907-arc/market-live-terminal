import sys
import os
import sqlite3
import logging

# Ensure backend module is found
sys.path.append(os.getcwd())

from backend.app.services.analysis import aggregate_intraday_30m
from backend.app.core.config import DB_FILE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backfill():
    logger.info(">>> Starting Historical Data Backfill <<<")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Get all symbols
    c.execute("SELECT DISTINCT symbol FROM trade_ticks")
    symbols = [r[0] for r in c.fetchall()]
    
    logger.info(f"Found {len(symbols)} symbols to backfill.")
    
    for symbol in symbols:
        # Get dates for this symbol
        c.execute("SELECT DISTINCT date FROM trade_ticks WHERE symbol=? ORDER BY date", (symbol,))
        dates = [r[0] for r in c.fetchall()]
        logger.info(f"Processing {symbol}: {len(dates)} dates found.")
        
        for date_str in dates:
            try:
                res = aggregate_intraday_30m(symbol, date_str)
                if res.get('code') != 200:
                    logger.warning(f"   Failed {symbol} {date_str}: {res}")
            except Exception as e:
                logger.error(f"   Error {symbol} {date_str}: {e}")
                
    conn.close()
    logger.info(">>> Backfill Completed <<<")

if __name__ == "__main__":
    backfill()
